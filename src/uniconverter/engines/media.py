"""Audio and video: ffmpeg (the full Homebrew build is preferred when installed),
otherwise afconvert (macOS) for the basic audio formats.

Each target format has a fixed codec profile, chosen so the file plays where that
format is typically used. --width/--height/--max scale the picture down, --small
lowers quality and bitrates, --target-size aims a video at a file size.
"""

import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

from .. import sizing
from ..errors import ConvError
from ..formats import AUDIO_EXT, OUT_ALIASES, VIDEO_ALIASES, VIDEO_OUT, ext_of
from . import tools
from .tools import need, run

FFMPEG_HINT = "brew install ffmpeg"
FULL_HINT = "brew install ffmpeg-full  (keg-only, used automatically when installed)"
# Input option: ffmpeg may only open local files, never network protocols that a
# playlist or reference inside a media file could point to.
FF_INPUT = ["-protocol_whitelist", "file,pipe,data"]

AFCONVERT_MAP = {
    "m4a": ["-f", "m4af", "-d", "aac", "-b", "192000"],
    "wav": ["-f", "WAVE", "-d", "LEI16"],
    "aiff": ["-f", "AIFF", "-d", "BEI16"],
    "aif": ["-f", "AIFF", "-d", "BEI16"],
    "caf": ["-f", "caff", "-d", "LEI16"],
}

# audio target: (ffmpeg encoders needed, ffmpeg arguments, bitrate, bitrate with --small)
AUDIO_PROFILES = {
    "mp3": (["libmp3lame"], ["-c:a", "libmp3lame"], "192k", "128k"),
    "wav": (["pcm_s16le"], ["-c:a", "pcm_s16le"], None, None),
    "m4a": (["aac"], ["-c:a", "aac", "-movflags", "+faststart"], "192k", "128k"),
    "m4b": (["aac"], ["-f", "ipod", "-c:a", "aac"], "128k", "64k"),          # audiobook
    "alac": (["alac"], ["-f", "ipod", "-c:a", "alac"], None, None),          # lossless, .m4a
    "aac": (["aac"], ["-f", "adts", "-c:a", "aac"], "192k", "128k"),
    "flac": (["flac"], ["-c:a", "flac"], None, None),
    "opus": (["libopus"], ["-c:a", "libopus"], "128k", "64k"),
    "aiff": (["pcm_s16be"], ["-f", "aiff", "-c:a", "pcm_s16be"], None, None),
    "aif": (["pcm_s16be"], ["-f", "aiff", "-c:a", "pcm_s16be"], None, None),
    "caf": (["pcm_s16le"], ["-f", "caf", "-c:a", "pcm_s16le"], None, None),
    "wma": (["wmav2"], ["-f", "asf", "-c:a", "wmav2"], "192k", "96k"),
    "ac3": (["ac3"], ["-c:a", "ac3"], "384k", "192k"),
    "mp2": (["mp2"], ["-c:a", "mp2"], "256k", "160k"),
    "au": (["pcm_s16be"], ["-f", "au", "-c:a", "pcm_s16be"], None, None),
    "snd": (["pcm_s16be"], ["-f", "au", "-c:a", "pcm_s16be"], None, None),
    "mka": (["flac"], ["-f", "matroska", "-c:a", "flac"], None, None),
    "wv": (["wavpack"], ["-c:a", "wavpack"], None, None),
    # AMR-NB: 8 kHz mono speech codec of old phones (ffmpeg-full)
    "amr": (["libopencore_amrnb"],
            ["-c:a", "libopencore_amrnb", "-ar", "8000", "-ac", "1", "-b:a", "12.2k"],
            None, None),
}

