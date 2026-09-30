"""Durability and migration tests with synthetic review records only."""
import copy,csv,hashlib,io,json,multiprocessing,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from csv_storage import CsvJournal,StorageError,encode,decode,read_object,write_object,atomic_write
from migrate_legacy import migrate

def worker(root,ready,start,output):
 j=CsvJournal(root,'shared');ready.put(1);start.wait()
 try:j.save({'id':'A','status':'draft','payload':{'note':'worker'}},0);output.put('saved')
 except StorageError:output.put('conflict')

class CSVStorageTests(unittest.TestCase):
 def test_roundtrip_exact(self):
  data=[{'id':'é漢字','empty':'','null':None,'yes':True,'no':False,'n':2,'d':1.25,'list':[{},[],None,'line 1\n"line, 2"'],'a/b~c':{'formula':'=2+2','quote':"'text"}},{}]
  self.assertEqual(decode(encode(data)),data)
 def test_revision_conflict_and_restart(self):
  with tempfile.TemporaryDirectory() as d:
   a=CsvJournal(d,'test');b=CsvJournal(d,'test');a.save({'id':'A','status':'draft','payload':{'value':'first'}},0)
   with self.assertRaises(StorageError):b.save({'id':'A','status':'confirmed'},0)
   b.save({'id':'A','status':'later','payload':{'value':'revised'}},1)
   a.current_path.unlink();again=CsvJournal(d,'test');self.assertEqual(len(again.history()),2);self.assertEqual(again.states()['A']['payload']['value'],'revised');self.assertTrue(again.current_path.exists())
   self.assertEqual(len(decode((Path(d)/'test.backup.csv').read_bytes())),1)
 def test_failed_replace_keeps_original(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'x.csv';atomic_write(p,b'original')
   with patch('csv_storage.os.replace',side_effect=OSError('locked')):
    with self.assertRaises(OSError):atomic_write(p,b'new')
   self.assertEqual(p.read_bytes(),b'original');self.assertEqual(list(Path(d).glob('*.tmp')),[])
 def test_detects_damaged_history(self):
  with tempfile.TemporaryDirectory() as d:
   j=CsvJournal(d,'test');j.save({'id':'A','payload':{'note':'ORIGINAL'}},0)
   j.path.write_bytes(j.path.read_bytes().replace(b'ORIGINAL',b'MODIFIED'))
   with self.assertRaises(StorageError):j.states()
 def test_concurrent_processes(self):
  with tempfile.TemporaryDirectory() as d:
   ctx=multiprocessing.get_context('spawn');ready=ctx.Queue();out=ctx.Queue();start=ctx.Event()
   jobs=[ctx.Process(target=worker,args=(d,ready,start,out)) for _ in range(2)]
   for j in jobs:j.start()
   for _ in jobs:ready.get(timeout=15)
   start.set();results=[out.get(timeout=15) for _ in jobs]
   for j in jobs:j.join(15);self.assertEqual(j.exitcode,0)
   self.assertCountEqual(results,['saved','conflict']);self.assertEqual(len(CsvJournal(d,'shared').history()),1)
 def test_migration_preserves_originals_and_history(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);old=root/'old';old.mkdir();(old/'papers').mkdir();(old/'classification').mkdir()
   paper={'pages':['Synthetic page.'],'evidence':[]};(old/'papers/A.json').write_text(json.dumps(paper));h=hashlib.sha256((old/'papers/A.json').read_bytes()).hexdigest()
   (old/'manifest.json').write_text(json.dumps({'version':'old','records':[{'record_id':'A','evidence_sha256':h}]}))
   (old/'classification/catalog.json').write_text(json.dumps({'records':[]}))
   with sqlite3.connect(old/'extraction.sqlite3') as db:
    db.execute('CREATE TABLE reviews(id TEXT,revision INTEGER,status TEXT,payload TEXT,updated_at TEXT)');db.execute('CREATE TABLE history(event INTEGER,id TEXT,revision INTEGER,status TEXT,payload TEXT,updated_at TEXT)')
    one={'fields':{'outcome':{'value':'first'}},'evidence_sha256':h};two={'fields':{'outcome':{'value':'revised'}},'evidence_sha256':h}
    db.execute('INSERT INTO history VALUES(1,?,?,?,?,?)',('A',1,'draft',json.dumps(one),'time1'));db.execute('INSERT INTO history VALUES(2,?,?,?,?,?)',('A',2,'confirmed',json.dumps(two),'time2'));db.execute('INSERT INTO reviews VALUES(?,?,?,?,?)',('A',2,'confirmed',json.dumps(two),'time2'))
   db.close()
   before={p.relative_to(old):p.read_bytes() for p in old.rglob('*') if p.is_file()}
   result=migrate(old,root/'new');j=CsvJournal(root/'new','extraction');self.assertEqual(j.states()['A']['status'],'confirmed');self.assertEqual(j.states()['A']['payload']['fields'],two['fields']);self.assertEqual(j.history()[0]['payload'],one)
   self.assertEqual(before,{p.relative_to(old):p.read_bytes() for p in old.rglob('*') if p.is_file()});self.assertFalse(list((root/'new').rglob('*.sqlite3')));self.assertEqual(read_object(root/'new/papers/A.csv'),paper)
   with self.assertRaises(ValueError):migrate(old,root/'new')
 def test_archive_preserves_current_and_history(self):
  import zipfile,io
  from csv_storage import archive_records,decode
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);j=CsvJournal(root,'extraction');j.save({'id':'A','status':'draft','payload':{'note':'first'}},0);j.save({'id':'A','status':'confirmed','payload':{'note':'final'}},1)
   (root/'project.json').write_text('{"name":"Test"}');(root/'unrelated.pdf').write_bytes(b'not included')
   with zipfile.ZipFile(io.BytesIO(archive_records(root))) as z:
    self.assertEqual(len(decode(z.read('extraction.csv'))),2)
    self.assertEqual(decode(z.read('extraction_current.csv'))[0]['status'],'confirmed')
    self.assertIn('project.json',z.namelist());self.assertNotIn('unrelated.pdf',z.namelist());self.assertFalse(any(x.endswith('.lock') for x in z.namelist()))
 def test_failed_migration_not_resumable(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);old=root/'old';old.mkdir();(old/'manifest.json').write_text('{broken')
   with self.assertRaises(ValueError):migrate(old,root/'new')
   self.assertFalse((root/'new').exists());self.assertFalse(list(root.glob('.csv-import-*')))

if __name__=='__main__':unittest.main()
