"""Submission document traceability and worked-example checks, not product tests."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'Docs'


class RequirementsDocumentTests(unittest.TestCase):
    def test_local_document_links_resolve(self):
        for name in ('09-需求分析文档.md', '10-AI协作记录.md', '11-人工核实说明.md'):
            path = DOCS / name
            body = path.read_text(encoding='utf-8-sig')
            for target in re.findall(r'\]\(([^)]+)\)', body):
                if not target.startswith(('http://', 'https://', '#')):
                    self.assertTrue((path.parent / target).is_file(), target)

    def test_all_core_requirements_have_existing_acceptance_rows(self):
        body = (DOCS / '09-需求分析文档.md').read_text(encoding='utf-8-sig')
        requirements = re.findall(r'^\| (MF-\d+) \| .*? \| P0 \| .*? \| (AC-\d+) \|$', body, re.M)
        self.assertEqual(len(requirements), 13)
        for requirement, acceptance in requirements:
            row = re.search(rf'^\| {acceptance} \| ([^|]+) \|', body, re.M)
            self.assertIsNotNone(row, acceptance)
            self.assertIn(requirement, row.group(1), requirement)

    def test_worked_scores_and_ranking(self):
        # Parse the actual published example; independently calculate its scores.
        body = (DOCS / '09-需求分析文档.md').read_text(encoding='utf-8-sig')
        rows = re.findall(r'^\| (T[123]) \| (.+) \|$', body, re.M)
        self.assertEqual(len(rows), 3)
        values = {'有空': 2, '勉强': 1, '没空': -2, '未填': 0}
        evaluated = []
        for slot, rest in rows:
            fields = [item.strip() for item in rest.split('|')]
            votes = fields[:4]
            base = sum(weight * values[vote] for weight, vote in zip((3, 3, 1, 1), votes))
            conflicts = votes[:2].count('没空')
            missing = votes.count('未填')
            score = base - 20 * conflicts - 2 * missing
            self.assertEqual(list(map(int, fields[4:8])), [base, conflicts, missing, score])
            evaluated.append(((conflicts, -score, -votes.count('有空'), slot), slot, int(fields[8])))
        ranked = sorted(evaluated)
        self.assertEqual([r[1] for r in ranked], ['T1', 'T3', 'T2'])
        self.assertEqual([r[2] for r in ranked], [1, 2, 3])

    def test_human_verification_is_not_claimed_complete(self):
        body = (DOCS / '11-人工核实说明.md').read_text(encoding='utf-8-sig')
        rows = re.findall(r'^\| (H-\d+) \| (.+) \|$', body, re.M)
        self.assertEqual(len(rows), 10)
        for key, rest in rows:
            self.assertIn('待', rest.split('|')[3], key)
        self.assertIn('待验证状态', body)

    def test_nabcd_is_connected_to_requirements(self):
        body = (DOCS / '09-需求分析文档.md').read_text(encoding='utf-8-sig')
        nabcd = (DOCS / '02-NABCD分析.md').read_text(encoding='utf-8-sig')
        for term in ('Need', 'Approach', 'Benefit', 'Competitors', 'Delivery'):
            self.assertIn(term, body)
            self.assertIn(term, nabcd)
        self.assertIn('从NABCD到需求的映射', body)
        self.assertEqual(body.count('https://github.com/'), 1)

    def test_project_voice_and_real_revision_record(self):
        for name in ('09-需求分析文档.md', '10-AI协作记录.md', '11-人工核实说明.md'):
            body = (DOCS / name).read_text(encoding='utf-8-sig')
            for phrase in ('请在正式提交时填写', '本人须', '提交前须', '不得伪填', '待本人填写', '内部分析重点的可复用表达', '本次仅成功读取首页'):
                self.assertNotIn(phrase, body)
        record = (DOCS / '10-AI协作记录.md').read_text(encoding='utf-8-sig')
        self.assertIn('第2轮', record)
        self.assertIn('不能出现你对于自己的提示', record)


if __name__ == '__main__':
    unittest.main()
