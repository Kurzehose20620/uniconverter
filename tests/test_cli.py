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
    assert "Supported conversions" in capsys.readouterr().out


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


def test_missing_output_file_is_a_usage_error(fixtures):
    code = run(str(fixtures / "pixel.png"))
    assert isinstance(code, str) and "output file missing" in code


def test_missing_input_file(tmp_path):
    code = run(str(tmp_path / "nope.png"), str(tmp_path / "nope.jpg"))
    assert isinstance(code, str) and "not found" in code


def test_unsupported_route_exits_1(fixtures, tmp_path, capsys):
    assert run(str(fixtures / "pixel.png"), str(tmp_path / "pixel.mp3")) == 1
    assert "is not supported" in capsys.readouterr().out


def test_existing_target_needs_force(fixtures, tmp_path, capsys):
    dst = tmp_path / "pixel.jpg"
    dst.write_bytes(b"old")
    assert run(str(fixtures / "pixel.png"), str(dst)) == 1
    assert "already exists" in capsys.readouterr().out
    assert dst.read_bytes() == b"old"
    assert run(str(fixtures / "pixel.png"), str(dst), "--force") == 0
    assert dst.read_bytes() != b"old"


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


def test_several_inputs_need_pdf_target_or_batch_flag(fixtures, tmp_path):
    code = run(str(fixtures / "pixel.png"), str(fixtures / "mini.pdf"), str(tmp_path / "x.png"))
    assert isinstance(code, str) and "-t EXT" in code


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
    out = capsys.readouterr().out
    assert "✗ bad.png" in out and "✓ good.png" in out
    assert (tmp_path / "good.jpg").exists()
