"""uniconverter app – local drag-and-drop interface in its own window.

A small web server listens on 127.0.0.1 only; the interface (app.html) runs
in a native WebKit window (pywebview), no browser needed. Files are handed
to the server, converted and saved to Downloads or the Desktop. Nothing
leaves the machine.

`uniconverter-app` opens the window; the server stops when the window closes.
`uniconverter-app --serve` runs just the server (to open it in a browser).
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

from . import __version__
from . import router as core

APP_NAME = "Uniconverter"
APP_VERSION = __version__
PORT_RANGE = range(8756, 8766)
HTML_FILE = files(__package__).joinpath("app.html")
ICON_FILE = files(__package__).joinpath("Uniconverter.icns")

UPLOAD_DIR = None     # created by make_server()
UPLOADS = {}          # id -> Path
UPLOAD_LOCK = threading.Lock()
UPLOAD_SEQ = [0]
PRODUCED = set()      # paths the app created (for "show in Finder")
CONVERT_LOCK = threading.Lock()   # LibreOffice & co. prefer running one at a time

OUTDIRS = {
    "downloads": Path.home() / "Downloads",
    "desktop": Path.home() / "Desktop",
}

LABELS = {
    "jpg": "JPG · image", "jpeg": "JPEG · image", "png": "PNG · image",
    "webp": "WebP · image", "heic": "HEIC · image", "tiff": "TIFF · image",
    "tif": "TIFF · image", "bmp": "BMP · image", "gif": "GIF", "avif": "AVIF · image",
    "ico": "ICO · icon", "pdf": "PDF", "md": "Markdown", "txt": "Text",
    "html": "HTML", "docx": "DOCX · Word", "doc": "DOC · Word",
    "odt": "ODT · OpenDocument", "rtf": "RTF", "mp3": "MP3 · audio",
    "m4a": "M4A · audio", "wav": "WAV · audio", "aiff": "AIFF · audio",
    "caf": "CAF · audio", "flac": "FLAC · audio", "ogg": "OGG · audio",
    "mp4": "MP4 · video", "mov": "MOV · video", "mkv": "MKV · video",
    "webm": "WebM · video", "avi": "AVI · video",
}


def safe_name(name):
    name = Path(name).name
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip() or "file"
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
    """Convert one file; move everything it produced into outdir."""
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
        # take along image folders created by pdf→md --extract-images
        for d in sorted(p for p in Path(td).iterdir() if p.is_dir()):
            final = unique_path(outdir / d.name)
            shutil.move(str(d), str(final))
            moved.append(final.name + "/")
        return moved


def merge_job(sources, outdir: Path, opts):
    with tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as td:
        name = Path(sources[0]).stem + "-merged.pdf" if len(sources) else "merged.pdf"
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
            self._send(404, {"error": "not found"})

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
                self._send(404, {"error": "not found"})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _upload(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 2 * 1024 ** 3:
            return self._send(413, {"error": "file larger than 2 GB"})
        raw_name = urllib.parse.unquote(self.headers.get("X-Filename", "file"))
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
            return self._send(400, {"error": "no files or no target format"})

        results = []
        with CONVERT_LOCK:
            if payload.get("merge") and target == "pdf" and len(sources) > 1:
                try:
                    files_ = merge_job(sources, outdir, opts)
                    results.append({"name": f"{len(sources)} files",
                                    "ok": True, "files": files_})
                except Exception as e:
                    results.append({"name": f"{len(sources)} files",
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
            self._send(403, {"error": "unknown file"})


# ---------------------------------------------------------------- Server

def make_server():
    """Bind the server to the first free port on 127.0.0.1 and create the upload folder."""
    global UPLOAD_DIR
    for port in PORT_RANGE:
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    else:
        sys.exit("No free port found.")
    UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="uniconverter-app-"))
    return server


def cleanup():
    global UPLOAD_DIR
    if UPLOAD_DIR:
        shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    UPLOAD_DIR = None


def serve():
    """Run only the server in the foreground (browser variant, tests)."""
    server = make_server()
    print(f"uniconverter app running at http://127.0.0.1:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


# ---------------------------------------------------------------- App window

def _brand_process():
    """Present the process as "Uniconverter": name in menu bar and Dock, Dock icon.

    Started from a venv the process would otherwise be called "Python". The
    Uniconverter.app built by install.sh brings name and icon itself.
    """
    try:
        from AppKit import NSApplication, NSBundle, NSImage
    except ImportError:
        return
    NSBundle.mainBundle().infoDictionary()["CFBundleName"] = APP_NAME
    icon = NSImage.alloc().initWithContentsOfFile_(str(ICON_FILE))
    if icon is not None:
        NSApplication.sharedApplication().setApplicationIconImage_(icon)


def run_window():
    """Server in a background thread, interface in its own window; closing it ends both."""
    try:
        import webview
    except ImportError:
        sys.exit("pywebview is missing – install with: pipx inject uniconverter pywebview\n"
                 "Without a window: uniconverter-app --serve  (then open the URL in a browser)")
    server = make_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    _brand_process()
    webview.create_window(APP_NAME, url, width=640, height=760, min_size=(520, 600))
    try:
        webview.start()
    finally:
        server.shutdown()
        cleanup()


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="uniconverter-app",
        description="Uniconverter as an app: drag-and-drop window, local server on 127.0.0.1 only.")
    p.add_argument("--serve", action="store_true",
                   help="no window, just run the server in the foreground (prints the URL)")
    p.add_argument("--version", action="version", version=f"uniconverter {__version__}")
    args = p.parse_args(argv)
    if args.serve:
        return serve()
    run_window()


if __name__ == "__main__":
    main()
