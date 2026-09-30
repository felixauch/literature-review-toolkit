"""Copy an explicit record_id,pdf_path manifest into a project; no fuzzy matching or network."""
from pathlib import Path
import csv,hashlib,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_config import CFG
from lib import read_csv
from corpus_files import find_local_pdf,pdf_name,upsert_manifest,rescan_pdfs
import shutil

def main():
    if len(sys.argv)!=2:raise SystemExit('Usage: import_pdf_manifest.py --project PROJECT import_manifest.csv')
    CFG.guard_writable();source=Path(sys.argv[1]).expanduser().resolve()
    with source.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    if not rows:raise SystemExit('The manifest is empty.')
    records={r['record_id']:r for r in read_csv(CFG.file('title_screening.csv'))}
    seen=set();planned=[]
    for row in rows:
        rid=row.get('record_id','').strip();raw=row.get('pdf_path','').strip()
        if rid in seen or rid not in records:raise SystemExit('Unknown or duplicate record ID: '+rid)
        seen.add(rid)
        src=(source.parent/raw).resolve()
        if not raw or not src.is_file():raise SystemExit('PDF not found for '+rid)
        with src.open('rb') as f:
            if not f.read(5).startswith(b'%PDF'):raise SystemExit('Not a PDF: '+str(src))
        existing=find_local_pdf(rid)
        if existing:
            if hashlib.sha256(existing.read_bytes()).digest()!=hashlib.sha256(src.read_bytes()).digest():raise SystemExit('Different PDF already linked to '+rid+'; reconcile it before importing.')
            continue
        planned.append((rid,src))
    CFG.ensure_dirs()
    for rid,src in planned:
        dest=CFG.pdf_pending/pdf_name(rid,records[rid].get('title',''))
        shutil.copy2(src,dest)
        upsert_manifest(rid,records[rid].get('title',''),dest,str(src),'not_reviewed','explicit mapping','')
    rescan_pdfs();print(f'Copied {len(planned)} PDFs; original files unchanged. Verify the PDFs against the records.')

if __name__=='__main__':main()
