import json
import tempfile
from pathlib import Path

from memolite.cli import main as cli_main


def test_cli_health_and_signal(capsys) -> None:
    import sys

    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "a.db"
        sys.argv = ["memolite", "health", "--db", str(db)]
        try:
            cli_main()
        except SystemExit as e:
            assert e.code == 0
        out = capsys.readouterr().out
        assert "integrity_ok" in out or "integrity" in out

        # signal json
        sys.argv = ["memolite", "signal", "--json"]
        try:
            cli_main()
        except SystemExit as e:
            assert e.code == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["name"] == "memolite"
        assert "install" in data

        # signal plain
        sys.argv = ["memolite", "signal"]
        try:
            cli_main()
        except SystemExit as e:
            assert e.code == 0
        out = capsys.readouterr().out
        assert "memolite" in out


def test_cli_skill_status(capsys) -> None:
    import sys

    sys.argv = ["memolite", "skill", "status"]
    try:
        cli_main()
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "opencode" in out


def test_cli_skill_install_and_uninstall(monkeypatch) -> None:
    import sys

    with tempfile.TemporaryDirectory() as tmp_home:
        monkeypatch.setattr(Path, "home", lambda: Path(tmp_home))
        sys.argv = ["memolite", "skill", "install", "--target", "opencode"]
        try:
            cli_main()
        except SystemExit as e:
            assert e.code == 0
        assert (
            Path(tmp_home) / ".config" / "opencode" / "skills" / "memolite" / "SKILL.md"
        ).exists()
        sys.argv = ["memolite", "skill", "uninstall", "--target", "opencode"]
        try:
            cli_main()
        except SystemExit as e:
            assert e.code == 0
        assert not (Path(tmp_home) / ".config" / "opencode" / "skills" / "memolite").exists()


def test_cli_auto_install_status_uninstall(monkeypatch, tmp_path, capsys) -> None:
    import sys
    import sysconfig

    from memolite.cli import main as cli_main

    fake_pure = tmp_path / "site"
    fake_pure.mkdir()
    monkeypatch.setattr(sysconfig, "get_paths", lambda: {"purelib": str(fake_pure)})
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    sys.argv = ["memolite", "autoinstall", "--db", str(tmp_path / "a.db"), "--session", "s1"]
    try:
        cli_main()
    except SystemExit as e:
        assert e.code == 0
    assert (fake_pure / "memolite.pth").exists()
    sys.argv = ["memolite", "autostatus"]
    try:
        cli_main()
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "installed" in out
    sys.argv = ["memolite", "autouninstall"]
    try:
        cli_main()
    except SystemExit as e:
        assert e.code == 0
    assert not (fake_pure / "memolite.pth").exists()


def test_cli_verify(tmp_path, capsys) -> None:
    import sys

    from memolite import MemoryStore
    from memolite.cli import main as cli_main

    db = str(tmp_path / "v.db")
    s = MemoryStore(db)
    s.add_turn(session="s1", role="user", content="hi")
    s.close()
    sys.argv = ["memolite", "verify", "--db", db]
    try:
        cli_main()
    except SystemExit as e:
        assert e.code == 0
    out = capsys.readouterr().out
    assert "ok" in out
