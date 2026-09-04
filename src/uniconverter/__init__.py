"""uniconverter – universeller lokaler Datei-Konverter für macOS.

Alles läuft zu 100 % lokal, keine Datei verlässt den Rechner.
Nutzt vorhandene macOS-Bordmittel (sips, textutil, afconvert), LibreOffice,
Chrome (Headless-PDF-Druck) und Python-Bibliotheken (PyMuPDF, Pillow, …).
"""

from .errors import ConvError

__version__ = "0.1.0"
__all__ = ["ConvError", "__version__"]
