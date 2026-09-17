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
