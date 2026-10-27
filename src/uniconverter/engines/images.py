"""Images: image → image and image(s) → PDF.

Every source is first opened as a Pillow image – directly, or through PyMuPDF (SVG),
Ghostscript (EPS/PS/AI), sips (camera RAW, JPEG XL, EXR), djxl, ImageMagick or
ffmpeg – then scaled down if asked and written by Pillow, or by sips/cjxl/ImageMagick
for the formats Pillow cannot write.
"""

import tempfile
from pathlib import Path

from .. import sizing
from ..errors import ConvError
from ..formats import IMAGE_MAGICK_OUT, IMAGE_OUT, IMAGE_RAW_EXT, IMAGE_VECTOR_IN, ext_of
from . import tools
from .tools import need, pip_hint, run

SIPS_FORMATS = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "tif": "tiff",
                "tiff": "tiff", "gif": "gif", "bmp": "bmp", "heic": "heic",
                "pdf": "pdf", "exr": "exr", "psd": "psd", "jp2": "jp2",
                "tga": "tga", "icns": "icns", "avif": "avif"}
PIL_OUT = IMAGE_OUT - {"exr", "hdr", "psd"}       # sips writes exr/psd, ImageMagick hdr
NO_ALPHA_OUT = {"jpg", "jpeg", "bmp", "pcx", "ppm", "pgm", "pbm", "pnm"}
# Pillow reads only the embedded preview of camera RAW files (or nothing): sips first
SIPS_FIRST = IMAGE_RAW_EXT | {"jxl", "exr", "pict", "pct"}
QUALITY_OUT = {"jpg", "jpeg", "webp", "avif", "heic", "heif", "jxl"}
SMALL_QUALITY = {"jpg": 70, "jpeg": 70, "webp": 70, "jxl": 70,
                 "avif": 55, "heic": 55, "heif": 55}
ICC_OUT = {"jpg", "jpeg", "png", "webp", "tif", "tiff", "avif", "heic", "heif"}
MAGICK_HINT = "brew install imagemagick  (or imagemagick-full for RAW, EPS and more)"


def magick(args, err_hint=""):
    """Run ImageMagick under uniconverter's policy (no network, no scripts)."""
    need(tools.MAGICK, "ImageMagick", MAGICK_HINT)
    return run([tools.MAGICK, *args], err_hint=err_hint, env=tools.magick_env())


def image_out_formats():
    """Image formats this machine can write."""
    out = set(IMAGE_OUT) - {"hdr"}
    if tools.magick_can("hdr", "w") or tools.FFMPEG:
        out.add("hdr")
    if tools.CJXL or tools.magick_can("jxl", "w"):
        out.add("jxl")
    out |= {f for f in IMAGE_MAGICK_OUT if tools.magick_can(f, "w")}
    return out


def _has_alpha(im):
    return im.mode in ("RGBA", "LA", "PA", "La", "RGBa") or \
        (im.mode == "P" and "transparency" in im.info)


def _load(Image, path):
    im = Image.open(path)
    im.load()
    return im


def open_image(src: Path, tmpdir: str, opts):
    """The source as a loaded Pillow image, reading it through other engines if needed."""
    Image = tools.load_pil()
    need(Image, "Pillow", pip_hint("pillow pillow-heif"))
    se = ext_of(src)
    tmp = Path(tmpdir) / "uniconverter-read.png"
    if se == "svg":
        fitz = tools.load_fitz()
        if fitz is not None:
            try:
                # rendered as vector: --dpi sets the size (72 = nominal size)
                zoom = getattr(opts, "dpi", 150) / 72.0
                doc = fitz.open(str(src))
                doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True).save(str(tmp))
                return _load(Image, tmp)
            except Exception:
                pass
    elif se in IMAGE_VECTOR_IN:
        need(tools.MAGICK and tools.GS, "ImageMagick + Ghostscript (for .eps/.ps/.ai)",
             "brew install imagemagick ghostscript")
        magick(["-density", str(getattr(opts, "dpi", 150)), f"{src}[0]", f"PNG32:{tmp}"])
        return _load(Image, tmp)
    elif se not in SIPS_FIRST:
        try:
            return _load(Image, src)
        except Exception:
            pass
    attempts = [["sips", "-s", "format", "png", str(src), "--out", str(tmp)]]
    if se == "jxl" and tools.DJXL:
        attempts.append([tools.DJXL, str(src), str(tmp)])
    if tools.MAGICK:
        attempts.append("magick")
    if tools.FFMPEG:
        attempts.append([tools.FFMPEG, "-y", "-v", "error", "-i", str(src),
                         "-frames:v", "1", str(tmp)])
    for cmd in attempts:
        try:
            tmp.unlink(missing_ok=True)
            if cmd == "magick":
                magick([f"{src}[0]", f"PNG32:{tmp}"])
            else:
                run(cmd)
            return _load(Image, tmp)
        except Exception:
            continue
    hint = f" – ImageMagick may help: {MAGICK_HINT}" if not tools.MAGICK else ""
    raise ConvError(f".{se} could not be read{hint}")


def _upright(im):
    """Apply the EXIF orientation, so photos are not saved sideways."""
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(im) or im
    except Exception:
        return im


def shrink(im, opts):
    """Scale down into the --width/--height/--max box (never up, aspect ratio kept)."""
    limit = sizing.box(opts)
    if not limit:
        return im
    size = sizing.fit(im.size, limit)
    if size == im.size:
        return im
    from PIL import Image as I
    if im.mode in ("P", "1"):
        im = im.convert("RGBA" if _has_alpha(im) else "RGB")
    return im.resize(size, I.Resampling.LANCZOS)


