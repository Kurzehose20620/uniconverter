"""Making files smaller: --width/--height/--max, --small and --target-size."""

import shutil
import subprocess

import pytest
from conftest import ffmpeg, make_opts, needs_ffmpeg, probe
from PIL import Image

from uniconverter import cli, router, sizing
from uniconverter.engines import media, tools

# ---------------------------------------------------------------- option parsing


@pytest.mark.parametrize("text, expected", [
    ("50MB", 50_000_000), ("50M", 50_000_000), ("1.5GB", 1_500_000_000),
    ("700k", 700_000), ("2 MiB", 2 * 1024 ** 2), ("1,5mb", 1_500_000), ("123", 123),
])
def test_parse_size(text, expected):
    assert sizing.parse_size(text) == expected


@pytest.mark.parametrize("text", ["", "MB", "-5MB", "5 parsecs", "0"])
def test_parse_size_rejects_nonsense(text):
    with pytest.raises(ValueError):
        sizing.parse_size(text)


def test_box_combines_width_height_and_max():
    assert sizing.box(make_opts()) is None
    assert sizing.box(make_opts(max=800)) == (800, 800)
    assert sizing.box(make_opts(width=1000)) == (1000, None)
    assert sizing.box(make_opts(height=720)) == (None, 720)
    assert sizing.box(make_opts(width=1000, max=800)) == (800, 800)
    assert sizing.box(make_opts(width=500, height=900, max=800)) == (500, 800)


@pytest.mark.parametrize("size, limit, expected", [
    ((4000, 3000), (800, 800), (800, 600)),       # landscape: longest side
    ((3000, 4000), (800, 800), (600, 800)),       # portrait
    ((400, 300), (800, 800), (400, 300)),         # never enlarged
    ((1920, 1080), (None, 720), (1280, 720)),
    ((1920, 1080), (1000, None), (1000, 562)),
])
def test_fit(size, limit, expected):
    assert sizing.fit(size, limit) == expected


def test_cli_rejects_bad_sizes(capsys):
    for argv in (["a.jpg", "b.jpg", "--max", "3"], ["a.mp4", "b.mp4", "--target-size", "lots"]):
        with pytest.raises(SystemExit) as e:
            cli.main(argv)
        assert e.value.code == 2


# ---------------------------------------------------------------- images


@pytest.fixture
def photo(tmp_path):
    """A 1600×1200 photo with an EXIF orientation tag and some detail."""
    im = Image.effect_mandelbrot((1600, 1200), (-2, -1.5, 1, 1.5), 60).convert("RGB")
    exif = Image.Exif()
    exif[0x010F] = "Camera Maker"
    p = tmp_path / "photo.jpg"
    im.save(p, quality=95, exif=exif.tobytes())
    return p


def test_image_max_keeps_aspect_ratio(photo, tmp_path, opts):
    out = tmp_path / "small.webp"
    router.convert_one(photo, out, opts(max=800))
    assert Image.open(out).size == (800, 600)


@pytest.mark.parametrize("kw, expected", [
    ({"width": 400}, (400, 300)), ({"height": 300}, (400, 300)),
    ({"max": 5000}, (1600, 1200)),                 # never enlarged
    ({"width": 1000, "height": 300}, (400, 300)),  # the tighter limit wins
])
def test_image_width_height(photo, tmp_path, opts, kw, expected):
    out = tmp_path / "out.png"
    router.convert_one(photo, out, opts(**kw))
    assert Image.open(out).size == expected


def test_same_format_with_small_is_smaller_and_has_no_metadata(photo, tmp_path, opts):
    plain, small = tmp_path / "plain.jpg", tmp_path / "small.jpg"
    router.convert_one(photo, plain, opts())
    router.convert_one(photo, small, opts(small=True))
    assert small.stat().st_size < plain.stat().st_size < photo.stat().st_size * 1.5
    assert not Image.open(small).getexif()


def test_png_small_is_optimised(tmp_path, opts):
    src = tmp_path / "flat.png"
    Image.new("RGB", (600, 400), (10, 120, 200)).save(src, compress_level=0)
    out = tmp_path / "flat-small.png"
    router.convert_one(src, out, opts(small=True))
    assert out.stat().st_size < src.stat().st_size / 10


def test_exif_orientation_is_applied(tmp_path, opts):
    src = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6                                  # "rotate 90° clockwise"
    Image.new("RGB", (300, 200), (0, 0, 255)).save(src, exif=exif.tobytes())
    out = tmp_path / "upright.png"
    router.convert_one(src, out, opts())
    assert Image.open(out).size == (200, 300)


