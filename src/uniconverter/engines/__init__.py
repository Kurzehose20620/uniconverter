"""Konvertierungs-Engines, gruppiert nach Dateigattung.

images  Bild → Bild, Bild(er) → PDF          (Pillow → sips → ImageMagick, PyMuPDF)
pdf     PDF → Bilder/Markdown/Text/DOCX      (PyMuPDF, pymupdf4llm, pdf2docx)
office  Office → PDF/DOCX/Markdown/…         (LibreOffice headless, textutil, pandoc/mammoth)
text    Markdown/HTML/Text → PDF/HTML/Office (python-markdown, Chrome headless, pandoc/typst)
media   Audio und Video                      (ffmpeg, afconvert)
tools   Erkennung externer Programme, Prozessaufruf, Fehlermeldungen
"""
