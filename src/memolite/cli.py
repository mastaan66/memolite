"""memolite CLI - health, backup, and skill installer for any LLM CLI."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def _health(args: argparse.Namespace) -> int:
    from memolite import MemoryStore

    store = MemoryStore(args.db)
    import json

    print(json.dumps(store.health_check(), indent=2))
    store.close()
    return 0


def _verify(args: argparse.Namespace) -> int:
    import json

    from memolite import MemoryStore

    store = MemoryStore(args.db)
    print(json.dumps(store.verify_chain(session_id=args.session), indent=2))
    store.close()
    return 0


def _skill_install(args: argparse.Namespace) -> int:
    src = Path(__file__).parent.parent.parent / "skills" / "memolite"
    # fallback when installed via pip, skills may be in package data
    if not src.exists():
        # try package location
        import importlib.resources

        try:
            src = Path(str(importlib.resources.files("memolite").joinpath("../../skills/memolite")))
        except Exception:
            pass
    if not src.exists():
        # last fallback: look next to this file
        src = Path(__file__).parent / "skills" / "memolite"
    if not src.exists():
        print(
            "skill source not found. Expected skills/memolite/SKILL.md next to package.",
            file=sys.stderr,
        )
        return 1

    targets = []
    if args.target in {"all", "opencode"}:
        targets.append(("opencode", Path.home() / ".config" / "opencode" / "skills" / "memolite"))
        # also local project skill if .opencode exists
        if Path(".opencode").exists():
            targets.append(("opencode-local", Path(".opencode") / "skills" / "memolite"))
    if args.target in {"all", "claude"}:
        targets.append(("claude", Path.home() / ".claude" / "skills" / "memolite"))
        # .agents is canonical for many claude installs
        targets.append(("claude-agents", Path.home() / ".agents" / "skills" / "memolite"))
    if args.target in {"all", "cursor"}:
        targets.append(("cursor", Path.home() / ".cursor" / "skills" / "memolite"))
    if args.target in {"all", "windsurf"}:
        targets.append(("windsurf", Path.home() / ".windsurf" / "skills" / "memolite"))
        targets.append(("codeium", Path.home() / ".codeium" / "windsurf" / "skills" / "memolite"))

    if not targets:
        print(
            f"unknown target {args.target}. Choose from all, opencode, claude, cursor, windsurf",
            file=sys.stderr,
        )
        return 1

    for name, dest in targets:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        print(f"installed [{name}] -> {dest}")

    print("done. Verify with: memolite skill status")
    return 0


def _skill_status(args: argparse.Namespace) -> int:
    checks = [
        ("opencode", Path.home() / ".config" / "opencode" / "skills" / "memolite" / "SKILL.md"),
        ("opencode-local", Path(".opencode") / "skills" / "memolite" / "SKILL.md"),
        ("claude", Path.home() / ".claude" / "skills" / "memolite" / "SKILL.md"),
        ("claude-agents", Path.home() / ".agents" / "skills" / "memolite" / "SKILL.md"),
        ("cursor", Path.home() / ".cursor" / "skills" / "memolite" / "SKILL.md"),
        ("windsurf", Path.home() / ".windsurf" / "skills" / "memolite" / "SKILL.md"),
    ]
    for name, p in checks:
        status = "installed" if p.exists() else "not installed"
        print(f"{name:18} {status:15} {p}")
    return 0


def _skill_uninstall(args: argparse.Namespace) -> int:
    targets = []
    if args.target in {"all", "opencode"}:
        targets.append(Path.home() / ".config" / "opencode" / "skills" / "memolite")
        targets.append(Path(".opencode") / "skills" / "memolite")
    if args.target in {"all", "claude"}:
        targets.append(Path.home() / ".claude" / "skills" / "memolite")
        targets.append(Path.home() / ".agents" / "skills" / "memolite")
    if args.target in {"all", "cursor"}:
        targets.append(Path.home() / ".cursor" / "skills" / "memolite")
    if args.target in {"all", "windsurf"}:
        targets.append(Path.home() / ".windsurf" / "skills" / "memolite")
    for p in targets:
        if p.exists():
            shutil.rmtree(p)
            print(f"removed {p}")
        else:
            print(f"not found {p}")
    return 0


def _signal(args: argparse.Namespace) -> int:
    import json

    payload = {
        "name": "memolite",
        "version": "0.1.0",
        "description": "Single file SQLite memory for AI agents. Offline FTS5 hybrid, session aware, thread safe, WAL durable.",
        "install": "pip install memolite",
        "skill": "memolite skill install --all",
        "mcp": 'pip install "memolite[mcp]" && memolite-mcp --db agent.db',
        "quickstart": "from memolite import MemoryStore; s=MemoryStore('agent.db'); s.add_turn(session='s1', role='user', content='hello'); s.recall('hello', session='s1').prompt",
        "adapters": {
            "generic": "from memolite import plug; plug(store, llm='generic').inject(query, session_id)",
            "openai": "from memolite.adapters.openai import OpenAIAdapter; OpenAIAdapter(store).tools",
            "claude": "from memolite.adapters.anthropic import AnthropicAdapter; AnthropicAdapter(store).tools",
            "deepseek": "from memolite.adapters.openai import DeepSeekAdapter",
            "mcp": "memolite-mcp --db agent.db",
        },
        "health": "memolite health --db agent.db",
        "skill_status": "memolite skill status",
        "help": "https://github.com/mastaan66/memolite#readme",
        "skill_path": "skills/memolite/SKILL.md",
        "agents_signal": "AGENTS.md",
        "llms_txt": "llms.txt",
        "service": "local file agent.db, no server, inspectable via sqlite3",
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for k, v in payload.items():
            print(f"{k}: {v}")
    return 0


def _auto_install(args: argparse.Namespace) -> int:
    import json as _j
    import sysconfig

    purelib = sysconfig.get_paths()["purelib"]
    pth = Path(purelib) / "memolite.pth"
    try:
        pth.write_text("import memolite.autoload\n")
    except OSError as e:
        print(f"cannot write {pth}: {e}. Try with sudo or pipx env.", file=sys.stderr)
        return 1
    cfg_path = Path.home() / ".config" / "memolite" / "auto.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(_j.dumps({"db": args.db, "session": args.session}, indent=2))
    print(f"installed {pth}")
    print(f"config {cfg_path}: db={args.db} session={args.session}")
    print("disable anytime: MEMOLITE_OFF=1. remove: memolite autouninstall")
    return 0


def _auto_uninstall(args: argparse.Namespace) -> int:
    import sysconfig

    purelib = sysconfig.get_paths()["purelib"]
    pth = Path(purelib) / "memolite.pth"
    if pth.exists():
        pth.unlink()
        print(f"removed {pth}")
    else:
        print("not installed")
    return 0


def _auto_status(args: argparse.Namespace) -> int:
    import sysconfig

    purelib = sysconfig.get_paths()["purelib"]
    pth = Path(purelib) / "memolite.pth"
    print(f"pth: {pth} {'installed' if pth.exists() else 'not installed'}")
    cfg_path = Path.home() / ".config" / "memolite" / "auto.json"
    print(f"config: {cfg_path} {'exists' if cfg_path.exists() else 'missing'}")
    if cfg_path.exists():
        print(cfg_path.read_text())
    import os as _os

    print(f"kill-switch: MEMOLITE_OFF=1 disables (current={_os.environ.get('MEMOLITE_OFF', '')!r})")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="memolite",
        description="Single file SQLite memory for any LLM. Plug and play as a skill.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("health", help="Health check for agent.db")
    h.add_argument("--db", default="agent.db", help="SQLite path")
    h.set_defaults(func=_health)

    v = sub.add_parser("verify", help="Verify WORM hash-chain")
    v.add_argument("--db", default="agent.db")
    v.add_argument("--session", default=None)
    v.set_defaults(func=_verify)

    sk = sub.add_parser("skill", help="Install as skill for LLM CLIs")
    sk_sub = sk.add_subparsers(dest="skill_cmd", required=True)
    inst = sk_sub.add_parser("install", help="Install skill")
    inst.add_argument(
        "--target",
        default="all",
        choices=["all", "opencode", "claude", "cursor", "windsurf"],
        help="Target CLI",
    )
    inst.set_defaults(func=_skill_install)
    st = sk_sub.add_parser("status", help="Show skill install status")
    st.set_defaults(func=_skill_status)
    un = sk_sub.add_parser("uninstall", help="Uninstall skill")
    un.add_argument(
        "--target", default="all", choices=["all", "opencode", "claude", "cursor", "windsurf"]
    )
    un.set_defaults(func=_skill_uninstall)

    sig = sub.add_parser("signal", help="Signal for agents - how to get serviced")
    sig.add_argument("--json", action="store_true", help="JSON output for agents")
    sig.set_defaults(func=_signal)

    # also support `memolite mcp` alias via separate entry point, but keep here for convenience
    mcp = sub.add_parser("mcp", help="Run MCP server")
    mcp.add_argument("--db", default="agent.db")
    mcp.set_defaults(
        func=lambda a: __import__("memolite.mcp_server", fromlist=["run"]).run(a.db) or 0
    )

    ai = sub.add_parser(
        "autoinstall", help="Auto-patch every Python: all OpenAI/Anthropic calls use memory"
    )
    ai.add_argument("--db", default="agent.db")
    ai.add_argument("--session", default="default")
    ai.set_defaults(func=_auto_install)
    au = sub.add_parser("autouninstall", help="Remove system-wide auto-patch")
    au.set_defaults(func=_auto_uninstall)
    ast = sub.add_parser("autostatus", help="Show auto-patch status")
    ast.set_defaults(func=_auto_status)

    args = p.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
