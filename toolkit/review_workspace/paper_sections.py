from csv_storage import read_object, write_object
"""Extract labelled abstract/conclusion sections locally. No inference model or prose generation."""
import argparse,hashlib,json,re
from pathlib import Path

DEFAULTS=[{'id':'abstract','title':'Abstract','headings':['abstract','summary']},
 {'id':'conclusion','title':'Conclusions','headings':['conclusion','conclusions','concluding remarks','conclusions and future work','conclusion and future work','conclusions and perspectives','discussion and conclusions','results and conclusions']}]
NUMBER=r'(?:(?:\d{1,2}(?:\.\d+)*|[IVX]{1,5})[.)]?\s+)??'
MAJOR=re.compile(r'^\s*(?:(?:\d{1,2}(?:\.\d+)*|[IVX]{1,5})[.)]?\s+)?(?:introduction|background|materials? and methods?|methods?|methodology|results?(?: and discussion)?|discussion|conclusions?|references|bibliography|literature cited|acknowledg\w*|funding|author contributions|declarations?|conflicts? of interest|data availability|appendix.*|supplementary material)\s*[:.]?\s*$',re.I)
ABSTRACT_END=re.compile(r'^\s*(?:(?:\d{1,2}|[IVX]{1,5})[.)]?\s+)?(?:key\s*words?|index terms|introduction)\b',re.I)

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def lines(pages):
    output=[]
    for page,text in enumerate(pages,1):
        offset=0
        for line in text.splitlines(keepends=True):output.append((page,offset,offset+len(line),line));offset+=len(line)
    return output

def extract_sections(pages,specs=None):
    specs=specs or DEFAULTS;ls=lines(pages);answer={};abstract_range=None
    for spec in sorted(specs,key=lambda s:s['id']!='abstract'):
        names=sorted(spec['headings'],key=len,reverse=True)
        pattern=re.compile(r'^\s*'+NUMBER+r'(?P<heading>'+ '|'.join(re.escape(n) for n in names)+r')(?P<sep>\s*[:.\-–—]\s*|\s*$)',re.I)
        candidates=[]
        for i,(page,start,end,line) in enumerate(ls):
            match=pattern.match(line.rstrip('\r\n'))
            if not match or re.search(r'\.{3,}\s*\d+\s*$',line):continue
            if spec['id']=='abstract' and page>3:continue
            if spec['id']!='abstract' and abstract_range and abstract_range[0]<=i<abstract_range[1]:continue
            candidates.append((i,match))
        empty={'id':spec['id'],'title':spec['title'],'status':'not_found','note':'No dependable matching heading found. Read the PDF; the section may be unlabelled, scanned or use another heading.','spans':[]}
        if not candidates:answer[spec['id']]=empty;continue
        i,match=candidates[0] if spec['id']=='abstract' else candidates[-1]
        start_page,start_offset,_,line=ls[i];start_offset+=match.end();heading=match.group('heading')
        stop=None
        for j in range(i+1,len(ls)):
            text=ls[j][3].strip()
            if spec['id']=='abstract':
                boundary=bool(ABSTRACT_END.match(text))
            else:boundary=bool(MAJOR.match(text)) or bool(re.fullmatch(r'\s*\d{1,2}[.)]?\s+[A-Z][^.!?\n]{1,65}',text))
            if boundary:stop=j;break
        status='found';note='Detected heading and following section boundary; verify PDF reading order.'
        if stop is None:
            # Never silently label the remainder of a document as a complete abstract/conclusion.
            stop=next((j for j in range(i+1,len(ls)) if ls[j][0]>start_page+(1 if spec['id']=='abstract' else 3)),len(ls))
            status='uncertain_boundary';note='No clear following section boundary. This bounded excerpt may be incomplete or include unrelated text.'
        end_page,end_offset=(ls[stop][0],ls[stop][1]) if stop<len(ls) else (len(pages),len(pages[-1]) if pages else 0)
        if spec['id']=='abstract':abstract_range=(i,stop)
        spans=[];size=0
        for page in range(start_page,end_page+1):
            a=start_offset if page==start_page else 0;b=end_offset if page==end_page else len(pages[page-1]);raw=pages[page-1]
            while a<b and raw[a].isspace():a+=1
            while b>a and raw[b-1].isspace():b-=1
            if b<=a:continue
            if size+b-a>24000:
                b=a+max(0,24000-size);status='truncated';note='Section exceeded the extraction limit. Read the complete PDF section.'
            if b>a:spans.append({'page':page,'start':a,'end':b,'quote':raw[a:b]});size+=b-a
            if size>=24000:break
        if not spans:answer[spec['id']]={**empty,'status':'empty','note':'A heading was found, but no body text was extracted.'};continue
        combined=bool(re.search(r'discussion|results',heading,re.I))
        if combined:note='Combined '+heading+' section, not conclusions alone. '+note
        if len(candidates)>1:note+=' Multiple matching headings were found; check the selected occurrence.'
        answer[spec['id']]={'id':spec['id'],'title':spec['title'],'heading':heading,'status':status,'combined':combined,'note':note,'spans':spans}
    return answer

def run(run_path):
    root=Path(run_path);manifest=read_object(root/'manifest.csv');out=root/'paper_sections';out.mkdir(exist_ok=True);counts={}
    specs=manifest.get('project',{}).get('sections',DEFAULTS)
    for r in manifest['records']:
        source=root/'papers'/f"{r['record_id']}.csv"
        if sha(source)!=r['evidence_sha256']:raise ValueError('Stored extraction changed.')
        data=read_object(source);sections=extract_sections(data['pages'],specs)
        for section in sections.values():
            key=section['id']+':'+section['status'];counts[key]=counts.get(key,0)+1
            for e in section['spans']:assert data['pages'][e['page']-1][e['start']:e['end']]==e['quote']
        result={'record_id':r['record_id'],'pdf_sha256':r['pdf_sha256'],'evidence_sha256':r['evidence_sha256'],'method':'heading boundaries; local Python only','sections':sections}
        path=out/f"{r['record_id']}.csv";write_object(path,result)
    summary={'records':len(manifest['records']),'status_counts':counts,'runtime_llm_calls':False}
    write_object(out/'coverage.csv',summary);print(json.dumps(summary));return summary
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);a=p.parse_args();run(a.run)
