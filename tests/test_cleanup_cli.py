from pathlib import Path

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
