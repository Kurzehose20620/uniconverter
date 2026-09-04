# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `uniconverter` command line: images (PNG, JPEG, HEIC, WebP, TIFF, BMP, GIF, AVIF, ICO)
  in any direction and to PDF; PDF to images, Markdown, text, HTML and (optionally,
  via pdf2docx) DOCX; Office documents to PDF, images, Markdown and text via
  LibreOffice and textutil; Markdown, HTML and text to PDF via Chrome headless
  (or pandoc + typst when installed); audio via afconvert or ffmpeg; video via ffmpeg.
- Merging several files of mixed formats into a single PDF.
- OCR for scanned PDFs: pages without a text layer are recognised with Tesseract
  (built into PyMuPDF; needs language data, e.g. `brew install tesseract`) before
  converting to Markdown, text or HTML. `--ocr-lang` picks the languages.
  Without it the OCR languages follow the system language, plus English.
- `uniconverter doctor` (shows which engines are available) and `uniconverter formats`.
- `uniconverter-app`: drag-and-drop app in its own native window (WebKit via
  pywebview, no browser needed) backed by a server on 127.0.0.1 only; `install.sh`
  packages it as `Uniconverter.app`. `--serve` runs just the server for a browser.
- Packaging with `pyproject.toml`; installable with `pipx install .`.
- MIT license.
