"""Synthetic unrelated-topic tests. No research papers are used."""
from pathlib import Path
import csv,io,json,subprocess,sys,tempfile,unittest,copy
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from project_setup import validate,term_pattern
from domain_rules import assess
from passages import windows

PROJECT={'schema_version':1,'name':'Synthetic building review','categories':[
 {'name':'Thermal simulation','description':'Reported modelling work','terms':['heat simulation'],'require_any':['tested'],'exclude_terms':[]},
 {'name':'Material testing','description':'Reported material testing','terms':['specimen testing']}],
 'domains':[{'name':'Buildings','terms':['building*'],'require_any':['heat*']},{'name':'Transport','terms':['railway*']}],
 'fields':[{'id':'outcome','group':'Study evidence','title':'Measured outcome','hint':'Report the units and conditions.','required':True,'terms':['temperature']},
 {'id':'reflection','group':'My interpretation','title':'My reflection','author':True,'terms':[]}],
 'domain_notes':[{'id':'connections','title':'Connections to other findings'}]}
TEXT='We tested a heat simulation for buildings and measured the temperature with sensors. '
FILL='The controlled experiment documented the measurements and the comparison conditions. '
def make(root):
 from reportlab.pdfgen.canvas import Canvas
 p=root/'synthetic.pdf';c=Canvas(str(p));t=c.beginText(35,790);t.setFont('Helvetica',10)
 for line in ['Methods',TEXT]+[FILL]*12:t.textLine(line)
 c.drawText(t);c.save()
 config=root/'project.json';config.write_text(json.dumps(PROJECT),encoding='utf8')
 source=root/'records.csv'
 with source.open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=['record_id','title','pdf_path','report_categories','report_primary_domain','report_core_domains','decision_link']);w.writeheader()
  w.writerow(dict(record_id='TEST001',title='Synthetic building review',pdf_path='synthetic.pdf',report_categories='Thermal simulation',report_primary_domain='Buildings',report_core_domains='Buildings',decision_link=''))
 return config,source

class Configuration(unittest.TestCase):
 def test_configuration(self):
  validate(PROJECT,'classification');validate(PROJECT,'synthesis')
  with self.assertRaises(ValueError):validate({'schema_version':1,'name':'Empty','categories':[]},'classification')
  with self.assertRaises(ValueError):validate({'schema_version':1,'name':'Empty','fields':[]},'synthesis')
 def test_terms_are_literal_and_stems(self):
  self.assertTrue(term_pattern(['build*']).search('buildings'))
  self.assertFalse(term_pattern(['heat']).search('wheat'))
  self.assertTrue(term_pattern(['a+b']).search('a+b'))
 def test_multiple_labels_and_exact_evidence(self):
  pages=['Methods\n'+TEXT+' We performed specimen testing for a railway station.']
  rows=assess(pages,PROJECT['categories'],windows,PROJECT)
  self.assertEqual([v['suggestion'] for v in rows.values()],['yes','yes'])
  for v in rows.values():
   for e in v['evidence']:self.assertEqual(e['quote'],pages[e['page']-1][e['start']:e['end']])
 def test_context_and_absence(self):
  for content in ['In future work we could test a heat simulation.','We have not tested a heat simulation.','Other studies tested a heat simulation.']:
   rows=assess(['Introduction\n'+content],PROJECT['categories'],windows,PROJECT)
   self.assertEqual(rows['Thermal simulation']['suggestion'],'uncertain')
  self.assertEqual(assess(['Methods\n'+TEXT],PROJECT['domains'],windows,PROJECT)['Transport']['suggestion'],'uncertain')
 def test_references_and_warning(self):
  rows=assess(['References\n'+TEXT],PROJECT['domains'],windows,PROJECT)
  self.assertFalse(rows['Buildings']['evidence'])
  rows=assess(['Methods\n'+TEXT],PROJECT['domains'],windows,PROJECT,'Source mismatch')
  self.assertEqual(rows['Buildings']['suggestion'],'uncertain')
 def test_guard(self):
  module='classify' if (ROOT/'classify.py').exists() else 'synthesis.extract'
  symbol='guard' if module=='classify' else 'offline_guard'
  code=f'''import socket,subprocess,sys
from {module} import {symbol}
sys.addaudithook({symbol})
for fn in [lambda:socket.getaddrinfo('example.invalid',443),lambda:subprocess.run([sys.executable,'-c','pass'])]:
 try:fn()
 except RuntimeError:pass
 else:raise AssertionError('Operation was not blocked')
'''
  r=subprocess.run([sys.executable,'-c',code],cwd=ROOT,capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)

