from csv_storage import read_object, write_object
"""Prepare a configured review: one PDF extraction, category/domain proposals, blank human forms."""
import argparse,csv,hashlib,json,subprocess,sys
from pathlib import Path
from project_setup import load
from domain_rules import assess
from passages import windows

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def make_catalog(run):
    root=Path(run).resolve();manifest=read_object(root/'manifest.csv');project=manifest['project']
    target=root/'classification'
    if target.exists():raise FileExistsError('Classification run exists; never replace reviewed work.')
    target.mkdir();records=[];quotes=0
    from synthesis.extract import offline_guard
    sys.addaudithook(offline_guard)
    for source in manifest['records']:
        path=root/'papers'/f"{source['record_id']}.csv"
        if sha(path)!=source['evidence_sha256']:raise ValueError('Extraction changed')
        data=read_object(path);pages=data['pages']
        warning=' '.join(source.get('warnings',[]))
        severe=warning if not pages or sum(map(len,pages))<600 or 'mismatch' in warning else ''
        ca=assess(pages,project['categories'],windows,project,severe);da=assess(pages,project['domains'],windows,project,severe)
        labels={k:v['suggestion'] for k,v in ca.items()};evidence=[]
        for k,v in ca.items():
            for e in v['evidence']:evidence.append({**e,'id':'E'+str(len(evidence)+1),'kind':'support' if e['support'] else 'context','categories':[k] if e['support'] else [],'candidate_categories':[k]})
        prop={'decision':{'labels':labels},'assessments':ca,'evidence':evidence,'origin':'Configured local rules; human decision required'}
        record={k:source.get(k,'') for k in ('record_id','title','authors','year','doi','pdf_path','pdf_sha256','pdf_pages')}
        record.update(proposal=prop,domain_proposals=da,original={},legacy_audit={},source_warning=warning,
          proposal_hash=hashlib.sha256(json.dumps(prop,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
        records.append(record);quotes+=len(evidence)+sum(len(x['evidence']) for x in da.values())
    cat={'schema_version':1,'source_csv':manifest['source_csv'],'source_csv_sha256':manifest['source_csv_sha256'],'pdf_root':manifest['pdf_root'],'project':project,
      'categories':[d['name'] for d in project['categories']],'domains':[d['name'] for d in project['domains']],'records':records,
      'rules':{'statements':[d['name']+': '+d.get('description','') for d in project['categories']]},'audit_count':len(records),'removed_since_audit':[]}
    write_object(target/'catalog.csv',cat)
    print(json.dumps({'records':len(records),'category_domain_quote_spans':quotes,'author_decisions_changed':False}),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('config','csv','pdf-root','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();load(a.config,'classification');load(a.config,'synthesis')
    result=subprocess.run([sys.executable,str(Path(__file__).parent/'run_synthesis.py'),'extract','--config',a.config,'--csv',a.csv,'--pdf-root',a.pdf_root,'--out',a.out])
    if result.returncode:raise SystemExit(result.returncode)
    make_catalog(a.out)
    from paper_sections import run as section_extract
    section_extract(a.out)
if __name__=='__main__':main()