# video target → encoders it needs (default: H.264 + AAC)
VIDEO_ENCODERS = {
    "webm": ["libvpx-vp9", "libopus"], "wmv": ["wmv2", "wmav2"], "asf": ["wmv2", "wmav2"],
    "flv": ["flv", "libmp3lame"], "mpg": ["mpeg2video", "mp2"],
    "mpeg": ["mpeg2video", "mp2"], "vob": ["mpeg2video", "ac3"],
    "dv": ["dvvideo"], "rm": ["rv20", "ac3"], "ogv": ["libvpx", "libopus"],
    "avi": ["mpeg4", "libmp3lame"], "divx": ["mpeg4", "libmp3lame"],
}
MPEG2_FPS = (23.976, 24, 25, 29.97, 30, 50, 59.94, 60)     # frame rates MPEG-2 allows
TARGET_SIZE_FORMATS = {"mp4", "m4v", "mov", "mkv", "ts", "m2ts", "mts", "3gp", "webm",
                       "avi", "divx"}


# ---------------------------------------------------------------- audio

def audio_args(fmt, opts=None):
    """ffmpeg arguments for an audio target, or None if this ffmpeg lacks the encoder."""
    small = sizing.small(opts)
    if fmt == "ogg":
        # Vorbis is classic Ogg; without libvorbis (Homebrew's plain ffmpeg) Opus in Ogg
        if tools.ff_has("libvorbis"):
            return ["-f", "ogg", "-c:a", "libvorbis", "-q:a", "3" if small else "6"]
        if tools.ff_has("libopus"):
            return ["-f", "ogg", "-c:a", "libopus", "-b:a", "96k" if small else "160k"]
        return None
    if fmt not in AUDIO_PROFILES:
        return None
    encs, args, rate, small_rate = AUDIO_PROFILES[fmt]
    if not tools.ff_has(*encs):
        return None
    rate = small_rate if small else rate
    return list(args) + (["-b:a", rate] if rate else [])


def audio_out_formats():
    if not tools.FFMPEG:
        return set(AFCONVERT_MAP)
    return {f for f in set(AUDIO_PROFILES) | {"ogg"} if audio_args(f) is not None}


def audio_to_audio(src: Path, dst: Path, opts, fmt=None):
    de = fmt or ext_of(dst)
    if tools.FFMPEG:
        args = audio_args(de, opts)
        if args is None:
            need(False, f"an ffmpeg with an encoder for .{de}", FULL_HINT)
        run([tools.FFMPEG, "-y", *FF_INPUT, "-i", src, "-vn", "-map", "0:a:0", *args, dst],
            err_hint="does the file have an audio track?")
        return
    if de in AFCONVERT_MAP:
        args = list(AFCONVERT_MAP[de])
        if "-b" in args and sizing.small(opts):
            args[args.index("-b") + 1] = "128000"
        try:
            run(["afconvert", *args, src, dst])
        except ConvError:
            if "-b" not in args:
                raise
            # the fixed AAC bitrate is too high for low sample rates (voice memos etc.)
            i = args.index("-b")
            run(["afconvert", *args[:i], *args[i + 2:], src, dst])
        return
    need(False, f"ffmpeg (for .{de} output)", FFMPEG_HINT)


# ---------------------------------------------------------------- video helpers

def probe(src: Path):
    """Width, height, frame rate, duration and stream kinds of a media file (if known)."""
    info = {"width": None, "height": None, "fps": None, "duration": None,
            "audio": False, "video": False}
    if not tools.FFPROBE:
        return info
    res = subprocess.run(
        [tools.FFPROBE, "-v", "error", *FF_INPUT, "-show_entries",
         "stream=codec_type,width,height,avg_frame_rate:stream_disposition=attached_pic"
         ":format=duration", "-of", "json", str(src)],
        capture_output=True, text=True)
    try:
        data = json.loads(res.stdout or "{}")
    except ValueError:
        data = {}
    try:
        info["duration"] = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        pass
    for s in data.get("streams", []):
        if s.get("codec_type") == "audio":
            info["audio"] = True
        elif s.get("codec_type") == "video" and not info["video"] \
                and not s.get("disposition", {}).get("attached_pic"):
            info["video"] = True
            info["width"], info["height"] = s.get("width"), s.get("height")
            try:
                num, den = (s.get("avg_frame_rate") or "0/0").split("/")
                info["fps"] = float(num) / float(den) if float(den) else None
            except ValueError:
                pass
    return info


