"""File extensions grouped by family, plus a helper for the extension of a path."""

from pathlib import Path

IMAGE_EXT = {"png", "jpg", "jpeg", "heic", "heif", "tif", "tiff", "bmp",
             "gif", "webp", "avif", "ico"}
OFFICE_EXT = {"docx", "doc", "odt", "rtf", "pptx", "ppt", "xlsx", "xls"}
MD_EXT = {"md", "markdown"}
HTML_EXT = {"html", "htm"}
AUDIO_EXT = {"mp3", "wav", "m4a", "aac", "aiff", "aif", "caf", "flac", "ogg"}
VIDEO_EXT = {"mp4", "mov", "mkv", "webm", "avi", "m4v"}


def ext_of(p: Path):
    return p.suffix.lower().lstrip(".")
