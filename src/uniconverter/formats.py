"""File extensions grouped by family, plus a helper for the extension of a path.

*_EXT sets name what can be read, *_OUT sets what can be written. Whether a route
is really offered also depends on the installed engines; the router checks that.
"""

from pathlib import Path

# ---------------------------------------------------------------- images
IMAGE_RAW_EXT = {"dng", "cr2", "cr3", "crw", "nef", "nrw", "arw", "srf", "sr2", "orf",
                 "rw2", "raf", "pef", "srw", "erf", "3fr", "iiq", "mos", "mrw", "dcr"}
IMAGE_OUT = {"png", "jpg", "jpeg", "heic", "heif", "tif", "tiff", "bmp", "gif", "webp",
             "avif", "ico", "icns", "tga", "ppm", "pgm", "pbm", "pcx", "jp2", "qoi",
             "dds", "sgi", "exr", "hdr", "psd"}
IMAGE_MAGICK_OUT = {"dpx", "xpm"}            # written only by ImageMagick
IMAGE_VECTOR_IN = {"eps", "ps", "ai"}         # PostScript family, rendered by Ghostscript
# read-only: SVG (PyMuPDF), JPEG XL (written via cjxl when installed), legacy and niche
# formats via sips/ImageMagick. FITS has no colour model, so it is input only.
IMAGE_EXT = (IMAGE_OUT | IMAGE_MAGICK_OUT | IMAGE_VECTOR_IN | IMAGE_RAW_EXT
             | {"svg", "jxl", "pnm", "pict", "pct", "fits", "pcd", "xcf"})

# ---------------------------------------------------------------- documents
OFFICE_EXT = {"docx", "doc", "odt", "rtf", "pptx", "ppt", "xlsx", "xls"}
MD_EXT = {"md", "markdown"}
HTML_EXT = {"html", "htm"}
PANDOC_ONLY_EXT = {"rst", "org", "tex", "latex", "ipynb"}   # readable through pandoc only

# ---------------------------------------------------------------- e-books (calibre)
EBOOK_EXT = {"epub", "mobi", "azw", "azw3", "fb2", "lit", "lrf", "cbz", "cbr"}
EBOOK_OUT = {"epub", "mobi", "azw3", "fb2", "lit", "lrf"}
COMIC_EXT = {"cbz", "cbr"}
DOC_EBOOK_OUT = {"epub", "mobi", "azw3", "fb2"}   # e-book targets offered for documents

# ---------------------------------------------------------------- audio, video, subtitles
AUDIO_EXT = {"mp3", "wav", "m4a", "m4b", "aac", "aiff", "aif", "caf", "flac", "ogg",
             "oga", "opus", "wma", "ac3", "eac3", "dts", "amr", "au", "snd", "mp2",
             "mka", "wv", "ape", "ra", "weba"}
VIDEO_OUT = {"mp4", "m4v", "mov", "mkv", "webm", "avi", "divx", "wmv", "asf", "flv",
             "mpg", "mpeg", "vob", "ts", "m2ts", "mts", "3gp", "ogv", "dv", "rm"}
VIDEO_EXT = VIDEO_OUT | {"rmvb", "f4v", "3g2", "qt", "mod", "tod", "vro", "m2v", "mxf"}
SUB_EXT = {"srt", "vtt", "ass", "ssa"}
VIDEO_SUB_SRC = {"mkv", "mp4", "m4v", "mov", "webm", "ts", "m2ts", "mts"}

# ---------------------------------------------------------------- 3D models (Blender)
MODEL_EXT = {"glb", "gltf", "obj", "fbx", "stl", "ply", "usd", "usdc", "usdz", "usda", "abc"}
MODEL_OUT = {"obj", "glb", "gltf", "fbx", "stl", "ply", "usdz", "usdc"}

# Pseudo targets: the name offered → the extension actually written
# (ALAC lives in .m4a; 3gp-h263 is a 3GP with H.263 + AMR for very old phones).
OUT_ALIASES = {"alac": "m4a", "3gp-h263": "3gp"}
VIDEO_ALIASES = {"3gp-h263"}
# Alias extensions that are not listed twice as targets
HIDDEN_ALIASES = {"jpeg", "tif", "htm", "aif", "heif", "mpeg", "mts", "snd", "markdown",
                  "latex"}


def ext_of(p: Path):
    return p.suffix.lower().lstrip(".")
