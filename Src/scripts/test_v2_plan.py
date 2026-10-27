"""Validate review-plan task references and local document links."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / 'Docs/44-第二版范围与任务计划.md'


class V2PlanTests(unittest.TestCase):
    def test_tasks_are_unique_and_dependencies_precede_tasks(self):
        rows = [line.split('|') for line in PLAN.read_text(encoding='utf-8').splitlines()
                if re.match(r'\| V2-\d{2} \|', line)]
        self.assertEqual([row[1].strip() for row in rows],
                         [f'V2-{i:02}' for i in range(1, 25)])
        for number, row in enumerate(rows, 1):
            dependency = row[3].replace('V2-', '')
            for prior in re.findall(r'\d{2}', dependency):
                self.assertLess(int(prior), number)

    def test_document_links_resolve(self):
        for relative in ['README.md', 'Docs/03-需求边界与MVP.md',
                         'Docs/08-分阶段开发与Agent提示词.md',
                         'Docs/13-版本与变更记录.md', str(PLAN.relative_to(ROOT))]:
            path = ROOT / relative
            for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8-sig')):
                if '://' not in target and not target.startswith('#'):
                    self.assertTrue((path.parent / target.split('#')[0]).exists(), target)


if __name__ == '__main__':
    unittest.main()
