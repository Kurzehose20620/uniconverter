"""Command line: argument parsing, batch loop, PDF merge, `doctor` and `formats`."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .engines import tools
from .engines.pdf import default_ocr_languages
from .engines.tools import pip_hint
from .errors import ConvError
from .formats import ext_of
from .router import convert_one, merge_to_pdf

# ---------------------------------------------------------------- Doctor / Formats


def cmd_doctor():
    def row(ok, name, what, hint=""):
        mark = "✓" if ok else "✗"
        line = f"  {mark} {name:<14} {what}"
        if not ok and hint:
            line += f"\n      → {hint}"
        print(line)

    def has(module):
        try:
            __import__(module)
            return True
        except ImportError:
            return False

    print("Built into macOS:")
    row(True, "sips", "image formats incl. HEIC")
    row(True, "textutil", "Word/RTF/HTML/TXT between each other")
    row(True, "afconvert", "basic audio formats (wav, m4a, aiff)")

    print("\nPython libraries:")
    row(tools.load_fitz() is not None, "pymupdf", "PDF → images, images → PDF, PDF merge",
        pip_hint("pymupdf"))
    row(has("pymupdf4llm"), "pymupdf4llm", "PDF → Markdown", pip_hint("pymupdf4llm"))
    row(tools.load_pil() is not None, "pillow", "image conversion (webp, ico, …)",
        pip_hint("pillow pillow-heif"))
    row(has("markdown"), "markdown", "Markdown → HTML/PDF/DOCX", pip_hint("markdown"))
    row(has("mammoth"), "mammoth", "DOCX → Markdown (without pandoc)", pip_hint("mammoth"))
    row(has("html2text"), "html2text", "HTML → Markdown", pip_hint("html2text"))
    row(has("pdf2docx"), "pdf2docx", "PDF → DOCX (optional, ~100 MB)", pip_hint("pdf2docx"))

    print("\nPrograms:")
    row(bool(tools.SOFFICE), "LibreOffice", "Word/Excel/PowerPoint → PDF",
        "brew install --cask libreoffice")
    row(bool(tools.CHROME), "Chrome", "Markdown/HTML → PDF (headless printing)",
        "brew install --cask google-chrome")
    row(bool(tools.PANDOC), "pandoc", "best quality for md ↔ docx (optional)",
        "brew install pandoc")
    row(bool(tools.TYPST), "typst", "nicer md → PDF typesetting with pandoc (optional)",
        "brew install typst")
    row(bool(tools.MAGICK), "imagemagick", "exotic image formats (optional)",
        "brew install imagemagick")
    row(bool(tools.FFMPEG), "ffmpeg", "audio/video conversion (optional)",
        "brew install ffmpeg")
    td = tools.find_tessdata()
    note = ""
    if td:
        default, installed = default_ocr_languages(td), tools.tessdata_languages(td)
        note = f" – uses {'+'.join(default)}"
        if len(installed) > len(default):
            note += f" ({len(installed)} languages installed)"
    row(bool(td), "tesseract", "OCR for scanned PDFs (optional)" + note,
        "brew install tesseract  (plus tesseract-lang for more languages)")


def cmd_formats():
    print("""Supported conversions
=====================

Images   png jpg jpeg heic heif tiff bmp gif webp avif ico
         · between each other in any direction
         · image(s) → pdf   (several inputs = one multi-page PDF)

PDF      pdf → png/jpg/…   (one file per page, --dpi sets the resolution)
         pdf → md          (--extract-images saves the images next to it)
         pdf → txt, html
         · scanned pages without text are read with OCR
           (needs Tesseract language data, see 'doctor'; --ocr-lang deu+eng)
         pdf → docx        (optional: install pdf2docx)

Office   docx doc odt rtf pptx xlsx …
         · → pdf           (via LibreOffice)
         · → png/jpg       (one file per page)
         · docx/doc/odt/rtf → md, txt, html, docx, odt, rtf

Markdown md → pdf, html, docx, rtf, odt

HTML     html → pdf, md, docx, rtf, txt

Text     txt → pdf, docx, rtf, html

Audio    wav m4a aiff caf  (built in) · mp3 flac ogg … (with ffmpeg)
Video    mp4 mov mkv webm avi → each other, → gif, → mp3/… (with ffmpeg)

Merge several files into ONE PDF:
    uniconverter scan1.png chapter.docx notes.md all.pdf
""")


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="uniconverter",
        description="Universal local file converter – nothing leaves your Mac.",
        epilog="""examples:
  uniconverter photo.heic photo.jpg          single file
  uniconverter *.heic -t jpg                 batch: every HEIC → JPG (same folder)
  uniconverter *.png -t webp -o ./web/       batch into a target folder
  uniconverter report.docx report.pdf        Word → PDF
  uniconverter script.md script.pdf          Markdown → PDF
  uniconverter paper.pdf paper.md            PDF → Markdown (OCR for scans)
  uniconverter scan1.png scan2.png doc.pdf   several files → ONE PDF
  uniconverter doctor                        show which engines are available
  uniconverter formats                       list every supported route""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*",
                   help="input file(s), optionally followed by the output file")
    p.add_argument("-t", "--to", metavar="EXT",
                   help="target format for batch conversion (e.g. jpg)")
    p.add_argument("-o", "--out", metavar="PATH",
                   help="output folder (batch) or output file (PDF merge)")
    p.add_argument("-q", "--quality", type=int, default=90,
                   help="JPEG/WebP quality 1–100 (default 90)")
    p.add_argument("--dpi", type=int, default=150,
                   help="resolution for PDF → image (default 150)")
    p.add_argument("--extract-images", action="store_true",
                   help="PDF → md: also extract the images")
    p.add_argument("--ocr-lang", metavar="LANG", default=None,
                   help="OCR language(s) for scanned PDFs, e.g. deu+eng "
                        "(default: chosen from the installed language data)")
    p.add_argument("-f", "--force", action="store_true",
                   help="overwrite existing output files")
    p.add_argument("--version", action="version", version=f"uniconverter {__version__}")
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
            sys.exit("Error: output file missing. Example: uniconverter photo.heic photo.jpg")
        *inputs, dst = files
        if dst.exists() and dst in [Path(f) for f in inputs]:
            sys.exit(f"Error: '{dst}' is both input and output.")
        if len(inputs) > 1:
            if ext_of(dst) != "pdf":
                sys.exit("Error: several inputs need -t EXT (batch) "
                         "or a .pdf output file (merge).")
            merge = (inputs, dst)
        else:
            jobs.append((inputs[0], dst))

    for src in (merge[0] if merge else [j[0] for j in jobs]):
        if not src.exists():
            sys.exit(f"Error: input file not found: {src}")

    if merge:
        inputs, dst = merge
        if dst.exists() and not args.force:
            sys.exit(f"Error: '{dst}' already exists (--force to overwrite).")
        try:
            merge_to_pdf(inputs, dst, args)
        except ConvError as e:
            sys.exit(f"✗ merge failed: {e}")
        return

    failed = 0
    for src, dst in jobs:
        if src.resolve() == dst.resolve():
            print(f"✗ {src.name}: source and target are the same file – skipped")
            failed += 1
            continue
        if dst.exists() and not args.force:
            print(f"✗ {dst.name} already exists (--force to overwrite)")
            failed += 1
            continue
        try:
            convert_one(src, dst, args)
            print(f"✓ {src.name} → {dst}")
        except ConvError as e:
            print(f"✗ {src.name}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {src.name}: unexpected error: {e}")
            failed += 1
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
