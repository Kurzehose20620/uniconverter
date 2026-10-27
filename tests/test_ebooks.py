"""E-books through calibre (and pandoc): the text survives every route."""

import shutil
import zipfile

import pytest
from conftest import MARKDOWN, assert_text, make_opts, needs_calibre, needs_pandoc
from PIL import Image
from test_documents import RST

from uniconverter import router
from uniconverter.engines import tools

pytestmark = [needs_calibre, needs_pandoc]


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    """An EPUB made from Markdown, plus every e-book format calibre makes from it."""
    d = tmp_path_factory.mktemp("books")
    md = d / "book.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    epub = d / "book.epub"
    router.convert_one(md, epub, make_opts())
    return d, epub


def test_markdown_to_epub(book):
    assert_text(book[1])


@pytest.mark.parametrize("target", ["mobi", "azw3", "fb2", "lit", "lrf", "pdf", "docx",
                                    "txt", "rtf", "md", "html", "odt"])
def test_epub_to(book, tmp_path, opts, target):
    out = tmp_path / f"book.{target}"
    router.convert_one(book[1], out, opts())
    assert_text(out)


@pytest.mark.parametrize("source", ["mobi", "azw3", "fb2", "azw"])
@pytest.mark.parametrize("target", ["epub", "txt", "md"])
def test_ebook_sources(book, tmp_path, opts, source, target):
    mid = tmp_path / f"mid.{source}"
    if source == "azw":                    # .azw is the old Kindle name for MOBI
        router.convert_one(book[1], tmp_path / "mid.mobi", opts())
        shutil.copy(tmp_path / "mid.mobi", mid)
    else:
        router.convert_one(book[1], mid, opts())
    out = tmp_path / f"from-{source}.{target}"
    router.convert_one(mid, out, opts())
    assert_text(out)


@pytest.mark.parametrize("source, target", [("md", "mobi"), ("md", "azw3"), ("rst", "fb2"),
                                            ("docx", "epub"), ("docx", "mobi"),
                                            ("html", "mobi"), ("txt", "epub")])
def test_documents_to_ebooks(tmp_path, opts, source, target):
    md = tmp_path / "doc.md"
    md.write_text(MARKDOWN, encoding="utf-8")
    src = tmp_path / f"doc.{source}"
    if source == "rst":
        src.write_text(RST, encoding="utf-8")
    elif source != "md":
        router.convert_one(md, src, opts())
    out = tmp_path / f"out.{target}"
    router.convert_one(src, out, opts())
    assert_text(out)


def test_pdf_to_ebook(book, tmp_path, opts):
    pdf = tmp_path / "book.pdf"
    router.convert_one(book[1], pdf, opts())
    out = tmp_path / "from-pdf.epub"
    router.convert_one(pdf, out, opts())
    assert_text(out, ["Straße und Größe"])


@pytest.fixture
def comic(tmp_path):
    cbz = tmp_path / "comic.cbz"
    with zipfile.ZipFile(cbz, "w") as z:
        for i, colour in enumerate(((220, 30, 30), (30, 160, 30), (30, 30, 220)), 1):
            page = tmp_path / f"page{i}.png"
            Image.new("RGB", (400, 600), colour).save(page)
            z.write(page, f"page{i:02d}.png")
    return cbz


def test_comic_to_pdf(comic, tmp_path, opts):
    out = tmp_path / "comic.pdf"
    router.convert_one(comic, out, opts())
    assert len(tools.load_fitz().open(str(out))) >= 3


def test_comic_to_epub(comic, tmp_path, opts):
    out = tmp_path / "comic.epub"
    router.convert_one(comic, out, opts())
    with zipfile.ZipFile(out) as z:
        pics = [n for n in z.namelist() if n.lower().endswith((".png", ".jpg", ".jpeg"))]
    assert len(pics) >= 3


def test_calibre_does_not_fetch_remote_images(tmp_path, opts, web_server):
    """An HTML/e-book source with remote references converts without any request."""
    url, hits = web_server
    html = tmp_path / "remote.html"
    html.write_text(f"<html><body><h1>Remote</h1><p>Text</p><img src='{url}/x.png'>"
                    f"<link rel='stylesheet' href='{url}/s.css'></body></html>")
    for target in ("mobi", "pdf"):
        router.convert_one(html, tmp_path / f"remote.{target}", opts())
    assert hits == []
