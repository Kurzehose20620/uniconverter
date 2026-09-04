#!/usr/bin/env python3
"""uniconv – universeller lokaler Datei-Konverter für macOS.

Alles läuft zu 100% lokal, keine Datei verlässt den Rechner.
Nutzt vorhandene macOS-Bordmittel (sips, textutil, afconvert), LibreOffice,
Chrome (Headless-PDF-Druck) und Python-Bibliotheken (PyMuPDF, Pillow, …).
"""

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- Konstanten

IMAGE_EXT = {"png", "jpg", "jpeg", "heic", "heif", "tif", "tiff", "bmp",
             "gif", "webp", "avif", "ico"}
OFFICE_EXT = {"docx", "doc", "odt", "rtf", "pptx", "ppt", "xlsx", "xls"}
MD_EXT = {"md", "markdown"}
HTML_EXT = {"html", "htm"}
AUDIO_EXT = {"mp3", "wav", "m4a", "aac", "aiff", "aif", "caf", "flac", "ogg"}
VIDEO_EXT = {"mp4", "mov", "mkv", "webm", "avi", "m4v"}

SIPS_FORMATS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "tif": "tiff",
                "tiff": "tiff", "gif": "gif", "bmp": "bmp", "heic": "heic",
                "pdf": "pdf"}

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]


class ConvError(Exception):
    pass


# ---------------------------------------------------------------- Engines

def _which(name):
    return shutil.which(name)


def find_soffice():
    for p in SOFFICE_CANDIDATES:
        if os.path.exists(p):
            return p
    return _which("soffice")


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return _which("chromium") or _which("google-chrome")


SOFFICE = find_soffice()
CHROME = find_chrome()
PANDOC = _which("pandoc")
TYPST = _which("typst")
MAGICK = _which("magick")
FFMPEG = _which("ffmpeg")


def _pil():
    try:
        from PIL import Image
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        try:
            from pillow_heif import register_avif_opener
            register_avif_opener()
        except ImportError:
            pass
        return Image
    except ImportError:
        return None


def _fitz():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz  # ältere PyMuPDF-Versionen
            return fitz
        except ImportError:
            return None


def run(cmd, err_hint=""):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip().splitlines()
        detail = msg[-1] if msg else "unbekannter Fehler"
        raise ConvError(f"{Path(cmd[0]).name}: {detail}" +
                        (f" – {err_hint}" if err_hint else ""))
    return res


def need(condition, was, install_hint):
    if not condition:
        raise ConvError(f"dafür wird {was} benötigt – Installation: {install_hint}")


def ext_of(p: Path):
    return p.suffix.lower().lstrip(".")


# ---------------------------------------------------------------- Bilder

def img_to_img(src: Path, dst: Path, opts):
    de = ext_of(dst)
    Image = _pil()
    if Image is not None:
        try:
            im = Image.open(src)
            if de in ("jpg", "jpeg", "bmp") and im.mode not in ("RGB", "L"):
                # Transparenz auf weißem Hintergrund ablegen
                im = im.convert("RGBA")
                from PIL import Image as I
                bg = I.new("RGB", im.size, (255, 255, 255))
                bg.paste(im, mask=im.split()[-1])
                im = bg
            kwargs = {}
            if de in ("jpg", "jpeg"):
                kwargs = {"quality": opts.quality, "optimize": True}
            elif de in ("webp", "avif", "heic", "heif"):
                kwargs = {"quality": opts.quality}
            im.save(dst, **kwargs)
            return
        except Exception:
            pass  # weiter zu sips/magick
    if de in SIPS_FORMATS:
        cmd = ["sips", "-s", "format", SIPS_FORMATS[de]]
        if SIPS_FORMATS[de] == "jpeg":
            cmd += ["-s", "formatOptions", str(opts.quality)]
        run(cmd + [str(src), "--out", str(dst)])
        return
    need(MAGICK, f"ImageMagick (für .{de})", "brew install imagemagick")
    run([MAGICK, str(src), "-quality", str(opts.quality), str(dst)])


