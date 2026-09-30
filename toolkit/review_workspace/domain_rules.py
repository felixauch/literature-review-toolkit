"""Configurable, local passage rules. Suggestions only; no model calls."""
import re
from project_setup import term_pattern

FUTURE=re.compile(r'\b(?:future work|future research|could|might|may|planned|potential|will be|not yet)\b',re.I)
ATTRIBUTED=re.compile(r'\b(?:et al\.|previous studies|prior work|other studies|previously reported)\b',re.I)
OWN=re.compile(r'\b(?:we|our|this (?:study|paper|work))\b',re.I)
NEGATED=re.compile(r'\b(?:no|not|without|neither|never|failed)\b',re.I)

def assess(pages, definitions, windows, config=None, warning=''):
    context=(config or {}).get('context',{})
    result={d['name']:{'suggestion':'uncertain','reason':'No sufficient rule match; assess manually. Absence of a match is not evidence of absence.','evidence':[]} for d in definitions}
    patterns={d['name']:(term_pattern(d.get('terms',[])),term_pattern(d.get('require_any',[])),term_pattern(d.get('exclude_terms',[]))) for d in definitions}
    for page,start,end,raw,section in windows(pages):
        if section in ('references','backmatter') or len(raw.strip())<35:continue
        text=re.sub(r'\s+',' ',raw);cautions=[]
        if context.get('suppress_future',True) and FUTURE.search(text):cautions.append('Future or conditional wording')
        if context.get('suppress_background',True) and section=='background' and not OWN.search(text):cautions.append('Background context')
        if context.get('suppress_attribution',True) and ATTRIBUTED.search(text) and not OWN.search(text):cautions.append('May describe another study')
        if context.get('suppress_negation',True) and NEGATED.search(text):cautions.append('Negation needs human checking')
        for d in definitions:
            name=d['name'];terms,required,excluded=patterns[name];matches=list(dict.fromkeys(m.group(0) for m in terms.finditer(text)))
            if not matches:continue
            why=list(cautions)
            if d.get('require_any') and not required.search(text):why.append('Required context term missing')
            if excluded.search(text):why.append('Configured exclusion term matched')
            if warning:why.append('Source quality/identity requires checking')
            support=not why
            score=8*support+min(len(matches),4)+({'methods':4,'results':4,'abstract':2}.get(section,0))
            ev={'page':page,'start':start,'end':end,'quote':raw,'section':section,'support':support,'terms':matches,'cautions':why,'rank':score}
            assert pages[page-1][start:end]==raw
            result[name]['evidence'].append(ev)
    for d in definitions:
        row=result[d['name']];row['evidence'].sort(key=lambda e:(-e['rank'],e['page'],e['start']))
        has=any(e['support'] for e in row['evidence'])
        row['suggestion']='yes' if has else 'uncertain'
        row['reason']='Configured terms matched in a passage without a detected context warning; check the contribution before accepting.' if has else row['reason']
        if not d.get('terms'):row['reason']='No matching terms configured; assign this label manually.'
        row['evidence']=row['evidence'][:6]
    return result
