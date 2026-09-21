import argparse
import json
from pathlib import Path

from .config import profile_named, read_config
from .labels import render, to_zpl
from .worker import run, runtime_path


def main():
    parser = argparse.ArgumentParser(description="Feishu Base → Zebra label printer (Windows)")
    parser.add_argument("--config", default="config.local.json")
    sub = parser.add_subparsers(dest="command", required=True)
    preview = sub.add_parser("preview", help="Render a sample without Feishu access or printing")
    preview.add_argument("--profile", required=True)
    preview.add_argument("--input", required=True, help="JSON object with the queue field names")
    preview.add_argument("--output", required=True, help="PNG file path; sibling ZPL is also generated")
    worker = sub.add_parser("run", help="Consume queues and print; this is not a dry run")
    worker.add_argument("--once", action="store_true")
    sub.add_parser("stop", help="Request graceful stop; current network/spool operation may finish")
    sub.add_parser("resume", help="Remove STOP marker; does not start a worker")
    editor = sub.add_parser("editor", help="Open the local visual template editor; does not print")
    editor.add_argument("--port", type=int, default=8765)
    editor.add_argument("--templates-dir", default="templates")
    editor.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if args.command == "editor":
        from .editor import editor_config, serve
        serve(editor_config(args.config),args.templates_dir,args.port,not args.no_browser)
        return
    config = read_config(args.config)
    if args.command == "preview":
        profile = profile_named(config, args.profile)
        row = json.loads(Path(args.input).read_text(encoding="utf-8-sig"))
        image = render(config, profile, [row.get(f, "") for f in profile["fields"]])
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        output.with_suffix(".zpl").write_bytes(to_zpl(image))
        print(f"Preview saved: {output}; no printing performed")
    elif args.command == "run":
        run(config, once=args.once)
    else:
        marker = runtime_path(config) / "STOP"
        marker.parent.mkdir(parents=True, exist_ok=True)
        if args.command == "stop":
            marker.write_text("stop", encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)
