"""Synthetic export-boundary tests; no research papers or network requests."""
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from classification_store import ReviewStore, ReviewError
from csv_storage import write_object


def rows(body):
    return list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'))))


class ConfirmedExports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'records.csv'
        self.source.write_text('record_id,title\nT1,Demo one\nT2,Demo two\nT3,Demo three\n', encoding='utf8')
        self.original = self.source.read_bytes()
        storage = self.root / 'classification'
        storage.mkdir()
        records = []
        for rid in ('T1', 'T2', 'T3'):
            pdf = self.root / (rid + '.pdf')
            pdf.write_bytes(b'%PDF-1.4\nSynthetic hash-only fixture, not a research paper.\n')
            records.append(dict(record_id=rid, title='Demo ' + rid, doi='', pdf_path=str(pdf),
                                pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                proposal_hash='proposal-' + rid, proposal={'decision': {'labels': {'A': 'yes', 'B': 'uncertain'}}}))
        catalog = dict(schema_version=1, source_csv=str(self.source),
                       source_csv_sha256=hashlib.sha256(self.original).hexdigest(),
                       categories=['A', 'B'], domains=['Region'], records=records, rules={})
        write_object(storage/'catalog.csv',catalog)
        self.store = ReviewStore(self.root, storage)

    def save(self, rid, action='confirm', labels=None):
        prior = self.store.states().get(rid)
        labels = labels or {'A': 'no', 'B': 'yes'}
        decision = dict(review_scope='categories_domains', labels=labels, reviewer='Test reviewer', evidence_checked=True,
                        domains=dict(primary='Region', core=['Region'], secondary=[], reviewed=True, note=''))
        return self.store.save(dict(record_id=rid, action=action, revision=prior['revision'] if prior else 0,
                                    proposal_hash='proposal-' + rid, decision=decision))

    def complete(self):
        self.save('T1')
        self.save('T2', labels={'A': 'yes', 'B': 'yes'})
        self.save('T3', labels={'A': 'no', 'B': 'no'})

    def test_pending_never_becomes_final_or_silently_disappears(self):
        self.save('T1')
        self.save('T2', action='draft')
        pending = rows(self.store.export('pending')[0])
        self.assertEqual([(r['record_id'], r['review_status']) for r in pending], [('T2', 'draft'), ('T3', 'unreviewed')])
        self.assertTrue(all(r['reason'] for r in pending))
        for kind in ('corpus', 'final'):
            with self.assertRaisesRegex(ReviewError, '2 paper.*T2, T3'):
                self.store.export(kind)
        self.save('T3', action='flag')
        self.assertEqual(rows(self.store.export('pending')[0])[-1]['review_status'], 'needs_clarification')
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_export_uses_confirmed_choices_and_preserves_overlap(self):
        self.complete()
        self.assertEqual(rows(self.store.export('pending')[0]), [])
        exported = rows(self.store.export('corpus')[0])
        self.assertEqual([(r['record_id'], r['report_categories']) for r in exported], [('T1', 'B'), ('T2', 'A; B')])
        self.assertTrue(all(r['classification_status'] == 'confirmed' and r['classification_reviewer'] == 'Test reviewer' and r['classification_reviewed_at'] for r in exported))
        snapshot = json.loads(self.store.export('final')[0])
        self.assertEqual([r['record_id'] for r in snapshot['excluded']], ['T3'])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_changed_pdf_blocks_previously_confirmed_exports(self):
        self.complete()
        (self.root / 'T1.pdf').write_bytes(b'changed fixture')
        pending = rows(self.store.export('pending')[0])
        self.assertEqual([r['record_id'] for r in pending], ['T1'])
        self.assertIn('PDF changed', pending[0]['reason'])
        for kind in ('corpus', 'final'):
            with self.assertRaisesRegex(ReviewError, 'T1'):
                self.store.export(kind)

    def test_confirmed_export_retains_source_output_labels(self):
        self.source.write_text('record_id,title,output_label\nT1,Demo one,Advisory\nT2,Demo two,Informational\nT3,Demo three,Executive\n', encoding='utf8')
        catalog = self.store.catalog()
        catalog['source_csv_sha256'] = hashlib.sha256(self.source.read_bytes()).hexdigest()
        write_object(self.store.catalog_path, catalog)
        self.complete()
        exported = rows(self.store.export('corpus')[0])
        self.assertEqual([(r['record_id'], r['output_label']) for r in exported], [('T1', 'Advisory'), ('T2', 'Informational')])
        self.assertEqual(self.store.states()['T2']['payload']['preserved_assessment']['output_label'], 'Informational')

    def test_changed_source_and_unchecked_domains_block_export(self):
        self.complete()
        state=self.store.states()['T1']
        state['payload']['domains']['reviewed']=False
        self.store.journal.save(state,state['revision'])
        self.assertIn('domain assignments', rows(self.store.export('pending')[0])[0]['reason'])
        with self.assertRaises(ReviewError):
            self.store.export('corpus')
        self.source.write_bytes(self.original + b'\n')
        self.assertEqual(len(rows(self.store.export('pending')[0])), 3)
        with self.assertRaises(ReviewError):
            self.store.export('final')


class EarlierReports(unittest.TestCase):
    def test_draft_and_fallback_labels_cannot_overwrite_final_file(self):
        package = ROOT.parents[1]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = json.loads((package / 'projects/_template/project.json').read_text(encoding='utf8'))
            config['name'] = 'Synthetic export check'
            (root / 'project.json').write_text(json.dumps(config), encoding='utf8')
            (root / 'title_screening.csv').write_text('record_id,title\nT1,Demo one\nT2,Demo two\nT3,Demo three\n', encoding='utf8')
            (root / 'fulltext_recommendations.csv').write_text('record_id,fulltext_final_decision\nT1,Include\nT2,Include\nT3,Exclude\n', encoding='utf8')
            (root / 'corpus_assessment.csv').write_text('record_id,assess_domains,assess_tier\nT1,Demo region,Proposed category\n', encoding='utf8')
            final = root / 'final_corpus_included.csv'
            final.write_text('Preserved historical export\n', encoding='utf8')
            result = subprocess.run([sys.executable, str(ROOT.parent / 'build_overview.py'), '--project', str(root)], capture_output=True, text=True, encoding='utf8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            exported = rows((root / 'screening_corpus_draft.csv').read_bytes())
            self.assertEqual([r['record_id'] for r in exported], ['T1', 'T2'])
            self.assertTrue(all(r['classification_status'] == 'unconfirmed' for r in exported))
            self.assertEqual(final.read_text(), 'Preserved historical export\n')
            self.assertFalse((root / 'corpus_overview.md').exists())
            self.assertIn('provisional', (root / 'screening_overview_draft.md').read_text(encoding='utf8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