def _img_for_fitz(src: Path, tmpdir: str):
    """HEIC/WebP/AVIF etc. für PyMuPDF nach PNG normalisieren."""
    if ext_of(src) in ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff"):
        return src
    out = Path(tmpdir) / (src.stem + ".png")

    class _O:  # minimale Optionen für die Zwischenkonvertierung
        quality = 95
    img_to_img(src, out, _O)
    return out


def imgs_to_pdf(sources, dst: Path, opts):
    fitz = _fitz()
    if fitz is not None:
        out = fitz.open()
        with tempfile.TemporaryDirectory() as td:
            for s in sources:
                s = _img_for_fitz(s, td)
                imgdoc = fitz.open(str(s))
                pdfbytes = imgdoc.convert_to_pdf()
                out.insert_pdf(fitz.open("pdf", pdfbytes))
            out.save(str(dst))
        return
    if len(sources) == 1 and ext_of(sources[0]) in SIPS_FORMATS:
        run(["sips", "-s", "format", "pdf", str(sources[0]), "--out", str(dst)])
        return
    need(MAGICK, "ImageMagick oder PyMuPDF", "brew install imagemagick")
    run([MAGICK] + [str(s) for s in sources] + [str(dst)])


def pdf_to_images(src: Path, dst: Path, opts):
    fitz = _fitz()
    need(fitz, "PyMuPDF", f"{VENV_PIP} install pymupdf")
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


# ---------------------------------------------------------------- PDF → Text

def pdf_to_md(src: Path, dst: Path, opts):
    try:
        import pymupdf4llm
    except ImportError:
        raise ConvError(f"pymupdf4llm fehlt – Installation: {VENV_PIP} install pymupdf4llm")
    kwargs = {}
    if opts.extract_images:
        img_dir = dst.parent / f"{dst.stem}_bilder"
        kwargs = {"write_images": True, "image_path": str(img_dir)}
    md = pymupdf4llm.to_markdown(str(src), **kwargs)
    dst.write_text(md, encoding="utf-8")


def pdf_to_txt(src: Path, dst: Path, opts):
    fitz = _fitz()
    need(fitz, "PyMuPDF", f"{VENV_PIP} install pymupdf")
    doc = fitz.open(str(src))
    text = "\n\n".join(page.get_text() for page in doc)
    dst.write_text(text, encoding="utf-8")


def pdf_to_docx(src: Path, dst: Path, opts):
    try:
        from pdf2docx import Converter
    except ImportError:
        raise ConvError("pdf2docx fehlt (optional, ~100 MB) – "
                        f"Installation: {VENV_PIP} install pdf2docx")
    cv = Converter(str(src))
    cv.convert(str(dst))
    cv.close()


# ---------------------------------------------------------------- Office

def office_to_pdf(src: Path, dst: Path, opts):
    need(SOFFICE, "LibreOffice", "brew install --cask libreoffice")
    with tempfile.TemporaryDirectory() as td:
        profile = Path(td) / "lo-profile"
        run([SOFFICE, "--headless", "--norestore",
             f"-env:UserInstallation={profile.as_uri()}",
             "--convert-to", "pdf", "--outdir", td, str(src)],
            err_hint="läuft LibreOffice gerade offen? Bitte schließen.")
        produced = Path(td) / (src.stem + ".pdf")
        if not produced.exists():
            raise ConvError("LibreOffice hat keine PDF erzeugt "
                            "(Datei beschädigt oder Format nicht unterstützt?)")
        shutil.move(str(produced), str(dst))


def office_to_docx(src: Path, tmpdir: str):
    with tempfile.TemporaryDirectory() as td:
        profile = Path(td) / "lo-profile"
        run([SOFFICE, "--headless", "--norestore",
             f"-env:UserInstallation={profile.as_uri()}",
             "--convert-to", "docx", "--outdir", tmpdir, str(src)])
    out = Path(tmpdir) / (src.stem + ".docx")
    if not out.exists():
        raise ConvError("Zwischenschritt nach .docx fehlgeschlagen")
    return out