def scale_filter(opts, max_w=None, max_h=None, setsar=False, flags=None):
    """ffmpeg scale filter into the --width/--height/--max box and a format's own limit.

    Only ever scales down, keeps the aspect ratio and gives even sizes (yuv420p).
    """
    limit = sizing.box(opts) or (None, None)
    w = min((v for v in (limit[0], max_w) if v), default=None)
    h = min((v for v in (limit[1], max_h) if v), default=None)
    if not w and not h:
        f = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    else:
        f = (f"scale='{f'min({w},iw)' if w else 'iw'}':'{f'min({h},ih)' if h else 'ih'}'"
             ":force_original_aspect_ratio=decrease:force_divisible_by=2")
    if flags:
        f += f":flags={flags}"
    return f + (",setsar=1" if setsar else "")


def _pal_sd_filter(info):
    """Fit into PAL SD 720×576 (DVD/DV): 16:9 or 4:3, the rest padded black."""
    w, h = info.get("width") or 16, info.get("height") or 9
    box, dar = (1024, "16/9") if w / h >= 1.55 else (768, "4/3")
    return (f"scale={box}:576:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={box}:576:(ow-iw)/2:(oh-ih)/2,scale=720:576,setdar={dar}")


def video_out_formats():
    if not tools.FFMPEG:
        return set()
    out = {f for f in VIDEO_OUT if tools.ff_has(*VIDEO_ENCODERS.get(f, ["libx264", "aac"]))}
    if tools.ff_has("libtheora", "libvorbis"):
        out.add("ogv")          # classic Theora + Vorbis (ffmpeg-full)
    if tools.ff_has("h263", "libopencore_amrnb"):
        out.add("3gp-h263")     # 3GP for very old phones (ffmpeg-full)
    return out


def _kbps(rate):
    return int(float(rate.rstrip("k"))) if rate else 0


# ---------------------------------------------------------------- video profiles

