"""PDF → images (PyMuPDF), → Markdown (pymupdf4llm), → text, → DOCX (pdf2docx, optional).

Scanned pages without a text layer get one through OCR before Markdown/text
output (Tesseract is built into PyMuPDF; only the language data is needed).
"""

import contextlib
import io
import locale
import re
import subprocess
from pathlib import Path

from ..errors import ConvError
from ..formats import ext_of
from . import tools
from .images import img_to_img
from .tools import need, pip_hint

OCR_DPI = 300
OCR_MIN_CHARS = 20           # fewer characters on a page = no text layer
OCR_MAX_LANGS = 3            # more languages make Tesseract slower and less accurate
OCR_HINT = "brew install tesseract  (plus tesseract-lang for languages other than English)"
# ISO 639-1 (system language) → Tesseract language code
LANG_MAP = {"en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita", "nl": "nld",
            "pt": "por", "pl": "pol", "sv": "swe", "da": "dan", "nb": "nor", "no": "nor",
            "fi": "fin", "cs": "ces", "tr": "tur", "ru": "rus", "uk": "ukr", "el": "ell",
            "hu": "hun", "ro": "ron", "ja": "jpn", "ko": "kor", "zh": "chi_sim", "ar": "ara",
            "he": "heb", "hr": "hrv", "sk": "slk", "sl": "slv", "bg": "bul", "ca": "cat"}


@contextlib.contextmanager
def _quiet_pymupdf():
    """pymupdf4llm prints parser status lines to stdout; for users that is just noise."""
    fitz = tools.load_fitz()
    sink = io.StringIO()
    fitz.set_messages(stream=sink)
    try:
        with contextlib.redirect_stdout(sink):
            yield
    finally:
        fitz.set_messages(fd=1)


def _system_languages():
    """Tesseract codes for the user's preferred languages (macOS setting, else locale)."""
    codes = []
    try:
        out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"],
                             capture_output=True, text=True, timeout=2).stdout
        codes = re.findall(r'"([a-z]{2,3})(?:[-_][^"]*)?"', out)
    except (OSError, subprocess.SubprocessError):
        pass
    if not codes:
        loc = locale.getlocale()[0] or ""
        codes = [loc[:2].lower()] if loc else []
    langs = []
    for c in codes:
        t = LANG_MAP.get(c)
        if t and t not in langs:
            langs.append(t)
    return langs


def default_ocr_languages(tessdata):
    """Languages used when --ocr-lang is not given: installed system languages plus English."""
    avail = tools.tessdata_languages(tessdata)
    wanted = _system_languages()
    if "eng" not in wanted:
        wanted.append("eng")
    langs = [lang for lang in wanted if lang in avail][:OCR_MAX_LANGS]
    return langs or avail[:1]


def _ocr_language(tessdata, wanted=None):
    if not wanted:
        return "+".join(default_ocr_languages(tessdata))
    avail = tools.tessdata_languages(tessdata)
    missing = [lang for lang in wanted.split("+") if lang not in avail]
    if missing:
        shown = ", ".join(avail[:8]) + (f" … ({len(avail)} installed)" if len(avail) > 8 else "")
        raise ConvError(f"Tesseract language data missing: {', '.join(missing)} "
                        f"(available: {shown or 'none'})")
    return wanted


def _pages_without_text(doc):
    return {i for i, page in enumerate(doc)
            if len(page.get_text().strip()) < OCR_MIN_CHARS}


def ocr_pages(doc, pages, opts):
    """New document in which the given pages carry an OCR-generated text layer."""
    fitz = tools.load_fitz()
    tessdata = tools.find_tessdata()
    need(tessdata, "OCR (Tesseract language data) for scanned PDFs", OCR_HINT)
    lang = _ocr_language(tessdata, getattr(opts, "ocr_lang", None))
    print(f"  (OCR for {len(pages)} of {len(doc)} pages, language: {lang})")
    out = fitz.open()
    for i, page in enumerate(doc):
        if i in pages:
            pix = page.get_pixmap(dpi=OCR_DPI)
            pdfbytes = pix.pdfocr_tobytes(language=lang, tessdata=tessdata)
            out.insert_pdf(fitz.open("pdf", pdfbytes))
        else:
            out.insert_pdf(doc, from_page=i, to_page=i)
    return out


def open_with_text(src: Path, opts):
    """Open a PDF; pages without a text layer (scans) get one through OCR."""
    fitz = tools.load_fitz()
    need(fitz, "PyMuPDF", pip_hint("pymupdf"))
    doc = fitz.open(str(src))
    pages = _pages_without_text(doc)
    if not pages:
        return doc
    if not tools.find_tessdata():
        if len(pages) == len(doc):
            raise ConvError("the PDF contains no text (a scan?) – OCR needs Tesseract "
                            f"language data: {OCR_HINT}")
        return doc  # partly scanned, partly text: use what is there
    return ocr_pages(doc, pages, opts)


def pdf_to_images(src: Path, dst: Path, opts):
    fitz = tools.load_fitz()
    need(fitz, "PyMuPDF", pip_hint("pymupdf"))
    doc = fitz.open(str(src))
    zoom = opts.dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    de = ext_of(dst)
    written = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(matrix=mat)
        if len(doc) == 1:
            out = dst
        else:
            out = dst.with_name(f"{dst.stem}-{i + 1:02d}{dst.suffix}")
            if out.exists() and not getattr(opts, "force", False):
                raise ConvError(f"{out.name} already exists (--force to overwrite)")
        if de in ("jpg", "jpeg"):
            pix.save(str(out), jpg_quality=opts.quality)
        elif de == "png":
            pix.save(str(out))
        else:
            tmp = out.with_suffix(".uniconverter-tmp.png")
            pix.save(str(tmp))
            img_to_img(tmp, out, opts)
            tmp.unlink()
        written.append(out)
    if len(written) > 1:
        print(f"  ({len(written)} pages: {written[0].name} … {written[-1].name})")


def pdf_to_md(src: Path, dst: Path, opts):
    try:
        import pymupdf4llm
    except ImportError:
        raise ConvError(f"pymupdf4llm is missing – install with: {pip_hint('pymupdf4llm')}")
    kwargs = {}
    if opts.extract_images:
        img_dir = dst.parent / f"{dst.stem}_images"
        kwargs = {"write_images": True, "image_path": str(img_dir)}
    doc = open_with_text(src, opts)
    with _quiet_pymupdf():
        md = pymupdf4llm.to_markdown(doc, **kwargs)
    dst.write_text(md, encoding="utf-8")


def pdf_to_txt(src: Path, dst: Path, opts):
    doc = open_with_text(src, opts)
    text = "\n\n".join(page.get_text() for page in doc)
    dst.write_text(text, encoding="utf-8")


def pdf_to_docx(src: Path, dst: Path, opts):
    try:
        from pdf2docx import Converter
    except ImportError:
        raise ConvError("pdf2docx is missing (optional, ~100 MB) – "
                        f"install with: {pip_hint('pdf2docx')}")
    cv = Converter(str(src))
    cv.convert(str(dst))
    cv.close()
