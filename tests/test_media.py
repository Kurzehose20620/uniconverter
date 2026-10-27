"""Audio, video and subtitles through ffmpeg: every offered target, checked with ffprobe.

Which targets are offered depends on the encoders of the installed ffmpeg (the full
Homebrew build adds Theora, Vorbis, AMR and H.263), so the expectations follow it.
"""

import pytest
from conftest import decodes, ffmpeg, needs_ffmpeg, probe

from uniconverter import formats, router
from uniconverter.engines import tools
from uniconverter.errors import ConvError

pytestmark = needs_ffmpeg


def ogg_audio():
    return "vorbis" if tools.ff_has("libvorbis") else "opus"


def video_expected(target):
    """(video codec, audio codec) a target should contain."""
    h264 = ("h264", "aac")
    return {
        "mp4": h264, "m4v": h264, "mov": h264, "mkv": h264, "ts": h264, "m2ts": h264,
        "mts": h264, "3gp": h264, "webm": ("vp9", "opus"), "avi": ("mpeg4", "mp3"),
        "divx": ("mpeg4", "mp3"), "wmv": ("wmv2", "wmav2"), "asf": ("wmv2", "wmav2"),
        "flv": ("flv1", "mp3"), "mpg": ("mpeg2video", "mp2"), "mpeg": ("mpeg2video", "mp2"),
        "vob": ("mpeg2video", "ac3"), "dv": ("dvvideo", "pcm_s16le"),
        "ogv": ("theora" if tools.ff_has("libtheora") else "vp8", ogg_audio()),
        "rm": ("rv20", "ac3"), "3gp-h263": ("h263", "amr_nb"),
    }[target]


AUDIO_EXPECTED = {
    "mp3": "mp3", "wav": "pcm_s16le", "m4a": "aac", "m4b": "aac", "alac": "alac",
    "aac": "aac", "flac": "flac", "opus": "opus", "aiff": "pcm_s16be", "caf": "pcm_s16le",
    "wma": "wmav2", "ac3": "ac3", "mp2": "mp2", "au": "pcm_s16be", "mka": "flac",
    "wv": "wavpack", "amr": "amr_nb",
}


def offered_video_targets():
    if not tools.FFMPEG:
        return []
    return sorted(set(router.possible_targets("mp4")) & (formats.VIDEO_OUT | {"3gp-h263"})
                  | {"mp4"})


def offered_audio_targets():
    if not tools.FFMPEG:
        return []
    return sorted(set(router.possible_targets("wav")) & (set(AUDIO_EXPECTED) | {"ogg"}))


def check_video(path, target, with_audio=True):
    p = probe(path)
    vcodec, acodec = video_expected(target)
    assert p["video"] and p["video"]["codec_name"] == vcodec
    if with_audio:
        assert p["audio"] and p["audio"]["codec_name"] == acodec
    assert decodes(path)
    return p


@pytest.mark.parametrize("target", offered_video_targets())
def test_video_targets(clip, tmp_path, opts, target):
    out = tmp_path / f"out.{target}"
    router.convert_one(clip, out, opts())
    real = router.output_path(clip, out)
    p = check_video(real, target)
    assert float(p["format"].get("duration") or 0) >= 0.5


@pytest.mark.parametrize("target", offered_audio_targets())
def test_audio_targets(tone, tmp_path, opts, target):
    out = tmp_path / f"out.{target}"
    router.convert_one(tone, out, opts())
    real = router.output_path(tone, out)
    p = probe(real)
    expected = ogg_audio() if target == "ogg" else AUDIO_EXPECTED[target]
    assert p["audio"]["codec_name"] == expected and p["video"] is None
    assert decodes(real)
    if target == "amr":
        assert (p["audio"]["sample_rate"], p["audio"]["channels"]) == ("8000", 1)


@pytest.mark.parametrize("target", ["mp3", "m4a", "flac", "wav"])
def test_video_to_audio(clip, tmp_path, opts, target):
    out = tmp_path / f"sound.{target}"
    router.convert_one(clip, out, opts())
    p = probe(out)
    assert p["video"] is None and p["audio"]["codec_name"] == AUDIO_EXPECTED[target]


def test_alac_pseudo_target_never_overwrites_the_source(tone, tmp_path, opts):
    m4a = tmp_path / "song.m4a"
    router.convert_one(tone, m4a, opts())
    before = m4a.read_bytes()
    router.convert_one(m4a, m4a.with_suffix(".alac"), opts())
    assert m4a.read_bytes() == before
    assert probe(tmp_path / "song-alac.m4a")["audio"]["codec_name"] == "alac"


# input-only formats, written by ffmpeg directly → mp4
INPUTS = {
    "f4v": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "f4v"],
    "3g2": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100",
            "-f", "3g2"],
    "m2v": ["-an", "-c:v", "mpeg2video", "-f", "mpeg2video"],
    "mxf": ["-c:v", "mpeg2video", "-b:v", "8M", "-c:a", "pcm_s16le", "-ar", "48000",
            "-f", "mxf"],
    "qt": ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "mov"],
    "mod": ["-c:v", "mpeg2video", "-c:a", "mp2", "-f", "vob"],
}


