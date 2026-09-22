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
        version=f"magicdub-cli {__version__}",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="Create a new task and run the full pipeline.")
    run.add_argument("video", type=str, help="Path to source video file.")
    run.add_argument("--src", required=True, help="Source language code (e.g. en).")
    run.add_argument("--tgt", required=True, help="Target language code (e.g. zh-Hans).")

    update = sub.add_parser(
        "update",
        help="Reinstall this tool from GitHub via uv (upgrade / refresh).",
    )
    update.add_argument(
        "--ref",
        default=None,
        help="Git ref to install (tag/branch/sha). Default: MAGICDUB_REF or latest GitHub Release.",
    )
    update.add_argument(
        "--repo-url",
        default=None,
        help="Git repo URL. Default: MAGICDUB_REPO_URL or official GitHub URL.",
    )

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
        from magicdub_cli.pipeline.runner import run_pipeline

        return run_pipeline(video=args.video, src_lang=args.src, tgt_lang=args.tgt)

    if args.command == "update":
        from magicdub_cli.self_update import run_update

        return run_update(ref=args.ref, repo_url=args.repo_url)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
