"""Router: picks the engine for a source/target pair.

plan() returns a short label naming the engine plus a thunk that performs the
conversion; convert_one() simply runs it. The label feeds --dry-run and --verbose.
"""

import importlib.util
import tempfile
from pathlib import Path

from .engines import images, media, office, pdf, text, tools
from .engines.media import AFCONVERT_MAP
from .engines.tools import need, pip_hint
from .errors import ConvError
from .formats import AUDIO_EXT, HTML_EXT, IMAGE_EXT, MD_EXT, OFFICE_EXT, VIDEO_EXT, ext_of

TEXTUTIL_SOURCES = ("docx", "doc", "odt", "rtf")


def _via_temp(src, dst, opts, mid_ext, first, second):
    """Two-step conversion through a temporary intermediate file."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / (src.stem + "." + mid_ext)
        first(src, tmp, opts)
        return second(tmp, dst, opts)


def plan(src: Path, dst: Path, opts):
    """(engine label, thunk) for src → dst, or ConvError if there is no route."""
    se, de = ext_of(src), ext_of(dst)

    if se in IMAGE_EXT and de in IMAGE_EXT:
        return "Pillow", lambda: images.img_to_img(src, dst, opts)
    if se in IMAGE_EXT and de == "pdf":
        return "PyMuPDF", lambda: images.imgs_to_pdf([src], dst, opts)
    if se == "gif" and de in VIDEO_EXT:
        return "ffmpeg", lambda: media.video_convert(src, dst, opts)

    if se == "pdf":
        if de in IMAGE_EXT:
            return "PyMuPDF", lambda: pdf.pdf_to_images(src, dst, opts)
        if de in MD_EXT:
            return "pymupdf4llm", lambda: pdf.pdf_to_md(src, dst, opts)
        if de == "txt":
            return "PyMuPDF", lambda: pdf.pdf_to_txt(src, dst, opts)
        if de == "docx":
            return "pdf2docx", lambda: pdf.pdf_to_docx(src, dst, opts)
        if de in HTML_EXT:
            return "pymupdf4llm + python-markdown", lambda: _via_temp(
                src, dst, opts, "md", pdf.pdf_to_md, text.md_to_html)

    if se in OFFICE_EXT:
        if de == "pdf":
            return "LibreOffice", lambda: office.office_to_pdf(src, dst, opts)
        if de in IMAGE_EXT:
            return "LibreOffice + PyMuPDF", lambda: _via_temp(
                src, dst, opts, "pdf", office.office_to_pdf, pdf.pdf_to_images)
        if de in MD_EXT:
            if tools.PANDOC and se in ("docx", "odt", "rtf"):
                label = "pandoc"
            else:
                label = "pandoc" if tools.PANDOC else "mammoth"
                if se != "docx":
                    label = "LibreOffice + " + label
            return label, lambda: office.docx_to_md(src, dst, opts)
        if de in ("txt", "html", "htm", "rtf", "docx", "doc", "odt") and se in TEXTUTIL_SOURCES:
            return "textutil", lambda: office.textutil_convert(src, dst, opts)

    if se in MD_EXT:
        if de in HTML_EXT:
            return "python-markdown", lambda: text.md_to_html(src, dst, opts)
        if de == "pdf":
            label = "pandoc + typst" if tools.PANDOC and tools.TYPST else "Chrome headless"
            return label, lambda: text.md_to_pdf(src, dst, opts)
        if de in ("docx", "rtf", "odt"):
            label = "pandoc" if tools.PANDOC else "python-markdown + textutil"
            return label, lambda: text.md_to_office(src, dst, opts)

    if se in HTML_EXT:
        if de == "pdf":
            return "Chrome headless", lambda: text.html_to_pdf(src, dst, opts)
        if de in MD_EXT:
            return "html2text", lambda: text.html_to_md(src, dst, opts)
        if de in ("docx", "rtf", "txt", "odt"):
            return "textutil", lambda: office.textutil_convert(src, dst, opts)

    if se == "txt":
        if de == "pdf":
            return "Chrome headless", lambda: text.txt_to_pdf(src, dst, opts)
        if de in ("docx", "rtf", "html", "htm"):
            return "textutil", lambda: office.textutil_convert(src, dst, opts)

    if se in AUDIO_EXT and de in AUDIO_EXT:
        label = "ffmpeg" if tools.FFMPEG else "afconvert"
        return label, lambda: media.audio_to_audio(src, dst, opts)
    if se in VIDEO_EXT and (de in VIDEO_EXT | AUDIO_EXT or de == "gif"):
        return "ffmpeg", lambda: media.video_convert(src, dst, opts)

    raise ConvError(f".{se} → .{de} is not supported "
                    "('uniconverter formats' lists every route)")


def convert_one(src: Path, dst: Path, opts):
    return plan(src, dst, opts)[1]()


def to_pdf_temp(src: Path, tmpdir: str, opts, n=1):
    """Turn any input into a temporary PDF for merging (numbered, so names never clash)."""
    if ext_of(src) == "pdf":
        return src
    out = Path(tmpdir) / f"{n:03d}-{src.stem}.pdf"
    convert_one(src, out, opts)
    return out


def merge_to_pdf(sources, dst: Path, opts):
    fitz = tools.load_fitz()
    need(fitz, "PyMuPDF", pip_hint("pymupdf"))
    out = fitz.open()
    with tempfile.TemporaryDirectory() as td:
        for n, s in enumerate(sources, 1):
            pdf_file = to_pdf_temp(s, td, opts, n)
            out.insert_pdf(fitz.open(str(pdf_file)))
        out.save(str(dst))
    print(f"✓ {len(sources)} files → {dst}")


def possible_targets(se):
    """All target extensions convert_one offers for this source extension."""
    t = set()
    if se in IMAGE_EXT:
        t |= (IMAGE_EXT - {se, "heif"}) | {"pdf"}
        if se == "gif" and tools.FFMPEG:
            t |= {"mp4", "webm", "mov"}
    if se == "pdf":
        t |= {"png", "jpg", "webp", "tiff", "md", "txt", "html"}
        if importlib.util.find_spec("pdf2docx"):
            t |= {"docx"}
    if se in OFFICE_EXT:
        t |= {"pdf", "png", "jpg"}
        if se in TEXTUTIL_SOURCES:
            t |= {"md", "txt", "html", "docx", "odt", "rtf"} - {se}
    if se in MD_EXT:
        t |= {"pdf", "html", "docx", "rtf", "odt"}
    if se in HTML_EXT:
        t |= {"pdf", "md", "docx", "rtf", "txt", "odt"}
    if se == "txt":
        t |= {"pdf", "docx", "rtf", "html"}
    if se in AUDIO_EXT:
        t |= (AUDIO_EXT if tools.FFMPEG else set(AFCONVERT_MAP)) - {se, "aif"}
    if se in VIDEO_EXT and tools.FFMPEG:
        t |= (VIDEO_EXT - {se, "m4v"}) | {"gif", "mp3", "m4a", "wav"}
    return sorted(t - {"jpeg", "tif", "htm", "aif"})  # hide alias extensions
