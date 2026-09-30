"""Build a new local evidence run; never change corpus labels or author reviews."""
from __future__ import annotations
import argparse, csv, hashlib, json, logging, re, sys, io, warnings
from importlib.metadata import version as package_version
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from . import VERSION
from csv_storage import write_object
from .engine import retrieve, display

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def dump(path,value):write_object(path,value)

def offline_guard(event,args):
    # gethostname reads local OS metadata; PDFium uses it during platform detection.
    if event.startswith('socket.') and event not in ('socket.__new__','socket.gethostname'):raise RuntimeError('Network disabled during extraction')
    if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn'):raise RuntimeError('Child processes disabled during extraction')

def run(source,pdf_root,out,extractor='pypdfium2',config=None):
    from project_setup import load
    from . import schema,engine
    project=load(config,'synthesis');schema.configure(project);engine.configure(project)
    source=Path(source).resolve();pdf_root=Path(pdf_root).resolve();out=Path(out).resolve()
    if any(str(p).startswith(('\\\\','//')) for p in (source,pdf_root,out)):raise ValueError('Local drives only')
    if out.exists():raise FileExistsError('Use a new run folder. Existing evidence and decisions are never overwritten.')
    with source.open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    ids=[r.get('record_id','') for r in rows]
    if not rows or any(not re.fullmatch(r'[A-Za-z0-9_-]+',i) for i in ids) or len(ids)!=len(set(ids)):raise ValueError('Unique record IDs required')
    source_hash=sha(source)
    # Initialize parser libraries before opening any PDF. PDFium's Windows
    # platform detection may launch the local `ver` command during import.
    if extractor=='pypdfium2':import pypdfium2 as pdfium
    elif extractor=='pypdf':from pypdf import PdfReader
    else:raise ValueError('Unsupported extractor')
    sys.addaudithook(offline_guard)
    logging.getLogger('pypdf').setLevel(logging.CRITICAL)
    out.mkdir(parents=True);records=[];evidence_total=0;warning_total=0
    for row in rows:
        pages=[];path=None;digest='';problem=''
        try:
            raw=(row.get('fulltext_local_pdf') or row.get('pdf_path') or '').strip()
            if not raw or re.match(r'^[A-Za-z][A-Za-z0-9+.-]*://',raw) or raw.startswith(('\\\\','//')):raise ValueError('Local PDF required')
            path=Path(raw)
            if not path.is_absolute():path=pdf_root/path
            path=path.resolve()
            if not path.is_relative_to(pdf_root) or path.suffix.lower()!='.pdf' or not path.is_file():raise ValueError('Unavailable source')
            digest=sha(path)
            # Parser diagnostics may contain document fragments; never return them to logs.
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), warnings.catch_warnings():
                warnings.simplefilter('ignore')
                if extractor=='pypdfium2':
                    reader=pdfium.PdfDocument(path)
                    try:
                        for i in range(len(reader)):
                            page=reader[i]
                            try:
                                textpage=page.get_textpage()
                                try:pages.append(textpage.get_text_range())
                                finally:textpage.close()
                            finally:page.close()
                    finally:reader.close()
                else:
                    reader=PdfReader(path,strict=False)
                    pages=[p.extract_text() or '' for p in reader.pages]
            if sha(path)!=digest:raise ValueError('Source changed')
        except Exception as exc:
            problem='Source extraction failed ('+type(exc).__name__+'). Read the original PDF manually.';pages=[]
        data=retrieve(pages)
        if problem:data['warnings'].insert(0,problem)
        # Identity check is algorithmic and does not expose passages in logs.
        title_words={w.lower() for w in re.findall(r'\b[A-Za-z]{4,}\b',row.get('title','')) if w.lower() not in {'this','with','from','using','based','study','analysis'}}
        front=display(' '.join(pages[:2])).lower()
        overlap=sum(w in front for w in title_words)/len(title_words) if title_words else 1
        doi=row.get('doi','').lower().removeprefix('https://doi.org/')
        if pages and len(title_words)>=5 and overlap<.45 and not (doi and doi in re.sub(r'\s+','',front)):
            data['warnings'].append('Possible source/version mismatch: title/DOI not sufficiently matched on first two PDF pages. Verify identity.')
        record={k:row.get(k,'') for k in ('record_id','title','authors','year','doi','report_categories','report_core_domains','decision_link','output_label')}
        record.update(pdf_path=str(path) if path and path.is_file() else '',pdf_sha256=digest,pdf_pages=len(pages),warnings=data['warnings'],candidate_count=len(data['evidence']))
        data.update(record_id=row['record_id'],pages=pages,pdf_sha256=digest)
        # Every suggested quotation must be a literal slice of the page extraction.
        for e in data['evidence'].values():assert pages[e['page']-1][e['start']:e['end']]==e['quote']
        dump(out/'papers'/f"{row['record_id']}.csv",data)
        record['evidence_sha256']=sha(out/'papers'/f"{row['record_id']}.csv")
        records.append(record);evidence_total+=len(data['evidence']);warning_total+=bool(data['warnings'])
        if len(records)%25==0:print(json.dumps({'processed':len(records),'total':len(rows)}),flush=True)
    if sha(source)!=source_hash:raise RuntimeError('Source metadata changed while extracting')
    for r in records:
        if r['pdf_sha256'] and sha(r['pdf_path'])!=r['pdf_sha256']:raise RuntimeError('A PDF changed while extracting')
    manifest=dict(project=project,version=VERSION,created_at=now(),source_csv=str(source),source_csv_sha256=source_hash,pdf_root=str(pdf_root),records=records,
      runtime_llm_calls=False,trained_model=False,network_guard='Python audit hook blocks sockets and child processes during extraction; not an OS sandbox',
      extractor=extractor,extractor_version=package_version(extractor),code_sha256={p.name:sha(p) for p in Path(__file__).parent.glob('*.py')},
      evidence_spans=evidence_total,records_with_warnings=warning_total,author_fields_prefilled=False)
    dump(out/'manifest.csv',manifest)
    print(json.dumps({'records':len(records),'evidence_spans':evidence_total,'records_with_warnings':warning_total,'completed':True}),flush=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--csv',required=True);ap.add_argument('--pdf-root',required=True);ap.add_argument('--out',required=True)
    ap.add_argument('--extractor',choices=('pypdfium2','pypdf'),default='pypdfium2')
    ap.add_argument('--config',required=True)
    a=ap.parse_args();run(a.csv,a.pdf_root,a.out,a.extractor,a.config)
if __name__=='__main__':main()
