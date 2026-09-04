"""convert_one's decision table: which source/target pair calls which engine function.

Every engine function is replaced by a recorder, so no real conversion happens
and no external program is needed.
"""

from pathlib import Path

import pytest

from uniconverter import router
from uniconverter.engines import images, media, office, pdf, text, tools
from uniconverter.errors import ConvError

ENGINES = {
    "images": (images, ["img_to_img", "imgs_to_pdf"]),
    "pdf": (pdf, ["pdf_to_images", "pdf_to_md", "pdf_to_txt", "pdf_to_docx"]),
    "office": (office, ["office_to_pdf", "docx_to_md", "textutil_convert"]),
    "text": (text, ["md_to_html", "md_to_pdf", "md_to_office", "html_to_pdf",
                    "html_to_md", "txt_to_pdf"]),
    "media": (media, ["audio_to_audio", "video_convert"]),
}


@pytest.fixture
def calls(monkeypatch):
    """Replace every engine function with a recorder; returns the list of (name, args)."""
    log = []
    for prefix, (module, names) in ENGINES.items():
        for name in names:
            def record(*args, _name=f"{prefix}.{name}", **kwargs):
                log.append((_name, args))
            monkeypatch.setattr(module, name, record)
    return log


def convert(calls, src, dst, opts):
    router.convert_one(Path(src), Path(dst), opts())
    return [name for name, _ in calls]


@pytest.mark.parametrize("src, dst, expected", [
    ("a.png", "a.jpg", ["images.img_to_img"]),
    ("a.heic", "a.webp", ["images.img_to_img"]),
    ("a.png", "a.pdf", ["images.imgs_to_pdf"]),
    ("a.gif", "a.mp4", ["media.video_convert"]),
    ("a.pdf", "a.png", ["pdf.pdf_to_images"]),
    ("a.pdf", "a.md", ["pdf.pdf_to_md"]),
    ("a.pdf", "a.txt", ["pdf.pdf_to_txt"]),
    ("a.pdf", "a.docx", ["pdf.pdf_to_docx"]),
    ("a.pdf", "a.html", ["pdf.pdf_to_md", "text.md_to_html"]),
    ("a.docx", "a.pdf", ["office.office_to_pdf"]),
    ("a.pptx", "a.pdf", ["office.office_to_pdf"]),
    ("a.docx", "a.png", ["office.office_to_pdf", "pdf.pdf_to_images"]),
    ("a.docx", "a.md", ["office.docx_to_md"]),
    ("a.odt", "a.txt", ["office.textutil_convert"]),
    ("a.rtf", "a.docx", ["office.textutil_convert"]),
    ("a.md", "a.html", ["text.md_to_html"]),
    ("a.md", "a.pdf", ["text.md_to_pdf"]),
    ("a.md", "a.docx", ["text.md_to_office"]),
    ("a.html", "a.pdf", ["text.html_to_pdf"]),
    ("a.html", "a.md", ["text.html_to_md"]),
    ("a.html", "a.docx", ["office.textutil_convert"]),
    ("a.txt", "a.pdf", ["text.txt_to_pdf"]),
    ("a.txt", "a.rtf", ["office.textutil_convert"]),
    ("a.wav", "a.m4a", ["media.audio_to_audio"]),
    ("a.mp4", "a.gif", ["media.video_convert"]),
    ("a.mp4", "a.mp3", ["media.video_convert"]),
    ("a.mov", "a.webm", ["media.video_convert"]),
])
def test_route(calls, opts, src, dst, expected):
    assert convert(calls, src, dst, opts) == expected


def test_image_to_pdf_passes_source_list(calls, opts):
    router.convert_one(Path("a.png"), Path("a.pdf"), opts())
    name, args = calls[0]
    assert name == "images.imgs_to_pdf" and args[0] == [Path("a.png")]


def test_extension_case_is_ignored(calls, opts):
    assert convert(calls, "A.PNG", "A.JPG", opts) == ["images.img_to_img"]


@pytest.mark.parametrize("src, dst", [
    ("a.png", "a.mp3"),     # image → audio
    ("a.pptx", "a.txt"),    # textutil only handles docx/doc/odt/rtf
    ("a.mp3", "a.pdf"),     # audio → document
    ("a.xyz", "a.png"),     # unknown source
    ("a.pdf", "a.pdf"),     # same family, no route
])
def test_unsupported_routes_raise(calls, opts, src, dst):
    with pytest.raises(ConvError, match="is not supported"):
        router.convert_one(Path(src), Path(dst), opts())
    assert calls == []


def test_possible_targets_images():
    t = router.possible_targets("png")
    assert "jpg" in t and "webp" in t and "pdf" in t
    assert "png" not in t and "jpeg" not in t     # not itself, no alias extensions


def test_possible_targets_pdf():
    t = router.possible_targets("pdf")
    assert {"md", "txt", "html", "png", "jpg"} <= set(t)


def test_possible_targets_depend_on_ffmpeg(monkeypatch):
    monkeypatch.setattr(tools, "FFMPEG", None)
    assert router.possible_targets("mp4") == []
    assert "mp3" not in router.possible_targets("wav")
    monkeypatch.setattr(tools, "FFMPEG", "/usr/bin/ffmpeg")
    assert {"gif", "mp3", "mov"} <= set(router.possible_targets("mp4"))
    assert "mp3" in router.possible_targets("wav")


def test_possible_targets_unknown_extension():
    assert router.possible_targets("xyz") == []
