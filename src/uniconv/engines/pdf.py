"""PDF → Bilder (PyMuPDF), → Markdown (pymupdf4llm), → Text, → DOCX (pdf2docx, optional)."""

from pathlib import Path

from ..errors import ConvError
from ..formats import ext_of
from . import tools
from .images import img_to_img
from .tools import need, pip_hint


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
            tmp = out.with_suffix(".uniconv-tmp.png")
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
    md = pymupdf4llm.to_markdown(str(src), **kwargs)
    dst.write_text(md, encoding="utf-8")


def pdf_to_txt(src: Path, dst: Path, opts):
    fitz = tools.load_fitz()
    need(fitz, "PyMuPDF", pip_hint("pymupdf"))
    doc = fitz.open(str(src))
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
