"""Connect human full-text decisions to a new combined review run. No network or model calls."""
from pathlib import Path
import argparse,csv,hashlib,json,subprocess,sys
from datetime import datetime,timezone

HERE=Path(__file__).resolve().parent

def project_path(value):
    path=Path(value).expanduser()
    if not (path/'project.json').is_file(): path=HERE/'projects'/value
    if not (path/'project.json').is_file(): raise ValueError('Choose a project folder or slug containing project.json.')
    return path.resolve()

def read(path):
    if not path.is_file(): raise ValueError('Missing '+str(path))
    with path.open(encoding='utf-8-sig',newline='') as f: rows=list(csv.DictReader(f))
    ids=[r.get('record_id','') for r in rows]
    if any(not x for x in ids) or len(ids)!=len(set(ids)): raise ValueError('Missing or duplicate record IDs in '+path.name)
    return rows

def collect(project):
    metadata={r['record_id']:r for r in read(project/'title_screening.csv')}
    decisions=read(project/'fulltext_recommendations.csv')
    rows=[];problems=[]
    for decision in decisions:
        if decision.get('fulltext_final_decision')!='Include': continue
        rid=decision['record_id'];meta=metadata.get(rid)
        if not meta: problems.append(rid+': missing title/abstract record');continue
        if meta.get('human_decision')!='Include': problems.append(rid+': resolve title/abstract decision before handoff');continue
        raw=decision.get('fulltext_local_pdf','').strip()
        path=(project/raw).resolve() if raw else None
        if path is None or not path.is_file():
            hits=list((project/'pdfs').rglob(rid+'__*.pdf'))
            if len(hits)==1:path=hits[0].resolve()
        if path is None or not path.is_file(): problems.append(rid+': included record has no local PDF');continue
        if not path.is_relative_to(project/'pdfs'): problems.append(rid+': PDF must be inside this project/pdf folder');continue
        rows.append({k:meta.get(k,'') for k in ('record_id','title','authors','year','doi')})
        rows[-1]['fulltext_local_pdf']=path.relative_to(project/'pdfs').as_posix()
    if problems: raise ValueError('Handoff stopped; no records silently skipped:\n'+'\n'.join(problems))
    if not rows: raise ValueError('No human full-text Include decisions with local PDFs. Save those decisions first.')
    return rows,{'title_records':len(metadata),'fulltext_records':len(decisions),'included_transferred':len(rows),
                 'fulltext_excluded':sum(r.get('fulltext_final_decision')=='Exclude' for r in decisions),
                 'fulltext_pending':sum(r.get('fulltext_final_decision') not in ('Include','Exclude') for r in decisions)}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--project',required=True);ap.add_argument('--config');ap.add_argument('--out');ap.add_argument('--check',action='store_true')
    a=ap.parse_args();project=project_path(a.project)
    rows,counts=collect(project)
    if a.check:print(json.dumps(counts,indent=2));return
    if not a.config or not a.out:ap.error('--config and --out are required unless using --check')
    config=Path(a.config).expanduser().resolve();out=Path(a.out).expanduser().resolve()
    if out.exists():raise ValueError('Run folder already exists. Resume it or choose a new folder; decisions are never overwritten.')
    module=HERE/'toolkit/review_workspace'
    subprocess.run([sys.executable,str(module/'project_setup.py'),'--mode','review','--check',str(config)],check=True)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    source=project/'handoff-inputs'/f'{stamp}_records.csv';source.parent.mkdir(exist_ok=True)
    with source.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    subprocess.run([sys.executable,str(module/'prepare_review.py'),'--config',str(config),'--csv',str(source),'--pdf-root',str(project/'pdfs'),'--out',str(out)],check=True)
    manifest={'created_at':stamp,'source_project':str(project),'counts':counts,'input_csv':str(source),
              'note':'Only explicit human full-text Include decisions were transferred. Category, domain and evidence decisions start unconfirmed.',
              'source_hashes':{name:hashlib.sha256((project/name).read_bytes()).hexdigest() for name in ['title_screening.csv','fulltext_recommendations.csv']}}
    (out/'handoff.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'run':str(out),**counts},indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,FileNotFoundError) as exc:raise SystemExit(str(exc))
