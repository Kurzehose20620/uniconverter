"""The app's server endpoints and its conversion job, without opening a window."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from uniconverter import app


@pytest.fixture
def server():
    srv = app.make_server()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    app.cleanup()


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


def test_index_serves_the_interface(server):
    status, ctype, body = get(server + "/")
    assert status == 200 and ctype.startswith("text/html")
    assert b"<title>Uniconverter</title>" in body


def test_ping_reports_version(server):
    _, _, body = get(server + "/ping")
    assert json.loads(body) == {"app": "uniconverter", "version": app.APP_VERSION}


def test_targets_for_one_extension(server):
    _, _, body = get(server + "/targets?exts=png")
    data = json.loads(body)
    exts = [t["ext"] for t in data["targets"]]
    assert "jpg" in exts and "pdf" in exts and "png" not in exts
    assert data["mergeable"] is False              # a single file is not a merge


def test_targets_intersection_and_merge(server):
    _, _, body = get(server + "/targets?exts=png,md")
    data = json.loads(body)
    assert [t["ext"] for t in data["targets"]] == ["pdf"]
    assert data["mergeable"] is True


def test_upload_stores_file_with_safe_name(server, fixtures):
    data = (fixtures / "pixel.png").read_bytes()
    req = urllib.request.Request(server + "/upload", data=data, method="POST",
                                 headers={"X-Filename": "../evil/pixel.png"})
    with urllib.request.urlopen(req, timeout=5) as r:
        info = json.load(r)
    assert info["name"] == "pixel.png"
    stored = app.UPLOADS[info["id"]]
    assert stored.read_bytes() == data and stored.is_relative_to(app.UPLOAD_DIR)


def test_unknown_paths_are_404(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server + "/nope")
    assert e.value.code == 404


def test_convert_job_moves_results_to_outdir(fixtures, tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    moved = app.convert_job(fixtures / "pixel.png", "jpg", outdir, app.make_opts({"quality": 70}))
    assert moved == ["pixel.jpg"] and (outdir / "pixel.jpg").exists()
    moved = app.convert_job(fixtures / "pixel.png", "jpg", outdir, app.make_opts({}))
    assert moved == ["pixel-2.jpg"]                # never overwrites, numbers instead


def test_make_opts_clamps_values():
    o = app.make_opts({"quality": 500, "dpi": 10, "ocr_lang": ""})
    assert o.quality == 100 and o.dpi == 50 and o.ocr_lang is None and o.force is True


def test_safe_name_strips_paths_and_control_characters():
    assert app.safe_name("/tmp/../x/report:1.pdf") == "report_1.pdf"
    assert app.safe_name("") == "file"
