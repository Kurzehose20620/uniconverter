"""Office-Dokumente: LibreOffice headless, textutil (macOS), pandoc/mammoth für DOCX → Markdown."""

import shutil
import tempfile
from pathlib import Path

from ..errors import ConvError
from ..formats import ext_of
from . import tools
from .tools import need, pip_hint, run


def office_to_pdf(src: Path, dst: Path, opts):
    need(tools.SOFFICE, "LibreOffice", "brew install --cask libreoffice")
    with tempfile.TemporaryDirectory() as td:
        profile = Path(td) / "lo-profile"
        run([tools.SOFFICE, "--headless", "--norestore",
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
        run([tools.SOFFICE, "--headless", "--norestore",
             f"-env:UserInstallation={profile.as_uri()}",
             "--convert-to", "docx", "--outdir", tmpdir, str(src)])
    out = Path(tmpdir) / (src.stem + ".docx")
    if not out.exists():
        raise ConvError("Zwischenschritt nach .docx fehlgeschlagen")
    return out


def docx_to_md(src: Path, dst: Path, opts):
    if ext_of(src) != "docx":
        need(tools.SOFFICE, "LibreOffice", "brew install --cask libreoffice")
        with tempfile.TemporaryDirectory() as td:
            return docx_to_md(office_to_docx(src, td), dst, opts)
    if tools.PANDOC:
        run([tools.PANDOC, str(src), "-t", "gfm", "-o", str(dst),
             "--extract-media", str(dst.parent / f"{dst.stem}_medien")])
        return
    try:
        import mammoth
    except ImportError:
        raise ConvError("dafür wird pandoc oder mammoth benötigt – "
                        f"brew install pandoc  (oder: {pip_hint('mammoth')})")
    with open(src, "rb") as f:
        result = mammoth.convert_to_markdown(f)
    dst.write_text(result.value, encoding="utf-8")


def textutil_convert(src: Path, dst: Path, opts):
    fmt = {"txt": "txt", "html": "html", "htm": "html", "rtf": "rtf",
           "docx": "docx", "doc": "doc", "odt": "odt"}[ext_of(dst)]
    run(["textutil", "-convert", fmt, "-output", str(dst), str(src)])
