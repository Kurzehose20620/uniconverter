"""Real conversions on tiny fixtures.

The first group needs only the Python dependencies (Pillow, PyMuPDF, python-markdown).
Routes that need an external program are skipped when it is missing.
"""

import shutil
import subprocess
import wave

import pytest

from uniconverter import router
from uniconverter.engines import tools
from uniconverter.errors import ConvError


def convert(src, dst, opts, **kw):
    router.convert_one(src, dst, opts(**kw))
    assert dst.exists() and dst.stat().st_size > 0
    return dst


def pdf_pages(path):
    return len(tools.load_fitz().open(str(path)))


# ---------------------------------------------------------------- Python-only routes

def test_png_to_jpg(fixtures, tmp_path, opts):
    out = convert(fixtures / "pixel.png", tmp_path / "pixel.jpg", opts, quality=80)
    assert out.read_bytes()[:3] == b"\xff\xd8\xff"


def test_png_to_webp(fixtures, tmp_path, opts):
    out = convert(fixtures / "pixel.png", tmp_path / "pixel.webp", opts)
    assert out.read_bytes()[:4] == b"RIFF"


def test_png_to_pdf(fixtures, tmp_path, opts):
    out = convert(fixtures / "pixel.png", tmp_path / "pixel.pdf", opts)
    assert out.read_bytes()[:5] == b"%PDF-" and pdf_pages(out) == 1


def test_md_to_html(fixtures, tmp_path, opts):
    html = convert(fixtures / "note.md", tmp_path / "note.html", opts).read_text()
    assert "<h1>Title</h1>" in html and "<strong>bold</strong>" in html and "<li>item one" in html


def test_pdf_to_txt(fixtures, tmp_path, opts):
    txt = convert(fixtures / "mini.pdf", tmp_path / "mini.txt", opts).read_text()
    assert "HELLO WORLD" in txt


def test_pdf_to_md(fixtures, tmp_path, opts, capsys):
    md = convert(fixtures / "mini.pdf", tmp_path / "mini.md", opts).read_text()
    assert "HELLO WORLD" in md
    assert "Document parser messages" not in capsys.readouterr().out


def test_pdf_to_png(fixtures, tmp_path, opts):
    out = convert(fixtures / "mini.pdf", tmp_path / "mini.png", opts, dpi=72)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_merge_mixed_inputs_to_pdf(fixtures, tmp_path, opts):
    dst = tmp_path / "all.pdf"
    sources = [fixtures / "pixel.png", fixtures / "mini.pdf", fixtures / "pixel.png"]
    router.merge_to_pdf(sources, dst, opts())
    assert pdf_pages(dst) == 3


def test_scanned_pdf_without_ocr_data_explains(fixtures, tmp_path, opts, monkeypatch):
    monkeypatch.setattr(tools, "find_tessdata", lambda: None)
    scan = tmp_path / "scan.pdf"
    convert(fixtures / "pixel.png", scan, opts)          # image-only PDF, no text layer
    with pytest.raises(ConvError, match="contains no text"):
        router.convert_one(scan, tmp_path / "scan.md", opts())


# ---------------------------------------------------------------- routes needing external tools

@pytest.mark.skipif(not tools.find_tessdata(), reason="no Tesseract language data")
def test_scanned_pdf_is_ocred(fixtures, tmp_path, opts):
    fitz = tools.load_fitz()
    src = fitz.open(str(fixtures / "mini.pdf"))
    pix = src[0].get_pixmap(dpi=150)
    scan = fitz.open("pdf", fitz.open("png", pix.tobytes("png")).convert_to_pdf())
    scan.save(str(tmp_path / "scan.pdf"))
    assert not scan[0].get_text().strip()
    txt = convert(tmp_path / "scan.pdf", tmp_path / "scan.txt", opts, ocr_lang="eng").read_text()
    assert "HELLO" in txt.upper()


@pytest.mark.skipif(not tools.CHROME, reason="no Chrome/Chromium for headless printing")
def test_md_to_pdf_via_chrome(fixtures, tmp_path, opts):
    out = convert(fixtures / "note.md", tmp_path / "note.pdf", opts)
    assert pdf_pages(out) == 1


@pytest.mark.skipif(not shutil.which("textutil"), reason="textutil is macOS only")
def test_txt_to_docx_via_textutil(fixtures, tmp_path, opts):
    src = tmp_path / "hello.txt"
    src.write_text("Hello uniconverter\n")
    out = convert(src, tmp_path / "hello.docx", opts)
    assert out.read_bytes()[:2] == b"PK"


def make_wav(path, rate):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * (rate // 10))       # 0.1 s of silence


@pytest.mark.skipif(not shutil.which("afconvert"), reason="afconvert is macOS only")
@pytest.mark.parametrize("rate", [44100, 8000])       # 8 kHz: AAC bitrate must be relaxed
def test_wav_to_m4a_via_afconvert(tmp_path, opts, monkeypatch, rate):
    monkeypatch.setattr(tools, "FFMPEG", None)        # force the afconvert path
    src = tmp_path / "silence.wav"
    make_wav(src, rate)
    convert(src, tmp_path / "silence.m4a", opts)


@pytest.mark.skipif(not shutil.which("afconvert"), reason="afconvert is macOS only")
def test_wav_to_flac_needs_ffmpeg(tmp_path, opts, monkeypatch):
    monkeypatch.setattr(tools, "FFMPEG", None)
    src = tmp_path / "silence.wav"
    make_wav(src, 44100)
    with pytest.raises(ConvError, match="ffmpeg"):
        router.convert_one(src, tmp_path / "silence.flac", opts())


@pytest.mark.skipif(not tools.SOFFICE, reason="no LibreOffice")
def test_docx_to_pdf_via_libreoffice(tmp_path, opts):
    txt = tmp_path / "doc.txt"
    txt.write_text("Hello from a Word file\n")
    subprocess.run(["textutil", "-convert", "docx", "-output", str(tmp_path / "doc.docx"),
                    str(txt)], check=True)
    out = convert(tmp_path / "doc.docx", tmp_path / "doc.pdf", opts)
    assert pdf_pages(out) == 1


@pytest.mark.skipif(not tools.FFMPEG, reason="no ffmpeg")
def test_video_to_gif_via_ffmpeg(tmp_path, opts):
    src = tmp_path / "clip.mp4"
    subprocess.run([tools.FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=red:s=64x64:d=0.5", "-pix_fmt", "yuv420p", str(src)],
                   check=True)
    out = convert(src, tmp_path / "clip.gif", opts)
    assert out.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
