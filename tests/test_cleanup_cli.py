from pathlib import Path

import pathlib

from gp_data.main import run_cli


def test_cleanup_removes_legacy(tmp_path: Path, capsys):
    # create fake files in temp dir
    csv = tmp_path / "data.csv"
    csv.write_text("foo")
    bak = tmp_path / "data.csv.bak"
    bak.write_text("bar")
    pre = tmp_path / "data.csv.pre_restore.bak"
    pre.write_text("baz")
    old = tmp_path / "old.csv"
    old.write_text("qux")

    run_cli(["cleanup", "--path", str(tmp_path)])
    out = capsys.readouterr().out
    assert "removed:" in out
    for f in (csv, bak, pre, old):
        assert not f.exists()


def test_cleanup_nothing(tmp_path: Path, capsys):
    run_cli(["cleanup", "--path", str(tmp_path)])
    out = capsys.readouterr().out
    assert "nothing to clean" in out


def test_cleanup_reports_files_it_cannot_remove(tmp_path: Path, capsys, monkeypatch):
    csv = tmp_path / "data.csv"
    csv.write_text("foo")

    original_unlink = pathlib.Path.unlink

    def fake_unlink(path: Path, *args, **kwargs):
        if path == csv:
            raise PermissionError("locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "unlink", fake_unlink)

    run_cli(["cleanup", "--path", str(tmp_path)])
    captured = capsys.readouterr()

    assert "unable to remove:" in captured.err
    assert str(csv) in captured.err
    assert csv.exists()
