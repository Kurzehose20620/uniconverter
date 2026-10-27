"""convert_one's decision table: which source/target pair calls which engine function.

Every engine function is replaced by a recorder, so no real conversion happens
and no external program is needed.
"""

from pathlib import Path

import pytest

from uniconverter import router
from uniconverter.engines import (
    documents,
    ebooks,
    images,
    media,
    models,
    office,
    pdf,
    subtitles,
    text,
    tools,
)
from uniconverter.errors import ConvError

ENGINES = {
    "images": (images, ["img_to_img", "imgs_to_pdf"]),
    "pdf": (pdf, ["pdf_to_images", "pdf_to_md", "pdf_to_txt", "pdf_to_docx"]),
    "office": (office, ["office_to_pdf", "docx_to_md", "textutil_convert"]),
    "text": (text, ["md_to_html", "md_to_pdf", "md_to_office", "html_to_pdf",
                    "html_to_md", "txt_to_pdf"]),
    "documents": (documents, ["pandoc_convert", "pandoc_pdf"]),
    "ebooks": (ebooks, ["to_ebook", "from_ebook"]),
    "media": (media, ["audio_to_audio", "video_convert"]),
    "subtitles": (subtitles, ["sub_convert", "video_to_sub"]),
    "models": (models, ["model_convert"]),
}
ALL_ENCODERS = {"libx264", "aac", "libvpx-vp9", "libvpx", "libopus", "libvorbis", "libtheora",
                "mpeg4", "libmp3lame", "mpeg2video", "mp2", "ac3", "dvvideo", "wmv2", "wmav2",
                "flv", "rv20", "h263", "libopencore_amrnb", "alac", "flac", "wavpack",
                "pcm_s16le", "pcm_s16be"}


@pytest.fixture
def every_tool(monkeypatch):
    """Pretend every optional program is installed with every encoder/format."""
    for name in ("PANDOC", "TYPST", "EBOOK_CONVERT", "BLENDER", "FFMPEG", "FFPROBE", "CJXL",
                 "DJXL", "MAGICK", "GS", "CHROME", "SOFFICE"):
        monkeypatch.setattr(tools, name, f"/fake/{name.lower()}")
    monkeypatch.setattr(tools, "ffmpeg_encoders", lambda: ALL_ENCODERS)
    monkeypatch.setattr(tools, "magick_can", lambda fmt, mode="r": True)


@pytest.fixture
def calls(monkeypatch, every_tool):
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
    # images beyond Pillow's usual set
    ("a.svg", "a.png", ["images.img_to_img"]),
    ("a.eps", "a.png", ["images.img_to_img"]),
    ("a.eps", "a.pdf", ["images.imgs_to_pdf"]),
    ("a.dng", "a.jpg", ["images.img_to_img"]),
    ("a.png", "a.jxl", ["images.img_to_img"]),
    ("a.tga", "a.qoi", ["images.img_to_img"]),
    ("a.psd", "a.exr", ["images.img_to_img"]),
    ("a.png", "a.dpx", ["images.img_to_img"]),
    ("a.jpg", "a.jpg", ["images.img_to_img"]),          # same format: shrink/recompress
    # documents through pandoc
    ("a.md", "a.txt", ["documents.pandoc_convert"]),
    ("a.rst", "a.docx", ["documents.pandoc_convert"]),
    ("a.org", "a.html", ["documents.pandoc_convert"]),
    ("a.tex", "a.pdf", ["documents.pandoc_pdf"]),
    ("a.ipynb", "a.md", ["documents.pandoc_convert"]),
    ("a.odt", "a.md", ["office.docx_to_md"]),
    # e-books
    ("a.md", "a.epub", ["ebooks.to_ebook"]),
    ("a.docx", "a.mobi", ["ebooks.to_ebook"]),
    ("a.pdf", "a.azw3", ["ebooks.to_ebook"]),
    ("a.rst", "a.fb2", ["ebooks.to_ebook"]),
    ("a.epub", "a.mobi", ["ebooks.from_ebook"]),
    ("a.mobi", "a.pdf", ["ebooks.from_ebook"]),
    ("a.azw3", "a.md", ["ebooks.from_ebook"]),
    ("a.cbz", "a.pdf", ["ebooks.from_ebook"]),
    # audio and video
    ("a.flac", "a.opus", ["media.audio_to_audio"]),
    ("a.wma", "a.amr", ["media.audio_to_audio"]),
    ("a.mkv", "a.avi", ["media.video_convert"]),
    ("a.mp4", "a.divx", ["media.video_convert"]),
    ("a.rmvb", "a.mp4", ["media.video_convert"]),
    ("a.mp4", "a.mp4", ["media.video_convert"]),        # same format: shrink/recompress
    ("a.wav", "a.alac", ["media.audio_to_audio"]),
    ("a.mp4", "a.alac", ["media.audio_to_audio"]),
    ("a.mp4", "a.3gp-h263", ["media.video_convert"]),
    # subtitles and 3D
    ("a.srt", "a.vtt", ["subtitles.sub_convert"]),
    ("a.mkv", "a.srt", ["subtitles.video_to_sub"]),
    ("a.glb", "a.obj", ["models.model_convert"]),
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


