import unittest
from paper_sections import extract_sections
class Sections(unittest.TestCase):
 def test_inline_abstract_and_numbered_conclusions(self):
  pages=['Title\nAbstract: We tested a synthetic measurement.\nKeywords: sensors\n1. Introduction\nBody.', '4. Conclusions\nThe synthetic result supports further testing.\nReferences\nNot part of conclusions.']
  s=extract_sections(pages)
  self.assertEqual(s['abstract']['status'],'found');self.assertEqual(s['conclusion']['status'],'found')
  self.assertNotIn('Keywords',s['abstract']['spans'][0]['quote'])
  for v in s.values():
   for e in v['spans']:self.assertEqual(e['quote'],pages[e['page']-1][e['start']:e['end']])
 def test_structured_abstract_not_main_conclusion(self):
  p=['Abstract\nBackground\nContext.\nMethods\nDesign.\nConclusions\nAbstract conclusion.\n1 Introduction\nMain body.']
  s=extract_sections(p);self.assertIn('Methods',s['abstract']['spans'][0]['quote']);self.assertEqual(s['conclusion']['status'],'not_found')
 def test_combined_and_uncertain(self):
  s=extract_sections(['Methods\nBody.\nDiscussion and conclusions\nA combined section without a later heading.'])
  self.assertTrue(s['conclusion']['combined']);self.assertEqual(s['conclusion']['status'],'uncertain_boundary')
 def test_missing_and_contents(self):
  s=extract_sections(['Contents\nConclusions .......... 10\nSome introductory body without headings.'])
  self.assertEqual(s['conclusion']['status'],'not_found');self.assertEqual(s['abstract']['status'],'not_found')
if __name__=='__main__':unittest.main(verbosity=2)