def quality_for(de, opts):
    q = opts.quality
    if sizing.small(opts):
        q = min(q, SMALL_QUALITY.get(de, q))
    return q


def _colour_family(mode):
    return {"RGB": "rgb", "RGBA": "rgb", "RGBX": "rgb", "P": "rgb", "PA": "rgb",
            "L": "gray", "LA": "gray", "CMYK": "cmyk"}.get(mode, mode)


def _pil_prepare(im, de, opts):
    """Adapt the image mode to the target format; returns (image, save options)."""
    from PIL import Image as I
    src_mode, icc = im.mode, im.info.get("icc_profile")
    if de in NO_ALPHA_OUT and im.mode not in ("RGB", "L", "1"):
        im = im.convert("RGBA")                     # transparency onto white
        bg = I.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.split()[-1])
        im = bg
    if de == "pgm":
        im = im.convert("L")
    elif de == "pbm":
        im = im.convert("1")
    elif de in ("ico", "icns"):
        # icons are square: pad transparently instead of distorting
        im = im.convert("RGBA")
        side = max(im.size)
        if im.size[0] != im.size[1]:
            sq = I.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(im, ((side - im.size[0]) // 2, (side - im.size[1]) // 2))
            im = sq
    elif de in ("qoi", "dds", "heic", "heif", "avif", "sgi", "jp2", "tga", "webp") \
            and im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if _has_alpha(im) else "RGB")
    elif im.mode not in ("1", "L", "LA", "P", "RGB", "RGBA"):
        im = im.convert("RGBA" if _has_alpha(im) else "RGB")
    kwargs = {}
    if de in ("jpg", "jpeg"):
        kwargs = {"quality": quality_for(de, opts), "optimize": True}
    elif de in ("webp", "avif", "heic", "heif"):
        kwargs = {"quality": quality_for(de, opts)}
        if de == "webp" and sizing.small(opts):
            kwargs["method"] = 6
    elif de == "png" and sizing.small(opts):
        kwargs = {"optimize": True}
    # keep the colour profile (Display P3 photos would look dull without it), but only
    # when the colour model did not change; EXIF and other metadata are not copied
    if icc and de in ICC_OUT and _colour_family(src_mode) == _colour_family(im.mode):
        kwargs["icc_profile"] = icc
    for key in ("exif", "xmp", "XML:com.adobe.xmp", "comment"):
        im.info.pop(key, None)
    return im, kwargs


def img_to_img(src: Path, dst: Path, opts):
    de = ext_of(dst)
    with tempfile.TemporaryDirectory() as td:
        im = shrink(_upright(open_image(src, td, opts)), opts)
        if de in PIL_OUT:
            try:
                out, kwargs = _pil_prepare(im, de, opts)
                out.save(dst, **kwargs)
                return
            except Exception:
                dst.unlink(missing_ok=True)     # on to sips / ImageMagick
        # lossless PNG intermediate, then cjxl / sips / ImageMagick / ffmpeg
        tmp = Path(td) / "uniconverter-write.png"
        if im.mode not in ("RGB", "RGBA", "L", "LA"):
            im = im.convert("RGBA" if _has_alpha(im) else "RGB")
        im.save(tmp)
        q = str(quality_for(de, opts))
        attempts = []
        if de == "jxl" and tools.CJXL:
            attempts.append([tools.CJXL, "--quiet", str(tmp), str(dst), "-q", q])
        if de in SIPS_FORMATS:
            cmd = ["sips", "-s", "format", SIPS_FORMATS[de]]
            if SIPS_FORMATS[de] == "jpeg":
                cmd += ["-s", "formatOptions", q]
            attempts.append(cmd + [str(tmp), "--out", str(dst)])
        if tools.MAGICK:
            attempts.append(["magick", str(tmp), "-quality", q, str(dst)])
        if tools.FFMPEG and de in ("hdr", "exr"):
            attempts.append([tools.FFMPEG, "-y", "-v", "error", "-i", str(tmp), str(dst)])
        error = None
        for cmd in attempts:
            try:
                if cmd[0] == "magick":
                    magick(cmd[1:])
                else:
                    run(cmd)
                if dst.exists() and dst.stat().st_size > 0:
                    return
            except ConvError as e:
                error = e
        if error:
            raise error
        need(tools.MAGICK, f"ImageMagick (for .{de})", MAGICK_HINT)
        raise ConvError(f".{de} could not be written")


def _img_for_fitz(src: Path, tmpdir: str):
    """Normalise HEIC/WebP/AVIF etc. to PNG so PyMuPDF can open it (SVG stays vector)."""
    if ext_of(src) in ("png", "jpg", "jpeg", "bmp", "gif", "tif", "tiff", "svg"):
        return src
    out = Path(tmpdir) / (src.stem + ".png")

    class _O:  # minimal options for the intermediate conversion
        quality = 95
        dpi = 150
    img_to_img(src, out, _O)
    return out


def vector_to_pdf(src: Path, dst: Path, opts):
    """EPS/PS/AI → PDF as vectors (Ghostscript, -dSAFER: no file access beyond the input)."""
    need(tools.GS, "Ghostscript", "brew install ghostscript")
    run([tools.GS, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pdfwrite", "-dEPSCrop",
         f"-sOutputFile={dst}", str(src)])


def imgs_to_pdf(sources, dst: Path, opts):
    if len(sources) == 1 and ext_of(sources[0]) in IMAGE_VECTOR_IN and tools.GS:
        return vector_to_pdf(sources[0], dst, opts)
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
    need(tools.MAGICK, "ImageMagick or PyMuPDF", MAGICK_HINT)
    magick([str(s) for s in sources] + [str(dst)])
