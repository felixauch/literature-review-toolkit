"""Evidence-led reclassification UI. Standard library only; never writes legacy CSVs.

python reclassification.py --root ".." --port 8789
prepare_reclassification.py creates the input catalog. Drafts, confirmations and
history live in reclassification_review/classification.csv, separate from screening.
"""
from __future__ import annotations
from csv_storage import read_object, write_object
import argparse
import csv
import hashlib
import io
import json
import re
import secrets
import os
import subprocess
import threading
import time
from csv_storage import CsvJournal, StorageError
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

UI = Path(__file__).resolve().parent
VALUES = ['yes', 'no', 'uncertain']
TOKEN = secrets.token_urlsafe(32)
STORES = {}
APP_VERSION = 'configurable-domains-20260922'
DESKTOP_LAUNCHER = False

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def fingerprint(value): return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')

class ReviewError(Exception):
    def __init__(self, message, status=400): super().__init__(message); self.status=status

def blank_decision(categories=()):
    return {'labels':{k:'uncertain' for k in categories}, 'eligibility':'uncertain', 'components':[], 'reason':'', 'question':'', 'reviewer':'', 'evidence_checked':False}

def clean_text(value, name, limit=12000):
    if not isinstance(value, str) or len(value)>limit: raise ReviewError(f'Invalid {name}.')
    return value.strip()

PRESERVED_FIELDS = ['report_domains','report_primary_domain','report_core_domains','report_secondary_domains','decision_link','output_label']

def domains_from_source(source):
    def split(k):return list(dict.fromkeys(x.strip() for x in source.get(k,'').split(';') if x.strip()))
    primary=source.get('report_primary_domain','').strip()
    core=split('report_core_domains')
    if primary and primary not in core:core.insert(0,primary)
    if not primary and core:primary=core[0]
    return {'primary':primary,'core':core,'secondary':[d for d in split('report_secondary_domains') if d not in core],'reviewed':False,'note':''}

def validate_categories(raw,action,categories,domain_names):
    labels=raw.get('labels')
    if not isinstance(labels,dict) or set(labels)!=set(categories) or any(v not in VALUES for v in labels.values()):raise ReviewError('Record a valid judgement for each configured category.')
    out=blank_decision(categories);out.update(review_scope='categories_domains',labels=labels.copy())
    out['eligibility']='include' if 'yes' in labels.values() else 'exclude' if all(v=='no' for v in labels.values()) else 'uncertain'
    for k in ('reason','question','reviewer'):out[k]=clean_text(raw.get(k,''),k)
    out['evidence_checked']=raw.get('evidence_checked') is True
    out['components']=raw.get('components',[]);out['preserved_assessment']=raw.get('preserved_assessment',{})
    d=raw.get('domains')
    if not isinstance(d,dict):raise ReviewError('Reload the page to review domains.')
    domain={'primary':clean_text(d.get('primary',''),'primary domain',80),'reviewed':d.get('reviewed') is True,'note':clean_text(d.get('note',''),'domain note')}
    for k in ('core','secondary'):
        value=d.get(k,[])
        if not isinstance(value,list) or any(not isinstance(v,str) or v not in domain_names for v in value) or len(set(value))!=len(value):raise ReviewError('Choose only configured domains.')
        domain[k]=value.copy()
    if set(domain['core']) & set(domain['secondary']):raise ReviewError('A domain cannot be both core and secondary.')
    if domain['primary'] and domain['primary'] not in domain['core']:raise ReviewError('The primary domain must be a core domain.')
    out['domains']=domain
    if action=='flag' and not out['question']:out['question']='Set aside for later review.'
    if action=='confirm':
        if not out['reviewer'] or not out['evidence_checked']:raise ReviewError('Enter your name and check the source before confirming.')
        if 'uncertain' in labels.values():raise ReviewError('Resolve the category questions, or save for later.')
        if domain_names and not domain['reviewed']:raise ReviewError('Check the domain assignments before confirming.')
        if domain_names and out['eligibility']=='include' and not domain['core'] and not domain['note']:raise ReviewError('Choose a core domain or explain why none applies.')
        if domain['core'] and not domain['primary']:raise ReviewError('Choose the primary domain.')
        if out['eligibility']=='exclude' and not out['reason']:out['reason']='No qualifying category.'
    return out

def domain_columns(d):
    return {'report_primary_domain':d['primary'],'report_core_domains':'; '.join(d['core']),
       'report_secondary_domains':'; '.join(x for x in d['core']+d['secondary'] if x!=d['primary']),
       'report_domains':'; '.join(d['core']+d['secondary'])}