def docx_to_md(src: Path, dst: Path, opts):
    if ext_of(src) != "docx":
        need(SOFFICE, "LibreOffice", "brew install --cask libreoffice")
        with tempfile.TemporaryDirectory() as td:
            return docx_to_md(office_to_docx(src, td), dst, opts)
    if PANDOC:
        run([PANDOC, str(src), "-t", "gfm", "-o", str(dst),
             "--extract-media", str(dst.parent / f"{dst.stem}_medien")])
        return
    try:
        import mammoth
    except ImportError:
        raise ConvError("dafür wird pandoc oder mammoth benötigt – "
                        f"brew install pandoc  (oder: {VENV_PIP} install mammoth)")
    with open(src, "rb") as f:
        result = mammoth.convert_to_markdown(f)
    dst.write_text(result.value, encoding="utf-8")


def textutil_convert(src: Path, dst: Path, opts):
    fmt = {"txt": "txt", "html": "html", "htm": "html", "rtf": "rtf",
           "docx": "docx", "doc": "doc", "odt": "odt"}[ext_of(dst)]
    run(["textutil", "-convert", fmt, "-output", str(dst), str(src)])


# ---------------------------------------------------------------- Markdown / HTML

HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>{title}</title>
<style>
@page {{ margin: 2cm; }}
body {{ font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       font-size: 11pt; line-height: 1.55; color: #1a1a1a;
       max-width: 48em; margin: 2em auto; padding: 0 1em; }}
