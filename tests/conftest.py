import html
import http.server
import json
import re
import subprocess
import threading
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from uniconverter.engines import tools

FIXTURES = Path(__file__).parent / "fixtures"

needs_ffmpeg = pytest.mark.skipif(not (tools.FFMPEG and tools.FFPROBE),
                                  reason="no ffmpeg/ffprobe")
needs_pandoc = pytest.mark.skipif(not tools.PANDOC, reason="no pandoc")
needs_typst = pytest.mark.skipif(not (tools.PANDOC and tools.TYPST), reason="no pandoc + typst")
needs_calibre = pytest.mark.skipif(not tools.EBOOK_CONVERT, reason="no calibre")
needs_magick = pytest.mark.skipif(not tools.MAGICK, reason="no ImageMagick")
needs_blender = pytest.mark.skipif(not tools.BLENDER, reason="no Blender")


@pytest.fixture
def fixtures():
    return FIXTURES


def make_opts(**kw):
    """Options object as produced by the CLI parser or the app's make_opts()."""
    base = dict(quality=90, dpi=150, extract_images=False, ocr_lang=None, force=False,
                width=None, height=None, max=None, small=False, target_size=None)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def opts():
    return make_opts


# ---------------------------------------------------------------- media helpers

def ffmpeg(*args):
    subprocess.run([tools.FFMPEG, "-v", "error", "-y", *map(str, args)], check=True)


def probe(path):
    """{'video': stream, 'audio': stream, 'subtitle': stream, 'format': {...}} via ffprobe."""
    res = subprocess.run([tools.FFPROBE, "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,codec_tag_string,width,height,"
                          "has_b_frames,display_aspect_ratio,sample_rate,channels"
                          ":format=duration,format_name", "-of", "json", str(path)],
                         capture_output=True, text=True)
    data = json.loads(res.stdout or "{}")
    out = {"format": data.get("format", {})}
    for kind in ("video", "audio", "subtitle"):
        out[kind] = next((s for s in data.get("streams", []) if s.get("codec_type") == kind),
                         None)
    return out


def decodes(path):
    return subprocess.run([tools.FFMPEG, "-v", "error", "-i", str(path), "-f", "null", "-"],
                          capture_output=True).returncode == 0


@pytest.fixture(scope="session")
def clip(tmp_path_factory):
    """1 s, 320×240, with stereo sound."""
    if not tools.FFMPEG:
        pytest.skip("no ffmpeg")
    p = tmp_path_factory.mktemp("media") / "clip.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=1",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=48000",
           "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", p)
    return p


@pytest.fixture(scope="session")
def hd_clip(tmp_path_factory):
    """2 s, 1280×720 with B-frames, with sound."""
    if not tools.FFMPEG:
        pytest.skip("no ffmpeg")
    p = tmp_path_factory.mktemp("media") / "hd.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=2",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=48000",
           "-ac", "2", "-c:v", "libx264", "-bf", "3", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-shortest", p)
    return p


@pytest.fixture(scope="session")
def tone(tmp_path_factory):
    """2 s stereo WAV."""
    if not tools.FFMPEG:
        pytest.skip("no ffmpeg")
    p = tmp_path_factory.mktemp("media") / "tone.wav"
    ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=44100",
           "-ac", "2", "-c:a", "pcm_s16le", p)
    return p


# ---------------------------------------------------------------- document helpers

MARKDOWN = """# Chapter One

Umlauts äöüß and a **bold** sentence.

| Fruit | Colour |
|---|---|
| Apple | Green |

## Chapter Two

Second paragraph: Straße und Größe.
"""
EXPECTED = ["Umlauts äöüß", "Straße und Größe", "Apple"]


def _strip_tags(t):
    return html.unescape(re.sub(r"<[^>]+>", " ", t))


def text_of(p: Path, tmp_path: Path = None):
    """Text of a document or e-book, read independently of the program that wrote it."""
    e = p.suffix.lower()[1:]
    if e in ("txt", "md", "srt", "vtt", "ass", "ssa"):
        return p.read_text(encoding="utf-8")
    if e in ("html", "htm", "fb2"):
        return _strip_tags(p.read_text(encoding="utf-8"))
    if e == "pdf":
        return " ".join(page.get_text() for page in tools.load_fitz().open(str(p)))
    if e in ("docx", "odt", "epub"):
        with zipfile.ZipFile(p) as z:
            parts = [n for n in z.namelist()
                     if n in ("word/document.xml", "content.xml")
                     or (e == "epub" and n.endswith((".xhtml", ".html", ".htm")))]
            return " ".join(_strip_tags(z.read(n).decode("utf-8", "replace")) for n in parts)
    if e == "rtf":
        return subprocess.run(["textutil", "-convert", "txt", "-stdout", str(p)],
                              capture_output=True, text=True, check=True).stdout
    if e in ("mobi", "azw", "azw3", "lit", "lrf"):
        txt = (tmp_path or p.parent) / f"check-{p.stem}-{e}.txt"
        subprocess.run([tools.EBOOK_CONVERT, str(p), str(txt)], capture_output=True, check=True)
        return txt.read_text(encoding="utf-8", errors="replace")
    raise AssertionError(f"no text check for .{e}")


def assert_text(p: Path, expected=EXPECTED):
    assert p.exists() and p.stat().st_size > 0, f"{p.name} missing or empty"
    t = re.sub(r"\s+", " ", text_of(p))
    missing = [s for s in expected if s not in t]
    assert not missing, f"{p.name}: {missing} not found in {t[:200]!r}"


class _Recorder(http.server.BaseHTTPRequestHandler):
    hits = []

    def do_GET(self):
        self.hits.append(self.path)
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def web_server():
    """A local web server that records every request; test documents point at it."""
    _Recorder.hits = []
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Recorder)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://localhost:{srv.server_address[1]}", _Recorder.hits
    srv.shutdown()
