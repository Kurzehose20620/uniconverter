"""Externe Programme und Python-Bibliotheken finden, Prozesse aufrufen, Hinweise formulieren."""

import os
import shutil
import subprocess
from pathlib import Path

from ..errors import ConvError

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
SOFFICE_CANDIDATES = [
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
]
TESSDATA_CANDIDATES = [
    "/opt/homebrew/share/tessdata",
    "/usr/local/share/tessdata",
    "/opt/local/share/tessdata",
]


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


# Andere Module greifen über `tools.SOFFICE` usw. zu (nicht per from-import),
# damit sich die Erkennung in Tests austauschen lässt.
SOFFICE = find_soffice()
CHROME = find_chrome()
PANDOC = _which("pandoc")
TYPST = _which("typst")
MAGICK = _which("magick")
FFMPEG = _which("ffmpeg")


def _has_traineddata(d):
    return bool(d) and any(Path(d).glob("*.traineddata"))


def find_tessdata():
    """Ordner mit Tesseract-Sprachdaten (*.traineddata) oder None.

    Tesseract selbst steckt in PyMuPDF; nur die Sprachdaten müssen da sein
    (TESSDATA_PREFIX, Homebrew/MacPorts-Pfade oder neben einem tesseract-Binary).
    """
    cands = [os.environ.get("TESSDATA_PREFIX", "")] + TESSDATA_CANDIDATES
    t = _which("tesseract")
    if t:
        cands.append(str(Path(t).resolve().parent.parent / "share" / "tessdata"))
    for c in cands:
        if _has_traineddata(c):
            return c
        if c and _has_traineddata(Path(c) / "tessdata"):
            return str(Path(c) / "tessdata")
    return None


def tessdata_languages(tessdata):
    return sorted(p.stem for p in Path(tessdata).glob("*.traineddata") if p.stem != "osd")


def load_pil():
    """Pillow-Image-Modul mit HEIF/AVIF-Unterstützung, oder None."""
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


def load_fitz():
    """PyMuPDF-Modul, oder None."""
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


def pip_hint(pkg):
    """Installationshinweis für ein fehlendes Python-Paket (uniconverter läuft im pipx-venv)."""
    return f"pipx inject uniconverter {pkg}"
