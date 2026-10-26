"""Cross-document baseline checks; these do not exercise the future product."""
import hashlib
import json
from pathlib import Path
import re
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'Docs'


def read(prefix):
    return next(DOCS.glob(prefix + '-*.md')).read_text(encoding='utf-8-sig')


def rows(body, pattern):
    return [[c.strip() for c in line.strip('|').split('|')]
            for line in body.splitlines() if re.match(pattern, line)]


class BaselineDocumentTests(unittest.TestCase):
    def test_core_requirement_acceptance_mapping_matches_authority(self):
        def mapping(body):
            return {r[0]: re.findall(r'AC-\d+', r[-1])
                    for r in rows(body, r'^\| MF-\d+ \|') if 'P0' in r}
        expected = mapping(read('09'))
        self.assertEqual(len(expected), 13)
        self.assertEqual(mapping(read('03')), expected)
        acceptance = {r[0]: set(re.findall(r'MF-\d+', r[1]))
                      for r in rows(read('07'), r'^\| AC-\d+ \|')}
        self.assertEqual(set(acceptance), {f'AC-{i:02}' for i in range(1, 13)})
        for requirement, cases in expected.items():
            for case in cases:
                self.assertIn(requirement, acceptance[case])
        defined = set(re.findall(r'TV-\d+', read('12')))
        self.assertLessEqual(set(re.findall(r'TV-\d+', read('07'))), defined)

    def test_task_dependencies_are_complete_and_acyclic(self):
        tasks = rows(read('08'), r'^\| T\d+ \|')
        identifiers = [r[0] for r in tasks]
        self.assertGreaterEqual(len(tasks), 30)
        self.assertEqual(len(identifiers), len(set(identifiers)))
        graph = {r[0]: set(re.findall(r'T\d+', r[4])) for r in tasks}
        for row in tasks:
            self.assertIn(row[3], {'马若曦', '陈明强'})
            self.assertLessEqual(graph[row[0]], set(graph))
        visited, active = set(), set()
        def visit(key):
            self.assertNotIn(key, active, 'Dependency cycle')
            if key in visited:
                return
            active.add(key)
            for dep in graph[key]:
                visit(dep)
            active.remove(key)
            visited.add(key)
        visit('T36')
        self.assertEqual(visited, set(graph), 'Final acceptance must depend on every planned task')

    def test_changed_document_links_resolve(self):
        paths = [next(DOCS.glob(f'{i:02}-*.md')) for i in (*range(2, 9), 13, 14, 15, 16, 17, 18, 19, 20, 21, 22)]
        paths += [ROOT/'README.md', ROOT/'使用说明.md', ROOT/'Src/README.md', ROOT/'Src/prototype/README.md']
        paths += [ROOT/'Src/scripts/diagrams/README.md']
        paths += [ROOT/'Src/backend/README.md']
        paths += [ROOT/'Src/frontend/README.md']
        for path in paths:
            body = path.read_text(encoding='utf-8-sig')
            for target in re.findall(r'\]\(([^)]+)\)', body):
                if target.startswith(('https://', 'http://', '#')):
                    continue
                target = target.split('#')[0]
                self.assertTrue((path.parent/target).exists(), f'{path.name}: {target}')
            self.assertEqual(sum(line.startswith('```') for line in body.splitlines()) % 2, 0, path.name)

    def test_mindmap_outputs_share_the_current_source(self):
        source = DOCS/'images/MeetFlow-思维导图.json'
        raw = source.read_bytes()
        data = json.loads(raw)
        markdown = read('04')
        dot = source.with_suffix('.dot').read_text(encoding='utf-8')
        labels = [json.loads(s) for s in re.findall(r'label=("(?:[^"\\]|\\.)*")', dot)]
        for branch in data['branches']:
            self.assertIn('\n'.join([branch['title'], *branch['items']]), labels)
            for label in [branch['title'], *branch['items']]:
                self.assertIn(label, markdown)
        png = source.with_suffix('.png').read_bytes()
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        offset, metadata = 8, {}
        while offset < len(png):
            size = struct.unpack('>I', png[offset:offset+4])[0]
            kind, payload = png[offset+4:offset+8], png[offset+8:offset+8+size]
            if kind == b'tEXt':
                key, value = payload.split(b'\0', 1)
                metadata[key.decode()] = value.decode()
            offset += 12 + size
        self.assertEqual(metadata['source_sha256'], hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest())


if __name__ == '__main__':
    unittest.main()
