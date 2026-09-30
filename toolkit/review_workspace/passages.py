import re, hashlib, unicodedata
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

