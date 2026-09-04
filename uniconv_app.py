#!/usr/bin/env python3
"""uniconv App – lokale Drag-&-Drop-Oberfläche für uniconv.

Kleiner Webserver, der nur auf 127.0.0.1 lauscht. Dateien werden per
Drag & Drop an die Seite übergeben, konvertiert und in Downloads bzw. auf
dem Schreibtisch abgelegt. Nichts verlässt den Rechner.
"""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uniconv  # noqa: E402

APP_VERSION = "1"
PORT_RANGE = range(8756, 8766)
HTML_FILE = Path(__file__).resolve().parent / "app.html"

UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="uniconv-app-"))
UPLOADS = {}          # id -> Path
UPLOAD_LOCK = threading.Lock()
UPLOAD_SEQ = [0]
PRODUCED = set()      # Pfade, die die App erzeugt hat (für "Im Finder zeigen")
CONVERT_LOCK = threading.Lock()   # LibreOffice & Co. lieber nacheinander

OUTDIRS = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
}

LABELS = {
    "jpg": "JPG · Bild", "jpeg": "JPEG · Bild", "png": "PNG · Bild",
    "webp": "WebP · Bild", "heic": "HEIC · Bild", "tiff": "TIFF · Bild",
    "tif": "TIFF · Bild", "bmp": "BMP · Bild", "gif": "GIF", "avif": "AVIF · Bild",
    "ico": "ICO · Icon", "pdf": "PDF", "md": "Markdown", "txt": "Text",
    "html": "HTML", "docx": "DOCX · Word", "doc": "DOC · Word",
    "odt": "ODT · OpenDocument", "rtf": "RTF", "mp3": "MP3 · Audio",
    "m4a": "M4A · Audio", "wav": "WAV · Audio", "aiff": "AIFF · Audio",
    "caf": "CAF · Audio", "flac": "FLAC · Audio", "ogg": "OGG · Audio",
    "mp4": "MP4 · Video", "mov": "MOV · Video", "mkv": "MKV · Video",
    "webm": "WebM · Video", "avi": "AVI · Video",
}


def safe_name(name):
    name = Path(name).name
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "datei"
    return name


def unique_path(p: Path):
    if not p.exists():
        return p
    n = 2
    while True:
        cand = p.with_name(f"{p.stem}-{n}{p.suffix}")
        if not cand.exists():
            return cand
        n += 1


def make_opts(payload):
    return SimpleNamespace(
        quality=max(1, min(100, int(payload.get("quality", 90)))),
        dpi=max(50, min(600, int(payload.get("dpi", 150)))),
        extract_images=bool(payload.get("extract_images", False)),
        force=True,
    )


def convert_job(src: Path, target: str, outdir: Path, opts):
    """Eine Datei konvertieren; alle erzeugten Dateien nach outdir verschieben."""
    with tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as td:
        dst = Path(td) / (Path(src).stem + "." + target)
        uniconv.convert_one(src, dst, opts)
        produced = sorted(p for p in Path(td).iterdir() if p.is_file())
        moved = []
        for p in produced:
            final = unique_path(outdir / p.name)
            shutil.move(str(p), str(final))
            PRODUCED.add(str(final))
            moved.append(final.name)
        # von pdf→md --extract-images angelegte Bildordner mitnehmen
        for d in sorted(p for p in Path(td).iterdir() if p.is_dir()):
            final = unique_path(outdir / d.name)
            shutil.move(str(d), str(final))
            moved.append(final.name + "/")
        return moved


