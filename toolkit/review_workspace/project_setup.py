"""Interactive project setup. No papers are read and no network is used."""
import argparse, json, re
from pathlib import Path

def validate(config, mode=None):
    if not isinstance(config,dict) or config.get('schema_version')!=1:
        raise ValueError('Project configuration must have schema_version 1.')
    if not isinstance(config.get('name'),str) or not config['name'].strip():
        raise ValueError('Set a project name.')
    for key in ('categories','domains'):
        items=config.get(key,[])
        if not isinstance(items,list) or len(items)>50:raise ValueError('Invalid '+key)
        names=[]
        for item in items:
            name=item.get('name','')
            if not isinstance(name,str) or not name.strip() or len(name)>80 or any(c in name for c in ';|\r\n'):
                raise ValueError('Use nonempty labels (up to 80 characters), without semicolons or line breaks.')
            if name!=name.strip():raise ValueError('Remove surrounding spaces in labels.')
            names.append(name)
            for field in ('terms','require_any','exclude_terms'):
                terms=item.get(field,[])
                if not isinstance(terms,list) or len(terms)>150 or any(not isinstance(t,str) or not t.strip() or len(t)>150 or t.strip('* ')=='' for t in terms):
                    raise ValueError('Invalid terms for '+name)
            if not isinstance(item.get('description',''),str):raise ValueError('Invalid description')
        if len(set(names))!=len(names):raise ValueError('Duplicate '+key)
    if mode in ('classification','review') and not config.get('categories'):raise ValueError('Define at least one category.')
    fields=config.get('fields',[])
    if not isinstance(fields,list) or len(fields)>60:raise ValueError('Invalid extraction fields')
    ids=[]
    for f in fields:
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',f.get('id','')):raise ValueError('Field IDs need lowercase letters, digits or underscores, starting with a letter.')
        ids.append(f['id'])
        from choices import validate_spec
        validate_spec(f)
        for key in ('title','group'):
            if not isinstance(f.get(key),str) or not f[key].strip():raise ValueError('Each field needs title and group.')
        if any(type(f.get(k,False))!=bool for k in ('author','required')):raise ValueError('Field flags must be true/false.')
        if not isinstance(f.get('terms',[]),list) or any(not isinstance(t,str) or not t.strip() or len(t)>150 for t in f.get('terms',[])):raise ValueError('Invalid field terms')
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate field IDs')
    if mode in ('synthesis','review') and not fields:raise ValueError('Define at least one extraction field.')
    notes=config.get('domain_notes',[])
    if not isinstance(notes,list) or len(notes)>20:raise ValueError('Invalid domain note fields')
    if any(not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',f.get('id','')) or not isinstance(f.get('title'),str) or not f['title'].strip() for f in notes):raise ValueError('Domain notes need valid IDs and titles.')
    for f in notes:
        from choices import validate_spec
        validate_spec(f)
    if len({f['id'] for f in notes})!=len(notes):raise ValueError('Duplicate domain note IDs')
    if 'overview_fields' in config and (not isinstance(config['overview_fields'],list) or any(k not in ids for k in config['overview_fields'])):raise ValueError('Overview columns must be configured field IDs.')
    if 'sections' in config:
        sections=config['sections']
        if not isinstance(sections,list) or len(sections)>20:raise ValueError('Invalid section headings')
        section_ids=set()
        for section in sections:
            if not isinstance(section,dict) or not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',section.get('id','')) or section['id'] in section_ids:raise ValueError('Section IDs must be unique, lowercase identifiers.')
            section_ids.add(section['id'])
            if not isinstance(section.get('title'),str) or not section['title'].strip():raise ValueError('Each section needs a title.')
            headings=section.get('headings')
            if not isinstance(headings,list) or not headings or len(headings)>50 or any(not isinstance(h,str) or not h.strip() or len(h)>150 for h in headings):raise ValueError('Each section needs at least one nonempty heading.')
    for key in ('suppress_future','suppress_background','suppress_attribution','suppress_negation'):
        if type(config.get('context',{}).get(key,True))!=bool:raise ValueError('Context switches must be true/false')
    if 'reading_plan' in config:
        from reading_plan import validate as validate_reading
        validate_reading(config['reading_plan'])
        known={item['name'] for item in config.get('categories',[])}
        for group in config['reading_plan'].get('groups',[]):
            for key in ('categories_any','categories_exact'):
                if any(name not in known for name in group.get('match',{}).get(key,[])):
                    raise ValueError('Reading groups must use the category labels configured for this project.')
    return config

def load(path,mode=None):
    return validate(json.loads(Path(path).read_text(encoding='utf-8-sig')),mode)

def term_pattern(terms):
    # Only a trailing * is a stem wildcard; no arbitrary regex or code execution.
    parts=[]
    for raw in terms:
        raw=raw.strip();stem=raw.endswith('*');text=raw[:-1] if stem else raw
        part=re.escape(text).replace(r'\ ',r'\s+')+(r'\w*' if stem else '')
        parts.append(r'(?<!\w)'+part+r'(?!\w)')
    return re.compile('|'.join(parts) if parts else r'(?!)',re.I)

def terms(prompt):return [s.strip() for s in input(prompt).split(';') if s.strip()]
def yes(prompt,default=False):return (input(prompt+(' [Y/n]: ' if default else ' [y/N]: ')).strip().lower() or ('y' if default else 'n')) in ('y','yes')
def setup(mode,path):
    path=Path(path)
    if path.exists():raise FileExistsError('This configuration already exists. Edit it explicitly or choose a new file.')
    c={'schema_version':1,'name':input('Project name: ').strip(),'categories':[],'domains':[],'fields':[],
       'context':dict(suppress_future=True,suppress_background=True,suppress_attribution=True,suppress_negation=True)}
    print('Enter your own labels. No subject labels are supplied. Separate terms with ;. A trailing * matches a word stem.')
    for kind in ('categories','domains'):
        print('\n'+kind.title()+': press Enter at the name prompt to finish.')
        while True:
            name=input('Label name: ').strip()
            if not name:break
            item={'name':name,'description':input('Definition / boundary: ').strip(),
                  'terms':terms('Matching words or phrases (blank = manual assessment): '),
                  'require_any':terms('Also require one of these terms in the same passage (optional): '),
                  'exclude_terms':terms('Suppress matches with these terms in the passage (optional): ')}
            c[kind].append(item)
    if mode in ('synthesis','review') or yes('Configure extraction fields too?'):
        print('\nExtraction fields: press Enter at the ID prompt to finish. You define the fields and groups.')
        while True:
            ident=input('Field ID (e.g. outcome): ').strip()
            if not ident:break
            f=dict(id=ident,title=input('Display title: ').strip(),group=input('Group/tab: ').strip(),hint=input('Guidance: ').strip(),required=yes('Required before confirmation?'),author=yes('Author interpretation rather than source extraction?'))
            f['type']=input('Input type (single / multi / text) [multi]: ').strip().lower() or 'multi'
            if f['type']!='text':
                f['options']=terms('Choices (separate with ;): ')
                f['exclusive_options']=terms('Choices that must stand alone (optional): ')
            f['terms']=[] # Manual source search; no keyword ranking.
            c['fields'].append(f)
        headings=terms('Domain-level synthesis note headings (separate with ;, blank = none): ')
        c['domain_notes']=[]
        for i,title in enumerate(headings):
            item={'id':'note_'+str(i+1),'title':title,'type':input('Input type for '+title+' (multi / single / text) [multi]: ').strip().lower() or 'multi'}
            if item['type']!='text':item['options']=terms('Choices (separate with ;): ')
            c['domain_notes'].append(item)
    if mode in ('synthesis','review') and yes('Set up reading priorities and brief checks?'):
        print('Define groups in reading order. The first matching group wins. These rules change reading depth, not eligibility.')
        print('Available contribution labels: '+ '; '.join(x['name'] for x in c['categories']))
        plan={'groups':[],'reason_choices':[]}
        while True:
            title=input('Reading group title (Enter to finish): ').strip()
            if not title:break
            depth=input('Reading depth (brief / detailed) [detailed]: ').strip().lower() or 'detailed'
            match={}
            links=terms('Match decision_link values from your CSV (optional; separate with ;): ')
            any_categories=terms('Match any of these category labels (optional): ')
            exact_categories=terms('Require exactly this set of category labels (optional): ')
            if links:match['decision_links']=links
            if any_categories:match['categories_any']=any_categories
            if exact_categories:match['categories_exact']=exact_categories
            if not match:print('This is a catch-all group for records not matched above.')
            plan['groups'].append({'id':'priority_'+str(len(plan['groups'])+1),'title':title,'depth':depth,'match':match})
        if any(g['depth']=='brief' for g in plan['groups']):
            while not plan['reason_choices']:
                plan['reason_choices']=terms('Reasons for brief/detailed selection (at least one; separate with ;): ')
        c['reading_plan']=plan
    validate(c,mode);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(c,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print('Saved '+str(path)+'. You can edit this JSON before creating a run. Its full settings are copied into each run.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['classification','synthesis','review'],required=True);p.add_argument('--out',default='project.json');p.add_argument('--check')
    a=p.parse_args()
    if a.check:load(a.check,a.mode);print('Configuration valid.')
    else:setup(a.mode,a.out)
if __name__=='__main__':main()
