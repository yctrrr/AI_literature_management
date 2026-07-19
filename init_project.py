from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path
from typing import Callable

import yaml


InputFn = Callable[[str], str]


def prompt_value(input_fn: InputFn, label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input_fn(f"{label}{suffix}: ").strip()
    return value or default


def prompt_bool(input_fn: InputFn, label: str, default: bool = False) -> bool:
    default_text = "Y/n" if default else "y/N"
    while True:
        value = input_fn(f"{label} [{default_text}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Enter y or n.")


def collect_interactive(input_fn: InputFn = input) -> dict:
    library_root = prompt_value(input_fn, "Main literature library root")
    category_source = prompt_value(input_fn, "Category source directory")
    archive_root = prompt_value(input_fn, "Automated archive directory")
    use_profile = prompt_bool(input_fn, "Use a persistent browser profile", False)
    browser_profile = (
        prompt_value(input_fn, "Browser profile directory", "./.browser_profile")
        if use_profile
        else ""
    )
    zotero_enabled = prompt_bool(input_fn, "Enable Zotero linked-file integration", False)
    zotero_root = (
        prompt_value(input_fn, "Zotero linked-file allowed root", library_root)
        if zotero_enabled
        else ""
    )
    return {
        "library_root": library_root,
        "category_source": category_source,
        "archive_root": archive_root,
        "browser_profile": browser_profile,
        "zotero_enabled": zotero_enabled,
        "zotero_allowed_root": zotero_root,
        "llm_provider": prompt_value(input_fn, "LLM provider", "openai-compatible"),
        "llm_model": prompt_value(input_fn, "LLM model", "your-model"),
        "llm_base_url": prompt_value(input_fn, "LLM base URL", ""),
        "llm_api_key_env": prompt_value(input_fn, "LLM API key environment variable", "LLM_API_KEY"),
    }


def initialize_project(output: Path, values: dict, template_path: Path) -> Path:
    output = output.expanduser().resolve()
    template_path = template_path.expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Configuration already exists: {output}")
    config = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
    base = output.parent

    library_root = resolve_user_path(base, values["library_root"])
    category_source = resolve_user_path(base, values["category_source"])
    archive_root = resolve_user_path(base, values["archive_root"])
    if not library_root.is_dir():
        raise ValueError(f"Literature library root does not exist: {library_root}")
    if not category_source.is_dir():
        raise ValueError(f"Category source directory does not exist: {category_source}")
    if paths_overlap(category_source, archive_root):
        raise ValueError("Category source and archive root must not contain each other")
    archive_root.mkdir(parents=True, exist_ok=True)
    ensure_writable_directory(archive_root)

    api_key_env = str(values["llm_api_key_env"]).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env):
        raise ValueError(f"Invalid API key environment variable name: {api_key_env}")

    config["paths"] = {
        "library_root": str(library_root),
        "category_source": str(category_source),
        "archive_root": str(archive_root),
    }
    browser_profile = str(values.get("browser_profile") or "").strip()
    config["browser"] = {
        **(config.get("browser") or {}),
        "use_chrome_profile": bool(browser_profile),
        "user_data_dir": str(resolve_user_path(base, browser_profile)) if browser_profile else "",
    }
    zotero_enabled = bool(values.get("zotero_enabled", False))
    zotero_root_value = str(values.get("zotero_allowed_root") or "").strip()
    if zotero_enabled and not zotero_root_value:
        raise ValueError("Zotero allowed root is required when Zotero is enabled")
    zotero_root = resolve_user_path(base, zotero_root_value) if zotero_root_value else None
    if zotero_root is not None and not zotero_root.is_dir():
        raise ValueError(f"Zotero allowed root does not exist: {zotero_root}")
    config["zotero"] = {
        "enabled": zotero_enabled,
        "allowed_root": str(zotero_root) if zotero_root else "",
    }
    config["llm"] = {
        **(config.get("llm") or {}),
        "provider": str(values["llm_provider"]).strip(),
        "model": str(values["llm_model"]).strip(),
        "base_url": str(values.get("llm_base_url") or "").strip(),
        "api_key_env": api_key_env,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise
    return output


def resolve_user_path(base: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def paths_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def ensure_writable_directory(path: Path) -> None:
    descriptor, temp_name = tempfile.mkstemp(prefix=".write-test-", dir=path)
    os.close(descriptor)
    Path(temp_name).unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Initialize AI Literature Management")
    parser.add_argument("--output", type=Path, default=Path("config.yaml"))
    parser.add_argument("--template", type=Path, default=Path(__file__).with_name("config.example.yaml"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        output = initialize_project(args.output, collect_interactive(), args.template)
    except (FileExistsError, OSError, KeyError, ValueError) as error:
        print(f"ERROR: {error}")
        return 1
    print(f"Created configuration: {output}")
    print("Secrets were not stored. Set the configured API key environment variable before summary runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
