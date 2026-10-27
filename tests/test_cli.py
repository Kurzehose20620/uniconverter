"""The uniconverter command: subcommands, batch mode, error messages and exit codes."""

import shutil

import pytest

from uniconverter import __version__, cli


def run(*argv):
    """Run the CLI in-process; returns (exit_code, stdout, stderr-ish message)."""
    try:
        cli.main(list(argv))
    except SystemExit as e:
        return e.code
    return 0


def test_doctor(capsys):
    assert run("doctor") in (0, None)
    out = capsys.readouterr().out
    assert "Built into macOS" in out and "Python libraries" in out and "Programs" in out


def test_formats(capsys):
    run("formats")
    out = capsys.readouterr().out
    assert "Supported conversions" in out
    for family in ("E-books", "Subtitles", "3D", "Xvid-compatible"):
        assert family in out


def test_doctor_lists_the_new_engines(capsys):
    run("doctor")
    out = capsys.readouterr().out
    for name in ("calibre", "ghostscript", "jpeg-xl", "ffprobe", "Blender"):
        assert name in out


def test_dry_run_shows_the_real_file_for_pseudo_targets(tmp_path, capsys):
    src = tmp_path / "song.wav"
    src.write_bytes(b"RIFF")
    assert run(str(src), str(tmp_path / "song.alac"), "-n") == 0
    assert "song.m4a" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    assert e.value.code == 0
    assert f"uniconverter {__version__}" in capsys.readouterr().out


def test_no_arguments_prints_help(capsys):
    assert run() == 0
    assert "usage: uniconverter" in capsys.readouterr().out


def test_single_file(fixtures, tmp_path, capsys):
    dst = tmp_path / "pixel.jpg"
    assert run(str(fixtures / "pixel.png"), str(dst)) == 0
    assert dst.exists() and "✓ pixel.png" in capsys.readouterr().out


def test_missing_output_file_is_a_usage_error(fixtures, capsys):
    assert run(str(fixtures / "pixel.png")) == 2
    assert "output file missing" in capsys.readouterr().err


def test_missing_input_file(tmp_path, capsys):
    assert run(str(tmp_path / "nope.png"), str(tmp_path / "nope.jpg")) == 2
    assert "not found" in capsys.readouterr().err


def test_unsupported_route_exits_1(fixtures, tmp_path, capsys):
    assert run(str(fixtures / "pixel.png"), str(tmp_path / "pixel.mp3")) == 1
    captured = capsys.readouterr()
    assert "is not supported" in captured.err and captured.out == ""


def test_existing_target_needs_force(fixtures, tmp_path, capsys):
    dst = tmp_path / "pixel.jpg"
    dst.write_bytes(b"old")
    assert run(str(fixtures / "pixel.png"), str(dst)) == 1
    assert "already exists" in capsys.readouterr().err
    assert dst.read_bytes() == b"old"
    assert run(str(fixtures / "pixel.png"), str(dst), "--force") == 0
    assert dst.read_bytes() != b"old"


def test_dry_run_shows_engine_and_writes_nothing(fixtures, tmp_path, capsys):
    dst = tmp_path / "pixel.jpg"
    assert run(str(fixtures / "pixel.png"), str(dst), "--dry-run") == 0
    out = capsys.readouterr().out
    assert "pixel.png → " in out and "(Pillow)" in out
    assert not dst.exists()


def test_dry_run_reports_impossible_routes(fixtures, tmp_path, capsys):
    assert run(str(fixtures / "pixel.png"), str(tmp_path / "pixel.mp3"), "-n") == 0
    assert "not possible" in capsys.readouterr().out


def test_dry_run_merge(fixtures, tmp_path, capsys):
    dst = tmp_path / "all.pdf"
    assert run(str(fixtures / "pixel.png"), str(fixtures / "mini.pdf"), str(dst), "-n") == 0
    out = capsys.readouterr().out
    assert "merge 2 files" in out and "(PyMuPDF)" in out and "(as is)" in out
    assert not dst.exists()


def test_verbose_names_the_engine(fixtures, tmp_path, capsys):
    assert run(str(fixtures / "pixel.png"), str(tmp_path / "pixel.jpg"), "-v") == 0
    assert "(Pillow)" in capsys.readouterr().out


def test_batch_with_target_folder(fixtures, tmp_path):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    shutil.copy(fixtures / "pixel.png", a)
    shutil.copy(fixtures / "pixel.png", b)
    out = tmp_path / "web"
    assert run(str(a), str(b), "-t", "webp", "-o", str(out)) == 0
    assert sorted(p.name for p in out.iterdir()) == ["a.webp", "b.webp"]


def test_batch_without_target_folder_writes_next_to_source(fixtures, tmp_path):
    a = tmp_path / "a.png"
    shutil.copy(fixtures / "pixel.png", a)
    assert run(str(a), "-t", "jpg") == 0
    assert (tmp_path / "a.jpg").exists()


def test_several_inputs_need_pdf_target_or_batch_flag(fixtures, tmp_path, capsys):
    args = (str(fixtures / "pixel.png"), str(fixtures / "mini.pdf"), str(tmp_path / "x.png"))
    assert run(*args) == 2
    assert "-t EXT" in capsys.readouterr().err


def test_merge_to_pdf(fixtures, tmp_path, capsys):
    dst = tmp_path / "all.pdf"
    assert run(str(fixtures / "pixel.png"), str(fixtures / "mini.pdf"), str(dst)) == 0
    assert dst.exists() and "2 files" in capsys.readouterr().out


def test_batch_failures_exit_1_but_continue(fixtures, tmp_path, capsys):
    good = tmp_path / "good.png"
    shutil.copy(fixtures / "pixel.png", good)
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    assert run(str(bad), str(good), "-t", "jpg") == 1
    captured = capsys.readouterr()
    assert "[1/2] ✗ bad.png" in captured.err
    assert "[2/2] ✓ good.png" in captured.out and "1 converted, 1 failed" in captured.out
    assert (tmp_path / "good.jpg").exists()


def test_batch_summary(fixtures, tmp_path, capsys):
    a, b = tmp_path / "a.png", tmp_path / "b.png"
    shutil.copy(fixtures / "pixel.png", a)
    shutil.copy(fixtures / "pixel.png", b)
    assert run(str(a), str(b), "-t", "jpg") == 0
    out = capsys.readouterr().out
    assert "[1/2] ✓ a.png" in out and "[2/2] ✓ b.png" in out and "2 converted" in out
