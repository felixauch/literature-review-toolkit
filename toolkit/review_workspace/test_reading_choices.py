"""Synthetic tests for reading depth, structured codes and preservation of older notes."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from csv_storage import read_object,write_object
from reading_plan import ReadingPlan,ReadingError,assign,validate
from choices import selection,validate_spec
from test_configurable import make,PROJECT,ROOT

PLAN={'groups':[
 {'id':'use','title':'In use','depth':'detailed','match':{'decision_links':['operating']}},
 {'id':'tools','title':'Information tools','depth':'detailed','match':{'categories_any':['Material testing']}},
 {'id':'models','title':'Models','depth':'brief','match':{'categories_exact':['Thermal simulation']}}
]}

class ReadingChoices(unittest.TestCase):
 def test_setup_custom_topic_choices_and_priorities(self):
  from unittest.mock import patch
  from project_setup import setup
  answers=['Coastal flood review',
   'Flood modelling','Models of flooding','flood; simulation','','','',
   'Coast','Coastal locations','coast*','','','',
   'setting','Evaluation','Evidence','Choose the reported setting','y','n','single','Simulation; Field observations','','',
   'Evidence gaps','multi','Data; Transferability',
   'y','Field-focused','detailed','field','','','Other work','brief','','Flood modelling','','',
   'Independent test; Needs source check']
  with tempfile.TemporaryDirectory() as d:
   target=Path(d)/'project.json'
   with patch('builtins.input',side_effect=answers),patch('builtins.print'):setup('review',target)
   p=json.loads(target.read_text())
   self.assertEqual(p['name'],'Coastal flood review')
   self.assertEqual(p['fields'][0]['options'],['Simulation','Field observations'])
   self.assertEqual(len(p['fields']),1)
   self.assertEqual(len(p['reading_plan']['groups']),2)
   self.assertEqual(p['reading_plan']['groups'][1]['depth'],'brief')
   self.assertEqual(p['domain_notes'][0]['options'],['Data','Transferability'])

 def test_groups_overlap_order_and_fallback(self):
  validate(PLAN)
  self.assertEqual(assign({'decision_link':'operating','report_categories':'Thermal simulation'},PLAN)['reading_group'],'use')
  self.assertEqual(assign({'report_categories':'Material testing; Thermal simulation'},PLAN)['reading_group'],'tools')
  self.assertEqual(assign({'report_categories':'Thermal simulation'},PLAN)['reading_depth'],'brief')
  self.assertEqual(assign({'report_categories':'Other'},PLAN)['reading_group'],'unassigned')

 def test_separate_status_conflicts_and_recheck(self):
  with tempfile.TemporaryDirectory() as d:
   plan=ReadingPlan(d,{'reading_plan':PLAN});r={'record_id':'TEST001','report_categories':'Thermal simulation','decision_link':'measurement','pdf_sha256':'a','evidence_sha256':'b'}
   with self.assertRaises(ReadingError):plan.save(r,{'note':'Read','reviewer':'','checked':True},0,'brief_done')
   saved=plan.save(r,{'note':'Comparable example','reviewer':'Tester','checked':True},0,'brief_done');self.assertEqual(saved['status'],'brief_done')
   with self.assertRaises(ReadingError):plan.save(r,{},0,'draft')
   changed={**r,'report_categories':'Material testing'}
   self.assertEqual(plan.enrich(changed,plan.rows())['reading_status'],'needs_recheck')
   with self.assertRaises(ReadingError):plan.save(changed,{'note':'Read','reviewer':'Tester','checked':True},1,'brief_done')
   self.assertEqual(len(plan.export()['history']),1)

 def test_choice_validation(self):
  spec={'type':'multi','options':['Bench','Field','Neither'],'exclusive_options':['Neither']};validate_spec(spec)
  self.assertEqual(selection(spec,['Field','Bench']),['Bench','Field'])
  for value in [['Invented'],['Neither','Field'],['Bench','Bench']]:
   with self.assertRaises(ValueError):selection(spec,value)
  with self.assertRaises(ValueError):selection({**spec,'type':'single'},['Bench','Field'])

 def test_old_notes_preserved_and_choices_exported(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);cfg,source=make(root);run=root/'run'
   result=subprocess.run([sys.executable,str(ROOT/'prepare_review.py'),'--config',str(cfg),'--csv',str(source),'--pdf-root',str(root),'--out',str(run)],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stderr)
   from synthesis.store import Store,ReviewError
   store=Store(run);payload=store.review('TEST001')['payload'];payload['fields']['outcome'].update(value='Preserve this exact author note.',state='recorded',pages='1');store.save('TEST001',payload,0,'draft')
   before=(run/'extraction.csv').read_bytes()
   manifest=read_object(run/'manifest.csv');manifest['project']['fields']=[{'id':'setting','title':'Setting','group':'Context','type':'single','options':['Bench','Field'],'required':True}]
   manifest['project']['domain_notes']=[{'id':'connections','title':'Connections','type':'multi','options':['Thermal','Materials']}]
   write_object(run/'manifest.csv',manifest)
   store=Store(run);review=store.review('TEST001');self.assertEqual(review['payload']['legacy_fields']['outcome']['value'],'Preserve this exact author note.')
   self.assertEqual((run/'extraction.csv').read_bytes(),before)
   p=review['payload'];p.update(reviewer='Tester',verified=True);p['fields']['setting'].update(state='recorded',choices=['Field'],pages='1')
   saved=store.save('TEST001',p,1,'confirmed');self.assertEqual(saved['payload']['fields']['setting']['value'],'Field');self.assertIn('legacy_fields',saved['payload'])
   bad=copy.deepcopy(p);bad['fields']['setting']['choices']=['Invented']
   with self.assertRaises(ReviewError):store.save('TEST001',bad,2,'confirmed')
   store.save_domain('Buildings',{'connections':['Thermal']},0)
   with self.assertRaises(ReviewError):store.save_domain('Buildings',{'connections':['Invented']},1)
   self.assertIn('reading_status',store.csv_export());self.assertIn('Field',store.csv_export())
   self.assertEqual(len(store.export()['review_history']),2)

if __name__=='__main__':unittest.main()