class ReviewStore:
    def __init__(self, root, storage):
        self.root=Path(root).resolve(); self.storage=Path(storage).resolve()
        self.catalog_path=self.storage/'catalog.csv'
        if not self.catalog_path.exists(): raise ReviewError('Review catalog missing. Create a configured classification run first.',503)
        self.storage.mkdir(parents=True,exist_ok=True)
        self.journal=CsvJournal(self.storage,'classification','record_id','event_id')
        self.csv_path=self.journal.path

    def catalog(self):
        obj=read_object(self.catalog_path)
        if obj.get('schema_version')!=1: raise ReviewError('Unsupported review catalog version.',503)
        obj['categories']=obj.get('categories') or list(obj['records'][0]['proposal']['decision']['labels'])
        obj['domains']=obj.get('domains') or []
        return obj
    def source_current(self, catalog):
        file=Path(catalog['source_csv'])
        return file.exists() and sha(file)==catalog['source_csv_sha256']
    def records(self,catalog): return {r['record_id']:r for r in catalog['records']}
    def preserved_assessments(self):
        with Path(self.catalog()['source_csv']).open(encoding='utf-8-sig',newline='') as handle:
            return {row['record_id']:{key:row[key] for key in PRESERVED_FIELDS if key in row} for row in csv.DictReader(handle)}
    def states(self):
        return self.journal.states()

    def effective(self, state, record, source_current):
        if not state: return 'unreviewed'
        if not source_current or state['proposal_hash']!=record['proposal_hash']: return 'stale'
        return state['status']
    def load(self):
        cat=self.catalog(); states=self.states(); current=self.source_current(cat); preserved=self.preserved_assessments()
        for r in cat['records']:
            r['review']=states.get(r['record_id']); r['review_status']=self.effective(r['review'],r,current)
            r['preserved_assessment']=preserved.get(r['record_id'],{})
            r['domain_assignment']=(r['review'] or {}).get('payload',{}).get('domains') or domains_from_source(r['preserved_assessment'])
        extra=self.storage/'domain-suggestions.csv'
        if extra.exists():
            suggestions=read_object(extra)
            for r in cat['records']:
                entry=suggestions.get('records',{}).get(r['record_id'],{})
                if entry.get('pdf_sha256')==r.get('pdf_sha256'):
                    r['domain_proposals']=entry.get('proposals',{})
            cat['domains']=suggestions.get('domains',cat['domains'])
            cat['project']=suggestions.get('project',cat.get('project',{}))
        return {**cat, 'review_scope':'categories_domains','source_current':current, 'csrf_token':TOKEN,'saved_at':now()}
    def save(self, payload):
        if not isinstance(payload,dict): raise ReviewError('Invalid request.')
        cat=self.catalog(); records=self.records(cat); rid=payload.get('record_id')
        if rid not in records: raise ReviewError('This record is not in the current review catalog.',404)
        record=records[rid]; action=payload.get('action')
        if action not in ['draft','confirm','flag']: raise ReviewError('Unknown review action.')
        if payload.get('proposal_hash')!=record['proposal_hash']: raise ReviewError('The proposal has changed. Reload and review the latest evidence.',409)
        if action=='confirm' and not self.source_current(cat): raise ReviewError('The source corpus changed. Refresh the review catalog before confirming.',409)
        if action=='confirm' and record.get('pdf_path'):
            pdf=Path(record['pdf_path'])
            if not pdf.is_file() or sha(pdf)!=record.get('pdf_sha256'): raise ReviewError('The source PDF changed or moved. Refresh its evidence before confirming.',409)
        raw=payload.get('decision')
        if not isinstance(raw,dict) or raw.get('review_scope')!='categories_domains': raise ReviewError('Reload the page to use the category and domain review.',409)
        prior=self.states().get(rid,{}).get('payload',{})
        raw={**raw,'components':prior.get('components',[]),'preserved_assessment':self.preserved_assessments().get(rid,{})}
        decision=validate_categories(raw,action,cat['categories'],self.load()['domains'])
        proposed=record.get('proposal',{}).get('decision') if record.get('proposal') else None
        compared=['labels','eligibility']
        changes=[key for key in compared if proposed is not None and decision.get(key)!=proposed.get(key)]
        decision['domain_proposal_comparison']={'selected_core':decision['domains']['core'],'reviewed':decision['domains']['reviewed']}
        decision['proposal_comparison']={'kind':'own_classification' if proposed is None else 'amended' if changes else 'accepted','changed_fields':changes,'confirmed':action=='confirm'}
        revision=payload.get('revision')
        if type(revision) is not int or revision<0: raise ReviewError('Invalid review revision.')
        status={'draft':'draft','flag':'needs_clarification','confirm':'confirmed'}[action]
        stamp=now(); encoded=json.dumps(decision,ensure_ascii=False)
        try:
            return self.journal.save({'record_id':rid,'status':status,'payload':decision,'proposal_hash':record['proposal_hash'],'updated_at':stamp,'action':action},revision)
        except StorageError as e:raise ReviewError(str(e),e.status)

    def history(self,rid):
        if rid not in self.records(self.catalog()):raise ReviewError('Record not found.',404)
        return list(reversed(self.journal.history(rid)))

    def export_issues(self, data):
        """List records that cannot yet enter a confirmed classification export."""
        issues=[]
        for r in data['records']:
            reasons=[]
            if not data['source_current']:
                reasons.append('Source CSV changed; refresh and check the source version.')
            if r['review_status']!='confirmed':
                reasons.append('Classification is '+r['review_status']+'.')
            else:
                try:
                    d=validate_categories({**r['review']['payload'],'domains':r['domain_assignment']},'confirm',data['categories'],data['domains'])
                    if d['eligibility']=='include' and not r.get('pdf_path'):
                        reasons.append('Included paper has no linked PDF.')
                except ReviewError as exc:
                    reasons.append(str(exc))
                if r.get('pdf_path'):
                    pdf=Path(r['pdf_path'])
                    if not pdf.is_file() or sha(pdf)!=r.get('pdf_sha256'):
                        reasons.append('PDF changed or is unavailable; refresh and verify it.')
            if reasons:
                issues.append({'record_id':r['record_id'],'title':r.get('title',''),'review_status':r['review_status'],
                               'reason':' '.join(reasons)})
        return issues
    def export(self,kind):
        data=self.load(); data.pop('csrf_token',None)
        if kind=='json':
            history=self.journal.history()
            return json.dumps({**data,'history':history,'export_kind':'review progress; not final corpus'},ensure_ascii=False,indent=2).encode(),'application/json','reclassification-progress.json'
        if kind in ('pending','final','corpus'):
            issues=self.export_issues(data)
            if kind=='pending':
                out=io.StringIO(newline='')
                writer=csv.DictWriter(out,fieldnames=['record_id','title','review_status','reason'])
                writer.writeheader()
                for issue in issues:
                    writer.writerow({k:("'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v) for k,v in issue.items()})
                return ('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8','unfinished-classifications.csv'
            if issues:
                sample=', '.join(r['record_id'] for r in issues[:8])+(' ...' if len(issues)>8 else '')
                raise ReviewError(f'Final export blocked: {len(issues)} paper(s) need attention ({sample}). Use Export unfinished classifications for their status and next steps.',409)
        if kind=='final':
            if not data['source_current'] or any(r['review_status']!='confirmed' for r in data['records']): raise ReviewError('Final export is available after every active record is confirmed and the source version is current.',409)
            included=[]; excluded=[]
            for r in data['records']:
                if r.get('pdf_path') and (not Path(r['pdf_path']).is_file() or sha(r['pdf_path'])!=r.get('pdf_sha256')):
                    raise ReviewError('A source PDF changed after review. Refresh and verify it before final export.',409)
                raw={**r['review']['payload'],'domains':r['domain_assignment']}
                d=validate_categories(raw,'confirm',data['categories'],data['domains'])
                entry={'record_id':r['record_id'],'title':r['title'],'doi':r['doi'],**d}
                (included if d['eligibility']=='include' else excluded).append(entry)
            return json.dumps({'schema_version':1,'export_kind':'reviewer-confirmed classification snapshot; not applied to input corpus','source_csv_sha256':data['source_csv_sha256'],'rules':data['rules'],'included':included,'excluded':excluded},ensure_ascii=False,indent=2).encode(),'application/json','reclassification-confirmed.json'
        if kind=='corpus':
            if not data['source_current'] or any(r['review_status']!='confirmed' or (data['domains'] and not r['domain_assignment']['reviewed']) for r in data['records']):raise ReviewError('Confirm every category and domain review before exporting the final corpus.',409)
            rows=[]
            for r in data['records']:
                d=validate_categories({**r['review']['payload'],'domains':r['domain_assignment']},'confirm',data['categories'],data['domains'])
                if d['eligibility']!='include':continue
                if not r['pdf_path'] or not Path(r['pdf_path']).is_file() or sha(r['pdf_path'])!=r['pdf_sha256']:raise ReviewError('A source PDF changed or is unavailable.',409)
                rows.append({**{k:r.get(k,'') for k in ('record_id','title','authors','year','doi')},'fulltext_local_pdf':r['pdf_path'],
                    'report_categories':'; '.join(k for k,v in d['labels'].items() if v=='yes'),**domain_columns(d['domains']),
                    'decision_link':r['preserved_assessment'].get('decision_link',''),
                    'output_label':r['preserved_assessment'].get('output_label',''),
                    'classification_status':'confirmed','classification_reviewer':d['reviewer'],'classification_reviewed_at':r['review']['updated_at']})
            out=io.StringIO(newline='');names=['record_id','title','authors','year','doi','fulltext_local_pdf','report_categories','report_primary_domain','report_core_domains','report_secondary_domains','report_domains','decision_link','output_label','classification_status','classification_reviewer','classification_reviewed_at']
            writer=csv.DictWriter(out,fieldnames=names);writer.writeheader();writer.writerows(rows)
            return ('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8','confirmed-corpus.csv'
        if kind!='csv': raise ReviewError('Unknown export format.')
        out=io.StringIO(newline=''); fields=['record_id','title','doi','review_status','reviewer','reviewed_at','proposal_handling','changed_fields','eligibility',*data['categories'],'report_primary_domain','report_core_domains','report_secondary_domains','domains_reviewed','domain_note','review_scope','preserved_assessment_json','components_json','reason','question','proposal_hash']
        writer=csv.DictWriter(out,fieldnames=fields); writer.writeheader()
        def cell(s):
            s=str(s or ''); return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
        for r in data['records']:
            rev=r['review']; d=rev['payload'] if rev else blank_decision(data['categories'])
            row={'record_id':r['record_id'],'title':r['title'],'doi':r['doi'],'review_status':r['review_status'],'reviewer':d['reviewer'],'reviewed_at':rev['updated_at'] if rev else '', 'proposal_handling':d.get('proposal_comparison',{}).get('kind',''),'changed_fields':'; '.join(d.get('proposal_comparison',{}).get('changed_fields',[])), 'eligibility':d['eligibility'],**d['labels'],'components_json':json.dumps(d['components'],ensure_ascii=False),'reason':d['reason'],'question':d['question'],'proposal_hash':r['proposal_hash']}
            row.update({k:v for k,v in domain_columns(r['domain_assignment']).items() if k!='report_domains'},domains_reviewed=r['domain_assignment']['reviewed'],domain_note=r['domain_assignment']['note'])
            row.update(review_scope=d.get('review_scope','full_assessment' if rev else ''),preserved_assessment_json=json.dumps(d.get('preserved_assessment',r['preserved_assessment']),ensure_ascii=False))
            writer.writerow({k:cell(v) for k,v in row.items()})
        return ('\ufeff'+out.getvalue()).encode(),'text/csv; charset=utf-8','reclassification-progress.csv'

def send(handler,status,body,content_type='application/json; charset=utf-8',filename=None):
    if not isinstance(body,bytes): body=json.dumps(body,ensure_ascii=False).encode()
    handler.send_response(status); handler.send_header('Content-Type',content_type); handler.send_header('Content-Length',str(len(body)))
    handler.send_header('Cache-Control','no-store'); handler.send_header('X-Content-Type-Options','nosniff')
    handler.send_header('Referrer-Policy','no-referrer')
    handler.send_header('Content-Security-Policy',"default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-src 'self'; object-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'")
    if filename: handler.send_header('Content-Disposition',f'attachment; filename="{filename}"')
    handler.end_headers(); handler.wfile.write(body)

def send_pdf(handler,path,rid):
    size=path.stat().st_size; start=0; end=size-1; status=200
    range_header=handler.headers.get('Range')
    if range_header:
        m=re.fullmatch(r'bytes=(\d*)-(\d*)',range_header.strip())
        if not m or not any(m.groups()): raise ReviewError('Invalid PDF byte range.',416)
        if m[1]: start=int(m[1]); end=min(int(m[2]) if m[2] else end,end)
        else: start=max(0,size-int(m[2]))
        if start>end or start>=size: raise ReviewError('PDF byte range is outside the file.',416)
        status=206
    handler.send_response(status); handler.send_header('Content-Type','application/pdf'); handler.send_header('Accept-Ranges','bytes'); handler.send_header('Content-Length',str(end-start+1)); handler.send_header('Content-Disposition',f'inline; filename="{rid}.pdf"')
    if status==206: handler.send_header('Content-Range',f'bytes {start}-{end}/{size}')
    handler.end_headers()
    with path.open('rb') as source:
        source.seek(start); remaining=end-start+1
        while remaining:
            data=source.read(min(65536,remaining))
            if not data: break
            handler.wfile.write(data); remaining-=len(data)

_EDGE_OPEN_LOCK = threading.Lock()
_EDGE_OPEN_RECEIPTS = {}

def edge_executable():
    candidates = [Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft/Edge/Application/msedge.exe',
                  Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Microsoft/Edge/Application/msedge.exe']
    if os.environ.get('LOCALAPPDATA'):
        candidates.append(Path(os.environ['LOCALAPPDATA']) / 'Microsoft/Edge/Application/msedge.exe')
    for candidate in candidates:
        if candidate.is_file(): return candidate
    raise ReviewError('Microsoft Edge was not found. Use the PDF page link to open the source manually.', 503)

def open_pdf_in_edge(store, payload):
    if not DESKTOP_LAUNCHER:
        raise ReviewError('To enable Edge, start the review with --desktop from a terminal on your Windows desktop, then refresh this page.',503)
    if not isinstance(payload, dict): raise ReviewError('Invalid PDF-open request.')
    rid=payload.get('record_id'); request_id=payload.get('request_id')
    if not isinstance(rid,str) or not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}', request_id):
        raise ReviewError('A record ID and unique request ID are required.')
    record=store.records(store.catalog()).get(rid)
    if not record or not record.get('pdf_path'): raise ReviewError('No local corpus PDF is linked to this paper.',404)
    if payload.get('proposal_hash')!=record['proposal_hash']: raise ReviewError('The paper changed. Refresh before opening its PDF.',409)
    pdf=Path(record['pdf_path']).resolve(); corpus=Path(store.catalog()['pdf_root']).resolve()
    if not pdf.is_relative_to(corpus) or pdf.suffix.lower()!='.pdf' or not pdf.is_file():
        raise ReviewError('The linked PDF is unavailable in this corpus.',404)
    if sha(pdf)!=record.get('pdf_sha256'): raise ReviewError('The PDF changed since this assessment. Refresh its evidence before reviewing.',409)
    # Only a verified catalog PDF can be opened; never accept a client path/URL
    # or use a shell. Each requested PDF opens in a separate Edge window.
    key=(str(store.storage),request_id); now=time.monotonic()
    with _EDGE_OPEN_LOCK:
        for old,(stamp,_) in list(_EDGE_OPEN_RECEIPTS.items()):
            if now-stamp>600: del _EDGE_OPEN_RECEIPTS[old]
        if key in _EDGE_OPEN_RECEIPTS:
            previous=_EDGE_OPEN_RECEIPTS[key][1]
            if previous['record_id']!=rid: raise ReviewError('Request ID was reused for another paper.',409)
            return {**previous,'duplicate_request':True}
        executable=edge_executable()
        try:
            with (store.storage/'edge-launch.log').open('ab') as log:
                process=subprocess.Popen([str(executable),'--new-window',pdf.as_uri()],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                                         stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                code=process.wait(timeout=1.5)
            except subprocess.TimeoutExpired:
                code=None
            if code not in (None,0): raise ReviewError(f'Edge could not open the PDF (exit {code}). Restart the review with Start local classification review.cmd. Details: edge-launch.log.',503)
        except OSError as exc: raise ReviewError('Could not start Microsoft Edge. Check that Edge opens normally.',503) from exc
        receipt={'record_id':rid,'browser':'Microsoft Edge','launched':True,'duplicate_request':False}
        _EDGE_OPEN_RECEIPTS[key]=(now,receipt)
        return receipt

def dispatch(handler,root,storage=None):
    """Return True for handled routes; plug into existing GET and POST handlers."""
    path=urlparse(handler.path).path
    assets={'/reclassification.html':('reclassification.html','text/html; charset=utf-8'),'/reclassification.js':('reclassification.js','text/javascript; charset=utf-8'),'/reclassification.css':('reclassification.css','text/css; charset=utf-8')}
    if not (path.startswith('/api/reclassification') or path.startswith('/reclassification_review') or path in assets): return False
    try:
        if path.startswith('/reclassification_review'): raise ReviewError('Use the review export buttons to access saved decisions.',403)
        if path in assets:
            if handler.command!='GET': raise ReviewError('Method not allowed.',405)
            asset,mime=assets[path]; send(handler,200,(UI/asset).read_bytes(),mime); return True
        storage=Path(storage) if storage else UI/'reclassification_review'
        key=(str(Path(root).resolve()),str(storage.resolve()))
        if key not in STORES: STORES[key]=ReviewStore(root,storage)
        store=STORES[key]; query=parse_qs(urlparse(handler.path).query)
        if handler.command=='GET':
            if path=='/api/reclassification': send(handler,200,store.load())
            elif path=='/api/reclassification/status': send(handler,200,{'app':'local-classification-review','version':APP_VERSION,'desktop_launcher':DESKTOP_LAUNCHER,'csrf_token':TOKEN})
            elif path=='/api/reclassification/history': send(handler,200,{'history':store.history(query.get('id',[''])[0])})
            elif path=='/api/reclassification/export':
                body,mime,name=store.export(query.get('format',['json'])[0]); send(handler,200,body,mime,name)
            elif path=='/api/reclassification/pdf':
                rid=query.get('id',[''])[0]; record=store.records(store.catalog()).get(rid)
                if not record or not record.get('pdf_path'): raise ReviewError('No verified local PDF is linked to this record.',404)
                pdf=Path(record['pdf_path']).resolve(); corpus=Path(store.catalog()['pdf_root']).resolve()
                if not pdf.is_relative_to(corpus) or pdf.suffix.lower()!='.pdf' or not pdf.is_file(): raise ReviewError('The linked PDF is unavailable in this corpus.',404)
                send_pdf(handler,pdf,rid)
            else: raise ReviewError('Not found.',404)
        elif handler.command=='POST' and path in ['/api/reclassification/save','/api/reclassification/open-pdf-edge','/api/reclassification/stop']:
            if handler.headers.get('X-Review-Token')!=TOKEN: raise ReviewError('Reload this local review page and try again.',403)
            origin=handler.headers.get('Origin')
            if origin and urlparse(origin).netloc!=handler.headers.get('Host'): raise ReviewError('Cross-origin saves are not allowed.',403)
            if handler.headers.get('Content-Type','').split(';')[0]!='application/json': raise ReviewError('JSON required.',415)
            length=int(handler.headers.get('Content-Length','0'))
            if length<1 or length>1000000: raise ReviewError('Invalid request size.',413)
            payload=json.loads(handler.rfile.read(length).decode('utf-8'))
            if path=='/api/reclassification/stop':
                send(handler,200,{'stopping':True})
                threading.Thread(target=handler.server.shutdown,daemon=True).start()
            elif path=='/api/reclassification/open-pdf-edge': send(handler,200,open_pdf_in_edge(store,payload))
            else: send(handler,200,{'review':store.save(payload)})
        else: raise ReviewError('Method not allowed.',405)
    except ReviewError as exc: send(handler,exc.status,{'error':str(exc)})
    except (ValueError,UnicodeError,json.JSONDecodeError) as exc: send(handler,400,{'error':str(exc)})
    except (BrokenPipeError,ConnectionResetError): pass
    except Exception as exc: send(handler,500,{'error':f'Could not complete the request: {exc}'})
    return True

def main():
    global DESKTOP_LAUNCHER
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--root',type=Path,default=UI.parent); parser.add_argument('--storage',type=Path,default=UI/'reclassification_review'); parser.add_argument('--port',type=int,default=8796); parser.add_argument('--desktop',action='store_true',help='Started by the user from the Windows desktop launcher.'); args=parser.parse_args()
    DESKTOP_LAUNCHER=args.desktop
    ReviewStore(args.root,args.storage)
    class Handler(SimpleHTTPRequestHandler):
        def local_request(self):
            host=urlparse('http://'+self.headers.get('Host','')).hostname
            if host not in ('127.0.0.1','localhost'):
                self.send_error(403); return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self.send_error(403); return False
            return True
        def do_GET(self):
            if not self.local_request(): return
            if self.path=='/': self.path='/reclassification.html'
            if not dispatch(self,args.root,args.storage): self.send_error(404)
        def do_POST(self):
            if not self.local_request(): return
            if not dispatch(self,args.root,args.storage): self.send_error(404)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Reclassification review: http://127.0.0.1:{args.port}/reclassification.html',flush=True)
    print(f'Decisions: {args.storage / "classification.csv"}',flush=True)
    server.serve_forever()

if __name__=='__main__': main()
