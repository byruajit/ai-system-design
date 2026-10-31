"""
Render every episode's cheatsheet.md → cheatsheet.pdf (one A4 page, two columns)
and every diagrams/*.mmd → .png.

    pip install markdown playwright && playwright install chromium
    npm i -g @mermaid-js/mermaid-cli
    python tools/render.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import markdown
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

CSS = """
@page { size: A4; margin: 11mm 12mm; }
* { box-sizing: border-box; }
body { font-family: 'Segoe UI', Inter, Helvetica, Arial, sans-serif; color: #1d2433; font-size: 11pt; line-height: 1.38; margin: 0; }
h1 { font-size: 17pt; margin: 0 0 2mm; padding-bottom: 2mm; border-bottom: 3px solid #1f6feb; color: #0b1f44; column-span: all; }
.brand { column-span: all; font-size: 8.5pt; color: #5b6475; margin: -1mm 0 3mm; }
.cols { column-count: 2; column-gap: 7mm; }
h2 { font-size: 12pt; color: #1f6feb; margin: 3.2mm 0 1.2mm; break-after: avoid; text-transform: uppercase; letter-spacing: .3px; }
ul, ol { margin: 0 0 1mm; padding-left: 4.5mm; }
li { margin: 0 0 .7mm; break-inside: avoid; }
p { margin: 0 0 1.2mm; }
code { font-family: Consolas, "JetBrains Mono", monospace; font-size: 9.6pt; background: #eef3fb; padding: 0 2px; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; font-size: 9.6pt; margin: 1mm 0 2mm; break-inside: avoid; }
th, td { border: 1px solid #d6dce6; padding: 1mm 1.4mm; text-align: left; vertical-align: top; }
th { background: #eef3fb; }
strong { color: #0b1f44; }
.foot { column-span: all; margin-top: 3mm; font-size: 7.8pt; color: #7a8394; border-top: 1px solid #d6dce6; padding-top: 1.5mm; }
"""


def md_to_html(md_text: str) -> str:
    lines = md_text.strip().splitlines()
    title = lines[0].lstrip("# ").strip()
    body = markdown.markdown("\n".join(lines[1:]), extensions=["tables", "fenced_code"])
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>{CSS}</style></head>
<body><h1>{title}</h1><div class='brand'>AI System Design · AI Engineering with Ajit · github.com/byruajit/ai-system-design</div>
<div class='cols'>{body}</div>
<div class='foot'>Northwind Bank is fictional. Prices are illustrative tiers — check current provider pricing.</div></body></html>"""


def render_cheatsheets(only: str | None = None) -> None:
    sheets = sorted(ROOT.glob("ep*/cheatsheet.md"))
    if only:
        sheets = [s for s in sheets if only in str(s)]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        for md in sheets:
            html = md.with_suffix(".html")
            html.write_text(md_to_html(md.read_text(encoding="utf-8")), encoding="utf-8")
            page.goto(html.resolve().as_uri())
            page.pdf(path=str(md.with_suffix(".pdf")), format="A4", print_background=True)
            html.unlink()
            print("pdf ", md.with_suffix(".pdf").relative_to(ROOT))
        b.close()


def render_diagrams(only: str | None = None) -> None:
    for mmd in sorted(ROOT.glob("ep*/diagrams/*.mmd")):
        if only and only not in str(mmd):
            continue
        out = mmd.with_suffix(".png")
        subprocess.run(["mmdc", "-i", str(mmd), "-o", str(out), "-b", "white", "-w", "1600", "-s", "2"],
                       check=True, capture_output=True)
        print("png ", out.relative_to(ROOT))


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    render_cheatsheets(only)
    render_diagrams(only)
