"""Check T03 traceability and exported diagrams, not product behavior."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'Docs'
SOURCES = DOCS / 'diagrams/t03'
IMAGES = DOCS / 'images/t03'


def read(path):
    return path.read_text(encoding='utf-8-sig')


def state_edges(body):
    return set(re.findall(r'^\s*([A-Z_]+) --> ([A-Z_]+):', body, re.M))


def er_edges(body):
    return set(line.strip() for line in body.splitlines() if re.match(r'^\s*[A-Z_]+ [|o{}.\-]+ [A-Z_]+ :', line))


class DesignDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(read(SOURCES / 'catalog.json'))
        cls.manifest = json.loads(read(IMAGES / 'manifest.json'))
        cls.design = read(DOCS / '12-系统设计文档.md')
        cls.record = read(DOCS / '15-设计图与需求原型核对.md')

    def test_diagram_coverage_uses_only_current_p0_requirements(self):
        baseline = read(DOCS / '09-需求分析文档.md')
        p0 = set(re.findall(r'^\| (MF-\d+) \| .*? \| P0 \|', baseline, re.M))
        all_refs = set()
        ids = [d['id'] for d in self.catalog['diagrams']]
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), len(ids))
        for d in self.catalog['diagrams']:
            self.assertTrue((SOURCES / (d['id'] + '.mmd')).is_file())
            self.assertTrue(d['requirements'])
            self.assertLessEqual(set(d['requirements']), p0)
            all_refs.update(d['requirements'])
            for suffix in ('.mmd', '.svg', '.png'):
                self.assertIn(d['id'] + suffix, self.record)
        self.assertEqual(all_refs, p0)

    def test_poll_state_matches_design_and_has_no_reopening(self):
        source = read(SOURCES / '02-poll-state.mmd')
        diagrams = re.findall(r'```mermaid\n(stateDiagram-v2.*?)```', self.design, re.S)
        self.assertEqual(len(diagrams), 1)
        actual = state_edges(source)
        self.assertEqual(actual - {('DRAFT', 'DRAFT')}, state_edges(diagrams[0]))
        self.assertFalse(any(a in {'CONFIRMED', 'CANCELLED'} for a, b in actual))
        for phrase in ('到期请求判定', '无需后台定时器', '存储状态可能仍为OPEN'):
            self.assertIn(phrase, source)

    def test_invite_reset_is_explicitly_owner_only(self):
        source = read(SOURCES / '01-use-cases.mmd')
        node = re.search(r'(C\d+)\(\["重置小组邀请码', source).group(1)
        associations = re.findall(rf'^\s*(GUEST|USER|MEMBER|OWNER) --- {node}$', source, re.M)
        self.assertEqual(associations, ['OWNER'])

    def test_task_done_is_reopenable_and_not_a_terminal_state(self):
        source = read(SOURCES / '03-task-state.mmd')
        states = {'TODO', 'IN_PROGRESS', 'DONE'}
        self.assertEqual(state_edges(source), {(a, b) for a in states for b in states if a != b})
        self.assertNotIn('DONE --> [*]', source)
        self.assertIn('重复完成保留时间', source)
        self.assertIn('重开清空完成时间', source)

    def test_er_entities_and_cardinalities_match_the_design(self):
        source = read(SOURCES / '04-data-er.mmd')
        expected = set(re.findall(r'^\| DT-\d+ (\w+) \|', self.design, re.M))
        actual = {name.lower() for name in re.findall(r'^    ([A-Z_]+) \{', source, re.M)}
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual), 10)
        self.assertEqual(er_edges(source), er_edges(self.design))
        for relation in ('POLLS ||--o{ PARTICIPANTS', 'POLLS ||..o{ SLOTS', 'POLLS ||..o| MEETINGS'):
            self.assertIn(relation, source)

    def test_sequences_keep_database_writes_in_the_service(self):
        for prefix in ('05-vote', '06-confirm', '07-task'):
            source = read(next(SOURCES.glob(prefix + '*.mmd')))
            self.assertIn('BEGIN IMMEDIATE', source)
            self.assertIn('ROLLBACK', source)
            self.assertIn('COMMIT', source)
            for line in source.splitlines():
                if re.match(r'\s*\w+->>D:', line):
                    self.assertRegex(line, r'^\s*S->>D:', line)
        confirm = read(SOURCES / '06-confirm-sequence.mmd')
        for phrase in ('200 原MeetingOut', '409 STATE_CONFLICT', 'UNIQUE(poll_id)', '400 ACK_REQUIRED'):
            self.assertIn(phrase, confirm)
        self.assertLess(confirm.index('已存在会议'), confirm.index('effective_status=CLOSED'))

    def test_exported_assets_match_sources_and_are_valid_images(self):
        self.assertEqual(self.manifest['mermaid_version'], '12.2.0')
        self.assertEqual([d['id'] for d in self.manifest['diagrams']], [d['id'] for d in self.catalog['diagrams']])
        for d in self.manifest['diagrams']:
            source = (SOURCES / (d['id'] + '.mmd')).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(source).hexdigest(), d['sha256'], d['id'])
            svg = (IMAGES / (d['id'] + '.svg')).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(svg).hexdigest(), d['svg_sha256'])
            tree = ET.fromstring(svg)
            self.assertTrue(tree.tag.endswith('svg'))
            self.assertEqual(tree.attrib['data-source-sha256'], d['sha256'])
            self.assertEqual(tree.attrib['aria-label'], d['title'])
            self.assertNotIn(b'<script', svg)
            png = (IMAGES / (d['id'] + '.png')).read_bytes()
            self.assertEqual(hashlib.sha256(png).hexdigest(), d['png_sha256'])
            self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(struct.unpack('>II', png[16:24]), (d['width'], d['height']))

    def test_prototype_gaps_link_to_real_future_tasks(self):
        plan = read(DOCS / '08-分阶段开发与Agent提示词.md')
        task_ids = set(re.findall(r'^\| (T\d+) \|', plan, re.M))
        gaps = re.findall(r'^\| (GAP-\d+) \| (.+) \|$', self.record, re.M)
        self.assertEqual(len(gaps), 6)
        for key, rest in gaps:
            refs = set(re.findall(r'T\d+', rest))
            self.assertTrue(refs, key)
            self.assertLessEqual(refs, task_ids)
        self.assertIn('尚未实施', self.record)
        self.assertIn('不调整原型界面', self.record)


if __name__ == '__main__':
    unittest.main()
