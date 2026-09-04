# uniconv – universeller lokaler Datei-Konverter

Konvertiert Bilder, Dokumente, PDFs, Audio und Video **komplett lokal** auf
deinem Mac. Keine Datei verlässt den Rechner, kein Upload, keine Cloud.

## Die App

**Uniconv.app** (in `~/Applications`, per Spotlight „Uniconv" suchbar):
Dateien ins Fenster ziehen, Zielformat auswählen, fertig. Ergebnisse landen
in Downloads oder auf dem Schreibtisch („Zeigen" öffnet sie im Finder).
Bei mehreren Dateien kann alles zu **einer** PDF zusammengefügt werden.

Die App startet einen Mini-Server, der nur auf 127.0.0.1 lauscht – auch hier
verlässt nichts den Rechner. Start alternativ im Terminal: `uniconv-app`.

## Installation

Voraussetzungen: macOS und [pipx](https://pipx.pypa.io)
(`brew install pipx && pipx ensurepath`).

```bash
git clone <dieses Repo> uniconv && cd uniconv
./install.sh              # CLI per pipx + Uniconv.app in ~/Applications
```

Nur das CLI, ohne App-Bundle: `pipx install .` – danach gibt es die Befehle
`uniconv` und `uniconv-app`. Zum Entwickeln `./install.sh --editable`
(Codeänderungen sind sofort wirksam).

## Benutzung im Terminal

```bash
uniconv foto.heic foto.jpg              # einzelne Datei
uniconv *.heic -t jpg                   # Stapel: alle HEIC → JPG
uniconv *.png -t webp -o ./web/         # Stapel mit Zielordner
uniconv bericht.docx bericht.pdf        # Word → PDF
uniconv bericht.docx bericht.md         # Word → Markdown
uniconv skript.md skript.pdf            # Markdown → PDF (hübsch gesetzt)
uniconv paper.pdf paper.md              # PDF → Markdown
uniconv paper.pdf -t png --dpi 200      # PDF → ein PNG pro Seite
uniconv scan1.png scan2.png doc.pdf     # mehrere Dateien → EINE PDF
uniconv scan.png kapitel.docx notiz.md alles.pdf   # Merge quer durch Formate
```

Nützliche Befehle und Optionen:

| | |
|---|---|
| `uniconv doctor` | zeigt, welche Konverter verfügbar sind |
| `uniconv formats` | alle unterstützten Konvertierungswege |
| `-q 85` | JPEG/WebP-Qualität (Standard 90) |
| `--dpi 200` | Auflösung bei PDF → Bild (Standard 150) |
| `--extract-images` | bei PDF → md auch die Bilder herausziehen |
| `-f` / `--force` | vorhandene Zieldateien überschreiben |

## Was es kann

- **Bilder**: png, jpg, heic, webp, tiff, bmp, gif, avif, ico – kreuz und quer,
  außerdem Bild(er) → PDF (mehrere Bilder = mehrseitige PDF)
- **Word & Office**: docx/doc/odt/rtf (auch pptx, xlsx) → PDF oder Bilder
  (via LibreOffice), docx → Markdown/Text/HTML
- **PDF**: → Markdown, Text, HTML, Bilder (pro Seite); mehrere PDFs/Bilder/
  Dokumente zu einer PDF zusammenführen
- **Markdown**: → PDF (sauber gesetzt via Chrome-Druck), HTML, DOCX, RTF
- **Audio**: wav, m4a, aiff, caf mit Bordmitteln; mp3/flac/ogg mit ffmpeg
- **Video** (mit ffmpeg): mp4, mov, mkv, webm untereinander, → GIF, → Audio

## Optionale Upgrades

Alles funktioniert bereits – diese Installationen verbessern einzelne Wege:

```bash
brew install pandoc typst    # beste Qualität für md → docx/pdf (Tabellen!)
brew install ffmpeg          # Audio (mp3!) und Video
brew install imagemagick     # exotische Bildformate
pipx inject uniconv pdf2docx    # PDF → Word
```

## Aufbau

- `src/uniconv/cli.py` – Kommandozeile (`uniconv`)
- `src/uniconv/app.py` + `app.html` – Drag-&-Drop-App (`uniconv-app`),
  lokaler Server auf 127.0.0.1
- `src/uniconv/router.py` – wählt anhand von Quell- und Zielendung die Engine
- `src/uniconv/engines/` – `images`, `pdf`, `office`, `text`, `media`,
  dazu `tools` (Erkennung externer Programme)
- `install.sh` – pipx-Installation plus Uniconv.app; erneut ausführen, wenn
  der `uniconv`-Befehl fehlt

Genutzte Engines (Priorität je nach Verfügbarkeit): Pillow/PyMuPDF,
macOS-Bordmittel (`sips`, `textutil`, `afconvert`), LibreOffice headless,
Chrome Headless-Druck, optional pandoc/typst/ImageMagick/ffmpeg.

## Bekannte Einschränkungen

- **md → docx ohne pandoc**: Tabellen verlieren ihre Rahmen (der Fallback läuft
  über HTML + textutil). `brew install pandoc` behebt das.
- **PDF → Word** braucht das optionale `pdf2docx` (~100 MB).
- **mp3 erzeugen** braucht ffmpeg (macOS-Bordmittel können mp3 nur lesen).
- LibreOffice-Konvertierung kann fehlschlagen, während LibreOffice offen ist –
  dann kurz schließen.