def test_pseudo_targets_write_the_real_extension(calls, opts):
    router.convert_one(Path("song.wav"), Path("song.alac"), opts())
    name, args = calls[0]
    assert args[1] == Path("song.m4a")
    calls.clear()
    router.convert_one(Path("clip.mp4"), Path("clip.3gp-h263"), opts())
    assert calls[0][1][1] == Path("clip.3gp")
    assert router.output_path(Path("a.m4a"), Path("a.alac")) == Path("a-alac.m4a")


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
    assert router.possible_targets("srt") == []
    monkeypatch.setattr(tools, "FFMPEG", "/usr/bin/ffmpeg")
    monkeypatch.setattr(tools, "ffmpeg_encoders", lambda: ALL_ENCODERS)
    assert {"gif", "mp3", "mov", "avi", "divx", "vob", "3gp-h263"} <= set(
        router.possible_targets("mp4"))
    assert "mp3" in router.possible_targets("wav")
    assert router.possible_targets("srt") == ["ass", "ssa", "vtt"]


def test_possible_targets_follow_the_encoders(monkeypatch):
    """Plain Homebrew ffmpeg lacks Theora/Vorbis/AMR: ogv falls back to VP8, no amr."""
    monkeypatch.setattr(tools, "FFMPEG", "/usr/bin/ffmpeg")
    monkeypatch.setattr(tools, "ffmpeg_encoders",
                        lambda: ALL_ENCODERS - {"libtheora", "libvorbis", "libopencore_amrnb"})
    t = set(router.possible_targets("mp4"))
    assert "ogv" in t and "ogg" in t                    # VP8 + Opus, Opus in Ogg
    assert "amr" not in t and "3gp-h263" not in t


def test_possible_targets_for_new_families(every_tool):
    assert {"epub", "mobi", "azw3", "fb2", "txt"} <= set(router.possible_targets("md"))
    assert {"md", "pdf", "docx", "epub"} <= set(router.possible_targets("rst"))
    assert {"mobi", "azw3", "pdf", "md", "txt"} <= set(router.possible_targets("epub"))
    assert router.possible_targets("cbz") == ["azw3", "epub", "mobi", "pdf"]
    assert {"jxl", "dpx", "xpm", "tga", "qoi", "icns"} <= set(router.possible_targets("png"))
    assert {"png", "jpg", "pdf"} <= set(router.possible_targets("svg"))
    assert {"png", "jpg"} <= set(router.possible_targets("cr2"))
    assert {"obj", "stl", "usdz"} <= set(router.possible_targets("glb"))
    assert {"srt", "vtt"} <= set(router.possible_targets("mkv"))


def test_every_readable_extension_has_targets(every_tool):
    from uniconverter import formats as f
    readable = (f.IMAGE_EXT | f.OFFICE_EXT | f.MD_EXT | f.HTML_EXT | f.PANDOC_ONLY_EXT
                | f.EBOOK_EXT | f.AUDIO_EXT | f.VIDEO_EXT | f.SUB_EXT | f.MODEL_EXT
                | {"pdf", "txt"})
    assert [e for e in sorted(readable) if not router.possible_targets(e)] == []


def test_offered_targets_are_routable(calls, opts):
    """Everything possible_targets offers must have a route in plan()."""
    from uniconverter import formats as f
    for se in sorted(f.IMAGE_EXT | f.EBOOK_EXT | f.AUDIO_EXT | f.VIDEO_EXT | f.SUB_EXT
                     | f.PANDOC_ONLY_EXT | f.MODEL_EXT | {"md", "html", "txt", "pdf", "docx"}):
        for de in router.possible_targets(se):
            router.plan(Path("a." + se), Path("b." + de), opts())


def test_ebook_routes_depend_on_pandoc_and_calibre(monkeypatch):
    monkeypatch.setattr(tools, "EBOOK_CONVERT", None)
    monkeypatch.setattr(tools, "PANDOC", "/fake/pandoc")
    assert set(router.possible_targets("epub")) == {"md", "html", "odt", "docx", "txt", "rtf"}
    assert "mobi" not in router.possible_targets("md")
    monkeypatch.setattr(tools, "PANDOC", None)
    assert router.possible_targets("epub") == []
    assert router.possible_targets("rst") == []


def test_possible_targets_unknown_extension():
    assert router.possible_targets("xyz") == []


def test_plan_labels_follow_installed_tools(monkeypatch, opts):
    monkeypatch.setattr(tools, "PANDOC", None)
    monkeypatch.setattr(tools, "TYPST", None)
    assert router.plan(Path("a.md"), Path("a.pdf"), opts())[0] == "Chrome headless"
    assert router.plan(Path("a.md"), Path("a.docx"), opts())[0] == "python-markdown + textutil"
    monkeypatch.setattr(tools, "PANDOC", "/usr/bin/pandoc")
    monkeypatch.setattr(tools, "TYPST", "/usr/bin/typst")
    assert router.plan(Path("a.md"), Path("a.pdf"), opts())[0] == "pandoc + typst"
    assert router.plan(Path("a.odt"), Path("a.md"), opts())[0] == "pandoc"
    assert router.plan(Path("a.doc"), Path("a.md"), opts())[0] == "LibreOffice + pandoc"


def test_engine_detection_is_lazy_and_overridable(monkeypatch):
    monkeypatch.setattr(tools, "FFMPEG", "/nowhere/ffmpeg")
    assert tools.FFMPEG == "/nowhere/ffmpeg"
    monkeypatch.undo()
    assert tools.FFMPEG is None or "ffmpeg" in tools.FFMPEG      # back to the real lookup
    with pytest.raises(AttributeError):
        tools.NOT_A_TOOL  # noqa: B018
