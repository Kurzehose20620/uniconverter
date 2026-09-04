# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] – 2026-09-04

First public release.

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
- `--dry-run` shows the planned conversions and their engines; `--verbose` names the
  engine per file and echoes external commands; batches show `[n/N]` progress and a
  summary line. Exit codes: 0 ok, 1 conversion failed, 2 usage error; errors on stderr.
- The app server requires a per-session token on every request except `/ping`,
  rejects foreign origins and sends `Cache-Control: no-store`, so other local processes
  or web pages cannot use it. Upload folder is also removed via `atexit`.
- External programs are detected on first use instead of at import time.
- Page images from PDF → png/jpg never overwrite existing numbered files without `--force`.
- Test suite (routing table, real conversions on tiny fixtures, CLI, app server) and
  GitHub Actions CI on macOS with Python 3.12–3.14.
- MIT license.

[Unreleased]: https://github.com/Kurzehose20620/uniconverter/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Kurzehose20620/uniconverter/releases/tag/v1.0.0
