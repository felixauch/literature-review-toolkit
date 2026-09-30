from pathlib import Path
import json,tempfile,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
import setup_server as app
class SetupTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  (self.root/'one.pdf').write_bytes(b'%PDF-1.4 test');(self.root/'rows.csv').write_text('record_id,pdf_path\nT1,one.pdf\n')
  self.config={'schema_version':1,'name':'Test','categories':[{'name':'Measurement'}],'domains':[],'fields':[{'id':'setting','title':'Setting','group':'Evidence','type':'single','options':['Lab','Field']}]}
  self.raw=dict(config=self.config,csv=str(self.root/'rows.csv'),pdf_root=str(self.root),out=str(self.root/'run'))
  self.server=app.SetupServer(('127.0.0.1',0));threading.Thread(target=self.server.serve_forever,daemon=True).start();self.url='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.temp.cleanup()
 def request(self,path,headers=None):
  return urllib.request.urlopen(urllib.request.Request(self.url+path,json.dumps(self.raw).encode(),headers={'Content-Type':'application/json','X-Setup-Token':self.server.token,**(headers or {})}),timeout=5)
 def test_valid(self):
  with self.request('/api/check') as r:self.assertEqual(json.load(r)['records'],1)
 def test_missing_and_outside_pdf(self):
  for value in ['../outside.pdf','https://invalid/paper.pdf','absent.pdf']:
   (self.root/'rows.csv').write_text('record_id,pdf_path\nT1,'+value+'\n')
   with self.assertRaises(ValueError):app.preflight(self.raw)
 def test_existing_review(self):
  (self.root/'run').mkdir()
  with self.assertRaises(ValueError):app.preflight(self.raw)
 def test_existing_settings(self):
  (self.root/'run.project.json').write_text('original')
  with self.assertRaises(ValueError):app.preflight(self.raw)
  self.assertEqual((self.root/'run.project.json').read_text(),'original')
 def test_duplicates_and_invalid_choices(self):
  (self.root/'rows.csv').write_text('record_id,pdf_path\nT1,one.pdf\nT1,one.pdf\n')
  with self.assertRaises(ValueError):app.preflight(self.raw)
  self.config['fields'][0]['options']=['Same','Same']
  with self.assertRaises(ValueError):app.validate(self.config,'review')
 def test_origin_host_and_token(self):
  for h in [{'X-Setup-Token':''},{'Origin':'https://invalid'},{'Host':'invalid'},{'Sec-Fetch-Site':'cross-site'}]:
   with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/check',h)
   self.assertEqual(e.exception.code,403)
 def test_no_double_launch(self):
  with patch.object(self.server,'prepare'):
   self.server.begin(self.raw)
   with self.assertRaises(ValueError):self.server.begin(self.raw)
  self.assertEqual(json.loads((self.root/'run.project.json').read_text()),self.config)
 def test_section_validation(self):
  self.config['sections']=[{'id':'conclusion','title':'Conclusions','headings':[]}]
  with self.assertRaises(ValueError):app.validate(self.config,'review')
if __name__=='__main__':unittest.main()
