"""PDF → Bilder (PyMuPDF), → Markdown (pymupdf4llm), → Text, → DOCX (pdf2docx, optional).

Gescannte Seiten ohne Textebene werden vor Markdown/Text-Ausgabe per Texterkennung
ergänzt (Tesseract ist in PyMuPDF eingebaut, es braucht nur die Sprachdaten).
"""

import contextlib
import io
from pathlib import Path

from ..errors import ConvError
from ..formats import ext_of
from . import tools
from .images import img_to_img
from .tools import need, pip_hint

OCR_DPI = 300
OCR_MIN_CHARS = 20           # weniger Zeichen auf einer Seite = keine Textebene
OCR_PREFERRED = ["eng", "deu", "fra", "spa", "ita", "nld", "por"]
OCR_HINT = "brew install tesseract  (dazu tesseract-lang für Deutsch u. a.)"


@contextlib.contextmanager
def _quiet_pymupdf():
    """pymupdf4llm meldet seine Parser-Statuszeilen auf stdout – für Nutzer nur Rauschen."""
    fitz = tools.load_fitz()
    sink = io.StringIO()
    fitz.set_messages(stream=sink)
    try:
        with contextlib.redirect_stdout(sink):
            yield
    finally:
        fitz.set_messages(fd=1)


def _ocr_language(tessdata, wanted=None):
    avail = tools.tessdata_languages(tessdata)
    if wanted:
        missing = [lang for lang in wanted.split("+") if lang not in avail]
        if missing:
            raise ConvError(f"Tesseract-Sprachdaten fehlen: {', '.join(missing)} "
                            f"(vorhanden: {', '.join(avail) or 'keine'})")
        return wanted
    langs = [lang for lang in OCR_PREFERRED if lang in avail] or avail
    return "+".join(langs)


def _pages_without_text(doc):
    return {i for i, page in enumerate(doc)
            if len(page.get_text().strip()) < OCR_MIN_CHARS}


def ocr_pages(doc, pages, opts):
    """Neues Dokument, in dem die angegebenen Seiten eine per OCR erzeugte Textebene haben."""
    fitz = tools.load_fitz()
    tessdata = tools.find_tessdata()
    need(tessdata, "Texterkennung (Tesseract-Sprachdaten) für gescannte PDFs", OCR_HINT)
    lang = _ocr_language(tessdata, getattr(opts, "ocr_lang", None))
    print(f"  (Texterkennung für {len(pages)} von {len(doc)} Seiten, Sprache: {lang})")
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
    """PDF öffnen; Seiten ohne Textebene (Scans) bekommen per Texterkennung eine."""
    fitz = tools.load_fitz()
    need(fitz, "PyMuPDF", pip_hint("pymupdf"))
    doc = fitz.open(str(src))
    pages = _pages_without_text(doc)
    if not pages:
        return doc
    if not tools.find_tessdata():
        if len(pages) == len(doc):
            raise ConvError("PDF enthält keinen Text (Scan?) – Texterkennung braucht "
                            f"Tesseract-Sprachdaten: {OCR_HINT}")
        return doc  # teils Scan, teils Text: das Vorhandene nutzen
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
        print(f"  ({len(written)} Seiten: {written[0].name} … {written[-1].name})")


def pdf_to_md(src: Path, dst: Path, opts):
    try:
        import pymupdf4llm
    except ImportError:
        raise ConvError(f"pymupdf4llm fehlt – Installation: {pip_hint('pymupdf4llm')}")
    kwargs = {}
    if opts.extract_images:
        img_dir = dst.parent / f"{dst.stem}_bilder"
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
        raise ConvError("pdf2docx fehlt (optional, ~100 MB) – "
                        f"Installation: {pip_hint('pdf2docx')}")
    cv = Converter(str(src))
    cv.convert(str(dst))
    cv.close()
