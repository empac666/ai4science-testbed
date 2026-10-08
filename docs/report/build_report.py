#!/usr/bin/env python3
"""把 docs/report/ai4s_w1w2_report.md 转为自包含 HTML（图片内嵌），再用 Chrome 无头模式打印成 PDF。
只支持本报告用到的 Markdown 子集：标题、段落、列表、表格、图片、粗体、行内代码、引用。"""
import base64, html, re, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parent
md = (R/'ai4s_w1w2_report.md').read_text(encoding='utf-8').splitlines()

def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', r'<a href="\2">\1</a>', s)
    return s

out = []; i = 0
while i < len(md):
    line = md[i]
    if m := re.match(r'!\[(.*?)\]\((.+?)\)', line):
        p = (R/m.group(2)).resolve(); b = base64.b64encode(p.read_bytes()).decode()
        out.append(f'<figure><img src="data:image/png;base64,{b}"><figcaption>{inline(m.group(1))}</figcaption></figure>'); i += 1; continue
    if m := re.match(r'(#{1,4}) (.*)', line):
        n = len(m.group(1)); out.append(f'<h{n}>{inline(m.group(2))}</h{n}>'); i += 1; continue
    if line.startswith('|'):
        rows = []
        while i < len(md) and md[i].startswith('|'):
            rows.append([c.strip().replace('\\|', '|') for c in re.split(r'(?<!\\)\|', md[i].strip().strip('|'))]); i += 1
        t = ['<table>', '<tr>' + ''.join(f'<th>{inline(c)}</th>' for c in rows[0]) + '</tr>']
        for r in rows[2:]: t.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r) + '</tr>')
        out.append('\n'.join(t + ['</table>'])); continue
    if re.match(r'\s*[-*] ', line) or re.match(r'\s*\d+\. ', line):
        ordered = bool(re.match(r'\s*\d+\. ', line)); tag = 'ol' if ordered else 'ul'; items = []
        while i < len(md) and (re.match(r'\s*[-*] ', md[i]) or re.match(r'\s*\d+\. ', md[i])):
            items.append(re.sub(r'^\s*([-*]|\d+\.) ', '', md[i])); i += 1
        out.append(f'<{tag}>' + ''.join(f'<li>{inline(x)}</li>' for x in items) + f'</{tag}>'); continue
    if line.startswith('> '):
        out.append(f'<blockquote>{inline(line[2:])}</blockquote>'); i += 1; continue
    if line.strip():
        para = [line]; i += 1
        while i < len(md) and md[i].strip() and not re.match(r'(#|\||!\[|\s*[-*] |\s*\d+\. |> )', md[i]):
            para.append(md[i]); i += 1
        out.append('<p>' + inline(' '.join(para)) + '</p>'); continue
    i += 1
css = """body{font-family:'Noto Sans CJK SC',sans-serif;max-width:900px;margin:24px auto;line-height:1.65;color:#222;font-size:14px}
h1{font-size:24px;border-bottom:2px solid #333}h2{font-size:19px;border-bottom:1px solid #aaa;margin-top:28px}h3{font-size:16px}
table{border-collapse:collapse;margin:10px 0;font-size:12.5px}th,td{border:1px solid #999;padding:3px 7px}th{background:#eef}
figure{margin:12px 0;text-align:center;page-break-inside:avoid}img{max-width:100%}figcaption{font-size:12px;color:#555}
code{background:#f3f3f3;padding:0 3px;font-size:12px}blockquote{border-left:4px solid #c62828;margin:8px 0;padding:4px 10px;background:#fff5f5}
@page{size:A4;margin:14mm}"""
doc = f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>AI4Science 实验台 W1–W2 报告</title><style>{css}</style></head><body>' + '\n'.join(out) + '</body></html>'
(R/'ai4s_w1w2_report.html').write_text(doc, encoding='utf-8')
subprocess.run(['google-chrome', '--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer',
                f'--print-to-pdf={R/"ai4s_w1w2_report.pdf"}', f'file://{R/"ai4s_w1w2_report.html"}'], check=True,
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
print('ok', (R/'ai4s_w1w2_report.pdf').stat().st_size)