def video_plan(src: Path, de: str, opts, vbit=None):
    """Codec profile for a video target.

    Returns a namespace with `args` (everything between input and output file),
    `audio_kbps` and `two_pass` (whether --target-size may run a second pass).
    vbit is a video bitrate in kbit/s that replaces the quality setting.
    """
    small = sizing.small(opts)
    limit = sizing.box(opts) or (None, None)
    p = SimpleNamespace(args=[], audio_kbps=0, two_pass=False)

    def h264(crf_small="28"):
        v = ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
        v += ["-b:v", f"{vbit}k"] if vbit else ["-crf", crf_small if small else "23"]
        rate = "96k" if small else "160k"
        p.audio_kbps, p.two_pass = _kbps(rate), True
        return v + ["-c:a", "aac", "-b:a", rate]

    if de in ("mp4", "m4v", "mov"):
        # H.264/AAC – plays in QuickTime, on iPhone/iPad, Apple TV and in browsers
        p.args = h264() + ["-movflags", "+faststart", "-vf", scale_filter(opts)]
    elif de in ("mkv", "ts", "m2ts", "mts"):
        # H.264/AAC; ts/m2ts = MPEG transport stream (camcorder/Blu-ray style)
        p.args = h264() + ["-vf", scale_filter(opts)]
        if de != "mkv":
            p.args += ["-f", "mpegts"]
    elif de == "webm":
        # VP9 + Opus – the browser standard
        v = ["-b:v", f"{vbit}k"] if vbit else ["-crf", "40" if small else "32", "-b:v", "0"]
        rate = "64k" if small else "128k"
        p.audio_kbps, p.two_pass = _kbps(rate), True
        p.args = ["-c:v", "libvpx-vp9", *v, "-row-mt", "1", "-deadline", "good",
                  "-cpu-used", "4", "-pix_fmt", "yuv420p", "-c:a", "libopus", "-b:a", rate,
                  "-vf", scale_filter(opts)]
    elif de in ("avi", "divx"):
        # Xvid-compatible AVI that plays on older standalone (DVD/DivX) players:
        # MPEG-4 ASP with an XVID tag (.divx: DIVX tag), at most 640×480 with the aspect
        # ratio kept, square pixels, no B-frames, moderate bitrate, MP3 audio.
        rate = "96k" if small else "128k"
        vrate = f"{min(vbit, 2000)}k" if vbit else ("600k" if small else "1000k")
        p.audio_kbps, p.two_pass = _kbps(rate), True
        p.args = ["-map", "0:v:0", "-map", "0:a:0?",
                  "-vf", scale_filter(opts, 640, 480, setsar=True),
                  "-c:v", "mpeg4", "-vtag", "DIVX" if de == "divx" else "XVID",
                  "-pix_fmt", "yuv420p",
                  "-b:v", vrate, "-maxrate", "2000k", "-bufsize", "2000k",
                  "-g", "240", "-bf", "0", "-mbd", "rd",
                  "-c:a", "libmp3lame", "-b:a", rate, "-ar", "48000", "-ac", "2"]
        if de == "divx":
            p.args += ["-f", "avi"]
    elif de in ("wmv", "asf"):
        # Windows Media 8 (WMV2/WMA2) – plays in Windows Media Player since XP
        p.args = ["-c:v", "wmv2", "-b:v", "800k" if small else "2000k",
                  "-c:a", "wmav2", "-b:a", "96k" if small else "192k", "-ar", "44100",
                  "-vf", scale_filter(opts), "-f", "asf"]
    elif de == "flv":
        # classic Flash video: Sorenson H.263 (flv1) + MP3
        p.args = ["-c:v", "flv1", "-b:v", "600k" if small else "1500k",
                  "-c:a", "libmp3lame", "-b:a", "64k" if small else "128k", "-ar", "44100",
                  "-vf", scale_filter(opts)]
    elif de in ("mpg", "mpeg"):
        # MPEG-2 program stream + MP2 audio (DVD/set-top-box classic)
        fps = probe(src).get("fps")
        if not fps or min(abs(fps - s) for s in MPEG2_FPS) > 0.01:
            p.args += ["-r", "25"]
        p.args += ["-c:v", "mpeg2video", "-b:v", "2500k" if small else "6000k",
                   "-maxrate", "9000k", "-bufsize", "3000k", "-g", "15", "-pix_fmt", "yuv420p",
                   "-c:a", "mp2", "-b:a", "128k" if small else "224k", "-ar", "48000",
                   "-vf", scale_filter(opts), "-f", "vob"]
    elif de == "vob":
        # DVD-Video (PAL): MPEG-2 720×576, 25 fps, AC3 – a fixed size, no resizing
        p.args = ["-target", "pal-dvd", "-vf", _pal_sd_filter(probe(src))]
        if small:
            p.args += ["-b:v", "3000k", "-b:a", "192k"]
    elif de == "dv":
        # DV (PAL) for old camcorders and editors – fixed 720×576, 25 fps, fixed bitrate
        info = probe(src)
        p.args = ["-target", "pal-dv", "-vf", _pal_sd_filter(info)]
        if info.get("audio"):
            p.args += ["-af", "apad", "-shortest"]     # DV needs uninterrupted audio
    elif de == "3gp":
        # old phones: H.264 Baseline + AAC, at most 640×480 (H.263 + AMR: 3gp-h263)
        v = ["-b:v", f"{vbit}k"] if vbit else (["-crf", "28"] if small else [])
        rate = "64k" if small else "128k"
        p.audio_kbps, p.two_pass = _kbps(rate), True
        p.args = ["-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0", *v,
                  "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", rate, "-ar", "44100",
                  "-vf", scale_filter(opts, 640, 480), "-f", "3gp"]
    elif de == "3gp-h263":
        # very old phones: H.263 + AMR-NB 8 kHz mono, 15 fps. H.263 only knows fixed
        # sizes: QCIF 176×144, or CIF 352×288 when a height/max of 288+ is asked for;
        # the aspect ratio is kept, the rest padded black.
        need(tools.ff_has("h263", "libopencore_amrnb"), "ffmpeg-full (H.263 + AMR)",
             FULL_HINT)
        nw, nh = (352, 288) if limit[1] and limit[1] >= 288 else (176, 144)
        p.args = ["-map", "0:v:0", "-map", "0:a:0?",
                  "-vf", f"scale={nw}:{nh}:force_original_aspect_ratio=decrease,"
                         f"pad={nw}:{nh}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                  "-r", "15", "-c:v", "h263", "-b:v", "128k" if small else "192k",
                  "-pix_fmt", "yuv420p", "-c:a", "libopencore_amrnb", "-ar", "8000",
                  "-ac", "1", "-b:a", "12.2k", "-f", "3gp"]
    elif de == "ogv":
        # with ffmpeg-full classic Theora + Vorbis; otherwise VP8 + Opus in Ogg
        if tools.ff_has("libtheora", "libvorbis"):
            p.args = ["-c:v", "libtheora", "-q:v", "4" if small else "7",
                      "-c:a", "libvorbis", "-q:a", "2" if small else "5"]
        else:
            p.args = ["-c:v", "libvpx", "-b:v", "800k" if small else "2M", "-crf", "10",
                      "-deadline", "good", "-cpu-used", "4",
                      "-c:a", "libopus", "-b:a", "64k" if small else "128k"]
        p.args += ["-pix_fmt", "yuv420p", "-vf", scale_filter(opts), "-f", "ogg"]
    elif de == "rm":
        # RealMedia: RealVideo 2 + AC3, at most 640×480 – for RealPlayer/VLC
        p.args = ["-c:v", "rv20", "-b:v", "600k" if small else "1500k",
                  "-c:a", "ac3", "-b:a", "96k" if small else "192k", "-ar", "44100",
                  "-vf", scale_filter(opts, 640, 480)]
    elif sizing.box(opts):
        p.args = ["-vf", scale_filter(opts)]
    return p


