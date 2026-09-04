"""Office documents: LibreOffice headless, textutil (macOS), pandoc/mammoth for DOCX → Markdown."""

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
            err_hint="is LibreOffice open right now? Please close it.")
        produced = Path(td) / (src.stem + ".pdf")
        if not produced.exists():
            raise ConvError("LibreOffice produced no PDF "
                            "(file damaged or format not supported?)")
        shutil.move(str(produced), str(dst))


def office_to_docx(src: Path, tmpdir: str):
    with tempfile.TemporaryDirectory() as td:
        profile = Path(td) / "lo-profile"
        run([tools.SOFFICE, "--headless", "--norestore",
             f"-env:UserInstallation={profile.as_uri()}",
             "--convert-to", "docx", "--outdir", tmpdir, str(src)])
    out = Path(tmpdir) / (src.stem + ".docx")
    if not out.exists():
        raise ConvError("intermediate conversion to .docx failed")
    return out


def docx_to_md(src: Path, dst: Path, opts):
    if ext_of(src) != "docx":
        need(tools.SOFFICE, "LibreOffice", "brew install --cask libreoffice")
        with tempfile.TemporaryDirectory() as td:
            return docx_to_md(office_to_docx(src, td), dst, opts)
    if tools.PANDOC:
        run([tools.PANDOC, "--sandbox", str(src), "-t", "gfm", "-o", str(dst),
             "--extract-media", str(dst.parent / f"{dst.stem}_media")])
        return
    try:
        import mammoth
    except ImportError:
        raise ConvError("this needs pandoc or mammoth – "
                        f"brew install pandoc  (or: {pip_hint('mammoth')})")
    with open(src, "rb") as f:
        # external_file_access=False is mammoth's default; stated here because it is
        # what keeps linked (not embedded) images from being fetched over the network
        result = mammoth.convert_to_markdown(f, external_file_access=False)
    dst.write_text(result.value, encoding="utf-8")


def textutil_convert(src: Path, dst: Path, opts):
    fmt = {"txt": "txt", "html": "html", "htm": "html", "rtf": "rtf",
           "docx": "docx", "doc": "doc", "odt": "odt"}[ext_of(dst)]
    run(["textutil", "-convert", fmt, "-output", str(dst), str(src)])
