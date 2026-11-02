"""Check presentation structure, sources, timing and honest delivery boundaries."""
import json
import re
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'Presentation'
NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}


class PresentationChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.content = json.loads((OUT / 'content.json').read_text(encoding='utf-8'))
        cls.package = zipfile.ZipFile(OUT / 'MeetFlow-课程汇报.pptx')
        cls.html = (OUT / 'MeetFlow-网页演示.html').read_text(encoding='utf-8')

    def test_timing_and_sources(self):
        slides = self.content['slides']
        self.assertEqual(len(slides), 9)
        self.assertEqual(sum(s['seconds'] for s in slides), 480)
        self.assertEqual(slides[6]['seconds'], 150)
        self.assertTrue(all(s['sources'] and s['notes'] for s in slides))
        self.assertEqual(self.content['presentation_date'], '2026-11-06')

    def test_editable_slides_and_speaker_notes(self):
        files = self.package.namelist()
        slides = [p for p in files if re.fullmatch(r'ppt/slides/slide\d+\.xml', p)]
        notes = [p for p in files if re.fullmatch(r'ppt/notesSlides/notesSlide\d+\.xml', p)]
        self.assertEqual(len(slides), 9)
        self.assertEqual(len(notes), 9)
        for i in range(1, 10):
            tree = ET.fromstring(self.package.read(f'ppt/slides/slide{i}.xml'))
            self.assertGreaterEqual(len(tree.findall('.//a:t', NS)), 10)
            note = self.package.read(f'ppt/notesSlides/notesSlide{i}.xml').decode()
            self.assertIn(self.content['slides'][i-1]['notes'], note)

    def test_offline_html_and_demo_link(self):
        self.assertEqual(self.html.count('<section class="slide '), 9)
        self.assertIn('http://localhost:8002/login', self.html)
        self.assertNotRegex(self.html, r'<(?:script|link)[^>]+(?:src|href)="https?://')
        self.assertIn('data:image/png;base64,', self.html)
        self.assertIn('prefers-reduced-motion', self.html)

    def test_honest_claims_and_script(self):
        notes = '\n'.join(s['notes'] for s in self.content['slides'])
        for phrase in ['示意数据', '公开发布还没有验收', '五位非开发者试用仍待人工执行', '十月三十一日']:
            self.assertIn(phrase, notes)
        script = (OUT / '讲解稿.md').read_text(encoding='utf-8')
        for phrase in ['超过10秒', '未填不等于有空', '手动', '陈明强', '马若曦']:
            self.assertIn(phrase, script)

    def test_native_render_no_overflow(self):
        result = json.loads((OUT / '预览' / 'powerpoint-check.json').read_text(encoding='utf-8-sig'))
        self.assertEqual(result['slides'], 9)
        self.assertEqual(result['overflow_risks'], [])

    def test_pdf_and_source_references(self):
        from pypdf import PdfReader
        self.assertEqual(len(PdfReader(OUT / 'MeetFlow-课程汇报.pdf').pages), 9)
        for slide in self.content['slides']:
            for source in slide['sources']:
                filename = source.split('，')[0]
                self.assertTrue((ROOT / filename).is_file(), filename)


if __name__ == '__main__':
    unittest.main()
