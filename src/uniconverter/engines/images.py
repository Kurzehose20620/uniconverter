"""Images: image → image (Pillow → sips → ImageMagick) and image(s) → PDF (PyMuPDF)."""

import tempfile
from pathlib import Path

from ..formats import ext_of
from . import tools
from .tools import need, run

SIPS_FORMATS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "tif": "tiff",
                "tiff": "tiff", "gif": "gif", "bmp": "bmp", "heic": "heic",
                "pdf": "pdf"}


def img_to_img(src: Path, dst: Path, opts):
    de = ext_of(dst)
    Image = tools.load_pil()
    if Image is not None:
        try:
            im = Image.open(src)
            if de in ("jpg", "jpeg", "bmp") and im.mode not in ("RGB", "L"):
                # flatten transparency onto a white background
                im = im.convert("RGBA")
                bg = Image.new("RGB", im.size, (255, 255, 255))
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
            pass  # fall through to sips / ImageMagick
    if de in SIPS_FORMATS:
        cmd = ["sips", "-s", "format", SIPS_FORMATS[de]]
        if SIPS_FORMATS[de] == "jpeg":
            cmd += ["-s", "formatOptions", str(opts.quality)]
        run(cmd + [str(src), "--out", str(dst)])
        return
    need(tools.MAGICK, f"ImageMagick (for .{de})", "brew install imagemagick")
    run([tools.MAGICK, str(src), "-quality", str(opts.quality), str(dst)])


def _img_for_fitz(src: Path, tmpdir: str):
    """Normalise HEIC/WebP/AVIF etc. to PNG so PyMuPDF can open it."""
    if ext_of(src) in ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff"):
        return src
    out = Path(tmpdir) / (src.stem + ".png")

    class _O:  # minimal options for the intermediate conversion
        quality = 95
    img_to_img(src, out, _O)
    return out


def imgs_to_pdf(sources, dst: Path, opts):
    fitz = tools.load_fitz()
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
    need(tools.MAGICK, "ImageMagick or PyMuPDF", "brew install imagemagick")
    run([tools.MAGICK] + [str(s) for s in sources] + [str(dst)])