@pytest.mark.parametrize("ext", sorted(INPUTS))
def test_input_only_video_formats(clip, tmp_path, opts, ext):
    src = tmp_path / f"in.{ext}"
    ffmpeg("-i", clip, *INPUTS[ext], src)
    out = tmp_path / "back.mp4"
    router.convert_one(src, out, opts())
    check_video(out, "mp4", with_audio=ext != "m2v")


@pytest.mark.parametrize("ext, args", [
    ("eac3", ["-c:a", "eac3", "-ar", "48000"]),
    ("ra", ["-c:a", "real_144", "-ar", "8000", "-ac", "1", "-f", "rm"]),
    ("weba", ["-c:a", "libopus", "-f", "webm"]),
    ("oga", ["-c:a", "flac", "-f", "ogg"]),
])
def test_input_only_audio_formats(tone, tmp_path, opts, ext, args):
    if ext == "weba" and not tools.ff_has("libopus"):
        pytest.skip("no Opus encoder")
    src = tmp_path / f"in.{ext}"
    ffmpeg("-i", tone, *args, src)
    out = tmp_path / "back.mp3"
    router.convert_one(src, out, opts())
    assert probe(out)["audio"]["codec_name"] == "mp3"


@pytest.mark.parametrize("target", ["mp4", "webm", "avi"])
def test_gif_to_video(clip, tmp_path, opts, target):
    gif = tmp_path / "anim.gif"
    router.convert_one(clip, gif, opts())
    if target not in router.possible_targets("gif"):
        pytest.skip(f"no .{target} encoder")
    out = tmp_path / f"anim.{target}"
    router.convert_one(gif, out, opts())
    check_video(out, target, with_audio=False)


def test_vob_is_pal_dvd(clip, tmp_path, opts):
    if "vob" not in router.possible_targets("mp4"):
        pytest.skip("no MPEG-2/AC3 encoder")
    wide = tmp_path / "wide.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=1",
           "-f", "lavfi", "-i", "sine=duration=1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest", wide)
    out = tmp_path / "dvd.vob"
    router.convert_one(wide, out, opts(height=240))          # fixed norm: no resizing
    v = probe(out)["video"]
    assert (v["width"], v["height"], v["display_aspect_ratio"]) == (720, 576, "16:9")


@pytest.mark.parametrize("height, size", [(None, (176, 144)), (288, (352, 288))])
def test_3gp_h263(clip, tmp_path, opts, height, size):
    if not tools.ff_has("h263", "libopencore_amrnb"):
        pytest.skip("needs ffmpeg-full (H.263 + AMR)")
    out = tmp_path / "phone.3gp-h263"
    router.convert_one(clip, out, opts(height=height))
    real = tmp_path / "phone.3gp"
    assert not out.exists() and real.exists()
    p = check_video(real, "3gp-h263")
    assert (p["video"]["width"], p["video"]["height"]) == size
    assert (p["audio"]["sample_rate"], p["audio"]["channels"]) == ("8000", 1)


def test_3gp_stays_within_vga(tmp_path, opts, hd_clip):
    if "3gp" not in router.possible_targets("mp4"):
        pytest.skip("no H.264")
    out = tmp_path / "phone.3gp"
    router.convert_one(hd_clip, out, opts())
    v = probe(out)["video"]
    assert (v["width"], v["height"]) == (640, 360)


# ---------------------------------------------------------------- subtitles

SRT = """1
00:00:00,500 --> 00:00:02,000
Subtitle test äöü

2
00:00:02,500 --> 00:00:04,000
Second line
"""


@pytest.fixture
def srt(tmp_path):
    p = tmp_path / "subs.srt"
    p.write_text(SRT, encoding="utf-8")
    return p


@pytest.mark.parametrize("target", ["vtt", "ass", "ssa"])
def test_subtitle_roundtrip(srt, tmp_path, opts, target):
    out = tmp_path / f"subs.{target}"
    router.convert_one(srt, out, opts())
    assert "Subtitle test äöü" in out.read_text(encoding="utf-8")
    back = tmp_path / f"back-{target}.srt"
    router.convert_one(out, back, opts())
    text = back.read_text(encoding="utf-8")
    assert "Subtitle test äöü" in text and "00:00:02,500 --> 00:00:04,000" in text


@pytest.mark.parametrize("container, codec", [("mkv", "srt"), ("mp4", "mov_text")])
@pytest.mark.parametrize("target", ["srt", "vtt"])
def test_subtitles_out_of_a_video(srt, tmp_path, opts, container, codec, target):
    plain = tmp_path / "plain.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=5",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", plain)
    video = tmp_path / f"with-subs.{container}"
    ffmpeg("-i", plain, "-i", srt, "-map", "0", "-map", "1", "-c:v", "copy", "-c:s", codec,
           video)
    out = tmp_path / f"pulled.{target}"
    router.convert_one(video, out, opts())
    text = out.read_text(encoding="utf-8")
    assert "Subtitle test äöü" in text and "Second line" in text


def test_video_without_subtitles_explains(clip, tmp_path, opts):
    with pytest.raises(ConvError, match="no subtitle track"):
        router.convert_one(clip, tmp_path / "none.srt", opts())
