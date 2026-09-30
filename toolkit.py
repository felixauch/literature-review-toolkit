#!/usr/bin/env python3
"""Review toolkit command line.

    python toolkit.py workspace [--run DIR --port 8799] combined classification, extraction and synthesis
    python toolkit.py handoff --project SLUG --config FILE --out NEW_RUN
    python toolkit.py init <slug> ["Project name"]   create projects/<slug> from the template
    python toolkit.py serve <slug|dir> [--port N]      start the review interface for a project
    python toolkit.py run <stage> <slug|dir> [args…]   run one stage script on a project
    python toolkit.py stages                           list stage ids and scripts
    python toolkit.py check <slug|dir>                 validate project.json
    python toolkit.py projects                         list projects

<slug|dir> is a folder under projects/ or any folder containing project.json.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "toolkit"))
sys.path.insert(0, str(HERE / "toolkit" / "ui"))
from project_config import ConfigError, load_project, validate  # noqa: E402
import runner  # noqa: E402


def resolve(arg: str) -> Path:
    p = Path(arg)
    if (p / "project.json").is_file():
        return p.resolve()
    alt = HERE / "projects" / arg
    if (alt / "project.json").is_file():
        return alt.resolve()
    sys.exit(f"no project.json in {arg!r} or projects/{arg}")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "workspace":
        script = HERE / "toolkit" / "review_workspace" / "start.py"
        sys.exit(subprocess.call([sys.executable, str(script), *args[1:]]))
    if cmd == "handoff":
        script = HERE / "handoff.py"
        sys.exit(subprocess.call([sys.executable, str(script), *args[1:]]))
    if cmd == "init":
        if len(args) < 2:
            sys.exit("usage: toolkit.py init <slug> [name]")
        info = runner.new_project(args[1], args[2] if len(args) > 2 else "")
        print(f"created {info['path']}")
        print("next: copy your exports into exports/, then edit project.json or open the setup page:")
        print(f"      python toolkit.py serve {info['slug']}")
    elif cmd == "serve":
        if len(args) < 2:
            sys.exit("usage: toolkit.py serve <slug|dir> [--port N]")
        root = resolve(args[1])
        cmd_line = [sys.executable, str(HERE / "toolkit" / "ui" / "serve.py"), "--project", str(root), *args[2:]]
        subprocess.call(cmd_line)
    elif cmd == "run":
        if len(args) < 3:
            sys.exit("usage: toolkit.py run <stage> <slug|dir> [args…]")
        stage = next((s for s in runner.STAGES if s["id"] == args[1]), None)
        if not stage:
            sys.exit(f"unknown stage {args[1]!r}; see: toolkit.py stages")
        root = resolve(args[2])
        cmd_line = [sys.executable, str(HERE / "toolkit" / stage["script"]), "--project", str(root), *stage["args"], *args[3:]]
        sys.exit(subprocess.call(cmd_line, cwd=str(root)))
    elif cmd == "stages":
        for s in runner.STAGES:
            net = " [network]" if s["network"] else ""
            print(f"{s['id']:<20} {s['script']} {' '.join(s['args'])}{net}\n{'':<20}   {s['label']}")
    elif cmd == "check":
        if len(args) < 2:
            sys.exit("usage: toolkit.py check <slug|dir>")
        try:
            proj = load_project(resolve(args[1]))
        except ConfigError as exc:
            sys.exit(f"invalid: {exc}")
        problems = validate(proj)
        print(f"{proj.name} ({proj.root})")
        print("\n".join(f"  - {p}" for p in problems) if problems else "  ok")
        sys.exit(1 if problems else 0)
    elif cmd == "projects":
        for p in runner.list_projects():
            print(f"{p['slug']:<28} {p['name']}{'  (frozen)' if p['frozen'] else ''}")
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main()
