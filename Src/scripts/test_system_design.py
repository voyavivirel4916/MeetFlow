"""Validate the design baseline, traceability and document cross-references."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'Docs'


class SystemDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = (DOCS / '12-系统设计文档.md').read_text(encoding='utf-8-sig')
        cls.baseline = (DOCS / '09-需求分析文档.md').read_text(encoding='utf-8-sig')

    def test_requirement_ids_exactly_match_current_baseline(self):
        functional = set(re.findall(r'^\| (MF-\d+) \|', self.baseline, re.M))
        nonfunctional = set(re.findall(r'^\| (NFR-\d+) \|', self.baseline, re.M))
        matrix = self.design.split('## 11. 需求追溯矩阵', 1)[1].split('## 12.', 1)[0]
        design_ids = re.findall(r'^\| ((?:MF|NFR)-\d+) \|', matrix, re.M)
        self.assertEqual(len(design_ids), len(set(design_ids)))
        self.assertEqual(set(design_ids), functional | nonfunctional)
        for row in matrix.splitlines():
            if re.match(r'^\| (MF|NFR)-\d+', row):
                self.assertRegex(row, r'TV-\d+')
                self.assertRegex(row, r'(MD|IN|NF|AR|UI)-\d+')

    def test_every_referenced_verification_has_a_definition(self):
        references = set(re.findall(r'TV-\d+', self.design))
        definitions = set(re.findall(r'^\| (TV-\d+) \|', self.design, re.M))
        self.assertEqual(references, definitions)
        self.assertEqual(len(definitions), 16)

    def test_required_design_sections_and_links(self):
        headings = re.findall(r'^## (\d+)\.', self.design, re.M)
        self.assertEqual(headings, [str(i) for i in range(1, 13)])
        for term in ('架构设计', '模块设计', '接口设计', '数据设计', '关键流程设计',
                     '界面与交互设计', '非功能设计', '异常与故障处理设计',
                     '设计决策与权衡', '需求追溯矩阵', '测试与验证考虑', '需求变更说明'):
            self.assertIn(term, self.design)
        for link in re.findall(r'\]\(([^)]+)\)', self.design):
            if not link.startswith(('http:', 'https:', '#')):
                self.assertTrue((DOCS / link).is_file(), link)
        self.assertEqual(self.design.count('```') % 2, 0)

    def test_p0_interfaces_and_entities_have_definitions(self):
        for i in range(1, 14):
            self.assertRegex(self.design, rf'\| API-{i:02d} \|')
        for i in range(1, 11):
            self.assertRegex(self.design, rf'\| DT-{i:02d} \w+ \|')
        for i in range(1, 7):
            self.assertIn(f'| IN-{i:02d} |', self.design)

    def test_local_scope_and_critical_consistency_controls(self):
        for phrase in ('本次不修改实验1需求', 'a50eebe', '每组最多20人', '1～15个时段',
                       '无外部系统或第三方业务接口', '127.0.0.1',
                       'UNIQUE(poll_id)', 'BEGIN IMMEDIATE', 'client_request_id',
                       'effective_status', '原Cookie', '最后成功提交覆盖'):
            self.assertIn(phrase, self.design)
        self.assertNotIn('MF-14 |', self.design)
        self.assertNotIn('MF-16 |', self.design)


if __name__ == '__main__':
    unittest.main()
