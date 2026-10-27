"""Text documents through pandoc (and typst): content survives, nothing is fetched."""

import json
import zipfile

import pytest
from conftest import EXPECTED, MARKDOWN, assert_text, needs_pandoc, needs_typst

from uniconverter import router
from uniconverter.engines import documents, tools

RST = """Chapter One
===========

Umlauts äöüß and a **bold** sentence.

=====  ======
Fruit  Colour
=====  ======
Apple  Green
=====  ======

Chapter Two
-----------

Second paragraph: Straße und Größe.
"""
ORG = """* Chapter One
Umlauts äöüß and a *bold* sentence.

| Fruit | Colour |
|-------+--------|
| Apple | Green  |

** Chapter Two
Second paragraph: Straße und Größe.
"""
TEX = r"""\documentclass{article}
\begin{document}
\section{Chapter One}
Umlauts äöüß and a \textbf{bold} sentence.

\begin{tabular}{ll}
Fruit & Colour \\
Apple & Green \\
\end{tabular}

\subsection{Chapter Two}
Second paragraph: Straße und Größe.
\end{document}
"""
IPYNB = json.dumps({
    "cells": [{"cell_type": "markdown", "metadata": {}, "source": MARKDOWN.splitlines(True)},
              {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
               "source": ["print('hello')\n"]}],
    "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3",
                                "language": "python"}},
    "nbformat": 4, "nbformat_minor": 5}, ensure_ascii=False)
SOURCES = {"md": MARKDOWN, "rst": RST, "org": ORG, "tex": TEX, "ipynb": IPYNB}


@pytest.fixture
def doc(tmp_path):
    def make(ext):
        p = tmp_path / f"doc.{ext}"
        p.write_text(SOURCES[ext], encoding="utf-8")
        return p
    return make


def text_targets(ext):
    t = set(router.possible_targets(ext)) & {"md", "html", "docx", "odt", "rtf", "txt",
                                             "epub", "pdf"}
    if not tools.TYPST:
        t.discard("pdf")              # Chrome printing is covered in test_integration
    return sorted(t)


@needs_pandoc
@pytest.mark.parametrize("source", ["md", "rst", "org", "tex", "ipynb"])
def test_text_formats(doc, tmp_path, opts, source):
    src = doc(source)
    for target in text_targets(source):
        out = tmp_path / f"{source}-to.{target}"
        router.convert_one(src, out, opts())
        assert_text(out)


@needs_pandoc
def test_md_tables_stay_tables(doc, tmp_path, opts):
    src = doc("md")
    for ext, marker, part in (("docx", "<w:tbl>", "word/document.xml"),
                              ("odt", "<table:table ", "content.xml")):
        out = tmp_path / f"table.{ext}"
        router.convert_one(src, out, opts())
        with zipfile.ZipFile(out) as z:
            assert marker in z.read(part).decode()


@needs_pandoc
@pytest.mark.parametrize("source", ["docx", "odt", "rtf"])
def test_office_to_markdown_via_pandoc(doc, tmp_path, opts, source):
    mid = tmp_path / f"mid.{source}"
    router.convert_one(doc("md"), mid, opts())
    out = tmp_path / f"from-{source}.md"
    assert router.plan(mid, out, opts())[0] == "pandoc"
    router.convert_one(mid, out, opts())
    assert_text(out)


@needs_pandoc
def test_epub_gets_the_file_name_as_title(tmp_path, opts):
    src = tmp_path / "My Notes.md"
    src.write_text(MARKDOWN, encoding="utf-8")
    out = tmp_path / "book.epub"
    router.convert_one(src, out, opts())
    with zipfile.ZipFile(out) as z:
        opf = next(z.read(n).decode() for n in z.namelist() if n.endswith(".opf"))
    assert ">My Notes</dc:title>" in opf and "UNTITLED" not in opf


@needs_typst
def test_pdf_is_typeset_by_typst(doc, tmp_path, opts):
    out = tmp_path / "doc.pdf"
    router.convert_one(doc("md"), out, opts())
    pdf = tools.load_fitz().open(str(out))
    assert "typst" in (pdf.metadata.get("creator", "") + pdf.metadata.get("producer", "")).lower()
    width = pdf[0].rect.width
    assert abs(width - (612 if tools.letter_paper() else 595)) < 2      # Letter or A4
    assert_text(out)


@needs_typst
@pytest.mark.skipif(not tools.CHROME, reason="no Chrome for the fallback")
def test_pdf_falls_back_to_chrome(doc, tmp_path, opts, monkeypatch):
    monkeypatch.setattr(tools, "TYPST", "/usr/bin/false")       # typst "broken"
    out = tmp_path / "fallback.pdf"
    router.convert_one(doc("md"), out, opts())
    pdf = tools.load_fitz().open(str(out))
    assert "typst" not in str(pdf.metadata).lower()
    assert_text(out, EXPECTED[:2])


REMOTE_MD = """# Remote

![remote picture]({url}/image.png)

<img src="{url}/raw.png">

```{{=typst}}
#image("{url}/typst.png")
```

Still converted.
"""


@needs_pandoc
@pytest.mark.parametrize("target", ["docx", "epub", "html", "odt"])
def test_pandoc_never_fetches_remote_content(tmp_path, opts, web_server, target):
    url, hits = web_server
    src = tmp_path / "remote.md"
    src.write_text(REMOTE_MD.format(url=url), encoding="utf-8")
    out = tmp_path / f"remote.{target}"
    if target == "html":
        documents.pandoc_convert(src, out, opts())         # the pandoc route to HTML
    else:
        router.convert_one(src, out, opts())
    assert out.exists() and out.stat().st_size > 0
    assert hits == []
