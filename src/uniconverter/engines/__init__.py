"""Conversion engines, grouped by file family.

images  image → image, image(s) → PDF          (Pillow → sips → ImageMagick, PyMuPDF)
pdf     PDF → images/Markdown/text/DOCX        (PyMuPDF, pymupdf4llm, Tesseract OCR, pdf2docx)
office  Office → PDF/DOCX/Markdown/...         (LibreOffice headless, textutil, pandoc/mammoth)
text    Markdown/HTML/text → PDF/HTML/Office   (python-markdown, Chrome headless, pandoc/typst)
media   audio and video                        (ffmpeg, afconvert)
tools   detection of external programs, process calls, error messages
"""
