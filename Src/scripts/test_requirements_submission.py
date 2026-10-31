"""Regression checks for grading omissions and the self-contained submission."""
from pathlib import Path
from zipfile import ZipFile
import hashlib
import json
import re
import unittest

import build_requirements_submission as submission

DOCS = submission.DOCS


class RequirementsSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.requirements = (DOCS / submission.SOURCES[0]).read_text(encoding='utf-8-sig')

    def test_stable_identifiers_and_optional_acceptance(self):
        self.assertIn('MF-14原指', self.requirements)
        self.assertIn('MF-16原指', self.requirements)
        self.assertRegex(self.requirements, r'\| MF-15 \|[^\n]+\| AC-13 \|')
        self.assertRegex(self.requirements, r'\| AC-13 \| MF-15')
        self.assertIn('全集比对', self.requirements)
        self.assertIn('超过20条', self.requirements)

    def test_account_boundary_assertions_and_core_formats(self):
        for letter in 'abcdefgh':
            self.assertIn(f'| AC-01{letter} |', self.requirements)
        for obj in ('时段', '答案', '确认会议', '任务', '会议文本编辑'):
            self.assertIn(f'| {obj} |', self.requirements)
        for term in ('RFC3339', 'client_request_id', 'UTC整数毫秒', '2026-11-06T10:00:00.000Z'):
            self.assertIn(term, self.requirements)
        self.assertNotIn('详细账号校验规则在接口设计阶段进一步细化', self.requirements)

    def test_v2_has_one_explicit_priority_system(self):
        rows = re.findall(r'^\| (V2-[RE]\d{2}) \| (P[01]) \|', self.requirements, re.M)
        self.assertEqual(dict(rows), {**{f'V2-R{i:02}': 'P0' for i in range(1, 11)},
                                     **{f'V2-E{i:02}': 'P1' for i in range(1, 4)}})
        self.assertEqual(len(rows), 13)

    def test_sources_and_effectiveness_method_are_self_contained(self):
        for marker in ('附录A', '附录B', '附录C', '附录D', '41号', '43号', '44号',
                       '不是教师规定', '最多300格', '分析单位为一个真实小组',
                       '先后顺序', '未完成', '补问轮数', '不宣称统计显著'):
            self.assertIn(marker, self.requirements)
        self.assertIn('MF-02邀请码、MF-06三态填写', self.requirements)

    def test_combined_artifact_contains_all_sources_and_no_local_dependencies(self):
        expected = submission.combined_document()
        self.assertEqual((DOCS / submission.COMBINED).read_text(encoding='utf-8'), expected)
        self.assertIn('第3部分', expected)
        for source in submission.SOURCES:
            title = (DOCS / source).read_text(encoding='utf-8-sig').splitlines()[0].lstrip('# ')
            self.assertIn(title, expected)
        for target in re.findall(r'\]\(([^)]+)\)', expected):
            self.assertTrue(target.startswith(('https://', 'http://', '#')), target)
        self.assertIn('待独立人工复算', expected)
        self.assertIn('人工结果', expected)

    def test_archive_contents_hashes_and_sources_are_current(self):
        with ZipFile(submission.ARCHIVE) as archive:
            self.assertIsNone(archive.testzip())
            expected = submission.package_entries()
            self.assertEqual(set(archive.namelist()), set(expected))
            for name, content in expected.items():
                self.assertEqual(archive.read(name), content, name)
            manifest = json.loads(archive.read('manifest.json'))
            for name, digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
            self.assertEqual(manifest['version'], 'V1.3')
            self.assertEqual(len(manifest['artifacts']), 3)


if __name__ == '__main__':
    unittest.main()
