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


def get(url, token=True, origin=None):
    headers = {"X-Token": app.TOKEN} if token else {}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=5) as r:
        return r.status, r.headers, r.read()


def status_of(url, **kw):
    try:
        return get(url, **kw)[0]
    except urllib.error.HTTPError as e:
        return e.code


def test_index_serves_the_interface_with_the_token(server):
    status, headers, body = get(server + "/?token=" + app.TOKEN, token=False)
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b"<title>Uniconverter</title>" in body
    assert app.TOKEN.encode() in body and b"__TOKEN__" not in body
    assert headers["Cache-Control"] == "no-store"


def test_index_without_token_is_forbidden(server):
    assert status_of(server + "/", token=False) == 403
    assert status_of(server + "/?token=wrong", token=False) == 403


def test_api_needs_the_token(server):
    assert status_of(server + "/targets?exts=png", token=False) == 403
    assert status_of(server + "/targets?exts=png") == 200


def test_foreign_origin_is_rejected(server):
    assert status_of(server + "/targets?exts=png", origin="http://evil.example") == 403
    assert status_of(server + "/targets?exts=png", origin=server) == 200


def test_post_without_token_is_forbidden(server):
    req = urllib.request.Request(server + "/shutdown", data=b"", method="POST")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 403


def test_ping_reports_version(server):
    _, _, body = get(server + "/ping", token=False)     # the only endpoint without token
    assert json.loads(body) == {"app": "uniconverter", "version": app.APP_VERSION}


def test_targets_for_one_extension(server):
    _, _, body = get(server + "/targets?exts=png")
    data = json.loads(body)
    targets = {t["ext"]: t for t in data["targets"]}
    assert "jpg" in targets and "pdf" in targets
    assert "jpeg" not in targets                   # no alias extensions
    # the own format is offered too, so a picture can be made smaller
    assert targets["png"]["label"].endswith("(same format)")
    assert targets["jpg"]["kind"] == "image" and targets["pdf"]["kind"] == "other"
    assert data["mergeable"] is False              # a single file is not a merge


def test_targets_intersection_and_merge(server):
    _, _, body = get(server + "/targets?exts=png,md")
    data = json.loads(body)
    assert [t["ext"] for t in data["targets"]] == ["pdf"]
    assert data["mergeable"] is True


def test_upload_stores_file_with_safe_name(server, fixtures):
    data = (fixtures / "pixel.png").read_bytes()
    req = urllib.request.Request(server + "/upload", data=data, method="POST",
                                 headers={"X-Filename": "../evil/pixel.png",
                                          "X-Token": app.TOKEN})
    with urllib.request.urlopen(req, timeout=5) as r:
        info = json.load(r)
    assert info["name"] == "pixel.png"
    stored = app.UPLOADS[info["id"]]
    assert stored.read_bytes() == data and stored.is_relative_to(app.UPLOAD_DIR)


def test_unknown_paths_are_404(server):
    with pytest.raises(urllib.error.HTTPError) as e:
        get(server + "/nope")
    assert e.value.code == 404


def test_tokens_differ_per_server():
    first = app.make_server()
    t1 = app.TOKEN
    first.server_close()
    app.cleanup()
    second = app.make_server()
    t2 = app.TOKEN
    second.server_close()
    app.cleanup()
    assert t1 != t2 and len(t1) >= 32


def test_convert_job_moves_results_to_outdir(fixtures, tmp_path):
    outdir = tmp_path / "out"
    outdir.mkdir()
    moved = app.convert_job(fixtures / "pixel.png", "jpg", outdir, app.make_opts({"quality": 70}))
    assert moved == ["pixel.jpg"] and (outdir / "pixel.jpg").exists()
    moved = app.convert_job(fixtures / "pixel.png", "jpg", outdir, app.make_opts({}))
    assert moved == ["pixel-2.jpg"]                # never overwrites, numbers instead


def test_targets_kinds_for_media(server, monkeypatch):
    from uniconverter.engines import tools
    if not tools.FFMPEG:
        pytest.skip("no ffmpeg")
    _, _, body = get(server + "/targets?exts=mov")
    targets = {t["ext"]: t["kind"] for t in json.loads(body)["targets"]}
    assert targets["mp4"] == "video" and targets["mp3"] == "audio" and targets["gif"] == "image"
    assert targets["mov"] == "video"               # same format: shrink a video


def test_make_opts_clamps_values():
    o = app.make_opts({"quality": 500, "dpi": 10, "ocr_lang": ""})
    assert o.quality == 100 and o.dpi == 50 and o.ocr_lang is None and o.force is True
    assert o.max is None and o.small is False and o.target_size is None


def test_make_opts_size_options():
    assert app.make_opts({"max": 800, "small": True}).max == 800
    assert app.make_opts({"max": 800}).small is False
    assert app.make_opts({"max": 3}).max == 16               # clamped
    assert app.make_opts({"max": "x"}).max is None
    assert app.make_opts({"video_size": "720"}).max == 1280  # 720p = 1280×720
    assert app.make_opts({"video_size": "1080"}).max == 1920
    assert app.make_opts({"video_size": "bogus"}).max is None


def test_convert_job_shrinks_into_the_same_format(tmp_path):
    from PIL import Image
    src = tmp_path / "photo.jpg"
    Image.new("RGB", (1200, 800), (200, 30, 30)).save(src)
    outdir = tmp_path / "out"
    outdir.mkdir()
    moved = app.convert_job(src, "jpg", outdir, app.make_opts({"max": 600, "small": True}))
    assert moved == ["photo-small.jpg"]
    assert Image.open(outdir / "photo-small.jpg").size == (600, 400)


def test_interface_has_the_size_options(server):
    _, _, body = get(server + "/?token=" + app.TOKEN, token=False)
    for marker in (b'id="vsize"', b'id="isize"', b'id="small"', b"video_size"):
        assert marker in body


def test_safe_name_strips_paths_and_control_characters():
    assert app.safe_name("/tmp/../x/report:1.pdf") == "report_1.pdf"
    assert app.safe_name("") == "file"