def test_colour_profile_is_kept(tmp_path, opts):
    from PIL import ImageCms
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = tmp_path / "p3.png"
    Image.new("RGB", (64, 64), (200, 10, 10)).save(src, icc_profile=icc)
    for ext in ("jpg", "webp"):
        out = tmp_path / f"p3.{ext}"
        router.convert_one(src, out, opts(small=True, max=32))
        assert Image.open(out).info.get("icc_profile") == icc


def test_pdf_pages_fit_into_the_box(fixtures, tmp_path, opts):
    out = tmp_path / "page.png"
    router.convert_one(fixtures / "mini.pdf", out, opts(max=300, dpi=300))
    assert max(Image.open(out).size) <= 300


def test_cli_batch_same_format_never_replaces_the_source(photo, tmp_path, capsys):
    other = tmp_path / "second.jpg"
    shutil.copy(photo, other)
    before = photo.read_bytes()
    assert cli.main([str(photo), str(other), "-t", "jpg", "--max", "640"]) is None
    assert photo.read_bytes() == before
    assert Image.open(tmp_path / "photo-small.jpg").size == (640, 480)
    assert Image.open(tmp_path / "second-small.jpg").size == (640, 480)
    assert "2 converted" in capsys.readouterr().out


def test_cli_batch_into_folder_keeps_names(photo, tmp_path):
    out = tmp_path / "web"
    assert cli.main([str(photo), "-t", "jpg", "--max", "640", "-o", str(out)]) is None
    assert Image.open(out / "photo.jpg").size == (640, 480)


def test_cli_single_file_to_new_name(photo, tmp_path):
    dst = tmp_path / "photo-klein.jpg"
    assert cli.main([str(photo), str(dst), "--max", "800", "--small"]) is None
    assert Image.open(dst).size == (800, 600)


# ---------------------------------------------------------------- video: filters and profiles


def test_scale_filter_strings():
    assert media.scale_filter(make_opts()) == "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    assert media.scale_filter(make_opts(height=720)) == (
        "scale='iw':'min(720,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2")
    assert media.scale_filter(make_opts(max=1280), 640, 480, setsar=True) == (
        "scale='min(640,iw)':'min(480,ih)'"
        ":force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1")


def test_avi_profile_is_unchanged(tmp_path):
    """The Xvid profile was verified on real hardware – these arguments must stay."""
    args = media.video_plan(tmp_path / "x.mp4", "avi", make_opts()).args
    assert args == [
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", "scale='min(640,iw)':'min(480,ih)'"
               ":force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1",
        "-c:v", "mpeg4", "-vtag", "XVID", "-pix_fmt", "yuv420p",
        "-b:v", "1000k", "-maxrate", "2000k", "-bufsize", "2000k",
        "-g", "240", "-bf", "0", "-mbd", "rd",
        "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "48000", "-ac", "2"]
    divx = media.video_plan(tmp_path / "x.mp4", "divx", make_opts()).args
    assert divx[divx.index("-vtag") + 1] == "DIVX" and divx[-2:] == ["-f", "avi"]
    lower = media.video_plan(tmp_path / "x.mp4", "avi", make_opts(height=240)).args
    assert "min(240,ih)" in lower[lower.index("-vf") + 1]


@pytest.mark.parametrize("fmt", ["mp4", "webm", "avi", "wmv", "flv", "mpg", "3gp", "rm", "ogv"])
def test_small_lowers_the_bitrate_or_quality(tmp_path, fmt, monkeypatch):
    monkeypatch.setattr(media, "probe", lambda src: {"fps": 25.0})
    normal = media.video_plan(tmp_path / "x.mp4", fmt, make_opts()).args
    small = media.video_plan(tmp_path / "x.mp4", fmt, make_opts(small=True)).args
    assert normal != small


def test_target_size_needs_a_supported_format(tmp_path):
    from uniconverter.errors import ConvError
    with pytest.raises(ConvError, match="--target-size works for"):
        media._target_bitrate(tmp_path / "x.mp4", "flv", make_opts(target_size=10 ** 6))


# ---------------------------------------------------------------- video: real encodes


def _size(p):
    v = probe(p)["video"]
    return v["width"], v["height"]


@needs_ffmpeg
@pytest.mark.parametrize("kw, expected", [
    ({"height": 720}, (1280, 720)), ({"max": 640}, (640, 360)), ({"width": 854}, (854, 480)),
    ({"max": 4000}, (1280, 720)),                 # never enlarged
])
def test_video_box(hd_clip, tmp_path, opts, kw, expected):
    out = tmp_path / "out.mp4"
    router.convert_one(hd_clip, out, opts(**kw))
    assert _size(out) == expected


@needs_ffmpeg
def test_video_same_format_small_is_smaller(hd_clip, tmp_path, opts):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    router.convert_one(hd_clip, a, opts())
    router.convert_one(hd_clip, b, opts(small=True))
    assert b.stat().st_size < a.stat().st_size
    assert probe(b)["audio"]["codec_name"] == "aac"


@needs_ffmpeg
def test_portrait_video_max(tmp_path, opts):
    src = tmp_path / "portrait.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=720x1280:rate=25:duration=1",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", src)
    out = tmp_path / "portrait-small.mov"
    router.convert_one(src, out, opts(max=640))
    assert _size(out) == (360, 640)


@needs_ffmpeg
def test_odd_sizes_become_even(tmp_path, opts):
    src = tmp_path / "odd.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=1",
           "-c:v", "libx264", "-pix_fmt", "yuv444p", src)
    out = tmp_path / "odd-small.mp4"
    router.convert_one(src, out, opts(width=333))
    w, h = _size(out)
    assert w % 2 == 0 and h % 2 == 0 and w <= 333


