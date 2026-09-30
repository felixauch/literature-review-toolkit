"""Deterministic passage retrieval. Does not interpret findings or fill author fields."""
from __future__ import annotations
import re, hashlib, unicodedata
from .schema import FIELD_MAP

def configure(project):pass

def display(text):
    # Matching/display only. Stored quote offsets always refer to untouched extraction.
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()

def heading(line):
    s = re.sub(r'^\s*\d+(?:\.\d+)*[.)]?\s*', '', display(line)).lower().strip(': .')
    for kind, pattern in [
      ('references', r'references|bibliography|literature cited'),
      ('abstract', r'abstract'), ('background', r'introduction|background|related work'),
      ('methods', r'materials? and methods?|methods?|methodology|experimental (?:setup|design)|system (?:design|architecture)'),
      ('results', r'results?(?: and discussion)?|evaluation|experimental results?'),
      ('discussion', r'discussion|conclusions?(?: and future work)?|limitations?'),
      ('backmatter', r'acknowledg\w*|author contributions|funding|conflicts? of interest|data availability'),
      ('appendix', r'appendix.*|supplementary (?:material|information).*')]:
        if re.fullmatch(pattern, s): return kind
    return None

def windows(pages):
    section='unknown'
    for page_no, page in enumerate(pages,1):
        cursor=0; start=None
        for line in page.splitlines(keepends=True)+['\n']:
            h=heading(line)
            if (not line.strip() or h) and start is not None:
                end=cursor
                while start<end and page[start].isspace(): start+=1
                while end>start and page[end-1].isspace(): end-=1
                body=page[start:end]
                if len(body)>950:
                    spans=list(re.finditer(r'.+?(?:[.!?](?=\s|$)|$)', body, re.S))
                    block=0
                    for i,m in enumerate(spans):
                        if m.end()-block>=650 or i==len(spans)-1:
                            # Extremely long table/paragraph: bounded overlapping raw chunks.
                            a=start+block; b=start+m.end()
                            while a<b:
                                z=min(a+1600,b)
                                yield page_no,a,z,page[a:z],section
                                if z==b:break
                                a=z-150
                            block=m.end()
                elif body: yield page_no,start,end,body,section
                start=None
            if h:section=h
            elif line.strip() and start is None:start=cursor
            cursor+=len(line)

def evidence_id(page,start,end,quote):
    return 'E'+hashlib.sha256(f'{page}:{start}:{end}:{quote}'.encode()).hexdigest()[:18]

def make_evidence(page,start,end,quote,section='search'):
    return dict(id=evidence_id(page,start,end,quote),page=page,start=start,end=end,quote=quote,section=section)

def retrieve(pages):
    flags=[]
    low=[i+1 for i,p in enumerate(pages) if len(display(p))<80]
    if low:flags.append('Little extractable text on PDF pages '+', '.join(map(str,low))+'. Read figures, tables and scans in the original PDF.')
    if sum(map(len,pages))<1000:flags.append('Very little extracted text; no OCR was applied.')
    return {'evidence':{},'candidates':{},'warnings':flags}

def search(pages, query, limit=50):
    # Literal search, not regex and no external service.
    if not isinstance(query,str) or not 2<=len(query.strip())<=120:return []
    pattern=re.compile(re.escape(query.strip()),re.I); results=[]
    for i,page in enumerate(pages,1):
        last_end=-1
        for hit in pattern.finditer(page):
            if hit.start()<last_end:continue
            start=max(0,hit.start()-260);end=min(len(page),hit.end()+480)
            results.append(make_evidence(i,start,end,page[start:end]));last_end=end
            if len(results)>=limit:return results
    return results
