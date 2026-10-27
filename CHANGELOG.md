# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] – 2026-10-27

### Added

- Smaller files for images and video: `--max N` (longest side), `--width N` and
  `--height N` scale down only, never up, keeping the aspect ratio (even sizes for
  video); `--small` compresses harder (lower image quality, optimised PNG, no image
  metadata; higher CRF or lower bitrate for every video codec, lower audio bitrates);
  `--target-size 50MB` aims a video at a file size with two-pass encoding. Works when
  converting and within the same format; in a batch into the same folder the results
  get a `-small` suffix. PDF → image pages are rendered to fit the size limit.
- The app offers the source's own format for images and video, a size choice
  (original, 1080p/720p/480p for video, a longest side for images) and a
  "Smaller file" checkbox.
- Video: m4v, divx, wmv, asf, flv, mpg, vob (PAL DVD), ts, m2ts, 3gp, 3gp-h263
  (H.263 + AMR for very old phones), ogv, dv (PAL), rm as targets; rmvb, f4v, 3g2, qt,
  mod, tod, vro, m2v and mxf as sources. Every target has a fixed codec profile.
- AVI output uses Xvid-compatible settings that play on older standalone players:
  MPEG-4 Part 2 with the XVID tag (`.divx`: DIVX), at most 640×480 with square pixels,
  no B-frames, 1000 kbit/s (max. 2000), MP3 128k at 48 kHz.
- Audio: m4b, alac (written as .m4a), aac, opus, wma, ac3, mp2, au, mka, wv, amr as
  targets with fixed profiles (ogg is Vorbis when ffmpeg has it); eac3, dts, ape, ra,
  oga and weba as sources. Targets are offered only if the installed ffmpeg has the
  encoder.
- Subtitles: srt, vtt, ass and ssa into each other, and the text subtitle track of
  mkv/mp4/m4v/mov/webm/ts/m2ts videos to any of them.
- Images: icns, tga, ppm, pgm, pbm, pcx, jp2, qoi, dds, sgi, exr, hdr, psd, JPEG XL
  (with jpeg-xl), dpx and xpm (with ImageMagick) as targets; svg (vector, `--dpi` sets
  the size), eps/ps/ai (Ghostscript; → PDF stays vector), pict, pcd, xcf, fits and
  camera RAW (sips, else libraw) as sources. EXIF orientation is applied; colour
  profiles are kept.
- Documents through pandoc: md → txt and epub, docx/odt/rtf → md directly, rst, org,
  tex and ipynb as sources for md, html, docx, odt, rtf, txt, pdf and e-books.
- E-books through calibre: epub, mobi, azw3, fb2, lit and lrf in any direction, azw and
  cbz/cbr comics as sources, → pdf/docx/txt/rtf, → md/html/odt via EPUB and pandoc;
  documents and PDFs → epub/mobi/azw3/fb2. calibre's PDF output is retried once if it
  crashes on its first start.
- 3D models through Blender (background, offline mode): glb, gltf, obj, fbx, stl, ply,
  usd/usdc/usdz/usda, abc → obj, glb, gltf, fbx, stl, ply, usdz, usdc.
- Homebrew's keg-only full builds `ffmpeg-full` and `imagemagick-full` are preferred
  automatically when installed.
- `doctor` lists calibre, Ghostscript, jpeg-xl, ffprobe, Blender, the ffmpeg in use and
  its encoders; `formats` lists the new families and options.
- CI installs ffmpeg, pandoc and typst in the Python 3.14 job; the test suite covers
  every format direction with content checks (codecs, sizes, B-frames, text read back).

### Changed

- Markdown (and rst/org/tex/ipynb) → PDF is typeset in two steps, pandoc → Typst →
  `typst compile` in a temporary folder, on A4 or Letter depending on the region. If
  typst fails, Chrome prints the document instead.
- pandoc keeps running with `--sandbox`, now with a Lua filter that still embeds images
  next to the document (they were missing before) and replaces remote ones by their
  description.
- mp4 output names its codecs explicitly (H.264 CRF 23, AAC 160k); GIF output is no
  longer enlarged beyond the source size.
- EXIF and other metadata are no longer copied into converted images.

### Fixed

- Markdown → PDF with pandoc + typst could download remote images: pandoc's PDF
  pipeline ignores `--sandbox`.

### Security

- ImageMagick runs under a bundled policy that forbids URL/HTTP(S)/FTP coders and
  delegates, MSL/MVG scripts and `@file` indirection; Ghostscript runs with `-dSAFER`;
  ffmpeg may only open local files (`-protocol_whitelist file,pipe,data`); Blender runs
  with `--offline-mode`.

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
- Chrome prints Markdown/HTML to PDF with networking disabled, pandoc runs with
  `--sandbox` and mammoth never opens external files, so remote images or scripts
  referenced in a document are never fetched.
- Page images from PDF → png/jpg never overwrite existing numbered files without `--force`.
- Test suite (routing table, real conversions on tiny fixtures, CLI, app server) and
  GitHub Actions CI on macOS with Python 3.12–3.14.
- MIT license.

[Unreleased]: https://github.com/Kurzehose20620/uniconverter/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/Kurzehose20620/uniconverter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/Kurzehose20620/uniconverter/releases/tag/v1.0.0
