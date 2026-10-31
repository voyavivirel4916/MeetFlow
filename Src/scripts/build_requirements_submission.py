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
VERSION = 'V1.4'
ARCHIVE = ROOT / 'Deliverables' / f'MeetFlow-需求分析实验-{VERSION}.zip'
EVIDENCE = ('t33-delivery.json', 't36-e2e.json', 'requirements-revision-20261031.json',
            't31-backend-summary.json', 't30-frontend.json')
RECORDS = ('33-推荐样本与边界测试.md', '41-联合测试与交付验证报告.md',
           '43-四账号验收与人工试用记录.md', '44-第二版范围与任务计划.md')


def standalone(text):
    # Portable copy: local references have their content or summaries in the file.
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
                  lambda m: m.group(0) if m.group(2).startswith(('https://', 'http://', '#')) else m.group(1), text)


def combined_document():
    pieces = ['# MeetFlow需求分析实验提交稿\n\n作者：马若曦｜版本：V1.4｜日期：2026-10-31\n\n'
              '本稿包含需求分析、AI协作记录与人工核实说明三个规定部分，第四部分为内联原始证据。第一版与第二版分别定义范围和优先级，已有自动化证据与待人工验证结果分别列示。\n']
    for index, name in enumerate(SOURCES, 1):
        source = standalone((DOCS / name).read_text(encoding='utf-8-sig'))
        title, _, body = source.partition('\n')
        # Keep headings scoped under each independent artifact.
        body = re.sub(r'^(#{2,5}) ', r'#\1 ', body, flags=re.MULTILINE)
        pieces.append(f'\n## 第{index}部分：{title.lstrip("# ")}\n{body.rstrip()}\n')
    pieces.append(evidence_appendix())
    return '\n'.join(pieces).rstrip() + '\n'


def evidence_appendix():
    report = json.loads((DOCS / 'evidence' / 't33-delivery.json').read_text(encoding='utf-8-sig'))
    pieces = ['\n## 第4部分：内联原始证据与项目记录\n\n'
              '本部分内联既有证据，不要求读取外部附件才能核对数字。JSON内容取自项目文件，保留原字段、版本与日期；这些是已有执行记录，'
              '不能仅靠文档证明在其他环境可复现，也不能替代人工试用。33/41/43/44号全文是历史快照，'
              '其中计划和旧状态须结合记录日期理解；现行需求范围以第一部分为准。\n',
              '\n### 4.1 性能原始样本与P95复算\n\n'
              '单位毫秒；本机顺序HTTP，每接口预热5次后30次采样。最近秩P95为排序后第29项（从1计数）。'
              '完整环境、源码版本、隔离方式和恢复结果见下面原JSON。\n\n'
              '| 样本序号 | 推荐接口（ms） | 小组任务分页（ms） |\n| --- | ---: | ---: |']
    measurements = report['measurements']
    left = measurements['recommendations']['milliseconds']
    right = measurements['task_list']['milliseconds']
    if len(left) != 30 or len(right) != 30:
        raise ValueError('Performance evidence must contain exactly 30 samples per endpoint.')
    for i, (a, b) in enumerate(zip(left, right), 1):
        pieces.append(f'| {i} | {a} | {b} |')
    for name in ('recommendations', 'task_list'):
        values = measurements[name]['milliseconds']
        p95 = sorted(values)[28]
        if p95 != measurements[name]['p95_ms']:
            raise ValueError(f'P95 evidence mismatch: {name}')
        pieces.append(f'\n{name}：30项中第29项={p95}ms；最大值={max(values)}ms；'
                      f'HTTP错误={measurements[name]["http_errors"]}；目标≤1000ms。')
    pieces.append('\n复算只验证记录内部一致性，不产生新的性能采样，也不证明真实用户的排期效率。')
    pieces.append('\n### 4.2 原始JSON记录（全文）\n')
    for name in EVIDENCE:
        raw = (DOCS / 'evidence' / name).read_bytes()
        body = raw.decode('utf-8-sig').replace('\r\n', '\n').rstrip()
        json.loads(body)
        pieces.append(f'\n#### evidence/{name}\n\nSHA-256：`{hashlib.sha256(raw).hexdigest()}`（原文件字节）。'
                      f'JSON以下保留原文，仅将CRLF换行为LF并统一末尾换行。\n\n```json\n{body}\n```\n')
    pieces.append('\n### 4.3 关键项目记录（历史全文）\n')
    for name in RECORDS:
        raw = (DOCS / name).read_bytes()
        text = standalone(raw.decode('utf-8-sig').replace('\r\n', '\n'))
        _, _, body = text.partition('\n')
        body = re.sub(r'^(#{1,5}) ', lambda m: '#' * min(len(m.group(1)) + 3, 6) + ' ', body, flags=re.MULTILINE)
        pieces.append(f'\n#### {name}\n\n原文件SHA-256：`{hashlib.sha256(raw).hexdigest()}`。'
                      f'本节为历史内容，文件引用仅保留名称，其关键数据已在本稿内联。\n{body.rstrip()}\n')
    return '\n'.join(pieces)


def package_entries():
    entries = {COMBINED: combined_document().encode('utf-8')}
    for name in SOURCES:
        entries[name] = standalone((DOCS / name).read_text(encoding='utf-8-sig')).encode('utf-8')
    for name in EVIDENCE:
        entries['evidence/' + name] = (DOCS / 'evidence' / name).read_bytes()
    for name in RECORDS:
        entries['records/' + name] = (DOCS / name).read_bytes()
    manifest = {
        'version': VERSION,
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
