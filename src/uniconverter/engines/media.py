"""Audio and video: ffmpeg, otherwise afconvert (macOS) for the basic audio formats."""

from pathlib import Path

from ..errors import ConvError
from ..formats import AUDIO_EXT, ext_of
from . import tools
from .tools import need, run

AFCONVERT_MAP = {
    "m4a": ["-f", "m4af", "-d", "aac", "-b", "192000"],
    "wav": ["-f", "WAVE", "-d", "LEI16"],
    "aiff": ["-f", "AIFF", "-d", "BEI16"],
    "aif": ["-f", "AIFF", "-d", "BEI16"],
    "caf": ["-f", "caff", "-d", "LEI16"],
}


def audio_to_audio(src: Path, dst: Path, opts):
    if tools.FFMPEG:
        run([tools.FFMPEG, "-y", "-i", str(src), str(dst)])
        return
    de = ext_of(dst)
    if de in AFCONVERT_MAP:
        args = AFCONVERT_MAP[de]
        try:
            run(["afconvert"] + args + [str(src), str(dst)])
        except ConvError:
            if "-b" not in args:
                raise
            # the fixed AAC bitrate is too high for low sample rates (voice memos etc.)
            i = args.index("-b")
            run(["afconvert"] + args[:i] + args[i + 2:] + [str(src), str(dst)])
        return
    need(False, f"ffmpeg (for .{de} output)", "brew install ffmpeg")


def video_convert(src: Path, dst: Path, opts):
    need(tools.FFMPEG, "ffmpeg", "brew install ffmpeg")
    de = ext_of(dst)
    if de == "gif":
        vf = ("fps=12,scale=640:-1:flags=lanczos,"
              "split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse")
        run([tools.FFMPEG, "-y", "-i", str(src), "-vf", vf, str(dst)])
    elif de in AUDIO_EXT:
        run([tools.FFMPEG, "-y", "-i", str(src), "-vn", str(dst)])
    else:
        cmd = [tools.FFMPEG, "-y", "-i", str(src)]
        if de == "mp4":
            cmd += ["-movflags", "+faststart", "-pix_fmt", "yuv420p",
                    "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        run(cmd + [str(dst)])
