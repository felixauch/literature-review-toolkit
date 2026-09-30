from __future__ import annotations
from csv_storage import read_object, write_object
import csv, io, json
from csv_storage import CsvJournal, StorageError
from contextlib import contextmanager
from pathlib import Path
from .schema import FIELDS, FIELD_MAP, STATES, DOMAIN_FIELDS, blank
from .engine import make_evidence
from .extract import sha, now

class ReviewError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

def safe_text(value, limit=12000):
    if not isinstance(value,str) or len(value)>limit:raise ReviewError('Invalid or overlong text')
    return value.strip()

class Store:
    def __init__(self,run):
        self.root=Path(run).resolve();self.manifest=read_object(self.root/'manifest.csv')
        from .schema import configure
        configure(self.manifest['project'])
        self.records={r['record_id']:r for r in self.manifest['records']}
        self.domains=sorted({d.strip() for r in self.records.values() for d in r['report_core_domains'].split(';') if d.strip()})
        self.journal=CsvJournal(self.root,'extraction');self.domain_journal=CsvJournal(self.root,'domain_notes');self._papers={}
        from reading_plan import ReadingPlan
        self.reading=ReadingPlan(self.root,self.manifest['project'])
        from classification_store import ReviewStore
        self.classifier=ReviewStore(self.root,self.root/'classification') if (self.root/'classification/catalog.csv').exists() else None
        self._classification_stamp=None
        self.domains=list(dict.fromkeys([d['name'] for d in self.manifest['project'].get('domains',[])]+self.domains))
    def record(self,ident):
        self.sync_classification()
        if ident not in self.records:raise ReviewError('Unknown paper',404)
        return self.records[ident]
    def sync_classification(self):
        if not self.classifier:return
        stamp=self.classifier.journal.stamp
        if stamp==self._classification_stamp:return
        from classification_store import domain_columns
        data=self.classifier.load()
        for r in data['records']:
            target=self.records.get(r['record_id'])
            if target is None:continue
            decision=(r.get('review') or {}).get('payload',{})
            target.update(classification_status=r['review_status'],eligibility=decision.get('eligibility','uncertain'),domains_reviewed=r['domain_assignment']['reviewed'])
            state=r.get('review') or {}
            verified=r['review_status']=='confirmed' and decision.get('evidence_checked') is True
            target.update(output_label=decision.get('output_label',r['preserved_assessment'].get('output_label',target.get('output_label',''))),
                          author_verified='true' if verified else 'false',
                          verification_reviewer=decision.get('reviewer','') if verified else '',
                          verification_recorded_at=state.get('verification_recorded_at',state.get('updated_at','')) if verified else '',
                          verification_basis=state.get('verification_basis','Reviewer confirmed classification against the source') if verified else '')
            if decision.get('labels'):target['report_categories']='; '.join(k for k,v in decision['labels'].items() if v=='yes')
            target.update(domain_columns(r['domain_assignment']))
        self._classification_stamp=stamp
    def paper(self,ident):
        r=self.record(ident);path=self.root/'papers'/f'{ident}.csv'
        if sha(path)!=r['evidence_sha256']:raise ReviewError('Extracted evidence changed; create and review a new run.',409)
        if ident not in self._papers:self._papers[ident]=read_object(path)
        return self._papers[ident]
    def freshness(self,ident):
        r=self.record(ident);problems=[]
        source=Path(self.manifest['source_csv'])
        if not source.exists() or sha(source)!=self.manifest['source_csv_sha256']:problems.append('Corpus metadata changed since this extraction run.')
        path=Path(r['pdf_path']) if r['pdf_path'] else None
        if not path or not path.is_file():problems.append('Source PDF is unavailable.')
        elif sha(path)!=r['pdf_sha256']:problems.append('Source PDF changed since extraction.')
        return problems
    def assistance(self,ident):
        record=self.record(ident);path=self.root/'local_proposals'/f'{ident}.csv'
        if not path.exists():return None
        obj=read_object(path)
        if obj.get('evidence_sha256')!=record['evidence_sha256'] or obj.get('pdf_sha256')!=record['pdf_sha256']:
            return {'fields':{},'warning':'Local-model draft belongs to a different source version.'}
        return obj
    def sections(self,ident):
        record=self.record(ident);path=self.root/'paper_sections'/f'{ident}.csv'
        if not path.exists():return None
        obj=read_object(path)
        if obj.get('evidence_sha256')!=record['evidence_sha256'] or obj.get('pdf_sha256')!=record['pdf_sha256']:
            return {'sections':{},'warning':'Section excerpts belong to a different source version.'}
        return obj
    def review(self,ident):
        self.record(ident)
        row=self.journal.states().get(ident)
        if row:
            result=row;payload=result['payload'];old=payload.get('fields',{});legacy=payload.get('legacy_fields',{})
            for key,item in old.items():
                if key not in FIELD_MAP:legacy[key]=item
            missing=set(FIELD_MAP)-set(old)
            payload['fields']={key:old.get(key,blank()['fields'][key]) for key in FIELD_MAP}
            if legacy:payload['legacy_fields']=legacy
            if missing:
                payload['verified']=False;result['status']='draft';result['schema_changed']=True
            return result
        return dict(id=ident,revision=0,status='unreviewed',payload=blank(),updated_at='')
    def index(self):
        self.sync_classification()
        reviews={}
        for ident,row in self.journal.states().items():
            r=dict(row);payload=r.pop('payload')
            if set(FIELD_MAP)-set(payload.get('fields',{})):r['status']='draft'
            reviews[ident]=r
        reading=self.reading.rows()
        result=[]
        for ident,r in self.records.items():
            entry={k:v for k,v in self.reading.enrich(r,reading).items() if k not in ('pdf_path','evidence_sha256')}|reviews.get(ident,{'status':'unreviewed','revision':0})
            if entry.get('reading_depth')=='brief' and entry.get('reading_status')=='brief_done':entry['status']='brief_done'
            result.append(entry)
        return result
    def validate(self,ident,raw,status):
        if not isinstance(raw,dict):raise ReviewError('Invalid review')
        out=blank();out['reviewer']=safe_text(raw.get('reviewer',''),160);out['verified']=raw.get('verified') is True
        fields=raw.get('fields',{})
        if not isinstance(fields,dict) or set(fields)!=set(FIELD_MAP):raise ReviewError('The review fields do not match this version')
        pages=self.paper(ident)['pages']
        for key,spec in FIELD_MAP.items():
            value=fields[key]
            if not isinstance(value,dict) or value.get('state') not in STATES:raise ReviewError('Choose a valid field state')
            item={'state':value['state'],'value':safe_text(value.get('value','')),'pages':safe_text(value.get('pages',''),500),'evidence':[], 'assistance':safe_text(value.get('assistance',''),2500)}
            if spec.get('type','text')!='text':
                from choices import selection
                try:item['choices']=selection(spec,value.get('choices',[]))
                except ValueError as e:raise ReviewError(str(e))
                if item['choices'] and item['state']!='recorded':raise ReviewError('Selected choices require Recorded status')
                item['value']='; '.join(item['choices'])
            references=value.get('evidence',[])
            if not isinstance(references,list) or len(references)>40:raise ReviewError('Too many evidence passages')
            for e in references:
                if not isinstance(e,dict):raise ReviewError('Invalid evidence')
                page=e.get('page');start=e.get('start');end=e.get('end')
                if any(type(n)!=int for n in (page,start,end)) or not 1<=page<=len(pages):raise ReviewError('Invalid evidence page')
                text=pages[page-1]
                if not 0<=start<end<=len(text) or end-start>6000:raise ReviewError('Invalid quotation offsets')
                quote=text[start:end];correct=make_evidence(page,start,end,quote,e.get('section','search'))
                if e.get('quote')!=quote or e.get('id')!=correct['id']:raise ReviewError('Quotation differs from the stored PDF extraction')
                if correct['id'] not in {x['id'] for x in item['evidence']}:item['evidence'].append(correct)
            if status in ('confirmed','assessed'):
                if spec.get('required') and item['state']=='unchecked':raise ReviewError(f"Review the required field: {spec['title']}")
                if item['state']=='recorded':
                    if not item['value']:raise ReviewError(f"Add text for: {spec['title']}")
                    if not spec.get('author') and not (item['evidence'] or item['pages']):raise ReviewError(f"Attach evidence or enter a source page for: {spec['title']}")
                if spec.get('type','text')=='text' and item['state'] in ('unclear','not_applicable') and not item['value']:raise ReviewError(f"Add a brief reason for: {spec['title']}")
            out['fields'][key]=item
        if status=='confirmed':
            if not out['reviewer']:raise ReviewError('Enter your name before confirming')
            if not out['verified']:raise ReviewError('Confirm that you checked the source and distinguished your interpretation')
            stale=self.freshness(ident)
            if stale:raise ReviewError(' '.join(stale),409)
        else:out['verified']=False
        legacy=self.review(ident)['payload'].get('legacy_fields',{})
        if legacy:out['legacy_fields']=legacy
        out['source_pdf_sha256']=self.record(ident)['pdf_sha256'];out['evidence_sha256']=self.record(ident)['evidence_sha256']
        return out
    def save(self,ident,raw,revision,status):
        if status not in ('draft','later','confirmed','assessed'):raise ReviewError('Invalid review status')
        payload=self.validate(ident,raw,status);stamp=now()
        try:return self.journal.save({'id':ident,'status':status,'payload':payload,'updated_at':stamp},revision)
        except StorageError as e:raise ReviewError(str(e),e.status)

    def domain(self,ident):
        if ident not in self.domains:raise ReviewError('Unknown domain',404)
        row=self.domain_journal.states().get(ident)
        if row:return row
        return {'id':ident,'revision':0,'payload':{f['id']:('' if f.get('type','text')=='text' else []) for f in __import__('synthesis.schema',fromlist=['DOMAIN_SPECS']).DOMAIN_SPECS},'updated_at':''}
    def save_domain(self,ident,payload,revision):
        self.domain(ident)
        if not isinstance(payload,dict) or set(payload)!=set(DOMAIN_FIELDS):raise ReviewError('Invalid domain notes')
        from .schema import DOMAIN_SPECS
        from choices import selection
        checked={}
        for spec in DOMAIN_SPECS:
            k=spec['id']
            if spec.get('type','text')=='text':checked[k]=safe_text(payload[k],30000)
            else:
                try:checked[k]=selection(spec,payload[k])
                except ValueError as e:raise ReviewError(str(e))
        payload=checked;stamp=now()
        try:self.domain_journal.save({'id':ident,'payload':payload,'updated_at':stamp},revision)
        except StorageError as e:raise ReviewError(str(e),e.status)
        return self.domain(ident)

    def overview(self):
        records=[]
        for r in self.index():
            review=self.review(r['record_id']);records.append({**r,'review':review})
        return {'records':records,'domain_notes':[self.domain(d) for d in self.domains]}
    def export(self):
        history=self.journal.history();domain_history=self.domain_journal.history()
        return {'exported_at':now(),'run':{k:v for k,v in self.manifest.items() if k!='records'},**self.overview(),'review_history':history,'domain_history':domain_history,'reading_plan':self.reading.export(),'local_model_drafts':[self.assistance(i) for i in self.records if self.assistance(i)]}
    def csv_export(self):
        rows=self.overview()['records'];out=io.StringIO(newline='')
        base_headers=['record_id','title','doi','report_categories','report_core_domains','decision_link','output_label','status','reading_priority','reading_group','reading_depth','reading_status','reading_note','year','authors','eligibility','classification_status','author_verified','extraction_verified','verification_reviewer','verification_recorded_at','verification_basis']
        headers=list(base_headers)
        for f in FIELDS:headers += [f['id'],f['id']+'_state',f['id']+'_pages',f['id']+'_evidence_ids',f['id']+'_choices']
        writer=csv.DictWriter(out,fieldnames=headers);writer.writeheader()
        for r in rows:
            row={k:r.get(k,'') for k in base_headers};row['status']=r.get('status','unreviewed')
            row['extraction_verified']='true' if r['review'].get('status')=='confirmed' and r['review']['payload'].get('verified') is True else ('' if r['review'].get('status')=='unreviewed' else 'false')
            for key,item in r['review']['payload']['fields'].items():
                row[key+'_choices']=json.dumps(item.get('choices',[]),ensure_ascii=False);row[key]=item['value'];row[key+'_state']=item['state'];row[key+'_pages']=item['pages'] or '; '.join(map(str,sorted({e['page'] for e in item['evidence']})));row[key+'_evidence_ids']='; '.join(e['id'] for e in item['evidence'])
            # Protect spreadsheets from interpreting user/source text as formulae.
            row={k:("'"+str(v) if str(v).lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()};writer.writerow(row)
        return '\ufeff'+out.getvalue()