def merge_job(sources, outdir: Path, opts):
    with tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as td:
        name = Path(sources[0]).stem + "-gesamt.pdf" if len(sources) else "gesamt.pdf"
        dst = Path(td) / name
        uniconv.merge_to_pdf(sources, dst, opts)
        final = unique_path(outdir / dst.name)
        shutil.move(str(dst), str(final))
        PRODUCED.add(str(final))
        return [final.name]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    # ------------------------------------------------------------ GET
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        if url.path == "/":
            self._send(200, HTML_FILE.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/ping":
            self._send(200, {"app": "uniconv", "version": APP_VERSION})
        elif url.path == "/targets":
            qs = urllib.parse.parse_qs(url.query)
            exts = [e.lower().lstrip(".") for e in
                    qs.get("exts", [""])[0].split(",") if e]
            sets = [set(uniconv.possible_targets(e)) for e in exts]
            common = sorted(set.intersection(*sets)) if sets else []
            mergeable = bool(exts) and all(
                e == "pdf" or "pdf" in uniconv.possible_targets(e) for e in exts)
            self._send(200, {
                "targets": [{"ext": t, "label": LABELS.get(t, t.upper())}
                            for t in common],
                "mergeable": mergeable and len(exts) > 1,
            })
        else:
            self._send(404, {"error": "nicht gefunden"})

    # ------------------------------------------------------------ POST
    def do_POST(self):
        try:
            if self.path == "/upload":
                self._upload()
            elif self.path == "/convert":
                self._convert()
            elif self.path == "/reveal":
                self._reveal()
            elif self.path == "/shutdown":
                self._send(200, {"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self._send(404, {"error": "nicht gefunden"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _upload(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 2 * 1024 ** 3:
            return self._send(413, {"error": "Datei größer als 2 GB"})
        raw_name = urllib.parse.unquote(self.headers.get("X-Filename", "datei"))
        name = safe_name(raw_name)
        with UPLOAD_LOCK:
            UPLOAD_SEQ[0] += 1
            fid = str(UPLOAD_SEQ[0])
            fdir = UPLOAD_DIR / f"in-{fid}"
        fdir.mkdir()
        path = fdir / name
        remaining = length
        with open(path, "wb") as f:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                f.write(chunk)
                remaining -= len(chunk)
        UPLOADS[fid] = path
        self._send(200, {"id": fid, "name": name})

    def _convert(self):
        payload = self._json_body()
        ids = payload.get("ids", [])
        target = str(payload.get("target", "")).lower().lstrip(".")
        outdir = OUTDIRS.get(payload.get("outdir", "downloads"), OUTDIRS["downloads"])
        outdir.mkdir(parents=True, exist_ok=True)
        opts = make_opts(payload)
        sources = [UPLOADS[i] for i in ids if i in UPLOADS]
        if not sources or not target:
            return self._send(400, {"error": "keine Dateien oder kein Zielformat"})

        results = []
        with CONVERT_LOCK:
            if payload.get("merge") and target == "pdf" and len(sources) > 1:
                try:
                    files = merge_job(sources, outdir, opts)
                    results.append({"name": f"{len(sources)} Dateien",
                                    "ok": True, "files": files})
                except Exception as e:
                    results.append({"name": f"{len(sources)} Dateien",
                                    "ok": False, "error": str(e)})
            else:
                for src in sources:
                    try:
                        files = convert_job(src, target, outdir, opts)
                        results.append({"name": src.name, "ok": True,
                                        "files": files})
                    except Exception as e:
                        results.append({"name": src.name, "ok": False,
                                        "error": str(e)})
        self._send(200, {"results": results, "outdir": str(outdir)})

    def _reveal(self):
        payload = self._json_body()
        outdir = OUTDIRS.get(payload.get("outdir", "downloads"), OUTDIRS["downloads"])
        path = outdir / safe_name(payload.get("file", ""))
        target = str(path).rstrip("/")
        if target in PRODUCED or str(path) in PRODUCED:
            subprocess.run(["open", "-R", target])
            self._send(200, {"ok": True})
        else:
            self._send(403, {"error": "unbekannte Datei"})


def main():
    for port in PORT_RANGE:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit("Kein freier Port gefunden.")
    print(f"uniconv App läuft: http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    finally:
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)


if __name__ == "__main__":
    main()
