"""Check that acceptance summaries remain traceable to actual raw evidence."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'Docs/evidence'


class DeliveryRecords(unittest.TestCase):
    def read(self,name):
        return json.loads((EVIDENCE/name).read_text(encoding='utf-8-sig'))

    def test_performance_percentile_and_raw_sample_counts(self):
        value=self.read('t33-delivery.json')
        self.assertEqual(value['dataset'],{'members':20,'slots':15,'tasks':200})
        self.assertEqual(value['result'],'passed')
        for row in value['measurements'].values():
            self.assertEqual(len(row['milliseconds']),30)
            self.assertEqual(sorted(row['milliseconds'])[28],row['p95_ms'])
            self.assertLessEqual(row['p95_ms'],row['target_ms'])
            self.assertEqual(row['http_errors'],0)
        self.assertTrue(value['restart']['all_table_rows_equal'])
        self.assertTrue(value['restore']['old_session_rejected'])
        self.assertEqual(value['restore']['row_counts']['tasks'],200)

    def test_two_real_browser_reports_use_same_suites(self):
        chrome=self.read('t32-chrome.json');edge=self.read('t32-msedge.json')
        self.assertEqual(chrome['suites'],edge['suites'])
        self.assertEqual(len(chrome['suites']),9)
        for row in [chrome,edge]:
            self.assertEqual(row['result'],'passed')
            self.assertFalse(row['human_review'])
            self.assertTrue(row['version'])

    def test_clean_install_reports_and_four_account_automation(self):
        self.assertEqual(self.read('t34-install.json')['result'],'passed')
        self.assertEqual(self.read('t34-frontend-install.json')['result'],'passed')
        row=self.read('t36-e2e.json')
        self.assertEqual(row['result'],'passed')
        self.assertEqual(row['independent_browser_contexts'],4)
        self.assertEqual((row['candidates'],row['submissions'],row['meetings'],row['tasks']),(3,4,1,2))
        self.assertFalse(row['human_usability'])


if __name__=='__main__':unittest.main()
