"""Build a portable requirements submission with all three required artifacts."""
from pathlib import Path
import hashlib
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'Docs'
SOURCES = ('09-需求分析文档.md', '10-AI协作记录.md', '11-人工核实说明.md')
COMBINED = '55-需求分析实验提交稿.md'
ARCHIVE = ROOT / 'Deliverables' / 'MeetFlow-需求分析实验-V1.3.zip'
EVIDENCE = ('t33-delivery.json', 't36-e2e.json', 'requirements-revision-20261031.json')


def standalone(text):
    # Portable copy: local references have their content or summaries in the file.
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  lambda m: m.group(0) if m.group(2).startswith(('https://', 'http://', '#')) else m.group(1), text)


def combined_document():
    pieces = ['# MeetFlow需求分析实验提交稿\n\n作者：马若曦｜版本：V1.3｜日期：2026-10-31\n\n'
              '本稿包含需求分析、AI协作记录与人工核实说明三个部分。第一版与第二版分别定义范围和优先级，已有自动化证据与待人工验证结果分别列示。\n']
    for index, name in enumerate(SOURCES, 1):
        source = standalone((DOCS / name).read_text(encoding='utf-8-sig'))
        title, _, body = source.partition('\n')
        # Keep headings scoped under each independent artifact.
        body = re.sub(r'^(#{2,5}) ', r'#\1 ', body, flags=re.MULTILINE)
        pieces.append(f'\n## 第{index}部分：{title.lstrip("# ")}\n{body.rstrip()}\n')
    return '\n'.join(pieces).rstrip() + '\n'


def package_entries():
    entries = {COMBINED: combined_document().encode('utf-8')}
    for name in SOURCES:
        entries[name] = standalone((DOCS / name).read_text(encoding='utf-8-sig')).encode('utf-8')
    for name in EVIDENCE:
        entries['evidence/' + name] = (DOCS / 'evidence' / name).read_bytes()
    manifest = {
        'version': 'V1.3',
        'date': '2026-10-31',
        'author': '马若曦',
        'artifacts': list(SOURCES),
        'combined': COMBINED,
        'verification_boundary': 'Historical automation evidence; human usability and independent review remain pending.',
        'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(entries.items())},
    }
    entries['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    return entries


def build():
    entries = package_entries()
    (DOCS / COMBINED).write_bytes(entries[COMBINED])
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(ARCHIVE, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(entries.items()):
            info = ZipInfo(name, date_time=(2026, 10, 31, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, data)
    return ARCHIVE


if __name__ == '__main__':
    print(build())
