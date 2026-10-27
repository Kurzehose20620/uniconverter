"""Subtitles: srt ↔ vtt ↔ ass/ssa, and the text subtitle track of a video (ffmpeg)."""

import json
import subprocess
from pathlib import Path

from ..errors import ConvError
from . import tools
from .media import FF_INPUT, FFMPEG_HINT
from .tools import need, run

# Text subtitle codecs ffmpeg can rewrite as srt/vtt/ass. Picture subtitles
# (PGS, VobSub) would need OCR.
TEXT_SUBS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text", "ttml", "microdvd",
             "subviewer", "jacosub", "realtext", "sami", "stl", "mpl2", "pjs", "vplayer"}


def sub_convert(src: Path, dst: Path, opts):
    need(tools.FFMPEG, "ffmpeg", FFMPEG_HINT)
    run([tools.FFMPEG, "-y", *FF_INPUT, "-i", src, dst])


def video_to_sub(src: Path, dst: Path, opts):
    """Save a video's text subtitle track (the default one, else the first)."""
    need(tools.FFMPEG and tools.FFPROBE, "ffmpeg + ffprobe", FFMPEG_HINT)
    res = subprocess.run([tools.FFPROBE, "-v", "error", *FF_INPUT, "-select_streams", "s",
                          "-show_entries", "stream=index,codec_name:stream_tags=language,title"
                          ":stream_disposition=default", "-of", "json", str(src)],
                         capture_output=True, text=True)
    try:
        subs = json.loads(res.stdout or "{}").get("streams", [])
    except ValueError:
        subs = []
    if not subs:
        raise ConvError("the video has no subtitle track")
    text = [s for s in subs if s.get("codec_name") in TEXT_SUBS]
    if not text:
        names = ", ".join(sorted({s.get("codec_name") or "?" for s in subs}))
        raise ConvError(f"only picture subtitles ({names}) – they cannot be turned into "
                        "text without OCR")
    pick = next((s for s in text if s.get("disposition", {}).get("default")), text[0])
    run([tools.FFMPEG, "-y", *FF_INPUT, "-i", src, "-map", f"0:{pick['index']}", dst])
    if len(text) > 1:
        lang = pick.get("tags", {}).get("language") or "?"
        print(f"  ({len(text)} subtitle tracks – used track {text.index(pick) + 1}, "
              f"language {lang})")