h1, h2, h3 {{ line-height: 1.25; margin-top: 1.4em; }}
h1 {{ font-size: 1.7em; border-bottom: 1px solid #ddd; padding-bottom: .3em; }}
h2 {{ font-size: 1.35em; }}
code {{ font-family: "SF Mono", Menlo, monospace; font-size: .9em;
        background: #f2f2f4; padding: .15em .35em; border-radius: 4px; }}
pre {{ background: #f6f8fa; padding: 1em; border-radius: 8px;
       overflow-x: auto; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ border-left: 4px solid #d0d0d6; margin-left: 0;
              padding-left: 1em; color: #555; }}
table {{ border-collapse: collapse; margin: 1em 0; }}
th, td {{ border: 1px solid #ccc; padding: .4em .7em; }}
th {{ background: #f2f2f4; }}
img {{ max-width: 100%; }}
a {{ color: #0b5fff; }}
</style></head><body>
{body}
</body></html>
"""


def md_to_html_str(src: Path):
    try:
        import markdown
    except ImportError:
        raise ConvError(f"python-markdown fehlt – Installation: {VENV_PIP} install markdown")
    body = markdown.markdown(src.read_text(encoding="utf-8"),
                             extensions=["extra", "sane_lists"])
    return HTML_TEMPLATE.format(title=html.escape(src.stem), body=body)


def md_to_html(src: Path, dst: Path, opts):
    dst.write_text(md_to_html_str(src), encoding="utf-8")


def txt_to_html_str(src: Path):
    body = "<pre style='white-space: pre-wrap; font-family: SF Mono, Menlo, monospace; font-size: 10pt;'>" \
           + html.escape(src.read_text(encoding="utf-8")) + "</pre>"
    return HTML_TEMPLATE.format(title=html.escape(src.stem), body=body)


def chrome_html_to_pdf(html_file: Path, dst: Path):
    need(CHROME, "Chrome (Headless-PDF-Druck)", "brew install --cask google-chrome")
    import time
    with tempfile.TemporaryDirectory() as td:
        proc = subprocess.Popen(
            [CHROME, "--headless", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", "--disable-extensions",
             "--hide-scrollbars", f"--user-data-dir={td}/chrome-profile",
             "--no-pdf-header-footer",
             f"--print-to-pdf={dst}", html_file.resolve().as_uri()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Chrome beendet sich nach dem Druck oft nicht von selbst:
        # auf die fertige PDF warten (Größe stabil), dann Prozess beenden.
        deadline = time.time() + 120
        stable_since = None
        last_size = -1
        while time.time() < deadline:
            if proc.poll() is not None:
                break
            size = dst.stat().st_size if dst.exists() else -1
            if size > 0 and size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since > 1.5:
                    break
            else:
                stable_since = None
            last_size = size
            time.sleep(0.3)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    if not dst.exists() or dst.stat().st_size == 0:
        raise ConvError("Chrome konnte keine PDF erzeugen")


def md_to_pdf(src: Path, dst: Path, opts):
    if PANDOC and TYPST:
        run([PANDOC, str(src), "-o", str(dst), "--pdf-engine=typst"])
        return
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        tmp_html.write_text(md_to_html_str(src), encoding="utf-8")
        chrome_html_to_pdf(tmp_html, dst)


def md_to_office(src: Path, dst: Path, opts):
    if PANDOC:
        run([PANDOC, str(src), "-o", str(dst)])
        return
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        tmp_html.write_text(md_to_html_str(src), encoding="utf-8")
        textutil_convert(tmp_html, dst, opts)


def html_to_pdf(src: Path, dst: Path, opts):
    chrome_html_to_pdf(src, dst)


def html_to_md(src: Path, dst: Path, opts):
    try:
        import html2text
    except ImportError:
        raise ConvError(f"html2text fehlt – Installation: {VENV_PIP} install html2text")
    h = html2text.HTML2Text()
    h.body_width = 0
    dst.write_text(h.handle(src.read_text(encoding="utf-8")), encoding="utf-8")


def txt_to_pdf(src: Path, dst: Path, opts):
    with tempfile.TemporaryDirectory() as td:
        tmp_html = Path(td) / (src.stem + ".html")
        tmp_html.write_text(txt_to_html_str(src), encoding="utf-8")
        chrome_html_to_pdf(tmp_html, dst)


# ---------------------------------------------------------------- Audio / Video

AFCONVERT_MAP = {
    "m4a": ["-f", "m4af", "-d", "aac", "-b", "192000"],
    "wav": ["-f", "WAVE", "-d", "LEI16"],
    "aiff": ["-f", "AIFF", "-d", "BEI16"],
    "aif": ["-f", "AIFF", "-d", "BEI16"],
    "caf": ["-f", "caff", "-d", "LEI16"],
}


def audio_to_audio(src: Path, dst: Path, opts):
    if FFMPEG:
        run([FFMPEG, "-y", "-i", str(src), str(dst)])
        return
    de = ext_of(dst)
    if de in AFCONVERT_MAP:
        run(["afconvert"] + AFCONVERT_MAP[de] + [str(src), str(dst)])
        return
    need(False, f"ffmpeg (für .{de}-Ausgabe)", "brew install ffmpeg")


def video_convert(src: Path, dst: Path, opts):
    need(FFMPEG, "ffmpeg", "brew install ffmpeg")
    de = ext_of(dst)
    if de == "gif":
        vf = ("fps=12,scale=640:-1:flags=lanczos,"
              "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")
        run([FFMPEG, "-y", "-i", str(src), "-vf", vf, str(dst)])
    elif de in AUDIO_EXT:
        run([FFMPEG, "-y", "-i", str(src), "-vn", str(dst)])
    else:
        cmd = [FFMPEG, "-y", "-i", str(src)]
        if de == "mp4":
            cmd += ["-movflags", "+faststart", "-pix_fmt", "yuv420p",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        run(cmd + [str(dst)])


# ---------------------------------------------------------------- Router

def convert_one(src: Path, dst: Path, opts):
    se, de = ext_of(src), ext_of(dst)

    if se in IMAGE_EXT and de in IMAGE_EXT:
        return img_to_img(src, dst, opts)
    if se in IMAGE_EXT and de == "pdf":
        return imgs_to_pdf([src], dst, opts)
    if se == "gif" and de in VIDEO_EXT:
        return video_convert(src, dst, opts)

    if se == "pdf":
        if de in IMAGE_EXT:
            return pdf_to_images(src, dst, opts)
        if de in MD_EXT:
            return pdf_to_md(src, dst, opts)
        if de == "txt":
            return pdf_to_txt(src, dst, opts)
        if de == "docx":
            return pdf_to_docx(src, dst, opts)
        if de in HTML_EXT:
            with tempfile.TemporaryDirectory() as td:
                tmp_md = Path(td) / (src.stem + ".md")
                pdf_to_md(src, tmp_md, opts)
                return md_to_html(tmp_md, dst, opts)

    if se in OFFICE_EXT:
        if de == "pdf":
            return office_to_pdf(src, dst, opts)
        if de in IMAGE_EXT:
            with tempfile.TemporaryDirectory() as td:
                tmp_pdf = Path(td) / (src.stem + ".pdf")
                office_to_pdf(src, tmp_pdf, opts)
                return pdf_to_images(tmp_pdf, dst, opts)
        if de in MD_EXT:
            return docx_to_md(src, dst, opts)
        if de in ("txt", "html", "htm", "rtf", "docx", "doc", "odt") and \
                se in ("docx", "doc", "odt", "rtf"):
            return textutil_convert(src, dst, opts)

    if se in MD_EXT:
        if de in HTML_EXT:
            return md_to_html(src, dst, opts)
        if de == "pdf":
            return md_to_pdf(src, dst, opts)
        if de in ("docx", "rtf", "odt"):
            return md_to_office(src, dst, opts)

    if se in HTML_EXT:
        if de == "pdf":
            return html_to_pdf(src, dst, opts)
        if de in MD_EXT:
            return html_to_md(src, dst, opts)
        if de in ("docx", "rtf", "txt", "odt"):
            return textutil_convert(src, dst, opts)

    if se == "txt":
        if de == "pdf":
            return txt_to_pdf(src, dst, opts)
        if de in ("docx", "rtf", "html", "htm"):
            return textutil_convert(src, dst, opts)

    if se in AUDIO_EXT and de in AUDIO_EXT:
        return audio_to_audio(src, dst, opts)
    if se in VIDEO_EXT and (de in VIDEO_EXT | AUDIO_EXT or de == "gif"):
        return video_convert(src, dst, opts)

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
    fitz = _fitz()
    need(fitz, "PyMuPDF", f"{VENV_PIP} install pymupdf")
    out = fitz.open()
    with tempfile.TemporaryDirectory() as td:
        for s in sources:
            pdf = to_pdf_temp(s, td, opts)
            out.insert_pdf(fitz.open(str(pdf)))
        out.save(str(dst))
    print(f"✓ {len(sources)} Dateien → {dst}")


def possible_targets(se):
    """Alle Ziel-Endungen, die convert_one für diese Quell-Endung anbietet."""
    import importlib.util
    t = set()
    if se in IMAGE_EXT:
        t |= (IMAGE_EXT - {se, "heif"}) | {"pdf"}
        if se == "gif" and FFMPEG:
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
        t |= (AUDIO_EXT if FFMPEG else set(AFCONVERT_MAP)) - {se, "aif"}
    if se in VIDEO_EXT and FFMPEG:
        t |= (VIDEO_EXT - {se, "m4v"}) | {"gif", "mp3", "m4a", "wav"}
    return sorted(t - {"jpeg", "tif", "htm", "aif"})  # Alias-Endungen ausblenden


# ---------------------------------------------------------------- Doctor / Formats

VENV_PIP = str(Path(__file__).resolve().parent / ".venv" / "bin" / "pip")


def cmd_doctor():
    def row(ok, name, what, hint=""):
        mark = "✓" if ok else "✗"
        line = f"  {mark} {name:<14} {what}"
        if not ok and hint:
            line += f"\n      → {hint}"
        print(line)

    print("Basis (macOS-Bordmittel):")
    row(True, "sips", "Bildformate inkl. HEIC")
    row(True, "textutil", "Word/RTF/HTML/TXT untereinander")
    row(True, "afconvert", "Audio-Basisformate (wav, m4a, aiff)")

    print("\nPython-Bibliotheken (im uniconv-venv):")
    row(_fitz() is not None, "pymupdf", "PDF → Bilder, Bilder → PDF, PDF-Merge",
        f"{VENV_PIP} install pymupdf")
    try:
        import pymupdf4llm  # noqa: F401
        ok4llm = True
    except ImportError:
        ok4llm = False
    row(ok4llm, "pymupdf4llm", "PDF → Markdown", f"{VENV_PIP} install pymupdf4llm")
    row(_pil() is not None, "pillow", "Bildkonvertierung (webp, ico, …)",
        f"{VENV_PIP} install pillow pillow-heif")
    try:
        import markdown  # noqa: F401
        okmd = True
    except ImportError:
        okmd = False
    row(okmd, "markdown", "Markdown → HTML/PDF/DOCX", f"{VENV_PIP} install markdown")
    try:
        import mammoth  # noqa: F401
        okmam = True
    except ImportError:
        okmam = False
    row(okmam, "mammoth", "DOCX → Markdown (ohne pandoc)", f"{VENV_PIP} install mammoth")
    try:
        import html2text  # noqa: F401
        okh2t = True
    except ImportError:
        okh2t = False
    row(okh2t, "html2text", "HTML → Markdown", f"{VENV_PIP} install html2text")
    try:
        import pdf2docx  # noqa: F401
        okp2d = True
    except ImportError:
        okp2d = False
    row(okp2d, "pdf2docx", "PDF → DOCX (optional, ~100 MB)",
        f"{VENV_PIP} install pdf2docx")

    print("\nProgramme:")
    row(bool(SOFFICE), "LibreOffice", "Word/Excel/PowerPoint → PDF",
        "brew install --cask libreoffice")
    row(bool(CHROME), "Chrome", "Markdown/HTML → PDF (Headless-Druck)",
        "brew install --cask google-chrome")
    row(bool(PANDOC), "pandoc", "beste Qualität für md ↔ docx (optional)",
        "brew install pandoc")
    row(bool(TYPST), "typst", "schönerer md → PDF-Satz mit pandoc (optional)",
        "brew install typst")
    row(bool(MAGICK), "imagemagick", "exotische Bildformate (optional)",
        "brew install imagemagick")
    row(bool(FFMPEG), "ffmpeg", "Audio/Video-Konvertierung (optional)",
        "brew install ffmpeg")


def cmd_formats():
    print("""Unterstützte Konvertierungen
============================

Bilder   png jpg jpeg heic heif tiff bmp gif webp avif ico
         · untereinander in beliebige Richtung
         · Bild(er) → pdf   (mehrere Eingaben = mehrseitige PDF)

PDF      pdf → png/jpg/…   (eine Datei pro Seite, --dpi steuert Auflösung)
         pdf → md          (--extract-images legt Bilder daneben ab)
         pdf → txt, html
         pdf → docx        (optional: pdf2docx installieren)

Office   docx doc odt rtf pptx xlsx …
         · → pdf           (via LibreOffice)
         · → png/jpg       (eine Datei pro Seite)
         · docx/doc/odt/rtf → md, txt, html, docx, odt, rtf

Markdown md → pdf, html, docx, rtf, odt

HTML     html → pdf, md, docx, rtf, txt

Text     txt → pdf, docx, rtf, html

Audio    wav m4a aiff caf  (Bordmittel) · mp3 flac ogg … (mit ffmpeg)
Video    mp4 mov mkv webm avi → untereinander, → gif, → mp3/… (mit ffmpeg)

Mehrere Dateien zu EINER PDF zusammenführen:
    uniconv scan1.png kapitel.docx notizen.md gesamt.pdf
""")


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="uniconv",
        description="Universeller lokaler Datei-Konverter – nichts verlässt deinen Mac.",
        epilog="""Beispiele:
  uniconv foto.heic foto.jpg              einzelne Datei
  uniconv *.heic -t jpg                   Stapel: alle HEIC → JPG (gleicher Ordner)
  uniconv *.png -t webp -o ./web/         Stapel mit Zielordner
  uniconv bericht.docx bericht.pdf        Word → PDF
  uniconv skript.md skript.pdf            Markdown → PDF
  uniconv paper.pdf paper.md              PDF → Markdown
  uniconv scan1.png scan2.png doc.pdf     mehrere Dateien → EINE PDF
  uniconv doctor                          zeigt, was installiert ist
  uniconv formats                         alle unterstützten Wege""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", help="Eingabedatei(en), optional gefolgt von der Zieldatei")
    p.add_argument("-t", "--to", metavar="EXT", help="Zielformat für Stapelverarbeitung (z.B. jpg)")
    p.add_argument("-o", "--out", metavar="PFAD", help="Zielordner (Stapel) oder Zieldatei (PDF-Merge)")
    p.add_argument("-q", "--quality", type=int, default=90, help="JPEG/WebP-Qualität 1–100 (Standard 90)")
    p.add_argument("--dpi", type=int, default=150, help="Auflösung für PDF → Bild (Standard 150)")
    p.add_argument("--extract-images", action="store_true",
                   help="bei PDF → md: Bilder mit extrahieren")
    p.add_argument("-f", "--force", action="store_true", help="vorhandene Zieldateien überschreiben")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)

    if len(args.files) == 1 and args.files[0] in ("doctor", "check"):
        return cmd_doctor()
    if len(args.files) == 1 and args.files[0] == "formats":
        return cmd_formats()
    if not args.files:
        build_parser().print_help()
        return

    files = [Path(f) for f in args.files]
    jobs = []  # (src, dst)
    merge = None

    if args.to:
        target = args.to.lstrip(".").lower()
        inputs = files
        outdir = Path(args.out) if args.out else None
        if outdir and outdir.suffix.lower() == ".pdf" and len(inputs) > 1:
            merge = (inputs, outdir)
        else:
            if outdir:
                outdir.mkdir(parents=True, exist_ok=True)
            for src in inputs:
                dst = (outdir or src.parent) / (src.stem + "." + target)
                jobs.append((src, dst))
    else:
        if len(files) < 2:
            sys.exit("Fehler: Zieldatei fehlt. Beispiel: uniconv foto.heic foto.jpg")
        *inputs, dst = files
        if dst.exists() and dst in [Path(f) for f in inputs]:
            sys.exit(f"Fehler: '{dst}' ist Eingabe und Ziel zugleich.")
        if len(inputs) > 1:
            if ext_of(dst) != "pdf":
                sys.exit("Fehler: mehrere Eingaben brauchen -t EXT (Stapel) "
                         "oder eine .pdf-Zieldatei (Merge).")
            merge = (inputs, dst)
        else:
            jobs.append((inputs[0], dst))

    for src in (merge[0] if merge else [j[0] for j in jobs]):
        if not src.exists():
            sys.exit(f"Fehler: Eingabedatei nicht gefunden: {src}")

    if merge:
        inputs, dst = merge
        if dst.exists() and not args.force:
            sys.exit(f"Fehler: '{dst}' existiert schon (--force zum Überschreiben).")
        try:
            merge_to_pdf(inputs, dst, args)
        except ConvError as e:
            sys.exit(f"✗ Merge fehlgeschlagen: {e}")
        return

    failed = 0
    for src, dst in jobs:
        if src.resolve() == dst.resolve():
            print(f"✗ {src.name}: Quelle und Ziel identisch – übersprungen")
            failed += 1
            continue
        if dst.exists() and not args.force:
            print(f"✗ {dst.name} existiert schon (--force zum Überschreiben)")
            failed += 1
            continue
        try:
            convert_one(src, dst, args)
            print(f"✓ {src.name} → {dst}")
        except ConvError as e:
            print(f"✗ {src.name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {src.name}: unerwarteter Fehler: {e}")
            failed += 1
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