@needs_ffmpeg
def test_gif_is_never_enlarged(clip, tmp_path, opts):
    out = tmp_path / "clip.gif"
    router.convert_one(clip, out, opts())
    assert _size(out) == (320, 240)
    router.convert_one(clip, tmp_path / "tiny.gif", opts(max=160, small=True))
    assert _size(tmp_path / "tiny.gif") == (160, 120)


@needs_ffmpeg
@pytest.mark.parametrize("fmt", ["mp4", "webm", "avi"])
def test_target_size(tmp_path, opts, fmt):
    if fmt not in media.video_out_formats():
        pytest.skip(f"this ffmpeg cannot write .{fmt}")
    noisy = tmp_path / "noisy.mkv"     # film grain: the encoder really needs the bits
    ffmpeg("-f", "lavfi", "-i", "testsrc2=s=480x270:r=25:d=8,noise=alls=10:allf=t",
           "-f", "lavfi", "-i", "sine=duration=8", "-c:v", "libx264", "-crf", "12",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", noisy)
    target = 800_000
    out = tmp_path / f"mail.{fmt}"
    router.convert_one(noisy, out, opts(target_size=target))
    assert 0.7 * target < out.stat().st_size < 1.1 * target


@needs_ffmpeg
def test_target_size_too_small_explains(clip, tmp_path, opts):
    from uniconverter.errors import ConvError
    with pytest.raises(ConvError, match="too small"):
        router.convert_one(clip, tmp_path / "x.mp4", opts(target_size=2000))


# ---------------------------------------------------------------- AVI on older players


def avi_check(path, size, tag="XVID"):
    p = probe(path)
    v, a = p["video"], p["audio"]
    assert (v["width"], v["height"]) == size
    assert str(v.get("has_b_frames")) == "0"
    assert v["codec_name"] == "mpeg4" and v["codec_tag_string"] == tag
    assert a["codec_name"] == "mp3" and a["sample_rate"] == "48000" and a["channels"] == 2


@needs_ffmpeg
def test_avi_from_hd_with_b_frames(hd_clip, tmp_path, opts):
    out = tmp_path / "player.avi"
    router.convert_one(hd_clip, out, opts())
    avi_check(out, (640, 360))


@needs_ffmpeg
def test_avi_via_cli_with_height(hd_clip, tmp_path):
    out = tmp_path / "player-240.avi"
    assert cli.main([str(hd_clip), str(out), "--height", "240"]) is None
    avi_check(out, (426, 240))


@needs_ffmpeg
def test_divx_tag(hd_clip, tmp_path, opts):
    out = tmp_path / "player.divx"
    router.convert_one(hd_clip, out, opts())
    avi_check(out, (640, 360), tag="DIVX")


@needs_ffmpeg
def test_avi_small_still_without_b_frames(hd_clip, tmp_path, opts):
    a, b = tmp_path / "a.avi", tmp_path / "b.avi"
    router.convert_one(hd_clip, a, opts())
    router.convert_one(hd_clip, b, opts(small=True))
    assert b.stat().st_size < a.stat().st_size
    assert str(probe(b)["video"]["has_b_frames"]) == "0"


@needs_ffmpeg
def test_audio_small_lowers_bitrate(tone, tmp_path, opts):
    a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
    router.convert_one(tone, a, opts())
    router.convert_one(tone, b, opts(small=True))
    assert b.stat().st_size < a.stat().st_size


def test_ffmpeg_never_opens_network_protocols():
    assert media.FF_INPUT == ["-protocol_whitelist", "file,pipe,data"]
    if tools.FFMPEG:
        res = subprocess.run([tools.FFMPEG, "-v", "error", *media.FF_INPUT,
                              "-i", "https://example.invalid/x.mp4", "-f", "null", "-"],
                             capture_output=True, text=True)
        assert res.returncode != 0 and "not on whitelist" in res.stderr
