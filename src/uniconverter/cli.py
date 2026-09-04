"""Kommandozeile: Argumente, Stapelverarbeitung, PDF-Merge, `doctor` und `formats`."""

import argparse
import sys
from pathlib import Path

from . import __version__
from .engines import tools
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

    print("Basis (macOS-Bordmittel):")
    row(True, "sips", "Bildformate inkl. HEIC")
    row(True, "textutil", "Word/RTF/HTML/TXT untereinander")
    row(True, "afconvert", "Audio-Basisformate (wav, m4a, aiff)")

    print("\nPython-Bibliotheken:")
    row(tools.load_fitz() is not None, "pymupdf", "PDF → Bilder, Bilder → PDF, PDF-Merge",
        pip_hint("pymupdf"))
    try:
        import pymupdf4llm  # noqa: F401
        ok4llm = True
    except ImportError:
        ok4llm = False
    row(ok4llm, "pymupdf4llm", "PDF → Markdown", pip_hint("pymupdf4llm"))
    row(tools.load_pil() is not None, "pillow", "Bildkonvertierung (webp, ico, …)",
        pip_hint("pillow pillow-heif"))
    try:
        import markdown  # noqa: F401
        okmd = True
    except ImportError:
        okmd = False
    row(okmd, "markdown", "Markdown → HTML/PDF/DOCX", pip_hint("markdown"))
    try:
        import mammoth  # noqa: F401
        okmam = True
    except ImportError:
        okmam = False
    row(okmam, "mammoth", "DOCX → Markdown (ohne pandoc)", pip_hint("mammoth"))
    try:
        import html2text  # noqa: F401
        okh2t = True
    except ImportError:
        okh2t = False
    row(okh2t, "html2text", "HTML → Markdown", pip_hint("html2text"))
    try:
        import pdf2docx  # noqa: F401
        okp2d = True
    except ImportError:
        okp2d = False
    row(okp2d, "pdf2docx", "PDF → DOCX (optional, ~100 MB)",
        pip_hint("pdf2docx"))

    print("\nProgramme:")
    row(bool(tools.SOFFICE), "LibreOffice", "Word/Excel/PowerPoint → PDF",
        "brew install --cask libreoffice")
    row(bool(tools.CHROME), "Chrome", "Markdown/HTML → PDF (Headless-Druck)",
        "brew install --cask google-chrome")
    row(bool(tools.PANDOC), "pandoc", "beste Qualität für md ↔ docx (optional)",
        "brew install pandoc")
    row(bool(tools.TYPST), "typst", "schönerer md → PDF-Satz mit pandoc (optional)",
        "brew install typst")
    row(bool(tools.MAGICK), "imagemagick", "exotische Bildformate (optional)",
        "brew install imagemagick")
    row(bool(tools.FFMPEG), "ffmpeg", "Audio/Video-Konvertierung (optional)",
        "brew install ffmpeg")
    td = tools.find_tessdata()
    langs = ", ".join(tools.tessdata_languages(td)) if td else ""
    row(bool(td), "tesseract", "Texterkennung für gescannte PDFs (optional)"
        + (f" – Sprachen: {langs}" if langs else ""),
        "brew install tesseract  (dazu tesseract-lang für Deutsch u. a.)")


def cmd_formats():
    print("""Unterstützte Konvertierungen
============================

Bilder   png jpg jpeg heic heif tiff bmp gif webp avif ico
         · untereinander in beliebige Richtung
         · Bild(er) → pdf   (mehrere Eingaben = mehrseitige PDF)

PDF      pdf → png/jpg/…   (eine Datei pro Seite, --dpi steuert Auflösung)
         pdf → md          (--extract-images legt Bilder daneben ab)
         pdf → txt, html
         · gescannte Seiten ohne Text werden per Texterkennung gelesen
           (Tesseract-Sprachdaten nötig, siehe 'doctor'; --ocr-lang deu+eng)
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
    uniconverter scan1.png kapitel.docx notizen.md gesamt.pdf
""")


# ---------------------------------------------------------------- CLI

def build_parser():
    p = argparse.ArgumentParser(
        prog="uniconverter",
        description="Universeller lokaler Datei-Konverter – nichts verlässt deinen Mac.",
        epilog="""Beispiele:
  uniconverter foto.heic foto.jpg              einzelne Datei
  uniconverter *.heic -t jpg                   Stapel: alle HEIC → JPG (gleicher Ordner)
  uniconverter *.png -t webp -o ./web/         Stapel mit Zielordner
  uniconverter bericht.docx bericht.pdf        Word → PDF
  uniconverter skript.md skript.pdf            Markdown → PDF
  uniconverter paper.pdf paper.md              PDF → Markdown
  uniconverter scan1.png scan2.png doc.pdf     mehrere Dateien → EINE PDF
  uniconverter doctor                          zeigt, was installiert ist
  uniconverter formats                         alle unterstützten Wege""",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="*", help="Eingabedatei(en), optional gefolgt von der Zieldatei")
    p.add_argument("-t", "--to", metavar="EXT",
                   help="Zielformat für Stapelverarbeitung (z.B. jpg)")
    p.add_argument("-o", "--out", metavar="PFAD",
                   help="Zielordner (Stapel) oder Zieldatei (PDF-Merge)")
    p.add_argument("-q", "--quality", type=int, default=90,
                   help="JPEG/WebP-Qualität 1–100 (Standard 90)")
    p.add_argument("--dpi", type=int, default=150, help="Auflösung für PDF → Bild (Standard 150)")
    p.add_argument("--extract-images", action="store_true",
                   help="bei PDF → md: Bilder mit extrahieren")
    p.add_argument("--ocr-lang", metavar="LANG", default=None,
                   help="Sprache(n) der Texterkennung bei gescannten PDFs, z.B. deu+eng "
                        "(Standard: automatisch aus den vorhandenen Sprachdaten)")
    p.add_argument("-f", "--force", action="store_true",
                   help="vorhandene Zieldateien überschreiben")
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
            sys.exit("Fehler: Zieldatei fehlt. Beispiel: uniconverter foto.heic foto.jpg")
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
