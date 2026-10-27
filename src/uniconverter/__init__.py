"""uniconverter – universal local file converter for macOS.

Everything runs on your machine; no file ever leaves it. Uses what macOS
ships (sips, textutil, afconvert), LibreOffice, Chrome (headless PDF
printing), Python libraries (PyMuPDF, Pillow, ...) and, when installed,
pandoc/typst, calibre, ffmpeg, ImageMagick/Ghostscript and Blender.
"""

from .errors import ConvError

__version__ = "1.1.0"
__all__ = ["ConvError", "__version__"]
