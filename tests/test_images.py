"""Image formats beyond the basics: every writable format, input-only formats, vectors."""

import struct
import subprocess

import pytest
from conftest import needs_magick
from PIL import Image, ImageDraw

from uniconverter import router
from uniconverter.engines import images, tools
from uniconverter.errors import ConvError

SIZE = (160, 120)
SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="80" height="60" viewBox="0 0 80 60">
<rect width="80" height="60" fill="#0b5fff"/><circle cx="40" cy="30" r="20" fill="#ffcc00"/>
<text x="40" y="35" font-size="12" text-anchor="middle" fill="#000">uni</text></svg>
"""


@pytest.fixture(scope="module")
def rgba(tmp_path_factory):
    """160×120 RGBA gradient with a transparent hole."""
    im = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for x in range(SIZE[0]):
        d.line([(x, 0), (x, SIZE[1] - 1)], fill=(x * 255 // 159, 80, 255 - x * 255 // 159, 255))
    d.ellipse([20, 20, 70, 70], fill=(255, 255, 0, 128))
    d.rectangle([100, 60, 150, 110], fill=(0, 0, 0, 0))
    p = tmp_path_factory.mktemp("img") / "source.png"
    im.save(p)
    return p


def size_of(p):
    """Width and height via Pillow, else sips, else ImageMagick."""
    try:
        with Image.open(p) as im:
            im.load()
            return im.size
    except Exception:
        pass
    out = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(p)],
                         capture_output=True, text=True).stdout
    vals = dict(line.strip().split(": ", 1) for line in out.splitlines()
                if line.startswith("  ") and ": " in line)
    if vals.get("pixelWidth", "<nil>") != "<nil>":
        return int(vals["pixelWidth"]), int(vals["pixelHeight"])
    res = subprocess.run([tools.MAGICK, "identify", "-format", "%w %h", f"{p}[0]"],
                         capture_output=True, text=True)
    w, h = res.stdout.split()[:2]
    return int(w), int(h)


def writable():
    return sorted(set(router.possible_targets("png")) - {"pdf"})


@pytest.mark.parametrize("target", writable())
def test_png_to_every_image_format(rgba, tmp_path, opts, target):
    out = tmp_path / f"out.{target}"
    router.convert_one(rgba, out, opts())
    assert out.stat().st_size > 0
    w, h = size_of(out)
    if target in ("ico", "icns"):
        assert w == h                                  # icons are padded square
    else:
        assert (w, h) == SIZE


@pytest.mark.parametrize("target", [t for t in writable() if t not in ("ico", "icns", "gif")])
def test_every_image_format_reads_back(rgba, tmp_path, opts, target):
    mid = tmp_path / f"mid.{target}"
    router.convert_one(rgba, mid, opts())
    out = tmp_path / "back.png"
    router.convert_one(mid, out, opts())
    assert Image.open(out).size == SIZE


def test_transparency_becomes_white_in_jpeg(rgba, tmp_path, opts):
    out = tmp_path / "flat.jpg"
    router.convert_one(rgba, out, opts())
    assert min(Image.open(out).convert("RGB").getpixel((125, 85))) >= 240


def test_cmyk_jpeg_to_png(rgba, tmp_path, opts):
    cmyk = tmp_path / "cmyk.jpg"
    Image.open(rgba).convert("RGB").convert("CMYK").save(cmyk)
    out = tmp_path / "rgb.png"
    router.convert_one(cmyk, out, opts())
    assert Image.open(out).mode in ("RGB", "RGBA")


def test_svg_is_rendered_at_dpi(tmp_path, opts):
    svg = tmp_path / "logo.svg"
    svg.write_text(SVG, encoding="utf-8")
    for dpi in (150, 300):
        out = tmp_path / f"logo-{dpi}.png"
        router.convert_one(svg, out, opts(dpi=dpi))
        w, h = Image.open(out).size
        assert abs(w - 80 * dpi / 72) <= 2 and abs(h - 60 * dpi / 72) <= 2


def test_svg_to_pdf_stays_vector(tmp_path, opts):
    svg = tmp_path / "logo.svg"
    svg.write_text(SVG, encoding="utf-8")
    out = tmp_path / "logo.pdf"
    router.convert_one(svg, out, opts())
    assert "uni" in tools.load_fitz().open(str(out))[0].get_text()


@pytest.mark.skipif(not tools.CJXL, reason="no cjxl (brew install jpeg-xl)")
def test_jxl_is_real_jpeg_xl(rgba, tmp_path, opts):
    out = tmp_path / "out.jxl"
    router.convert_one(rgba, out, opts())
    head = out.read_bytes()[:12]
    assert head[:2] == b"\xff\x0a" or head == b"\x00\x00\x00\x0cJXL \r\n\x87\n"


@needs_magick
@pytest.mark.parametrize("ext", ["xpm", "pict", "fits"])
def test_input_only_formats_via_imagemagick(rgba, tmp_path, opts, ext):
    if not tools.magick_can(ext, "w"):
        pytest.skip(f"this ImageMagick cannot write .{ext} test files")
    src = tmp_path / f"in.{ext}"
    images.magick([str(rgba), "-background", "white", "-flatten",
                   ("PICT:" if ext == "pict" else "") + str(src)])
    out = tmp_path / "back.png"
    router.convert_one(src, out, opts())
    assert Image.open(out).size == SIZE


@pytest.mark.skipif(not (tools.MAGICK and tools.GS), reason="no ImageMagick + Ghostscript")
@pytest.mark.parametrize("ext", ["eps", "ai", "ps"])
def test_postscript_family(rgba, tmp_path, opts, ext):
    src = tmp_path / f"drawing.{ext}"
    images.magick([str(rgba), "-background", "white", "-flatten", str(src)])
    png = tmp_path / "drawing.png"
    router.convert_one(src, png, opts(dpi=150))
    w, h = Image.open(png).size
    assert abs(w - SIZE[0] * 150 / 72) <= 3 and abs(h - SIZE[1] * 150 / 72) <= 3
    pdf = tmp_path / "drawing.pdf"
    router.convert_one(src, pdf, opts())
    page = tools.load_fitz().open(str(pdf))[0]
    if ext != "ps":                    # EPS/AI: the page is the drawing (EPSCrop)
        assert abs(page.rect.width - SIZE[0]) <= 2 and abs(page.rect.height - SIZE[1]) <= 2


def make_dng(path, w=160, h=120):
    """Minimal valid DNG (Bayer RGGB, 12 bit): red on the left, blue on the right."""
    px = bytearray()
    for y in range(h):
        for x in range(w):
            r, b, g = int(4095 * (1 - x / (w - 1))), int(4095 * x / (w - 1)), 1200
            c = r if (y % 2, x % 2) == (0, 0) else b if (y % 2, x % 2) == (1, 1) else g
            px += struct.pack("<H", c)
    entries = []

    def tag(nr, typ, values):
        fmt = {1: "B", 2: "s", 3: "H", 4: "I", 5: "II", 10: "ii"}[typ]
        if typ == 2:
            data = values.encode() + b"\0"
            count = len(data)
        else:
            data = b"".join(struct.pack("<" + fmt, *(v if isinstance(v, tuple) else (v,)))
                            for v in values)
            count = len(values)
        entries.append((nr, typ, count, data))
    for args in ((254, 4, [0]), (256, 4, [w]), (257, 4, [h]), (258, 3, [16]), (259, 3, [1]),
                 (262, 3, [32803]), (271, 2, "uniconverter"), (272, 2, "test"),
                 (273, 4, [0]), (274, 3, [1]), (277, 3, [1]), (278, 4, [h]),
                 (279, 4, [len(px)]), (284, 3, [1]), (33421, 3, [2, 2]),
                 (33422, 1, [0, 1, 1, 2]), (50706, 1, [1, 4, 0, 0]), (50707, 1, [1, 1, 0, 0]),
                 (50708, 2, "uniconverter test"), (50714, 4, [0]), (50717, 4, [4095]),
                 (50721, 10, [(1, 1), (0, 1), (0, 1), (0, 1), (1, 1), (0, 1), (0, 1),
                              (0, 1), (1, 1)]),
                 (50728, 5, [(1, 1)] * 3), (50778, 3, [21])):
        tag(*args)
    entries.sort()
    extra_off = 8 + 2 + len(entries) * 12 + 4
    extra, recs = bytearray(), []
    for nr, typ, count, data in entries:
        if len(data) <= 4:
            recs.append([nr, struct.pack("<HHI", nr, typ, count) + data.ljust(4, b"\0")])
        else:
            recs.append([nr, struct.pack("<HHII", nr, typ, count, extra_off + len(extra))])
            extra += data + (b"\0" if len(data) % 2 else b"")
    data_off = extra_off + len(extra)
    for r in recs:
        if r[0] == 273:
            r[1] = r[1][:8] + struct.pack("<I", data_off)
    path.write_bytes(b"II*\0" + struct.pack("<IH", 8, len(recs)) + b"".join(r[1] for r in recs)
                     + b"\0\0\0\0" + bytes(extra) + bytes(px))


def test_camera_raw(tmp_path, opts):
    dng = tmp_path / "camera.dng"
    make_dng(dng)
    out = tmp_path / "camera.png"
    try:
        router.convert_one(dng, out, opts())
    except ConvError:
        pytest.skip("no RAW reader for this synthetic DNG (sips or ImageMagick with libraw)")
    im = Image.open(out).convert("RGB")
    left, right = im.getpixel((5, 60)), im.getpixel((154, 60))
    assert im.size == SIZE and left[0] > 200 > left[2] and right[2] > 200 > right[0]


@needs_magick
def test_imagemagick_never_fetches_urls(tmp_path):
    """The bundled policy forbids URL coders: nothing is downloaded."""
    with pytest.raises(ConvError, match="not authorized|security policy"):
        images.magick(["https://example.invalid/x.png", str(tmp_path / "x.png")])


def test_unreadable_file_explains(tmp_path, opts):
    bad = tmp_path / "broken.tga"
    bad.write_bytes(b"not an image")
    with pytest.raises(ConvError):
        router.convert_one(bad, tmp_path / "x.png", opts())


def test_image_to_pdf_with_exotic_source(rgba, tmp_path, opts):
    tga = tmp_path / "src.tga"
    router.convert_one(rgba, tga, opts())
    pdf = tmp_path / "src.pdf"
    router.convert_one(tga, pdf, opts())
    assert len(tools.load_fitz().open(str(pdf))) == 1
