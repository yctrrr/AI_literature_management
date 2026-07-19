#!/usr/bin/env python3
"""Validate and invoke an AI Literature Management weekly workflow."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ENV = "AI_LITERATURE_PROJECT_ROOT"
CONFIG_ENV = "AI_LITERATURE_CONFIG"
ENTRY_POINTS = ("run_weekly.py", "run_summary.py", "prepare_endnote_import.py")
PATH_ENVIRONMENTS = {
    "library_root": "AI_LITERATURE_LIBRARY_ROOT",
    "category_source": "AI_LITERATURE_CATEGORY_SOURCE",
    "archive_root": "AI_LITERATURE_ARCHIVE_ROOT",
}


def resolve_project_root(explicit: Path | None = None) -> Path:
    value = explicit or (Path(os.environ[PROJECT_ENV]) if os.environ.get(PROJECT_ENV) else None)
    root = (value or Path.cwd()).expanduser().resolve()
    missing = [name for name in ENTRY_POINTS if not (root / name).is_file()]
    if missing:
        raise RuntimeError(
            f"AI Literature Management project not found at {root}; missing: {', '.join(missing)}"
        )
    return root


def resolve_config(project_root: Path, explicit: Path | None = None) -> Path:
    value = explicit or (Path(os.environ[CONFIG_ENV]) if os.environ.get(CONFIG_ENV) else None)
    path = (value or project_root / "config.yaml").expanduser()
    path = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    if not path.is_file():
        raise RuntimeError(f"Initialized configuration not found: {path}")
    return path


def validate_config(path: Path, project_root: Path):
    config_module_path = project_root / "src" / "config.py"
    if not config_module_path.is_file():
        raise RuntimeError(f"Canonical project config loader not found: {config_module_path}")
    module_name = f"_ai_literature_config_{abs(hash(config_module_path))}"
    spec = importlib.util.spec_from_file_location(module_name, config_module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Could not load project config module: {config_module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        config = module.load_config(path)
    finally:
        sys.modules.pop(module_name, None)

    missing_directories = []
    for key in PATH_ENVIRONMENTS:
        directory = getattr(config.paths, key)
        if not directory.is_dir():
            missing_directories.append(f"{key}={directory}")
    if missing_directories:
        raise RuntimeError(
            "Configured directories do not exist: " + ", ".join(missing_directories)
        )
    return config


def require_llm_key(config) -> None:
    variable = str(config.llm.api_key_env or "").strip()
    if not variable:
        raise RuntimeError("Configuration does not define llm.api_key_env")
    if not os.environ.get(variable):
        raise RuntimeError(f"Missing configured LLM API Key environment variable: {variable}")


def add_crawl_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int)
    parser.add_argument("--headless", choices=("true", "false"))
    parser.add_argument("--delay-seconds", type=int)
    parser.add_argument("--skip-search-fallback", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a configured weekly literature workflow")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--python", default=sys.executable, help="Python executable for project commands")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    subparsers.add_parser("check", help="validate project and configuration without network access")
    dry_run = subparsers.add_parser("dry-run", help="discover candidates without downloading")
    add_crawl_options(dry_run)

    crawl = subparsers.add_parser("crawl", help="download new literature after explicit approval")
    add_crawl_options(crawl)
    crawl.add_argument("--confirm-download", action="store_true")
    crawl.add_argument("--summarize", action="store_true")
    crawl.add_argument("--skip-endnote-export", action="store_true")

    summary = subparsers.add_parser("summary", help="process pending summaries")
    summary.add_argument("--limit", type=int)
    summary.add_argument("--rebuild-summary", action="store_true")

    subparsers.add_parser("rebuild", help="rebuild the summary index without crawling")
    endnote = subparsers.add_parser("endnote", help="export EndNote packages")
    endnote.add_argument("--all", dest="all_records", action="store_true")
    endnote.add_argument("--since-days", type=int, default=7)
    endnote.add_argument("--group")
    endnote.add_argument("--output-dir", type=Path)
    return parser


def append_option(command: list[str], name: str, value) -> None:
    if value is not None:
        command.extend([name, str(value)])


def append_crawl_options(command: list[str], args: argparse.Namespace) -> None:
    append_option(command, "--limit", args.limit)
    append_option(command, "--headless", args.headless)
    append_option(command, "--delay-seconds", args.delay_seconds)
    if args.skip_search_fallback:
        command.append("--skip-search-fallback")


def build_command(
    args: argparse.Namespace,
    project_root: Path,
    config_path: Path,
) -> list[str]:
    python = str(args.python)
    if args.operation in {"dry-run", "crawl", "rebuild"}:
        command = [python, str(project_root / "run_weekly.py"), "--config", str(config_path)]
        if args.operation == "dry-run":
            command.append("--dry-run")
            append_crawl_options(command, args)
        elif args.operation == "crawl":
            if not args.confirm_download:
                raise RuntimeError("Live crawl requires --confirm-download after user approval")
            append_crawl_options(command, args)
            if args.summarize:
                command.append("--summarize")
            else:
                command.append("--no-summarize")
            if args.skip_endnote_export:
                command.append("--skip-endnote-export")
        else:
            command.append("--rebuild-summary")
        return command

    if args.operation == "summary":
        command = [python, str(project_root / "run_summary.py"), "--config", str(config_path)]
        append_option(command, "--limit", args.limit)
        if args.rebuild_summary:
            command.append("--rebuild-summary")
        return command

    if args.operation == "endnote":
        command = [
            python,
            str(project_root / "prepare_endnote_import.py"),
            "--config",
            str(config_path),
        ]
        if args.all_records:
            command.append("--all")
        else:
            append_option(command, "--since-days", args.since_days)
        append_option(command, "--group", args.group)
        append_option(command, "--output-dir", args.output_dir)
        return command

    raise RuntimeError(f"Unsupported operation: {args.operation}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        project_root = resolve_project_root(args.project_root)
        config_path = resolve_config(project_root, args.config)
        config = validate_config(config_path, project_root)
        if args.operation == "check":
            print(
                json.dumps(
                    {
                        "status": "ok",
                        "project_root": str(project_root),
                        "config": str(config_path),
                        "entry_points": list(ENTRY_POINTS),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.operation == "summary" or (
            args.operation == "crawl" and args.summarize
        ):
            require_llm_key(config)
        command = build_command(args, project_root, config_path)
        return subprocess.run(command, cwd=project_root, check=False).returncode
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
