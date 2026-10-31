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
            self.assertEqual(manifest['version'], 'V1.4')
            self.assertEqual(len(manifest['artifacts']), 3)

    def test_all_raw_evidence_is_inline_and_exact(self):
        body = submission.combined_document()
        embedded = [json.loads(block) for block in re.findall(r'```json\n(.*?)\n```', body, re.S)]
        self.assertEqual(len(embedded), len(submission.EVIDENCE))
        for name, actual in zip(submission.EVIDENCE, embedded):
            expected = json.loads((DOCS / 'evidence' / name).read_text(encoding='utf-8-sig'))
            self.assertEqual(actual, expected, name)
        for record in submission.RECORDS:
            self.assertIn('#### ' + record, body)

    def test_inline_samples_recalculate_p95(self):
        body = submission.evidence_appendix()
        rows = re.findall(r'^\| (\d+) \| ([\d.]+) \| ([\d.]+) \|$', body, re.M)
        self.assertEqual([int(r[0]) for r in rows], list(range(1, 31)))
        self.assertEqual(sorted(float(r[1]) for r in rows)[28], 46.9619)
        self.assertEqual(sorted(float(r[2]) for r in rows)[28], 38.2339)

    def test_goals_optional_gate_and_role_information_are_explicit(self):
        for number in range(1, 5):
            row = re.search(rf'^\| G{number} \| P0 \| (.+)$', self.requirements, re.M)
            self.assertIsNotNone(row)
            self.assertIn('AC-', row.group(1))
            self.assertIn('E2E-01', row.group(1))
        self.assertIn('不单独导致P0核心验收失败', self.requirements)
        for number in range(1, 6):
            self.assertIn(f'| UI-R{number:02} |', self.requirements)
        self.assertIn('保存空字符串即清空', self.requirements)

    def test_v2_child_requirements_have_parent_priority_and_assertions(self):
        rows = re.findall(r'^\| (V2-D\d{2}) \| P0 \| ([^|]+) \| ([^|]+) \|$', self.requirements, re.M)
        self.assertEqual([r[0] for r in rows], [f'V2-D{i:02}' for i in range(1, 13)])
        for identifier, parents, assertion in rows:
            self.assertRegex(parents, r'V2-R\d{2}')
            self.assertGreater(len(assertion), 20, identifier)

    def test_dated_decisions_and_original_ai_excerpts_preserve_provenance(self):
        for commit in ('f7de546', 'a50eebe', 'c9187e2'):
            self.assertIn(commit, self.requirements)
        record = (DOCS / '10-AI协作记录.md').read_text(encoding='utf-8')
        for number in range(1, 5):
            self.assertIn(f'| AI-Q{number:02} |', record)
        self.assertIn('第5轮', record)
        self.assertIn('没有真实受访者或操作签认', record)


if __name__ == '__main__':
    unittest.main()
