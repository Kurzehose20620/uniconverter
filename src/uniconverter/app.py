"""uniconverter App – lokale Drag-&-Drop-Oberfläche für uniconverter.

Kleiner Webserver, der nur auf 127.0.0.1 lauscht. Dateien werden per
Drag & Drop an die Seite übergeben, konvertiert und in Downloads bzw. auf
dem Schreibtisch abgelegt. Nichts verlässt den Rechner.

`uniconverter-app` sucht einen laufenden Server (oder startet einen im
Hintergrund) und öffnet das App-Fenster. `uniconverter-app --serve` startet
den Server im Vordergrund.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

from . import __version__
from . import router as core

APP_VERSION = __version__
PORT_RANGE = range(8756, 8766)
HTML_FILE = files(__package__).joinpath("app.html")

UPLOAD_DIR = None     # wird in serve() angelegt
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
        ocr_lang=payload.get("ocr_lang") or None,
        force=True,
    )


def convert_job(src: Path, target: str, outdir: Path, opts):
    """Eine Datei konvertieren; alle erzeugten Dateien nach outdir verschieben."""
    with tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as td:
        dst = Path(td) / (Path(src).stem + "." + target)
        core.convert_one(src, dst, opts)
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
        core.merge_to_pdf(sources, dst, opts)
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
            self._send(200, {"app": "uniconverter", "version": APP_VERSION})
        elif url.path == "/targets":
            qs = urllib.parse.parse_qs(url.query)
            exts = [e.lower().lstrip(".") for e in
                    qs.get("exts", [""])[0].split(",") if e]
            sets = [set(core.possible_targets(e)) for e in exts]
            common = sorted(set.intersection(*sets)) if sets else []
            mergeable = bool(exts) and all(
                e == "pdf" or "pdf" in core.possible_targets(e) for e in exts)
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
                    files_ = merge_job(sources, outdir, opts)
                    results.append({"name": f"{len(sources)} Dateien",
                                    "ok": True, "files": files_})
                except Exception as e:
                    results.append({"name": f"{len(sources)} Dateien",
                                    "ok": False, "error": str(e)})
            else:
                for src in sources:
                    try:
                        files_ = convert_job(src, target, outdir, opts)
                        results.append({"name": src.name, "ok": True,
                                        "files": files_})
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


# ---------------------------------------------------------------- Server

def serve():
    """Server im Vordergrund starten (bis /shutdown oder Ctrl-C)."""
    global UPLOAD_DIR
    for port in PORT_RANGE:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit("Kein freier Port gefunden.")
    UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="uniconverter-app-"))
    print(f"uniconverter App läuft: http://127.0.0.1:{server.server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)


# ---------------------------------------------------------------- Launcher

def _ping(port, timeout=1.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/ping", timeout=timeout) as r:
            return json.load(r)
    except (OSError, ValueError):
        return None


def _post(port, path, timeout=2.0):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"", method="POST")
    try:
        urllib.request.urlopen(req, timeout=timeout).close()
    except OSError:
        pass


def find_server():
    """Port eines laufenden Servers dieser Version; veraltete Server werden beendet."""
    for port in PORT_RANGE:
        info = _ping(port)
        if not info or info.get("app") != "uniconverter":
            continue
        if info.get("version") == APP_VERSION:
            return port
        _post(port, "/shutdown")   # alte Version läuft noch – beenden, damit die neue startet
    return None


def ensure_server():
    """Laufenden Server finden oder einen im Hintergrund starten; liefert den Port."""
    port = find_server()
    if port:
        return port
    subprocess.Popen([sys.executable, "-m", "uniconverter.app", "--serve"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)
    for _ in range(40):
        time.sleep(0.25)
        port = find_server()
        if port:
            return port
    return None


def open_window(url):
    if os.path.isdir("/Applications/Google Chrome.app"):
        subprocess.run(["open", "-na", "Google Chrome", "--args", f"--app={url}"])
    else:
        subprocess.run(["open", url])


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="uniconverter-app",
        description="Startet die uniconverter App (lokaler Server auf 127.0.0.1 + App-Fenster).")
    p.add_argument("--serve", action="store_true",
                   help="nur den Server im Vordergrund starten, kein Fenster öffnen")
    args = p.parse_args(argv)
    if args.serve:
        return serve()
    port = ensure_server()
    if port is None:
        sys.exit("uniconverter App konnte nicht gestartet werden.")
    open_window(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    main()
