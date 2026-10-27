"""Conversion engines, grouped by file family.

images     image → image, image(s) → PDF         (Pillow, sips, cjxl, ImageMagick, Ghostscript)
pdf        PDF → images/Markdown/text/DOCX       (PyMuPDF, pymupdf4llm, Tesseract OCR, pdf2docx)
office     Office → PDF/DOCX/Markdown/...        (LibreOffice headless, textutil, pandoc/mammoth)
text       Markdown/HTML/text → PDF/HTML/Office  (python-markdown, Chrome headless, pandoc/typst)
documents  text formats via pandoc, PDF via typst (md, docx, odt, rtf, epub, rst, org, tex, ipynb)
ebooks     e-books                               (calibre ebook-convert, pandoc)
media      audio and video                       (ffmpeg, afconvert)
subtitles  srt/vtt/ass/ssa, subtitle tracks       (ffmpeg)
models     3D models                             (Blender in the background)
tools      detection of external programs, process calls, error messages
"""
