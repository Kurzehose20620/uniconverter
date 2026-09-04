"""Router: entscheidet anhand von Quell- und Zielendung, welche Engine konvertiert."""

import importlib.util
import tempfile
from pathlib import Path

from .engines import images, media, office, pdf, text, tools
from .engines.media import AFCONVERT_MAP
from .engines.tools import need, pip_hint
from .errors import ConvError
from .formats import AUDIO_EXT, HTML_EXT, IMAGE_EXT, MD_EXT, OFFICE_EXT, VIDEO_EXT, ext_of


def convert_one(src: Path, dst: Path, opts):
    se, de = ext_of(src), ext_of(dst)

    if se in IMAGE_EXT and de in IMAGE_EXT:
        return images.img_to_img(src, dst, opts)
    if se in IMAGE_EXT and de == "pdf":
        return images.imgs_to_pdf([src], dst, opts)
    if se == "gif" and de in VIDEO_EXT:
        return media.video_convert(src, dst, opts)

    if se == "pdf":
        if de in IMAGE_EXT:
            return pdf.pdf_to_images(src, dst, opts)
        if de in MD_EXT:
            return pdf.pdf_to_md(src, dst, opts)
        if de == "txt":
            return pdf.pdf_to_txt(src, dst, opts)
        if de == "docx":
            return pdf.pdf_to_docx(src, dst, opts)
        if de in HTML_EXT:
            with tempfile.TemporaryDirectory() as td:
                tmp_md = Path(td) / (src.stem + ".md")
                pdf.pdf_to_md(src, tmp_md, opts)
                return text.md_to_html(tmp_md, dst, opts)

    if se in OFFICE_EXT:
        if de == "pdf":
            return office.office_to_pdf(src, dst, opts)
        if de in IMAGE_EXT:
            with tempfile.TemporaryDirectory() as td:
                tmp_pdf = Path(td) / (src.stem + ".pdf")
                office.office_to_pdf(src, tmp_pdf, opts)
                return pdf.pdf_to_images(tmp_pdf, dst, opts)
        if de in MD_EXT:
            return office.docx_to_md(src, dst, opts)
        if de in ("txt", "html", "htm", "rtf", "docx", "doc", "odt") and \
                se in ("docx", "doc", "odt", "rtf"):
            return office.textutil_convert(src, dst, opts)

    if se in MD_EXT:
        if de in HTML_EXT:
            return text.md_to_html(src, dst, opts)
        if de == "pdf":
            return text.md_to_pdf(src, dst, opts)
        if de in ("docx", "rtf", "odt"):
            return text.md_to_office(src, dst, opts)

    if se in HTML_EXT:
        if de == "pdf":
            return text.html_to_pdf(src, dst, opts)
        if de in MD_EXT:
            return text.html_to_md(src, dst, opts)
        if de in ("docx", "rtf", "txt", "odt"):
            return office.textutil_convert(src, dst, opts)

    if se == "txt":
        if de == "pdf":
            return text.txt_to_pdf(src, dst, opts)
        if de in ("docx", "rtf", "html", "htm"):
            return office.textutil_convert(src, dst, opts)

    if se in AUDIO_EXT and de in AUDIO_EXT:
        return media.audio_to_audio(src, dst, opts)
    if se in VIDEO_EXT and (de in VIDEO_EXT | AUDIO_EXT or de == "gif"):
        return media.video_convert(src, dst, opts)

    raise ConvError(f".{se} → .{de} wird nicht unterstützt "
                    "('uniconv formats' zeigt alle Wege)")


def to_pdf_temp(src: Path, tmpdir: str, opts):
    """Beliebige Eingabe für den Merge in eine temporäre PDF wandeln."""
    if ext_of(src) == "pdf":
        return src
    out = Path(tmpdir) / (src.stem + "-" + str(abs(hash(str(src))) % 10000) + ".pdf")
    convert_one(src, out, opts)
    return out


def merge_to_pdf(sources, dst: Path, opts):
    fitz = tools.load_fitz()
    need(fitz, "PyMuPDF", pip_hint("pymupdf"))
    out = fitz.open()
    with tempfile.TemporaryDirectory() as td:
        for s in sources:
            pdf_file = to_pdf_temp(s, td, opts)
            out.insert_pdf(fitz.open(str(pdf_file)))
        out.save(str(dst))
    print(f"✓ {len(sources)} Dateien → {dst}")


def possible_targets(se):
    """Alle Ziel-Endungen, die convert_one für diese Quell-Endung anbietet."""
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
        if se in ("docx", "doc", "odt", "rtf"):
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
    return sorted(t - {"jpeg", "tif", "htm", "aif"})  # Alias-Endungen ausblenden
