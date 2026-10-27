# uniconverter

[![CI](https://github.com/Kurzehose20620/uniconverter/actions/workflows/ci.yml/badge.svg)](https://github.com/Kurzehose20620/uniconverter/actions/workflows/ci.yml)

Convert images, documents, PDFs, e-books, audio, video, subtitles and 3D models
**entirely on your Mac**. One command for every format, the right engine picked
automatically, nothing uploaded anywhere.

```bash
uniconverter photo.heic photo.jpg           # HEIC → JPG
uniconverter *.heic -t jpg                  # every HEIC in the folder → JPG
uniconverter report.docx report.pdf         # Word → PDF (LibreOffice)
uniconverter paper.pdf paper.md             # PDF → Markdown, with OCR if it is a scan
uniconverter scan1.png notes.md all.pdf     # several files, any mix → one PDF
uniconverter photo.jpg small.jpg --max 1600 --small   # a smaller photo
uniconverter clip.mov clip.mp4 --height 720 # video at 720p
uniconverter book.epub book.azw3            # e-book for a Kindle (calibre)
```

![The Uniconverter app: a drop zone, target format, save location](docs/app.png)

## Why

Online converters mean handing your files to somebody else's server. On the Mac the
alternatives are paid apps or a toolbox of single-purpose commands (`sips`, `textutil`,
`soffice`, `pandoc`, `ffmpeg` …), each with its own syntax. uniconverter is one command
in front of all of them:

- **Works out of the box.** The common routes run on what macOS already ships
  (`sips`, `textutil`, `afconvert`) plus a few Python libraries. No brew install needed.
- **Gets better with every tool you install.** LibreOffice, pandoc, typst, calibre,
  ffmpeg, ImageMagick, Ghostscript, Blender and Tesseract are picked up automatically,
  including Homebrew's keg-only full builds (`ffmpeg-full`, `imagemagick-full`).
  `uniconverter doctor` shows what is available and what each missing tool would add.
- **Private by construction.** There is no network code, and the engines are run so
  that they do not fetch anything either (see [Privacy](#privacy)). The app talks to a
  server bound to 127.0.0.1 and to nothing else.

## Install

Requirements: macOS 12 or newer, Python 3.12+, [pipx](https://pipx.pypa.io)
(`brew install pipx && pipx ensurepath`).

```bash
git clone https://github.com/Kurzehose20620/uniconverter.git
cd uniconverter
./install.sh            # command line + Uniconverter.app in ~/Applications
```

Command line only: `pipx install .` gives you `uniconverter` and `uniconverter-app`.
For development run `./install.sh --editable`; code changes then take effect immediately.

## Command line

```
uniconverter SOURCE TARGET             one file, formats taken from the extensions
uniconverter SOURCE… -t EXT [-o DIR]   batch: every source → EXT, same folder or DIR
uniconverter SOURCE… TARGET.pdf        merge: several files (any mix) → one PDF
uniconverter doctor                    which engines are available
uniconverter formats                   every supported route
```

| Option | |
|---|---|
| `-q 85` | JPEG/WebP/AVIF/HEIC/JPEG XL quality (default 90) |
| `--dpi 200` | resolution for PDF/SVG/EPS → image (default 150) |
| `--extract-images` | PDF → Markdown: also save the images next to it |
| `--ocr-lang deu+eng` | OCR languages for scanned PDFs (default: your system language + English) |
| `-f`, `--force` | overwrite existing files |
| `-n`, `--dry-run` | show what would be converted and with which engine, change nothing |
| `-v`, `--verbose` | name the engine for each file and echo external commands |

### Smaller files

Images and videos can be scaled down and compressed harder – while converting, or
into the same format:

| Option | |
|---|---|
| `--max 1920` | longest side at most 1920 pixels |
| `--width 1280`, `--height 720` | at most this wide / high |
| `--small` | compress harder: lower image quality, PNG optimised, no image metadata (EXIF, XMP; the colour profile stays); lower video and audio bitrates or higher CRF for every codec |
| `--target-size 50MB` | video: aim at a file size (bitrate from the length, two-pass encoding) for mp4, m4v, mov, mkv, ts, m2ts, 3gp, webm, avi, divx |

Pictures are only ever made smaller, never larger, and keep their aspect ratio; video
sizes stay even. Formats with a fixed size (vob, dv) ignore the size options; avi, 3gp
and rm never exceed 640×480. PDF → image pages are rendered to fit the box.

```bash
uniconverter photo.jpg photo-small.jpg --max 1600 --small
uniconverter *.jpg -t jpg --max 1600              # → photo-small.jpg next to each photo
uniconverter *.jpg -t webp --max 1600 -o ./web/   # batch into another folder and format
uniconverter talk.mov talk.mp4 --height 720 --small
uniconverter talk.mov mail.mp4 --target-size 25MB
```

In a batch into the same format and folder the results get a `-small` suffix, so the
originals are never replaced.

Exit codes: 0 everything converted, 1 at least one conversion failed, 2 the command line
was wrong (missing file, no route, existing target without `--force`). Errors go to stderr,
so `uniconverter *.heic -t jpg 2> errors.log` keeps the terminal clean.

## The app

`Uniconverter.app` (Spotlight: "Uniconverter"): drop files into the window, pick the
target format, done. Results land in Downloads or on the Desktop, "Show in Finder"
reveals them. Several files can be merged into one PDF. For images and videos the
window offers a size (original, 1080p/720p/480p for video, a longest side for images)
and a "Smaller file" checkbox; the source's own format is offered too, so a photo or
clip can be shrunk without converting it.

The window is native (WebKit). Behind it runs a tiny server that listens on 127.0.0.1
only and stops when the window closes. `uniconverter-app` starts the same thing from
the terminal; `uniconverter-app --serve` runs just the server for use in a browser.

## What it converts

`uniconverter formats` prints the full list; `uniconverter doctor` shows which routes
work on your machine. Targets whose engine is missing are not offered.

### Images

| Format | Read | Write | Engine |
|---|---|---|---|
| png, jpg, heic, tiff, bmp, gif, webp, avif | ✓ | ✓ | Pillow (+ pillow-heif) |
| ico, icns | ✓ | ✓ | Pillow, padded square |
| tga, ppm, pgm, pbm, pcx, jp2, qoi, dds, sgi | ✓ | ✓ | Pillow |
| psd, exr | ✓ | ✓ | Pillow/sips read, sips writes (flattened) |
| hdr | ✓ | ✓ | ImageMagick (or ffmpeg) |
| jxl (JPEG XL) | ✓ | ✓ | cjxl writes; sips, djxl or ImageMagick read |
| dpx, xpm | ✓ | ✓ | ImageMagick |
| svg | ✓ | – | PyMuPDF (vector; `--dpi` sets the size) |
| eps, ps, ai | ✓ | – | Ghostscript via ImageMagick; → PDF stays vector |
| pnm, pict, pcd, xcf, fits | ✓ | – | Pillow, sips or ImageMagick (fits: greyscale) |
| camera RAW: dng cr2 cr3 crw nef nrw arw srf sr2 orf rw2 raf pef srw erf 3fr iiq mos mrw dcr | ✓ | – | sips, else libraw (imagemagick-full) |

Any image → PDF (several images = one multi-page PDF). EXIF orientation is applied
when converting, so photos are never saved sideways.

### Documents

| From | To | Engine |
|---|---|---|
| Markdown | pdf, html, docx, odt, rtf, txt, epub, mobi, azw3, fb2 | pdf: pandoc + typst, else Chrome; html: python-markdown; rest: pandoc (+ calibre) |
| docx, odt, rtf (doc) | pdf, png/jpg per page | LibreOffice headless |
| docx, odt, rtf (doc) | md, txt, html, docx, odt, rtf, epub, mobi, azw3, fb2 | pandoc (doc via LibreOffice), textutil, calibre; without pandoc: mammoth |
| pptx, ppt, xlsx, xls | pdf, png/jpg per page | LibreOffice headless |
| HTML | pdf, md, docx, odt, rtf, txt, epub, mobi, azw3, fb2 | Chrome, html2text, textutil, pandoc, calibre |
| txt | pdf, docx, rtf, html, epub, mobi, azw3, fb2 | Chrome, textutil, calibre |
| rst, org, tex, ipynb | md, html, docx, odt, rtf, txt, pdf, epub, mobi, azw3, fb2 | pandoc (+ typst, calibre) |
| PDF | png, jpg, webp, tiff (one file per page), md, txt, html | PyMuPDF, pymupdf4llm; Tesseract OCR for scanned pages |
| PDF | docx | pdf2docx (optional) |
| PDF | epub, mobi, azw3, fb2 | calibre |
| any of the above | one merged PDF | each file → PDF, then PyMuPDF |

PDFs from pandoc are typeset by typst on A4 (Letter in the US and Canada); if typst
fails, Chrome prints the document instead.

### E-books (calibre)

| Format | Read | Write |
|---|---|---|
| epub, mobi, azw3, fb2, lit, lrf | ✓ | ✓ |
| azw (old Kindle) | ✓ | – |
| cbz, cbr (comics) | ✓ | – (→ epub, mobi, azw3, pdf) |

E-books also convert to pdf, docx, txt and rtf (calibre) and to md, html and odt
(through EPUB and pandoc). Without calibre, pandoc still reads EPUB. DRM-protected
books cannot be converted.

### Audio (ffmpeg; wav, m4a, aiff, caf also with the built-in afconvert)

| Format | Read | Write | Profile |
|---|---|---|---|
| mp3 | ✓ | ✓ | LAME 192k (`--small`: 128k) |
| m4a, aac | ✓ | ✓ | AAC 192k (128k) |
| alac (→ .m4a) | ✓ | ✓ | Apple Lossless |
| m4b | ✓ | ✓ | AAC 128k (64k), audiobook |
| ogg | ✓ | ✓ | Vorbis q6 (q3); Opus in Ogg if ffmpeg lacks Vorbis |
| opus | ✓ | ✓ | Opus 128k (64k) |
| flac, wav, aiff, caf, au, wv, mka | ✓ | ✓ | lossless / PCM 16 bit |
| wma | ✓ | ✓ | WMA2 192k (96k) |
| ac3 | ✓ | ✓ | AC3 384k (192k) |
| mp2 | ✓ | ✓ | MP2 256k (160k) |
| amr | ✓ | ✓ | AMR-NB 12.2k, 8 kHz mono (needs ffmpeg-full) |
| eac3, dts, ape, ra, oga, weba | ✓ | – | |

### Video (ffmpeg)

| Format | Read | Write | Profile |
|---|---|---|---|
| mp4, m4v, mov, mkv | ✓ | ✓ | H.264 CRF 23 (`--small`: 28) + AAC 160k (96k) |
| ts, m2ts | ✓ | ✓ | H.264 + AAC in MPEG-TS |
| webm | ✓ | ✓ | VP9 CRF 32 (40) + Opus |
| avi, divx | ✓ | ✓ | Xvid-compatible, see below |
| wmv, asf | ✓ | ✓ | WMV2 + WMA2 |
| flv | ✓ | ✓ | Sorenson H.263 + MP3 |
| mpg | ✓ | ✓ | MPEG-2 + MP2 (frame rate set to 25 if MPEG-2 does not allow the source's) |
| vob | ✓ | ✓ | DVD-Video PAL 720×576, 16:9 or 4:3, AC3 |
| dv | ✓ | ✓ | PAL DV 720×576, 25 fps |
| 3gp | ✓ | ✓ | H.264 Baseline + AAC, max. 640×480 |
| 3gp-h263 (→ .3gp) | – | ✓ | H.263 176×144 (`--height 288`: 352×288), 15 fps, AMR-NB (needs ffmpeg-full) |
| ogv | ✓ | ✓ | Theora + Vorbis (ffmpeg-full), else VP8 + Opus |
| rm | ✓ | ✓ | RealVideo 2 + AC3, max. 640×480 |
| gif | ✓ | ✓ | palette, 12 fps, at most 640 wide |
| rmvb, f4v, 3g2, qt, mod, tod, vro, m2v, mxf | ✓ | – | |

Every video converts to gif and to every audio format as well.

AVI output uses Xvid-compatible settings that play on older standalone players:
MPEG-4 Part 2 with the XVID tag (`.divx`: DIVX tag), at most 640×480 with the aspect
ratio kept and square pixels, no B-frames, 1000 kbit/s (max. 2000), MP3 128k at 48 kHz.

### Subtitles (ffmpeg)

srt, vtt, ass and ssa convert into each other. From mkv, mp4, m4v, mov, webm, ts and
m2ts the text subtitle track (the default one, else the first) can be saved as
srt/vtt/ass/ssa; picture subtitles (PGS, VobSub) would need OCR and are refused with a
clear message.

### 3D models (Blender)

glb, gltf, obj, fbx, stl, ply, usd/usdc/usdz/usda and abc → obj, glb, gltf, fbx, stl,
ply, usdz, usdc. Blender runs in the background with factory settings and in offline
mode; textures are embedded or copied next to the target.

### doctor

```
Programs:
  ✓ LibreOffice       Word/Excel/PowerPoint → PDF
  ✓ Chrome            Markdown/HTML → PDF (headless printing)
  ✓ pandoc            md/docx/odt/rtf/html/epub/rst/org/tex/ipynb (optional)
  ✓ typst             nicer PDF typesetting with pandoc (optional)
  ✗ calibre           e-books: epub mobi azw3 fb2 lit lrf cbz (optional)
      → brew install --cask calibre
  ✓ imagemagick       hdr dpx xpm fits pict pcd xcf (optional)
  ✓ ghostscript       EPS/PS/AI → image or vector PDF (optional)
  ✗ jpeg-xl           JPEG XL output (cjxl, optional)
      → brew install jpeg-xl
  ✓ ffmpeg            audio/video/subtitle conversion (optional)
  ✓ ffprobe           video analysis (size, frame rate, length, subtitles)
  ✗ Blender           3D models glb/gltf/fbx/stl/usdz/… (optional)
      → brew install --cask blender
  ✓ tesseract         OCR for scanned PDFs (optional) – uses deu+eng

ffmpeg encoders (decide which targets are offered):
  ✓ libx264           H.264 → mp4/m4v/mov/mkv/ts/m2ts/3gp
  ✗ libtheora         Theora in .ogv (otherwise VP8)
      → brew install ffmpeg-full  (keg-only, used automatically when installed)
  …
```

## Why not just pandoc / ffmpeg?

You can, and uniconverter calls them when they are installed. What it adds:

- **One syntax.** `uniconverter a.heic b.jpg` and `uniconverter a.docx b.pdf` look the
  same. You do not have to remember that HEIC → JPG is `sips -s format jpeg`, that Word
  → PDF is `soffice --headless --convert-to pdf --outdir`, or which pandoc flags produce
  a readable PDF.
- **Fallbacks instead of errors.** No pandoc? Markdown → PDF goes through Chrome's print
  engine with a clean stylesheet. No ffmpeg? wav, m4a, aiff and caf still work through
  afconvert. No LibreOffice? You get one line telling you the brew command.
- **Batches and merges.** `*.heic -t jpg`, or scans + a Word file + notes → one PDF,
  in one command.
- **A drop target** for the moments when a terminal is the wrong tool.

## Requirements and optional engines

macOS only for now: the built-in engines are `sips`, `textutil` and `afconvert`, and the
app window is WebKit. Everything else is optional and detected automatically:

```bash
brew install --cask libreoffice     # Word/Excel/PowerPoint → PDF and images
brew install pandoc typst           # best Markdown ↔ DOCX/PDF quality, rst/org/tex/ipynb; pandoc ≥ 3.1.2
brew install --cask calibre         # e-books: mobi, azw3, fb2, lit, lrf, comics
brew install ffmpeg                 # mp3, flac, ogg, video, subtitles
brew install ffmpeg-full            # adds Theora, Vorbis, AMR (keg-only, preferred automatically)
brew install imagemagick ghostscript  # hdr, dpx, xpm, pict, eps/ai …
brew install imagemagick-full       # adds camera RAW via libraw (keg-only, preferred automatically)
brew install jpeg-xl                # JPEG XL output
brew install --cask blender         # 3D models
brew install tesseract              # OCR for scanned PDFs (English); tesseract-lang adds the rest
pipx inject uniconverter pdf2docx   # PDF → Word (~100 MB)
```

Google Chrome, Chromium, Brave or Edge are used for Markdown/HTML → PDF when present.

## Privacy

Nothing leaves your machine. uniconverter contains no network code, no telemetry and
no update check. The app's server binds to 127.0.0.1, is reachable only from your own
Mac, starts with the window and stops with it. Files handed to the app live in a
temporary folder that is removed when the window closes.

Documents and media files can reference remote content (an image by URL in Markdown,
a linked picture in a Word file, a URL inside an SVG or a playlist). uniconverter does
not follow such references:

- Chrome prints with networking disabled (every host name resolves to nothing,
  background services off).
- pandoc runs with `--sandbox` and a small Lua filter: images next to the document are
  still embedded, remote images are replaced by their description. PDFs are typeset in
  two steps (pandoc → Typst → `typst compile` inside a temporary folder), because
  pandoc's own PDF pipeline is not sandboxed; raw Typst code is dropped.
- ImageMagick runs under a bundled `policy.xml` that forbids URL/HTTP(S)/FTP coders and
  delegates, MSL/MVG scripts and `@file` indirection. Ghostscript runs with `-dSAFER`.
- ffmpeg may only open local files (`-protocol_whitelist file,pipe,data`).
- calibre does not load remote resources (verified by the test suite), mammoth is told
  not to open external files, Blender runs with `--offline-mode`.

Such images simply appear as missing. LibreOffice is the one engine where uniconverter
cannot enforce this; it runs with a throwaway profile, but a document with linked
external content may make LibreOffice try to load it. Installing uniconverter itself
downloads Python packages from PyPI, and the optional engines come from Homebrew;
after that, no conversion needs a connection.

Anything running on your Mac can reach 127.0.0.1, including a web page open in your
browser. That is why every session gets a random token: the window passes it with each
request, requests without it (or from a foreign origin) are refused, and responses are
marked `no-store`. The server is not a general local API, it is private to the window.

## Known limitations

- Markdown → DOCX without pandoc: tables lose their borders (the fallback goes through
  HTML + textutil). `brew install pandoc` fixes it.
- PDF → Word needs the optional `pdf2docx` package.
- Creating mp3 needs ffmpeg; macOS can only read mp3.
- Animated GIF/WebP → image keeps only the first frame.
- Camera RAW was tested with a synthetic DNG only; real camera files go the same way
  (sips, else libraw). xcf and cbr input is offered but untested (no test files).
- `--target-size` lands within a few percent for normal footage; very noisy material
  or very short clips can end up larger.
- PDF → docx/epub keeps the text; the layout of complex PDFs is only approximated.
- vob is a single file, not a DVD folder structure. rmvb cannot be written (there is
  no RealVideo 4 encoder).
- LibreOffice conversions can fail while LibreOffice is open. Close it and retry.
- OCR output depends on the scan; expect the occasional misread character.
- Remote images in Markdown/HTML are not loaded when printing to PDF (by design, see Privacy).
- macOS only. Linux fallbacks (ImageMagick instead of sips, pandoc instead of textutil)
  are on the list.

## Development

```bash
./install.sh --editable                 # or, in a venv:  pip install -e ".[dev]"
ruff check src tests
pytest                                  # routes that need an optional program are
                                        # skipped when it is missing
```

The tests convert synthetic sources (ffmpeg test patterns, Pillow images, Markdown,
reStructuredText, …) and check the results by content: codecs, sizes and B-frames via
ffprobe, pixel colours, and the text read back from every document and e-book.

CI runs lint and tests on macOS with Python 3.12, 3.13 and 3.14; the 3.14 job also
installs ffmpeg, pandoc and typst so the media and document routes run there too.

Layout: `src/uniconverter/cli.py` (command line), `app.py` + `app.html` (the app),
`router.py` (chooses the engine for a source/target pair), `sizing.py` (the shrink
options), `formats.py` (extensions per family), `engines/` (`images`, `pdf`, `office`,
`text`, `documents` (pandoc/typst), `ebooks` (calibre), `media` (ffmpeg),
`subtitles`, `models` (Blender), and `tools` for detecting external programs).

This project was built with AI assistance (Claude Code). The code is reviewed, tested
and maintained by hand.

## License

MIT, see [LICENSE](LICENSE).

---

## Kurzfassung auf Deutsch

uniconverter konvertiert Bilder, Dokumente, PDFs, E-Books, Audio, Video, Untertitel und
3D-Modelle komplett lokal auf dem Mac: ein Befehl für alles, die passende Engine wird
automatisch gewählt, nichts wird hochgeladen. `./install.sh` installiert die Befehle
`uniconverter` und `uniconverter-app` sowie Uniconverter.app (Dateien ins Fenster
ziehen, Zielformat wählen, fertig).

```bash
uniconverter foto.heic foto.jpg             # einzelne Datei
uniconverter *.heic -t jpg                  # Stapel: alle HEIC → JPG
uniconverter bericht.docx bericht.pdf       # Word → PDF (LibreOffice)
uniconverter scan.pdf scan.md               # PDF → Markdown, bei Scans mit Texterkennung
uniconverter scan1.png notiz.md alles.pdf   # mehrere Dateien → eine PDF
uniconverter buch.epub buch.azw3            # E-Book für den Kindle (calibre)
uniconverter film.mkv film.srt              # Untertitel aus einem Video ziehen
```

Verkleinern (Bilder und Videos, auch im selben Format und im Stapel):
`--max 1920` (längste Seite), `--width`/`--height` (nur verkleinern, Seitenverhältnis
bleibt), `--small` (stärker komprimieren, Bild-Metadaten weg) und für Videos
`--target-size 50MB` (Zielgröße, Zwei-Pass). In der App gibt es dafür eine Größenwahl
(Original/1080p/720p/480p bzw. längste Bildkante) und den Haken „Smaller file“.

```bash
uniconverter foto.jpg foto-klein.jpg --max 1600 --small
uniconverter *.jpg -t jpg --max 1600        # → foto-small.jpg neben jedem Foto
uniconverter vortrag.mov vortrag.mp4 --height 720
```

AVI-Ausgabe nutzt Xvid-kompatible Einstellungen, die auch auf älteren Stand-alone-Playern
laufen (max. 640×480, keine B-Frames, MP3).

`uniconverter doctor` zeigt, welche Engines vorhanden sind, `uniconverter formats` alle
Wege. Optionale Programme (LibreOffice, pandoc, typst, calibre, ffmpeg, ImageMagick,
Ghostscript, Blender, Tesseract) werden automatisch erkannt, die Vollversionen
`ffmpeg-full` und `imagemagick-full` bevorzugt; ohne sie greifen Bordmittel und
Fallbacks. Keine Engine lädt dabei etwas aus dem Netz nach.
