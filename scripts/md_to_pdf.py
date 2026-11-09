#!/usr/bin/env python3
"""
Convertidor Automático de Markdown a PDF Corporativo
Utiliza Google Chrome en modo Headless para renderizar HTML con CSS profesional y exportar a PDF de alta resolución.
"""

import os
import sys
import re
import html
import subprocess
import tempfile

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def markdown_to_html(md_text: str, title: str = "Documento") -> str:
    lines = md_text.splitlines()
    html_lines = []
    in_table = False
    table_header = True
    in_list = False

    for line in lines:
        sline = line.strip()

        # Cierre de lista si la línea no es ítem
        if in_list and not sline.startswith(("- ", "* ")):
            html_lines.append("</ul>")
            in_list = False

        # Cierre de tabla si la línea no es fila
        if in_table and not sline.startswith("|"):
            html_lines.append("</tbody></table>")
            in_table = False

        if not sline:
            continue

        # Encabezados
        if sline.startswith("# "):
            html_lines.append(f"<h1>{html.escape(sline[2:])}</h1>")
            continue
        elif sline.startswith("## "):
            html_lines.append(f"<h2>{html.escape(sline[3:])}</h2>")
            continue
        elif sline.startswith("### "):
            html_lines.append(f"<h3>{html.escape(sline[4:])}</h3>")
            continue
        elif sline.startswith("#### "):
            html_lines.append(f"<h4>{html.escape(sline[5:])}</h4>")
            continue

        # Línea horizontal
        if sline in ["---", "***", "___"]:
            html_lines.append("<hr>")
            continue

        # Tablas
        if sline.startswith("|") and sline.endswith("|"):
            parts = [p.strip() for p in sline[1:-1].split("|")]
            # Ignorar línea separadora |---|---|
            if all(re.match(r'^:?-+:?$', p) for p in parts if p):
                continue

            if not in_table:
                in_table = True
                table_header = True
                html_lines.append("<table><thead><tr>")
                for p in parts:
                    clean = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(p))
                    html_lines.append(f"<th>{clean}</th>")
                html_lines.append("</tr></thead><tbody>")
            else:
                html_lines.append("<tr>")
                for p in parts:
                    clean = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(p))
                    clean = re.sub(r'`(.*?)`', r'<code>\1</code>', clean)
                    html_lines.append(f"<td>{clean}</td>")
                html_lines.append("</tr>")
            continue

        # Listas
        if sline.startswith(("- ", "* ")):
            if not in_list:
                in_list = True
                html_lines.append("<ul>")
            item_text = sline[2:].strip()
            clean = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(item_text))
            clean = re.sub(r'`(.*?)`', r'<code>\1</code>', clean)
            html_lines.append(f"<li>{clean}</li>")
            continue

        # Párrafos normales
        clean = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html.escape(sline))
        clean = re.sub(r'`(.*?)`', r'<code>\1</code>', clean)
        html_lines.append(f"<p>{clean}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_table:
        html_lines.append("</tbody></table>")

    body_html = "\n".join(html_lines)

    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
  @page {{
    size: A4;
    margin: 20mm 15mm 20mm 15mm;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: #1e293b;
    line-height: 1.6;
    font-size: 13px;
    padding: 0;
    margin: 0;
  }}
  h1 {{
    font-size: 22px;
    color: #0f172a;
    border-bottom: 3px solid #0284c7;
    padding-bottom: 8px;
    margin-top: 0;
  }}
  h2 {{
    font-size: 16px;
    color: #0369a1;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
    margin-top: 24px;
  }}
  h3 {{
    font-size: 14px;
    color: #334155;
    margin-top: 16px;
    margin-bottom: 6px;
  }}
  p {{
    margin: 8px 0;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 16px 0;
    font-size: 12px;
  }}
  th, td {{
    border: 1px solid #cbd5e1;
    padding: 8px 10px;
    text-align: left;
  }}
  th {{
    background-color: #f8fafc;
    color: #0f172a;
    font-weight: 600;
  }}
  tr:nth-child(even) {{
    background-color: #f1f5f9;
  }}
  code {{
    background-color: #e2e8f0;
    padding: 2px 5px;
    border-radius: 4px;
    font-family: Menlo, Monaco, Consolas, monospace;
    font-size: 11px;
  }}
  ul {{
    margin: 6px 0 12px 20px;
    padding: 0;
  }}
  li {{
    margin-bottom: 4px;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 20px 0;
  }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
    return full_html

def convert_md_to_pdf(md_path: str, pdf_path: str = None) -> str:
    if not pdf_path:
        pdf_path = os.path.splitext(md_path)[0] + ".pdf"
    
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    title = os.path.splitext(os.path.basename(md_path))[0]
    html_content = markdown_to_html(md_content, title=title)
    
    temp_html = tempfile.NamedTemporaryFile(suffix=".html", delete=False).name
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    cmd = [
        CHROME_BIN,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={pdf_path}",
        temp_html
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    if os.path.exists(temp_html):
        try:
            os.remove(temp_html)
        except Exception:
            pass

    return pdf_path

if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = convert_md_to_pdf(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
        print(f"PDF generado exitosamente: {out}")
