"""Generate the project mind map PNG, DOT and Markdown from one JSON source."""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Docs/images/MeetFlow-思维导图.json'


def render(font_path):
    raw = SOURCE.read_bytes()
    data = json.loads(raw)
    branches = data['branches']
    if len(branches) != 6:
        raise ValueError('This layout expects six branches.')
    fonts = {size: ImageFont.truetype(str(font_path), size) for size in (26, 28, 34, 50)}
    canvas = Image.new('RGB', (1800, 1250), '#f3f6fb')
    draw = ImageDraw.Draw(canvas)
    draw.text((900, 45), data['title'], font=fonts[50], fill='#173551', anchor='mt')
    draw.text((900, 115), data['subtitle'], font=fonts[26], fill='#526579', anchor='mt')
    colors = ['#2865a0', '#267e73', '#795ba8', '#b17329', '#386fa6', '#627187']
    draw.line([(900, 165), (900, 1010)], fill='#c3cedb', width=4)
    for index, branch in enumerate(branches):
        x = 60 if index % 2 == 0 else 940
        y = 200 + (index // 2) * 340
        draw.line([(900, y + 130), (x + (800 if index % 2 == 0 else 0), y + 130)], fill='#c3cedb', width=4)
        draw.rounded_rectangle((x, y, x + 800, y + 260), radius=22, fill='white', outline='#d5deea', width=2)
        draw.rounded_rectangle((x + 25, y + 30, x + 32, y + 66), radius=3, fill=colors[index])
        draw.text((x + 50, y + 23), branch['title'], font=fonts[34], fill=colors[index])
        for row, item in enumerate(branch['items']):
            if draw.textlength(item, font=fonts[28]) > 730:
                raise ValueError(f'Label too long: {item}')
            draw.text((x + 34, y + 90 + row * 48), item, font=fonts[28], fill='#24384b')
    draw.text((900, 1190), '需求 MF / 验收 AC / 设计 TV：沿用现有实验基线', font=fonts[26], fill='#526579', anchor='mt')
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text('source_sha256', hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest())
    canvas.save(SOURCE.with_suffix('.png'), pnginfo=metadata)

    quote = lambda value: json.dumps(value, ensure_ascii=False)
    dot = ['digraph MeetFlowMindMap {', '  graph [rankdir=LR, bgcolor="#f3f6fb"];',
           '  node [shape=box, style="rounded,filled", fillcolor="white", fontname="Microsoft YaHei"];',
           f'  root [label={quote(data["title"])}];']
    for index, branch in enumerate(branches):
        label = '\n'.join([branch['title'], *branch['items']])
        dot.extend([f'  branch{index} [label={quote(label)}];', f'  root -> branch{index};'])
    dot.append('}')
    SOURCE.with_suffix('.dot').write_text('\n'.join(dot) + '\n', encoding='utf-8')

    lines = ['# MeetFlow 第一版思维导图', '', '整理基线：B1｜2026-10-25。此图表示当前第一版范围，不回写立项会议当时的讨论内容。', '',
             '![MeetFlow第一版思维导图](images/MeetFlow-思维导图.png)', '', '## 节点内容', '']
    for branch in branches:
        lines.extend([f'### {branch["title"]}', ''])
        lines.extend(f'- {item}' for item in branch['items'])
        lines.append('')
    lines += ['## 维护方式', '',
              '编辑[JSON数据源](images/MeetFlow-思维导图.json)，运行[生成脚本](../Src/scripts/render_mindmap.py)更新PNG、[DOT](images/MeetFlow-思维导图.dot)及本页节点。需要Pillow和中文字体。', '',
              '```powershell', 'python Src/scripts/render_mindmap.py --font C:/Windows/Fonts/msyh.ttc', '```', '',
              '详细规则见[需求边界](03-需求边界与MVP.md)，任务安排见[开发计划](08-分阶段开发与Agent提示词.md)。']
    (ROOT / 'Docs/04-思维导图.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', type=Path, default=Path('C:/Windows/Fonts/msyh.ttc'))
    render(parser.parse_args().font)
