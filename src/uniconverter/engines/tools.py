"""Find external programs and Python libraries, run processes, phrase install hints."""

import functools
import os
import re
import shlex
import shutil
import subprocess
import sys
from importlib.resources import files
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
CALIBRE_CANDIDATES = [
    "/Applications/calibre.app/Contents/MacOS/ebook-convert",
    str(Path.home() / "Applications/calibre.app/Contents/MacOS/ebook-convert"),
]
BLENDER_CANDIDATES = [
    "/Applications/Blender.app/Contents/MacOS/Blender",
    str(Path.home() / "Applications/Blender.app/Contents/MacOS/Blender"),
]
# Homebrew keeps the full builds (ffmpeg-full, imagemagick-full) keg-only, i.e. off PATH
KEG_PREFIXES = ["/opt/homebrew/opt", "/usr/local/opt"]
TESSDATA_CANDIDATES = [
    "/opt/homebrew/share/tessdata",
    "/usr/local/share/tessdata",
    "/opt/local/share/tessdata",
]


def _which(name):
    return shutil.which(name)


def _first_existing(candidates, fallback):
    for p in candidates:
        if os.path.exists(p):
            return p
    return _which(fallback)


def find_soffice():
    return _first_existing(SOFFICE_CANDIDATES, "soffice")


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    return _which("chromium") or _which("google-chrome")


def find_calibre():
    return _first_existing(CALIBRE_CANDIDATES, "ebook-convert")


def find_blender():
    return _first_existing(BLENDER_CANDIDATES, "blender")


def prefer_keg(formula, program):
    """A keg-only full build (e.g. ffmpeg-full) when installed, else the program on PATH."""
    return _first_existing([f"{p}/{formula}/bin/{program}" for p in KEG_PREFIXES], program)


# External programs are looked up on first use, not at import time (PEP 562
# module __getattr__). Other modules access them as `tools.SOFFICE` etc., so
# tests can set a plain attribute to override the detection.
_DETECTORS = {
    "SOFFICE": find_soffice,
    "CHROME": find_chrome,
    "PANDOC": lambda: _which("pandoc"),
    "TYPST": lambda: _which("typst"),
    "MAGICK": lambda: prefer_keg("imagemagick-full", "magick"),
    "FFMPEG": lambda: prefer_keg("ffmpeg-full", "ffmpeg"),
    "FFPROBE": lambda: prefer_keg("ffmpeg-full", "ffprobe"),
    "GS": lambda: _which("gs"),            # Ghostscript: EPS/PS/AI
    "CJXL": lambda: _which("cjxl"),        # JPEG XL encoder (brew install jpeg-xl)
    "DJXL": lambda: _which("djxl"),
    "EBOOK_CONVERT": find_calibre,
    "BLENDER": find_blender,
}
_found = {}
VERBOSE = False     # set by the CLI's --verbose: echo external commands to stderr


def __getattr__(name):
    if name in _DETECTORS:
        if name not in _found:
            _found[name] = _DETECTORS[name]()
        return _found[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def tool(name):
    """Current value of an external-program attribute (honours test overrides)."""
    return getattr(sys.modules[__name__], name)


# ---------------------------------------------------------------- capabilities

_ff_encoders = {}     # ffmpeg path -> set of encoder names
_magick_formats = {}  # magick path -> {format: "rw+" flags}


def ffmpeg_encoders():
    """Encoder names the installed ffmpeg really has (cached per binary)."""
    ff = tool("FFMPEG")
    if not ff:
        return set()
    if ff not in _ff_encoders:
        encs = set()
        try:
            out = subprocess.run([ff, "-hide_banner", "-encoders"],
                                 capture_output=True, text=True).stdout
        except OSError:
            out = ""
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2 and len(parts[0]) == 6 and parts[0][0] in "VAS":
                encs.add(parts[1])
        _ff_encoders[ff] = encs
    return _ff_encoders[ff]


def ff_has(*encoders):
    return bool(tool("FFMPEG")) and all(e in ffmpeg_encoders() for e in encoders)


def magick_can(fmt, mode="r"):
    """Can the installed ImageMagick read ("r") or write ("w") this format?"""
    magick = tool("MAGICK")
    if not magick:
        return False
    if magick not in _magick_formats:
        table = {}
        try:
            out = subprocess.run([magick, "-list", "format"],
                                 capture_output=True, text=True).stdout
        except OSError:
            out = ""
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 3 and len(parts[2]) == 3 and parts[2][0] in "r-":
                table[parts[0].rstrip("*").lower()] = parts[2]
        _magick_formats[magick] = table
    flags = _magick_formats[magick].get(fmt.lower(), "---")
    return flags[0] == "r" if mode == "r" else flags[1] == "w"


def magick_env():
    """Environment for ImageMagick: our policy.xml forbids URL/HTTP(S)/FTP coders and
    delegates, MSL/MVG scripts and @file indirection, so an image never makes
    ImageMagick fetch or read anything beyond the files named on the command line."""
    policy_dir = files(__package__).joinpath("magick")
    return {"MAGICK_CONFIGURE_PATH": str(policy_dir)}


def _defaults_read(key):
    try:
        return subprocess.run(["defaults", "read", "-g", key], capture_output=True,
                              text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


LETTER_REGIONS = {"US", "CA", "MX", "PH", "CL", "CO", "VE", "CR", "GT", "PR"}


@functools.cache
def letter_paper():
    """True where Letter is the usual paper size (macOS region, else locale), else A4."""
    loc = (_defaults_read("AppleLocale").strip()
           or os.environ.get("LC_ALL") or os.environ.get("LANG") or "")
    m = re.search(r"rg=([a-zA-Z]{2})", loc) or re.search(r"_([A-Za-z]{2})", loc)
    return bool(m) and m.group(1).upper() in LETTER_REGIONS


def _has_traineddata(d):
    return bool(d) and any(Path(d).glob("*.traineddata"))


def find_tessdata():
    """Directory with Tesseract language data (*.traineddata), or None.

    Tesseract itself is built into PyMuPDF; only the language files are needed
    (TESSDATA_PREFIX, Homebrew/MacPorts paths, or next to a tesseract binary).
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
    """Pillow's Image module with HEIF/AVIF support registered, or None."""
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
    """The PyMuPDF module, or None."""
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        try:
            import fitz  # older PyMuPDF versions
            return fitz
        except ImportError:
            return None


def run(cmd, err_hint="", env=None, cwd=None):
    """Run an external program; ConvError with its last error line if it fails.

    env adds variables to the current environment.
    """
    cmd = [str(c) for c in cmd]
    if VERBOSE:
        prefix = "".join(f"{k}={shlex.quote(v)} " for k, v in (env or {}).items())
        print("$ " + prefix + " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
    full_env = {**os.environ, **env} if env else None
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, env=full_env, cwd=cwd,
                             errors="replace")
    except FileNotFoundError:
        raise ConvError(f"{Path(cmd[0]).name} was not found")
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip().splitlines()
        detail = msg[-1] if msg else "unknown error"
        raise ConvError(f"{Path(cmd[0]).name}: {detail}" +
                        (f" – {err_hint}" if err_hint else ""))
    return res


def need(condition, what, install_hint):
    if not condition:
        raise ConvError(f"this needs {what} – install with: {install_hint}")


def pip_hint(pkg):
    """Install hint for a missing Python package (uniconverter lives in a pipx venv)."""
    return f"pipx inject uniconverter {pkg}"
