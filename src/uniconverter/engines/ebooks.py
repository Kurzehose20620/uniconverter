"""E-books through calibre's ebook-convert (epub, mobi, azw3, fb2, lit, lrf, cbz/cbr).

pandoc builds the cleaner EPUB from Markdown and other text formats and reads
EPUB for md/html/odt output; calibre does everything else. calibre does not load
remote resources referenced in a book. DRM-protected books cannot be converted.
"""

import tempfile
from pathlib import Path

from ..errors import ConvError
from ..formats import COMIC_EXT, DOC_EBOOK_OUT, EBOOK_OUT, HTML_EXT, MD_EXT, PANDOC_ONLY_EXT, ext_of
from . import tools
from .documents import READERS, pandoc_convert
from .tools import need, run

CALIBRE_HINT = "brew install --cask calibre"


def calibre_convert(src: Path, dst: Path, opts):
    need(tools.EBOOK_CONVERT, "calibre", CALIBRE_HINT)
    de = ext_of(dst)
    cmd = [tools.EBOOK_CONVERT, src, dst]
    if de == "pdf":
        paper = "letter" if tools.letter_paper() else "a4"
        cmd += ["--paper-size", paper, "--pdf-default-font-size", "16"]
    if ext_of(src) in MD_EXT:
        cmd += ["--formatting-type", "markdown", "--paragraph-type", "off"]
    # PDF output (Qt WebEngine) occasionally crashes on the very first start: retry once
    attempts = 2 if de == "pdf" else 1
    for i in range(attempts):
        try:
            run(cmd, err_hint="calibre could not convert the file (DRM-protected?)")
            break
        except ConvError:
            if i + 1 == attempts:
                raise
    if not dst.exists() or dst.stat().st_size == 0:
        raise ConvError(f"calibre produced no .{de}")


def _via_epub(src: Path, dst: Path, opts, first, second):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / (src.stem + ".epub")
        first(src, tmp, opts)
        return second(tmp, dst, opts)


def to_ebook_route(se, de):
    """How a document becomes an e-book: 'pandoc', 'pandoc + calibre' or 'calibre'."""
    if de == "epub" and tools.PANDOC and se in READERS and se != "rtf":
        return "pandoc"                      # pandoc builds the cleanest EPUB
    if se in PANDOC_ONLY_EXT or (se in MD_EXT and tools.PANDOC):
        return "pandoc + calibre"            # calibre cannot read these (well)
    return "calibre"


def to_ebook(src: Path, dst: Path, opts):
    """Document (md, docx, odt, html, txt, rtf, pdf, rst, …) → e-book."""
    route = to_ebook_route(ext_of(src), ext_of(dst))
    if route == "pandoc":
        return pandoc_convert(src, dst, opts)
    if route == "pandoc + calibre":
        return _via_epub(src, dst, opts, pandoc_convert, calibre_convert)
    return calibre_convert(src, dst, opts)


def from_ebook_route(se, de):
    """How an e-book is converted: 'pandoc', 'calibre + pandoc' or 'calibre'."""
    if de in MD_EXT | HTML_EXT | {"odt"} or (not tools.EBOOK_CONVERT and se == "epub"):
        return "pandoc" if se == "epub" else "calibre + pandoc"
    return "calibre"


def from_ebook(src: Path, dst: Path, opts):
    """E-book → e-book or document. md/html/odt come from pandoc (via EPUB)."""
    route = from_ebook_route(ext_of(src), ext_of(dst))
    if route == "pandoc":
        return pandoc_convert(src, dst, opts)
    if route == "calibre + pandoc":
        return _via_epub(src, dst, opts, calibre_convert, pandoc_convert)
    return calibre_convert(src, dst, opts)


def doc_ebook_targets(se):
    """E-book targets a document format gets (depending on the installed engines)."""
    t = set()
    if se in PANDOC_ONLY_EXT:
        if tools.PANDOC:
            t |= {"epub"} | (DOC_EBOOK_OUT if tools.EBOOK_CONVERT else set())
        return t
    if se in MD_EXT | HTML_EXT | {"docx", "odt"} and tools.PANDOC:
        t.add("epub")
    if tools.EBOOK_CONVERT and se in MD_EXT | HTML_EXT | {"docx", "odt", "rtf", "txt", "pdf"}:
        t |= DOC_EBOOK_OUT
    return t


def ebook_targets(se):
    """Targets for an e-book source."""
    t = set()
    if tools.EBOOK_CONVERT:
        if se in COMIC_EXT:
            return {"epub", "mobi", "azw3", "pdf"}
        t |= EBOOK_OUT | {"pdf", "docx", "txt", "rtf"}
        if tools.PANDOC:
            t |= {"md", "html", "odt"}
    elif se == "epub" and tools.PANDOC:
        t |= {"md", "html", "odt", "docx", "txt", "rtf"}
    return t - {se}
