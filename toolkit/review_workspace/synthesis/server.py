"""Loopback-only review UI. Serves local sources; no external libraries or services."""
from __future__ import annotations
import argparse, hashlib, json, mimetypes, secrets, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
from . import VERSION
from .schema import FIELDS, GROUPS, DOMAIN_SPECS
from .store import Store, ReviewError
from classification_store import ReviewError as ClassificationError
from reading_plan import ReadingError
from csv_storage import StorageError
from .engine import search

STATIC=Path(__file__).parent/'static'
def serve(run,port):
    store=Store(run);token=secrets.token_urlsafe(32);host=f'127.0.0.1:{port}'
    run_id=hashlib.sha256(str(store.root).encode()).hexdigest()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass  # Never log source text, search terms or review notes.
        def base(self,code,ctype,length,attachment=None):
            self.send_response(code);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(length))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
            if attachment:self.send_header('Content-Disposition',f'attachment; filename="{attachment}"')
            self.end_headers()
        def send(self,obj,code=200):
            body=json.dumps(obj,ensure_ascii=False).encode();self.base(code,'application/json; charset=utf-8',len(body));self.wfile.write(body)
        def guard(self,write=False):
            if self.headers.get('Host')!=host:raise ReviewError('Invalid host',403)
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{host}':raise ReviewError('Cross-origin request denied',403)
            if self.headers.get('Sec-Fetch-Site')=='cross-site':raise ReviewError('Cross-site request denied',403)
            if write and self.headers.get('X-Review-Token')!=token:raise ReviewError('Invalid request token',403)
        def do_GET(self):
            try:
                self.guard();url=urlparse(self.path);path=unquote(url.path);qs=parse_qs(url.query)
                if path=='/favicon.ico':
                    self.base(204,'image/x-icon',0);return
                if path=='/theme.css':
                    body=(STATIC.parents[2]/'ui/theme.css').read_bytes();self.base(200,'text/css; charset=utf-8',len(body));return self.wfile.write(body)
                if path=='/api/status':return self.send(dict(app='local-synthesis-review',version=VERSION,records=len(store.records),run_id=run_id))
                if path=='/api/meta':return self.send(dict(token=token,fields=FIELDS,groups=GROUPS,domain_fields=DOMAIN_SPECS,project=store.manifest['project'],domains=store.domains,records=store.index(),version=VERSION,reading_plan=store.reading.config))
                if path.startswith('/api/classification/'):
                    if not store.classifier:raise ReviewError('Classification is not configured for this run.',404)
                    ident=path.rsplit('/',1)[-1];data=store.classifier.load()
                    record=next((r for r in data['records'] if r['record_id']==ident),None)
                    if not record:raise ReviewError('Unknown paper',404)
                    return self.send({'record':record,'categories':data['categories'],'domains':data['domains'],'project':data.get('project',{})})
                if path=='/api/classification-export':
                    if not store.classifier:raise ReviewError('Classification unavailable',404)
                    body,mime,name=store.classifier.export(qs.get('format',['json'])[0]);self.base(200,mime,len(body),name);return self.wfile.write(body)
                if path.startswith('/api/record/'):
                    ident=path.rsplit('/',1)[-1];r=store.record(ident);data=store.paper(ident)
                    return self.send({'record':{k:v for k,v in r.items() if k!='pdf_path'},'review':store.review(ident),'evidence':data['evidence'],'candidates':{},'paper_sections':store.sections(ident),'reading_review':store.reading.get(ident),'stale':store.freshness(ident)})
                if path.startswith('/api/search/'):
                    ident=path.rsplit('/',1)[-1];return self.send({'results':search(store.paper(ident)['pages'],qs.get('q',[''])[0])})
                if path=='/api/overview':return self.send(store.overview())
                if path=='/api/domain':return self.send(store.domain(qs.get('id',[''])[0]))
                if path=='/api/export':
                    mode=qs.get('format',['json'])[0]
                    if mode=='browser':
                        from assessment_browser import bundle
                        body=bundle(store.csv_export(),store.manifest['project']);self.base(200,'application/zip',len(body),'Corpus explorer.zip');return self.wfile.write(body)
                    if mode=='archive':
                        from csv_storage import archive_records
                        body=archive_records(store.root);self.base(200,'application/zip',len(body),'review-csv-records-and-history.zip');return self.wfile.write(body)
                    csv_mode=qs.get('format',['json'])[0]=='csv';body=(store.csv_export() if csv_mode else json.dumps(store.export(),ensure_ascii=False,indent=2)).encode('utf8')
                    self.base(200,'text/csv; charset=utf-8' if csv_mode else 'application/json; charset=utf-8',len(body),'synthesis-extraction.csv' if csv_mode else 'synthesis-extraction-with-history.json');return self.wfile.write(body)
                if path.startswith('/pdf/'):
                    r=store.record(path.rsplit('/',1)[-1]);p=Path(r['pdf_path']).resolve()
                    if not p.is_file() or p.suffix.lower()!='.pdf' or not p.is_relative_to(Path(store.manifest['pdf_root']).resolve()):raise ReviewError('PDF unavailable',404)
                    self.base(200,'application/pdf',p.stat().st_size)
                    with p.open('rb') as f:
                        while chunk:=f.read(1024*256):self.wfile.write(chunk)
                    return
                names={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css','/classification.js':'classification.js','/reading.js':'reading.js','/choices.js':'choices.js','/synthesis-map.js':'synthesis-map.js'}
                if path not in names:raise ReviewError('Not found',404)
                p=STATIC/names[path];body=p.read_bytes();self.base(200,(mimetypes.guess_type(p)[0] or 'text/plain')+'; charset=utf-8',len(body));self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
            except (ReviewError,ClassificationError,ReadingError,StorageError) as e:self.send({'error':str(e)},e.status)
            except Exception:self.send({'error':'Local request failed. No source text was logged.'},500)
        def do_POST(self):
            try:
                self.guard(True)
                if self.headers.get('Content-Type')!='application/json':raise ReviewError('JSON required',415)
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=2_000_000:raise ReviewError('Invalid request size',413)
                raw=json.loads(self.rfile.read(size));path=urlparse(self.path).path
                if path=='/api/reading':
                    ident=raw.get('id');record=store.record(ident)
                    if raw.get('status') in ('brief_done','detailed_needed'):
                        stale=store.freshness(ident)
                        if stale:raise ReviewError(' '.join(stale),409)
                    return self.send(store.reading.save(record,raw.get('payload'),raw.get('revision'),raw.get('status','draft')))
                if path=='/api/save':return self.send(store.save(raw.get('id'),raw.get('payload'),raw.get('revision'),raw.get('status','draft')))
                if path=='/api/classify':
                    if not store.classifier:raise ReviewError('Classification unavailable',404)
                    return self.send(store.classifier.save(raw))
                if path=='/api/domain':return self.send(store.save_domain(raw.get('id'),raw.get('payload'),raw.get('revision')))
                raise ReviewError('Not found',404)
            except (ReviewError,ClassificationError,ReadingError,StorageError) as e:self.send({'error':str(e)},e.status)
            except (ValueError,TypeError,KeyError):self.send({'error':'Invalid request'},400)
            except Exception:self.send({'error':'Save failed; your changes have not been confirmed.'},500)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    # Review needs an inbound loopback listener, never outbound connections.
    def no_outbound(event,args):
        if event in ('socket.connect','socket.connect_ex','socket.getaddrinfo','subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn'):
            raise RuntimeError('Outbound network and child processes are disabled in the review server')
    sys.addaudithook(no_outbound)
    print(json.dumps({'app':'local-synthesis-review','url':f'http://{host}/','records':len(store.records)}),flush=True)
    server.serve_forever()

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('--port',type=int,default=8797)
    a=ap.parse_args();serve(a.run,a.port)
if __name__=='__main__':main()
