"""Markdown, HTML and plain text: python-markdown, Chrome headless, pandoc/typst, html2text."""

import html
import subprocess
import tempfile
import time
from pathlib import Path

from ..errors import ConvError
from . import tools
from .office import textutil_convert
from .tools import need, pip_hint, run

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{title}</title>
<style>
@page {{ margin: 2cm; }}
body {{ font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       font-size: 11pt; line-height: 1.55; color: #1a1a1a;
       max-width: 48em; margin: 2em auto; padding: 0 1em; }}
h1, h2, h3 {{ line-height: 1.25; margin-top: 1.4em; }}
h1 {{ font-size: 1.7em; border-bottom: 1px solid #ddd; padding-bottom: .3em; }}
h2 {{ font-size: 1.35em; }}
code {{ font-family: "SF Mono", Menlo, monospace; font-size: .9em;
        background: #f2f2f4; padding: .15em .35em; border-radius: 4px; }}
pre {{ background: #f6f8fa; padding: 1em; border-radius: 8px;
       overflow-x: auto; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ border-left: 4px solid #d0d0d6; margin-left: 0;
              padding-left: 1em; color: #555; }}
table {{ border-collapse: collapse; margin: 1em 0; }}
th, td {{ border: 1px solid #ccc; padding: .4em .7em; }}
th {{ background: #f2f2f4; }}
img {{ max-width: 100%; }}
a {{ color: #0b5fff; }}
</style></head><body>
{body}
</body></html>
"""


def md_to_html_str(src: Path):
    try:
        import markdown
    except ImportError:
        raise ConvError(f"python-markdown is missing – install with: {pip_hint('markdown')}")
    body = markdown.markdown(src.read_text(encoding="utf-8"),
                             extensions=["extra", "sane_lists"])
    return HTML_TEMPLATE.format(title=html.escape(src.stem), body=body)


def md_to_html(src: Path, dst: Path, opts):
    dst.write_text(md_to_html_str(src), encoding="utf-8")


def txt_to_html_str(src: Path):
    style = "white-space: pre-wrap; font-family: SF Mono, Menlo, monospace; font-size: 10pt;"
    body = (f"<pre style='{style}'>"
            + html.escape(src.read_text(encoding="utf-8")) + "</pre>")
    return HTML_TEMPLATE.format(title=html.escape(src.stem), body=body)


# Chrome must not talk to the network while printing: no background services,
# and every host name resolves to nothing, so remote images or scripts in a
# document are simply not loaded. Local file:// content is unaffected.
CHROME_OFFLINE_FLAGS = [
    "--host-resolver-rules=MAP * ~NOTFOUND",
    "--disable-background-networking", "--disable-component-update",
    "--disable-sync", "--disable-default-apps", "--no-pings",
    "--metrics-recording-only", "--safebrowsing-disable-auto-update",
]


def chrome_html_to_pdf(html_file: Path, dst: Path):
    need(tools.CHROME, "Chrome (headless PDF printing)", "brew install --cask google-chrome")
    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.Popen(
            [tools.CHROME, "--headless", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--disable-extensions",
             "--hide-scrollbars", f"--user-data-dir={td}/chrome-profile",
             "--no-pdf-header-footer", *CHROME_OFFLINE_FLAGS,
             f"--print-to-pdf={dst}", html_file.resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Chrome often does not exit by itself after printing: wait until the
        # PDF is complete (size stable), then terminate the process.
        deadline = time.time() + 120
        stable_since = None
        last_size = -1
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            size = dst.stat().st_size if dst.exists() else -1
            if size > 0 and size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since > 1.5:
                    break
            else:
                stable_since = None
            last_size = size
            time.sleep(0.3)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    if not dst.exists() or dst.stat().st_size == 0:
        raise ConvError("Chrome did not produce a PDF")


def md_to_pdf(src: Path, dst: Path, opts):
    if tools.PANDOC and tools.TYPST:
        run([tools.PANDOC, str(src), "-o", str(dst), "--pdf-engine=typst"])
        return
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        tmp_html.write_text(md_to_html_str(src), encoding="utf-8")
        chrome_html_to_pdf(tmp_html, dst)


def md_to_office(src: Path, dst: Path, opts):
    if tools.PANDOC:
        run([tools.PANDOC, str(src), "-o", str(dst)])
        return
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        tmp_html.write_text(md_to_html_str(src), encoding="utf-8")
        textutil_convert(tmp_html, dst, opts)


def html_to_pdf(src: Path, dst: Path, opts):
    chrome_html_to_pdf(src, dst)


def html_to_md(src: Path, dst: Path, opts):
    try:
        import html2text
    except ImportError:
        raise ConvError(f"html2text is missing – install with: {pip_hint('html2text')}")
    h = html2text.HTML2Text()
    h.body_width = 0
    dst.write_text(h.handle(src.read_text(encoding="utf-8")), encoding="utf-8")


def txt_to_pdf(src: Path, dst: Path, opts):
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        tmp_html.write_text(txt_to_html_str(src), encoding="utf-8")
        chrome_html_to_pdf(tmp_html, dst)
