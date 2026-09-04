"""uniconverter – universal local file converter for macOS.

Everything runs on your machine; no file ever leaves it. Uses what macOS
ships (sips, textutil, afconvert), LibreOffice, Chrome (headless PDF
printing) and Python libraries (PyMuPDF, Pillow, ...).
"""

from .errors import ConvError

__version__ = "0.1.0"
__all__ = ["ConvError", "__version__"]
