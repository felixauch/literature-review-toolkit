"""One-time, read-only import of an older review into a NEW CSV review folder.

SQLite is imported here only to read legacy files. The running CSV toolkit does
not import or use it. The original folder, files, decisions and history remain.
"""
from pathlib import Path
import argparse, hashlib, json, shutil, sqlite3
from contextlib import closing
from csv_storage import CsvJournal, read_object, write_object
from synthesis import VERSION

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_db(path,current_table,history_table,id_key='id',event_key='event'):
    if not path.exists():return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row;db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        current=[dict(r) for r in db.execute('SELECT * FROM '+current_table)] if current_table in tables else []
        history=[dict(r) for r in db.execute('SELECT * FROM '+history_table+' ORDER BY '+event_key)] if history_table in tables else []
        for r in current+history:
            if isinstance(r.get('payload'),str):r['payload']=json.loads(r['payload'])
        # Preserve history exactly. A current row without an identical historical
        # version gets an explicit migration snapshot rather than losing either.
        last={r[id_key]:r for r in history}
        for r in current:
            prior=last.get(r[id_key]);compare={k:(prior or {}).get(k) for k in r}
            if compare==r:continue
            row=dict(r)
            if prior and row['revision']<=prior['revision']:
                row['legacy_revision']=row['revision'];row['revision']=prior['revision']+1
                row['migration_note']='Current legacy state differed from the saved history; both were preserved.'
            row['migration_snapshot']=True;history.append(row)
        return history

def _migrate(source,out):
    source=Path(source).resolve();out=Path(out).resolve()
    if out.exists() or out==source or out.is_relative_to(source):raise ValueError('Choose a new folder outside the original review.')
    if not (source/'manifest.json').is_file():raise ValueError('Select an older review containing manifest.json.')
    watched={p:sha(p) for p in source.rglob('*') if p.is_file() and (p.suffix in ('.json','.sqlite3') or p.name.endswith(('-wal','-shm')))}
    out.mkdir(parents=True)
    # Only explicit review artifacts are copied; source PDFs remain at their existing paths.
    data_names={'manifest.json','catalog.json','domain-suggestions.json','coverage.json'}
    for p in source.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(source)
        if p.suffix=='.json' and (p.name in data_names or rel.parts[0] in ('papers','paper_sections','local_proposals')):
            write_object((out/rel).with_suffix('.csv'),json.loads(p.read_text(encoding='utf-8-sig')))
        elif p.suffix in ('.csv','.json') and p.name not in data_names:
            dest=out/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    manifest=read_object(out/'manifest.csv');manifest['version']=VERSION
    old_hashes={r['record_id']:r.get('evidence_sha256') for r in manifest['records']}
    new_hashes={r['record_id']:sha(out/'papers'/(r['record_id']+'.csv')) for r in manifest['records']}
    for r in manifest['records']:r['evidence_sha256']=new_hashes[r['record_id']]
    def hashes(value,ident):
        if isinstance(value,dict):
            for k,v in value.items():
                if k=='evidence_sha256' and v==old_hashes.get(ident):value[k]=new_hashes[ident]
                else:hashes(v,ident)
        elif isinstance(value,list):
            for v in value:hashes(v,ident)
    for folder in ['paper_sections','local_proposals']:
        for p in (out/folder).glob('*.csv'):
            obj=read_object(p);hashes(obj,p.stem);write_object(p,obj)
    catpath=out/'classification/catalog.csv'
    if catpath.exists():
        cat=read_object(catpath)
        for r in cat.get('records',[]):hashes(r,r['record_id'])
        write_object(catpath,cat)
    write_object(out/'manifest.csv',manifest)
    specs=[('classification/reviews.sqlite3','classification','classification','decisions','history','record_id','event_id'),
           ('extraction.sqlite3','.','extraction','reviews','history','id','event'),
           ('extraction.sqlite3','.','domain_notes','domain_notes','domain_history','id','event'),
           ('reading.sqlite3','.','reading','reviews','history','id','event')]
    counts={}
    for old,folder,name,cur,hist,key,event in specs:
        rows=read_db(source/old,cur,hist,key,event)
        # Preserve historical hashes. Only the migrated current snapshot gets its
        # equivalent CSV extraction hash; prior revisions remain unchanged.
        latest={r[key]:r for r in rows}
        for ident,r in list(latest.items()):
            import copy
            changed=copy.deepcopy(r);hashes(changed,ident)
            if changed!=r:
                changed['revision']=r['revision']+1;changed['migration_note']='Storage conversion only; source PDF and decision values unchanged.';rows.append(changed)
        journal=CsvJournal(out/folder,name,key,event);journal.import_history(rows);counts[name]=len(rows)
    for p,digest in watched.items():
        if not p.exists() or sha(p)!=digest:raise RuntimeError('The old review changed during migration. Stop its server and retry into a new folder.')
    write_object(out/'migration_report.csv',{'source':str(source),'destination':str(out),'history_rows':counts,'original_files_unchanged':True,'changes':'Storage format only. No decisions confirmed or relabelled.'})
    return {'out':str(out),'history_rows':counts}


def migrate(source,out):
    import tempfile,shutil
    source=Path(source).resolve();out=Path(out).resolve()
    if out.exists() or out==source or out.is_relative_to(source):raise ValueError('Choose a new folder outside the original review.')
    out.parent.mkdir(parents=True,exist_ok=True)
    staging=Path(tempfile.mkdtemp(prefix='.csv-import-',dir=out.parent))/'review'
    try:
        result=_migrate(source,staging)
        report=read_object(staging/'migration_report.csv');report['destination']=str(out);write_object(staging/'migration_report.csv',report)
        # A failed import can never appear as a complete, resumable review.
        staging.rename(out);result['out']=str(out);return result
    finally:
        parent=staging.parent.resolve()
        if parent.parent==out.parent and parent.name.startswith('.csv-import-'):
            shutil.rmtree(parent)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(migrate(a.source,a.out)))