class Integration(unittest.TestCase):
 def test_new_project_review_export(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);config,source=make(root);original=source.read_bytes();run=root/'run'
   classification=(ROOT/'classify.py').exists()
   cmd=[sys.executable,str(ROOT/'classify.py')] if classification else [sys.executable,str(ROOT/'run_synthesis.py'),'extract']
   cmd+=['--config',str(config),'--csv',str(source),'--pdf-root',str(root),'--out',str(run)]
   r=subprocess.run(cmd,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr)
   self.assertEqual(source.read_bytes(),original)
   again=subprocess.run(cmd,capture_output=True,text=True);self.assertNotEqual(again.returncode,0)
   if classification:
    import reclassification as app
    store=app.ReviewStore(root,run);data=store.load();record=data['records'][0]
    self.assertEqual(data['categories'],['Thermal simulation','Material testing'])
    self.assertEqual(record['domain_proposals']['Buildings']['suggestion'],'yes')
    d={'review_scope':'categories_domains','labels':{'Thermal simulation':'yes','Material testing':'no'},'reviewer':'Tester','evidence_checked':True,
      'domains':{'primary':'Buildings','core':['Buildings'],'secondary':[],'reviewed':True,'note':''}}
    payload={'record_id':'TEST001','revision':0,'proposal_hash':record['proposal_hash'],'action':'confirm','decision':d}
    saved=store.save(payload);self.assertEqual(saved['status'],'confirmed')
    with self.assertRaises(app.ReviewError):store.save(payload)
    out=list(csv.DictReader(io.StringIO(store.export('corpus')[0].decode('utf-8-sig'))))
    self.assertEqual(out[0]['report_core_domains'],'Buildings');self.assertEqual(out[0]['report_categories'],'Thermal simulation')
    d['domains'].update(primary='Transport',core=['Transport'],reviewed=False)
    payload.update(revision=1,action='draft');self.assertEqual(store.save(payload)['status'],'draft')
    self.assertEqual(store.load()['records'][0]['domain_assignment']['core'],['Transport'])
    with self.assertRaises(app.ReviewError):store.export('corpus')
    self.assertEqual(len(store.history('TEST001')),2)
   else:
    from synthesis.store import Store,ReviewError
    store=Store(run);r=store.review('TEST001');d=r['payload'];d.update(reviewer='Tester',verified=True)
    from synthesis.engine import search
    e=search(store.paper('TEST001')['pages'],'temperature')[0]
    self.assertEqual(store.paper('TEST001')['candidates'],{})
    d['fields']['outcome'].update(state='recorded',value='A synthetic measurement.',evidence=[e])
    saved=store.save('TEST001',d,0,'confirmed');self.assertEqual(saved['status'],'confirmed')
    with self.assertRaises(ReviewError):store.save('TEST001',d,0,'draft')
    note=store.save_domain('Buildings',{'connections':'My synthetic note'},0);self.assertEqual(note['revision'],1)
    self.assertIn('outcome_state',store.csv_export());self.assertNotIn('adoption_state',store.csv_export())
    bad=copy.deepcopy(d);bad['fields']['outcome']['evidence'][0]['quote']='invented'
    with self.assertRaises(ReviewError):store.save('TEST001',bad,1,'draft')
   self.assertEqual(source.read_bytes(),original)

if __name__=='__main__':unittest.main(verbosity=2)
