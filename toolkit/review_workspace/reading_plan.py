"""Configurable reading priorities and separate human brief-check history. No PDF/model access."""
import json, re
from csv_storage import CsvJournal, StorageError
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

class ReadingError(Exception):
    def __init__(self,message,status=400):super().__init__(message);self.status=status

def validate(config):
    if not isinstance(config,dict):raise ValueError('Invalid reading plan')
    groups=config.get('groups',[])
    config={**config,'groups':groups}
    reasons=config.get('reason_choices',[])
    if not isinstance(reasons,list) or len(reasons)>40 or any(not isinstance(r,str) or not r.strip() or ';' in r for r in reasons):raise ValueError('Invalid reading reasons')
    if not isinstance(groups,list) or len(groups)>30:raise ValueError('Invalid reading groups')
    ids=set()
    for g in groups:
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,49}',g.get('id','')) or g['id'] in ids:raise ValueError('Reading group IDs must be unique')
        ids.add(g['id'])
        if not isinstance(g.get('title'),str) or not g['title'].strip():raise ValueError('Reading group title required')
        if g.get('depth') not in ('brief','detailed'):raise ValueError('Reading depth must be brief or detailed')
        conditions=g.get('match',{})
        if not isinstance(conditions,dict) or set(conditions)-{'decision_links','categories_any','categories_exact'}:raise ValueError('Invalid reading group conditions')
        for terms in conditions.values():
            if not isinstance(terms,list) or not terms or any(not isinstance(t,str) or not t.strip() for t in terms):raise ValueError('Reading conditions need nonempty lists of labels')
    return config

def assign(record,config):
    labels={s.strip() for s in record.get('report_categories','').split(';') if s.strip()}
    for i,g in enumerate(config.get('groups',[]),1):
        m=g.get('match',{})
        if 'decision_links' in m and record.get('decision_link','') not in m['decision_links']:continue
        if 'categories_any' in m and not labels.intersection(m['categories_any']):continue
        if 'categories_exact' in m and labels!=set(m['categories_exact']):continue
        return {'reading_priority':i,'reading_group':g['id'],'reading_title':g['title'],'reading_depth':g['depth']}
    return {'reading_priority':999,'reading_group':'unassigned','reading_title':'Unassigned — check manually','reading_depth':'detailed'}

def blank(ident):
    return {'id':ident,'revision':0,'status':'unreviewed','payload':{'note':'','reviewer':'','checked':False},'updated_at':''}

class ReadingPlan:
    def __init__(self,root,project):
        self.root=Path(root);path=self.root/'reading_plan.json'
        self.config=validate(json.loads(path.read_text(encoding='utf8')) if path.exists() else project.get('reading_plan',{'groups':[]}))
        self.enabled=bool(self.config['groups'])
        self.journal=CsvJournal(self.root,'reading') if self.enabled else None

    def rows(self):
        return self.journal.states() if self.enabled else {}

    def get(self,ident):return self.rows().get(ident,blank(ident))

    def save(self,record,raw,revision,status):
        if not self.enabled:raise ReadingError('No reading plan configured')
        if record.get('eligibility')=='exclude':raise ReadingError('This paper is excluded; its earlier reading notes remain available')
        if status not in ('draft','brief_done','detailed_needed','later'):raise ReadingError('Invalid reading status')
        if not isinstance(raw,dict):raise ReadingError('Invalid reading note')
        payload={}
        for key,limit in [('note',6000),('reviewer',160)]:
            v=raw.get(key,'')
            if not isinstance(v,str) or len(v)>limit:raise ReadingError('Invalid reading '+key)
            payload[key]=v.strip()
        reasons=raw.get('reason_choices',[])
        if self.config.get('reason_choices'):
            if not isinstance(reasons,list) or any(r not in self.config['reason_choices'] for r in reasons):raise ReadingError('Choose a configured reading reason')
            payload['reason_choices']=list(dict.fromkeys(reasons));payload['note']='; '.join(payload['reason_choices'])
        payload['checked']=raw.get('checked') is True
        group=assign(record,self.config)
        if status in ('brief_done','detailed_needed'):
            if not payload['checked'] or not payload['reviewer'] or not payload['note']:raise ReadingError('Enter your name, a brief reason and confirm the source check')
        else:payload['checked']=False
        if status=='brief_done' and group['reading_depth']!='brief':raise ReadingError('This group requires detailed extraction')
        payload.update(pdf_sha256=record.get('pdf_sha256'),evidence_sha256=record.get('evidence_sha256'),reading_group=group['reading_group'],categories=record.get('report_categories'),decision_link=record.get('decision_link'))
        stamp=datetime.now(timezone.utc).isoformat();ident=record['record_id']
        try:self.journal.save({'id':ident,'status':status,'payload':payload,'updated_at':stamp},revision)
        except StorageError as e:raise ReadingError(str(e),e.status)
        return self.get(ident)

    def export(self):
        return {'config':self.config,'reviews':list(self.rows().values()),'history':self.journal.history() if self.enabled else []}

    def enrich(self,record,rows):
        group=assign(record,self.config);review=rows.get(record['record_id'],blank(record['record_id']))
        p=review['payload'];stale=review['revision']>0 and any(p.get(k)!=record.get(k) for k in ('pdf_sha256','evidence_sha256','decision_link'))
        # Category changes can change the planned depth; a brief check must not hide a newly detailed paper.
        stale=stale or (review['revision']>0 and p.get('categories')!=record.get('report_categories'))
        return {**record,**group,'reading_status':'needs_recheck' if stale else review['status'],'reading_note':p.get('note',''),'reading_reviewer':p.get('reviewer','')}
