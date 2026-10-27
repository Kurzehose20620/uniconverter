"""Text documents through pandoc: md, docx, odt, rtf, html, epub, rst, org, tex, ipynb.

pandoc always runs with --sandbox (it may only read the input file) plus the filter
in filters/offline.lua, which embeds images next to the document but never fetches
remote ones. PDFs are typeset in two steps – pandoc writes Typst, typst compiles it
inside a temporary folder – because pandoc's own PDF pipeline is not sandboxed.
"""

import tempfile
from importlib.resources import as_file, files
from pathlib import Path

from ..errors import ConvError
from ..formats import HTML_EXT, MD_EXT, ext_of
from . import tools
from .tools import need, run

PANDOC_HINT = "brew install pandoc"
READERS = {"md": "markdown", "markdown": "markdown", "docx": "docx", "odt": "odt",
           "html": "html", "htm": "html", "rst": "rst", "org": "org", "tex": "latex",
           "latex": "latex", "ipynb": "ipynb", "epub": "epub", "rtf": "rtf"}
WRITERS = {"md": "gfm", "markdown": "gfm", "docx": "docx", "odt": "odt", "html": "html",
           "htm": "html", "epub": "epub3", "rtf": "rtf", "txt": "plain"}
FILTER = files(__package__).joinpath("filters", "offline.lua")


def _pandoc(args, src: Path, cwd=None, err_hint=""):
    need(tools.PANDOC, "pandoc", PANDOC_HINT)
    with as_file(FILTER) as lua:
        run([tools.PANDOC, "--sandbox", "--lua-filter", lua, *args], err_hint=err_hint,
            cwd=cwd, env={"UNICONVERTER_BASE": str(src.resolve().parent)})


def pandoc_convert(src: Path, dst: Path, opts):
    """Text formats among each other (md, docx, odt, html, epub, rtf, rst, …)."""
    se, de = ext_of(src), ext_of(dst)
    args = [src, "-f", READERS[se], "-t", WRITERS[de], "-o", dst]
    if de in MD_EXT:
        # images (from docx/odt/epub) go next to the Markdown file
        args += ["--extract-media", dst.parent / f"{dst.stem}_media"]
    elif de != "txt":
        args += ["-s"]
        if de in HTML_EXT:
            args += ["--embed-resources"]       # one file, images embedded
    _pandoc(args, src)
    if not dst.exists() or dst.stat().st_size == 0:
        raise ConvError(f"pandoc produced no .{de}")


def typst_pdf(src: Path, dst: Path, opts):
    """Typeset a text document as PDF: pandoc → Typst, then typst compile (offline)."""
    need(tools.PANDOC, "pandoc", PANDOC_HINT)
    need(tools.TYPST, "typst", "brew install typst")
    paper = "us-letter" if tools.letter_paper() else "a4"
    dst = dst.resolve()
    with tempfile.TemporaryDirectory() as td:
        _pandoc([src.resolve(), "-f", READERS[ext_of(src)], "-t", "typst", "-s",
                 "-o", "doc.typ", "--extract-media", "media", "-V", f"papersize={paper}"],
                src, cwd=td)
        # --root: the document may only read files from this temporary folder
        run([tools.TYPST, "compile", "--root", td, "doc.typ", dst], cwd=td,
            err_hint="typst could not typeset the document")
    if not dst.exists() or dst.stat().st_size == 0:
        raise ConvError("typst produced no PDF")


def pandoc_pdf(src: Path, dst: Path, opts):
    """rst/org/tex/ipynb → PDF: typst when installed, otherwise HTML printed by Chrome."""
    from .text import chrome_html_to_pdf
    if tools.TYPST:
        try:
            return typst_pdf(src, dst, opts)
        except ConvError as e:
            if not tools.CHROME:
                raise
            print(f"  ({e} – printing with Chrome instead)")
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        pandoc_convert(src, tmp_html, opts)
        chrome_html_to_pdf(tmp_html, dst)