def _target_bitrate(src: Path, de: str, opts):
    """Video bitrate (kbit/s) so that the file lands near --target-size."""
    if de not in TARGET_SIZE_FORMATS:
        raise ConvError("--target-size works for "
                        + ", ".join(sorted(TARGET_SIZE_FORMATS - {"mts"})) + f", not .{de}")
    info = probe(src)
    need(info.get("duration"), "ffprobe (to read the video length)", FFMPEG_HINT)
    audio = video_plan(src, de, opts).audio_kbps if info.get("audio") else 0
    total = sizing.target_size(opts) * 8 / 1000 / info["duration"] * 0.96  # container
    vbit = int(total - audio)
    if vbit < 64:
        raise ConvError(f"--target-size is too small for {info['duration']:.0f} s of video "
                        f"(only {max(vbit, 0)} kbit/s would be left for the picture)")
    return vbit


def video_convert(src: Path, dst: Path, opts, fmt=None):
    need(tools.FFMPEG, "ffmpeg", FFMPEG_HINT)
    de = fmt or ext_of(dst)
    ff = [tools.FFMPEG, "-y", *FF_INPUT, "-i", src]
    if de == "gif":
        fps = 8 if sizing.small(opts) else 12
        palette = "palettegen=max_colors=128" if sizing.small(opts) else "palettegen"
        vf = (f"fps={fps},{scale_filter(opts, 640, flags='lanczos')},"
              f"split[s0][s1];[s0]{palette}[p];[s1][p]paletteuse")
        run([*ff, "-vf", vf, dst])
    elif de in AUDIO_EXT or (de in OUT_ALIASES and de not in VIDEO_ALIASES):
        audio_to_audio(src, dst, opts, fmt=de)
    elif sizing.target_size(opts):
        vbit = _target_bitrate(src, de, opts)
        plan = video_plan(src, de, opts, vbit=vbit)
        with tempfile.TemporaryDirectory() as td:
            log = ["-passlogfile", str(Path(td) / "pass")]
            if plan.two_pass:
                try:
                    run([*ff, *plan.args, "-pass", "1", *log, "-an", "-f", "null", "-"])
                    run([*ff, *plan.args, "-pass", "2", *log, dst])
                    return
                except ConvError:
                    # rate control can fail to converge on extreme material (e.g. noise)
                    print("  (two-pass encoding failed – trying a single pass)")
            run([*ff, *plan.args, dst])
    else:
        run([*ff, *video_plan(src, de, opts).args, dst])
