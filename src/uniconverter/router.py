"""Router: picks the engine for a source/target pair.

plan() returns a short label naming the engine plus a thunk that performs the
conversion; convert_one() simply runs it. The label feeds --dry-run and --verbose.
"""

import importlib.util
import tempfile
from pathlib import Path

from .engines import (
    documents,
    ebooks,
    images,
    media,
    models,
    office,
    pdf,
    subtitles,
    text,
    tools,
)
from .engines.tools import need, pip_hint
from .errors import ConvError
from .formats import (
    AUDIO_EXT,
    EBOOK_EXT,
    HIDDEN_ALIASES,
    HTML_EXT,
    IMAGE_EXT,
    IMAGE_OUT,
    IMAGE_RAW_EXT,
    IMAGE_VECTOR_IN,
    MD_EXT,
    MODEL_EXT,
    MODEL_OUT,
    OFFICE_EXT,
    OUT_ALIASES,
    PANDOC_ONLY_EXT,
    SUB_EXT,
    VIDEO_ALIASES,
    VIDEO_EXT,
    VIDEO_OUT,
    VIDEO_SUB_SRC,
    ext_of,
)

TEXTUTIL_SOURCES = ("docx", "doc", "odt", "rtf")


def _via_temp(src, dst, opts, mid_ext, first, second):
    """Two-step conversion through a temporary intermediate file."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / (src.stem + "." + mid_ext)
        first(src, tmp, opts)
        return second(tmp, dst, opts)


def output_path(src: Path, dst: Path):
    """The file really written: pseudo targets such as .alac end up as .m4a."""
    de = ext_of(dst)
    if de not in OUT_ALIASES:
        return dst
    p = dst.with_suffix("." + OUT_ALIASES[de])
    if p.resolve() == src.resolve():
        p = p.with_name(f"{p.stem}-{de}{p.suffix}")
    return p


def _image_label(se, de):
    reader = ("PyMuPDF" if se == "svg" else "Ghostscript" if se in IMAGE_VECTOR_IN
              else "sips" if se in IMAGE_RAW_EXT | {"jxl", "exr", "pict", "pct"} else "")
    writer = ("cjxl" if de == "jxl" and tools.CJXL else "sips" if de in ("exr", "psd")
              else "ImageMagick" if de in ("hdr", "dpx", "xpm", "jxl") else "Pillow")
    return f"{reader} + {writer}" if reader else writer


def plan(src: Path, dst: Path, opts):
    """(engine label, thunk) for src → dst, or ConvError if there is no route."""
    se, de = ext_of(src), ext_of(dst)

    if de in OUT_ALIASES:                    # .alac → .m4a, .3gp-h263 → .3gp
        real = output_path(src, dst)
        if de in VIDEO_ALIASES and se in VIDEO_EXT:
            return "ffmpeg", lambda: media.video_convert(src, real, opts, fmt=de)
        if de not in VIDEO_ALIASES and se in AUDIO_EXT | VIDEO_EXT:
            return "ffmpeg", lambda: media.audio_to_audio(src, real, opts, fmt=de)

    if se in IMAGE_EXT and de in images.image_out_formats():
        return _image_label(se, de), lambda: images.img_to_img(src, dst, opts)
    if se in IMAGE_EXT and de == "pdf":
        label = "Ghostscript" if se in IMAGE_VECTOR_IN and tools.GS else "PyMuPDF"
        return label, lambda: images.imgs_to_pdf([src], dst, opts)
    if se == "gif" and de in VIDEO_OUT:
        return "ffmpeg", lambda: media.video_convert(src, dst, opts)

    if se in EBOOK_EXT and de in ebooks.ebook_targets(se):
        return (ebooks.from_ebook_route(se, de),
                lambda: ebooks.from_ebook(src, dst, opts))
    if de in ebooks.doc_ebook_targets(se):
        return ebooks.to_ebook_route(se, de), lambda: ebooks.to_ebook(src, dst, opts)
    if se in PANDOC_ONLY_EXT:
        if de == "pdf":
            label = "pandoc + typst" if tools.TYPST else "pandoc + Chrome headless"
            return label, lambda: documents.pandoc_pdf(src, dst, opts)
        if de in documents.WRITERS:
            return "pandoc", lambda: documents.pandoc_convert(src, dst, opts)

    if se == "pdf":
        if de in IMAGE_OUT:
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
        if de in IMAGE_OUT:
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
        if de == "txt":
            return "pandoc", lambda: documents.pandoc_convert(src, dst, opts)

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
    if se in VIDEO_EXT and (de in VIDEO_OUT | AUDIO_EXT or de == "gif"):
        return "ffmpeg", lambda: media.video_convert(src, dst, opts)
    if se in SUB_EXT and de in SUB_EXT:
        return "ffmpeg", lambda: subtitles.sub_convert(src, dst, opts)
    if se in VIDEO_SUB_SRC and de in SUB_EXT:
        return "ffmpeg", lambda: subtitles.video_to_sub(src, dst, opts)

    if se in MODEL_EXT and de in MODEL_OUT:
        return "Blender", lambda: models.model_convert(src, dst, opts)

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
        t |= (images.image_out_formats() - {se}) | {"pdf"}
        if se == "gif" and tools.FFMPEG:
            t |= {"mp4", "webm", "mov", "avi"} & media.video_out_formats()
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
        if tools.PANDOC:
            t |= {"txt"}
    if se in HTML_EXT:
        t |= {"pdf", "md", "docx", "rtf", "txt", "odt"}
    if se == "txt":
        t |= {"pdf", "docx", "rtf", "html"}
    if se in PANDOC_ONLY_EXT and tools.PANDOC:
        t |= {"md", "html", "docx", "odt", "rtf", "txt", "epub"}
        if tools.TYPST or tools.CHROME:
            t |= {"pdf"}
    t |= ebooks.doc_ebook_targets(se)
    if se in EBOOK_EXT:
        t |= ebooks.ebook_targets(se)
    if se in AUDIO_EXT:
        t |= media.audio_out_formats() - {se}
    if se in VIDEO_EXT and tools.FFMPEG:
        t |= (media.video_out_formats() - {se}) | {"gif"} | media.audio_out_formats()
    if se in SUB_EXT and tools.FFMPEG:
        t |= SUB_EXT - {se}
    if se in VIDEO_SUB_SRC and tools.FFMPEG and tools.FFPROBE:
        t |= SUB_EXT                          # pull out the subtitle track
    if se in MODEL_EXT and tools.BLENDER:
        t |= MODEL_OUT - {se}
    return sorted(t - HIDDEN_ALIASES)       # hide alias extensions
