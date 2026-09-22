"""CLI entry: magicdub."""

from __future__ import annotations

import argparse
import sys

from magicdub_cli import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="magicdub",
        description="Local video dubbing CLI (no lip-sync).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Create a new task and run the full pipeline.")
    run.add_argument("video", type=str, help="Path to source video file.")
    run.add_argument("--src", required=True, help="Source language code (e.g. en).")
    run.add_argument("--tgt", required=True, help="Target language code (e.g. zh-Hans).")

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "run":
        # Pipeline wired in later milestones; M0 only exposes the CLI surface.
        from magicdub_cli.pipeline.runner import run_pipeline

        return run_pipeline(video=args.video, src_lang=args.src, tgt_lang=args.tgt)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
