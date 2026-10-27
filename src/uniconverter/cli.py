"""Command line: argument parsing, batch loop, PDF merge, `doctor` and `formats`."""

import argparse
import importlib.util
import sys
from pathlib import Path

from . import __version__
from .engines import tools
from .engines.pdf import default_ocr_languages
from .engines.tools import pip_hint
from .errors import ConvError
from .formats import ext_of
from .router import merge_to_pdf, output_path, plan

# ---------------------------------------------------------------- Doctor / Formats


def cmd_doctor():
    def row(ok, name, what, hint=""):
        mark = "✓" if ok else "✗"
        line = f"  {mark} {name:<17} {what}"
        if not ok and hint:
            line += f"\n      → {hint}"
        print(line)

    def has(module):
        # find_spec instead of importing: pdf2docx would print a deprecation warning
        return importlib.util.find_spec(module) is not None

    full_hint = "(keg-only, used automatically when installed)"
    print("Built into macOS:")
    row(True, "sips", "image formats incl. HEIC, camera RAW, JPEG XL, EXR")
    row(True, "textutil", "Word/RTF/HTML/TXT between each other")
    row(True, "afconvert", "basic audio formats (wav, m4a, aiff)")

    print("\nPython libraries:")
    row(tools.load_fitz() is not None, "pymupdf", "PDF → images, images → PDF, PDF merge, SVG",
        pip_hint("pymupdf"))
    row(has("pymupdf4llm"), "pymupdf4llm", "PDF → Markdown", pip_hint("pymupdf4llm"))
    row(tools.load_pil() is not None, "pillow", "image conversion (webp, ico, tga, …)",
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
    row(bool(tools.PANDOC), "pandoc", "md/docx/odt/rtf/html/epub/rst/org/tex/ipynb (optional)",
        "brew install pandoc")
    row(bool(tools.TYPST), "typst", "nicer PDF typesetting with pandoc (optional)",
        "brew install typst")
    row(bool(tools.EBOOK_CONVERT), "calibre", "e-books: epub mobi azw3 fb2 lit lrf cbz (optional)",
        "brew install --cask calibre")
    magick = tools.MAGICK or ""
    full = "imagemagick-full" in magick
    row(bool(magick), "imagemagick",
        ("full build: " if full else "") + "hdr dpx xpm fits pict pcd xcf"
        + (", RAW via libraw" if full else "") + " (optional)",
        f"brew install imagemagick  (or imagemagick-full {full_hint})")
    row(bool(tools.GS), "ghostscript", "EPS/PS/AI → image or vector PDF (optional)",
        "brew install ghostscript")
    row(bool(tools.CJXL), "jpeg-xl", "JPEG XL output (cjxl, optional)", "brew install jpeg-xl")
    row(bool(tools.FFMPEG), "ffmpeg", "audio/video/subtitle conversion (optional)"
        + (f" – {tools.FFMPEG}" if tools.FFMPEG and "ffmpeg-full" in tools.FFMPEG else ""),
        "brew install ffmpeg")
    row(bool(tools.FFPROBE), "ffprobe", "video analysis (size, frame rate, length, subtitles)",
        "comes with ffmpeg")
    row(bool(tools.BLENDER), "Blender", "3D models glb/gltf/fbx/stl/usdz/… (optional)",
        "brew install --cask blender")
    td = tools.find_tessdata()
    note = ""
    if td:
        default, installed = default_ocr_languages(td), tools.tessdata_languages(td)
        note = f" – uses {'+'.join(default)}"
        if len(installed) > len(default):
            note += f" ({len(installed)} languages installed)"
    row(bool(td), "tesseract", "OCR for scanned PDFs (optional)" + note,
        "brew install tesseract  (plus tesseract-lang for more languages)")

    if tools.FFMPEG:
        print("\nffmpeg encoders (decide which targets are offered):")
        checks = [
            ("libx264", "H.264 → mp4/m4v/mov/mkv/ts/m2ts/3gp"),
            ("libvpx-vp9", "VP9 → webm"), ("libvpx", "VP8 → ogv (fallback without Theora)"),
            ("mpeg4", "MPEG-4 ASP → avi/divx (Xvid-compatible)"),
            ("mpeg2video", "MPEG-2 → mpg/vob"), ("dvvideo", "DV → dv"),
            ("wmv2", "WMV → wmv/asf"), ("flv", "Flash video (Sorenson) → flv"),
            ("rv20", "RealVideo → rm"),
            ("libmp3lame", "mp3"), ("aac", "aac/m4a/m4b"), ("libopus", "opus (+ ogg fallback)"),
            ("wmav2", "wma"), ("ac3", "ac3"), ("alac", "alac (.m4a)"),
            ("libvorbis", "Vorbis in .ogg (otherwise Opus in Ogg)"),
            ("libtheora", "Theora in .ogv (otherwise VP8)"),
            ("libopencore_amrnb", "amr (AMR-NB voice recordings)"),
            ("h263", "H.263 → 3gp-h263 (very old phones, with AMR)"),
        ]
        for enc, what in checks:
            row(enc in tools.ffmpeg_encoders(), enc, what, f"brew install ffmpeg-full  {full_hint}")


def cmd_formats():
    print("""Supported conversions
=====================

Images   png jpg heic tiff bmp gif webp avif ico icns tga ppm pgm pbm pcx jp2 qoi
         dds sgi exr hdr psd, jxl (with jpeg-xl), dpx xpm (with ImageMagick)
         · between each other in any direction
         · input only: svg (vector, --dpi sets the size), eps ps ai (Ghostscript),
           pict, pcd (Photo CD), xcf (GIMP), fits (greyscale),
           camera RAW (dng cr2 cr3 nef arw orf rw2 raf pef …, via sips or libraw)
         · image(s) → pdf   (several inputs = one multi-page PDF; SVG/EPS/AI stay vector)

PDF      pdf → png/jpg/…   (one file per page, --dpi sets the resolution)
         pdf → md          (--extract-images saves the images next to it)
         pdf → txt, html
         · scanned pages without text are read with OCR
           (needs Tesseract language data, see 'doctor'; --ocr-lang deu+eng)
         pdf → docx        (optional: install pdf2docx)
         pdf → epub, mobi, azw3, fb2   (calibre)

Office   docx doc odt rtf pptx xlsx …
         · → pdf           (via LibreOffice)
         · → png/jpg       (one file per page)
         · docx/doc/odt/rtf → md, txt, html, docx, odt, rtf
         · docx/odt/rtf → epub, mobi, azw3, fb2

Markdown md → pdf (pandoc + typst, else Chrome), html, docx, odt, rtf, txt,
         epub, mobi, azw3, fb2

HTML     html → pdf, md, docx, odt, rtf, txt, epub, mobi, azw3, fb2

Text     txt → pdf, docx, rtf, html, epub, mobi, azw3, fb2

pandoc   rst org tex ipynb → md, html, docx, odt, rtf, txt, pdf, epub, mobi, azw3, fb2

E-books  (with calibre) epub mobi azw3 fb2 lit lrf between each other,
         → pdf, docx, txt, rtf, md, html, odt
         · input only: azw (old Kindle), cbz/cbr (comics → epub/mobi/azw3/pdf)
         · DRM-protected books cannot be converted

Audio    wav m4a aiff caf (built in) · with ffmpeg: mp3 wav m4a aac flac ogg opus aiff
         wma ac3 mp2 au caf mka wv m4b, alac (→ .m4a, lossless), amr (ffmpeg-full)
         · ogg = Vorbis (with ffmpeg-full, otherwise Opus in Ogg)
         · input only: eac3 dts ape ra oga weba

Video    (with ffmpeg) mp4 m4v mov mkv webm avi divx wmv asf flv mpg vob ts m2ts
         3gp ogv dv rm → each other, → gif, → any audio format
         · avi/divx: Xvid-compatible settings that play on older standalone players
           (max. 640×480, no B-frames, MP3)
         · vob = DVD (PAL 720×576, AC3), dv = PAL DV, mpg = MPEG-2 + MP2
         · ogv = Theora + Vorbis (with ffmpeg-full, otherwise VP8 + Opus)
         · 3gp = H.264 + AAC; 3gp-h263 = very old phones: H.263 176×144 + AMR
           (→ .3gp, 352×288 with a larger size; needs ffmpeg-full)
         · input only: rmvb f4v 3g2 qt mod tod vro m2v mxf

Subtitles srt ↔ vtt ↔ ass ↔ ssa (with ffmpeg)
         · mkv/mp4/mov/m4v/webm/ts → srt/vtt/ass/ssa: pull out the text subtitle track

3D       glb gltf obj fbx stl ply usdz usd abc → obj glb gltf fbx stl ply usdz usdc
         (with Blender; textures are copied next to the target or embedded)

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
  uniconverter film.mkv film.avi             Xvid AVI for older standalone players
  uniconverter film.mkv film.srt             pull the subtitles out of a video
  uniconverter book.epub book.azw3           e-book for Kindle (calibre)
  uniconverter notes.md notes.epub           Markdown → e-book (pandoc)
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
                   help="resolution for PDF/SVG/EPS → image (default 150)")
    p.add_argument("--extract-images", action="store_true",
                   help="PDF → md: also extract the images")
    p.add_argument("--ocr-lang", metavar="LANG", default=None,
                   help="OCR language(s) for scanned PDFs, e.g. deu+eng "
                        "(default: chosen from the installed language data)")
    p.add_argument("-f", "--force", action="store_true",
                   help="overwrite existing output files")
    p.add_argument("-n", "--dry-run", action="store_true",
                   help="only show what would be converted and with which engine")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="show the engine used and the external commands run")
    p.add_argument("--version", action="version", version=f"uniconverter {__version__}")
    return p


def err(msg):
    print(msg, file=sys.stderr)


def usage_error(msg):
    """Exit code 2: the command line itself is wrong (like argparse)."""
    err(msg)
    sys.exit(2)


def dry_run(jobs, merge, opts):
    def label(src, dst):
        try:
            return plan(src, dst, opts)[0]
        except ConvError as e:
            return f"not possible: {e}"

    if merge:
        inputs, dst = merge
        print(f"merge {len(inputs)} files → {dst}  (PyMuPDF)")
        for src in inputs:
            note = "as is" if ext_of(src) == "pdf" else label(src, Path("x.pdf"))
            print(f"  {src.name}  ({note})")
        return
    for src, dst in jobs:
        print(f"{src.name} → {output_path(src, dst)}  ({label(src, dst)})")


def main(argv=None):
    args = build_parser().parse_args(argv)
    tools.VERBOSE = args.verbose

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
            if outdir and not args.dry_run:
                outdir.mkdir(parents=True, exist_ok=True)
            for src in inputs:
                dst = (outdir or src.parent) / (src.stem + "." + target)
                jobs.append((src, dst))
    else:
        if len(files) < 2:
            usage_error("Error: output file missing. Example: uniconverter photo.heic photo.jpg")
        *inputs, dst = files
        if dst.exists() and dst in [Path(f) for f in inputs]:
            usage_error(f"Error: '{dst}' is both input and output.")
        if len(inputs) > 1:
            if ext_of(dst) != "pdf":
                usage_error("Error: several inputs need -t EXT (batch) "
                            "or a .pdf output file (merge).")
            merge = (inputs, dst)
        else:
            jobs.append((inputs[0], dst))

    for src in (merge[0] if merge else [j[0] for j in jobs]):
        if not src.exists():
            usage_error(f"Error: input file not found: {src}")

    if args.dry_run:
        return dry_run(jobs, merge, args)

    if merge:
        inputs, dst = merge
        if dst.exists() and not args.force:
            usage_error(f"Error: '{dst}' already exists (--force to overwrite).")
        try:
            merge_to_pdf(inputs, dst, args)
        except ConvError as e:
            err(f"✗ merge failed: {e}")
            sys.exit(1)
        return

    total, done, failed = len(jobs), 0, 0
    for i, (src, dst) in enumerate(jobs, 1):
        prefix = f"[{i}/{total}] " if total > 1 else ""
        real = output_path(src, dst)          # .alac → .m4a, .3gp-h263 → .3gp
        if src.resolve() == real.resolve():
            err(f"{prefix}✗ {src.name}: source and target are the same file – skipped")
            failed += 1
            continue
        if real.exists() and not args.force:
            err(f"{prefix}✗ {real.name} already exists (--force to overwrite)")
            failed += 1
            continue
        try:
            label, run_conversion = plan(src, dst, args)
            run_conversion()
        except ConvError as e:
            err(f"{prefix}✗ {src.name}: {e}")
            failed += 1
            continue
        except Exception as e:
            err(f"{prefix}✗ {src.name}: unexpected error: {e}")
            failed += 1
            continue
        engine = f"  ({label})" if args.verbose else ""
        print(f"{prefix}✓ {src.name} → {real}{engine}")
        done += 1
    if total > 1:
        print(f"{done} converted, {failed} failed" if failed else f"{done} converted")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
