#!/usr/bin/env python3
"""Call the authenticated Zotero linked-file import endpoint."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


HEALTH_PATH = "/ai-literature-management/link-import/health"
IMPORT_PATH = "/ai-literature-management/link-import"


def default_config_path() -> Path:
    override = os.environ.get("ZOTERO_LINK_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "ai-literature-management" / "zotero-link-import.json"


def load_config(path: Path | None = None) -> dict:
    config_path = (path or default_config_path()).expanduser()
    if not config_path.is_file():
        raise RuntimeError(
            f"Plugin configuration is missing: {config_path}. Run install_plugin.py first"
        )
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    required = ("token", "base_url", "allowed_root")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError("Plugin configuration is incomplete: " + ", ".join(missing))
    return config


def validate_pdf(path_value: str, root_value: str) -> Path:
    path = Path(path_value).expanduser().resolve(strict=True)
    root = Path(root_value).expanduser().resolve(strict=True)
    try:
        common = os.path.commonpath([os.path.normcase(path), os.path.normcase(root)])
    except ValueError as error:
        raise ValueError("PDF path is outside the allowed literature root") from error
    if common != os.path.normcase(root):
        raise ValueError("PDF path is outside the allowed literature root")
    if not path.is_file() or path.suffix.lower() != ".pdf":
        raise ValueError("Path must point to an existing PDF file")
    return path


def request_json(
    url: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
    timeout: int = 180,
) -> dict:
    headers = {"Accept": "application/json"}
    data = None
    method = "GET"
    if payload is not None:
        method = "POST"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-Zotero-Link-Token"] = token
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"status": "error", "error": "http_error", "message": body.strip()}
        raise RuntimeError(json.dumps(parsed, ensure_ascii=False)) from error
    except urllib.error.URLError as error:
        raise RuntimeError("Zotero or the linked-import plugin is unavailable") from error


def run_health(config: dict) -> dict:
    result = request_json(f"{config['base_url']}{HEALTH_PATH}", timeout=10)
    reported_root = result.get("allowed_root")
    if reported_root and Path(reported_root).resolve() != Path(config["allowed_root"]).resolve():
        raise RuntimeError("Plugin and client allowed roots do not match; reinstall the plugin")
    return result


def run_import(config: dict, args: argparse.Namespace) -> dict:
    path = validate_pdf(args.path, config["allowed_root"])
    payload = {"path": str(path), "collection": args.collection}
    if args.doi:
        payload["doi"] = args.doi
    if args.title:
        payload["title"] = args.title
    return request_json(
        f"{config['base_url']}{IMPORT_PATH}",
        token=config["token"],
        payload=payload,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Link an existing PDF into a named Zotero collection"
    )
    parser.add_argument("--config", type=Path, help="Local plugin client configuration")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("health", help="check whether the Zotero plugin is available")
    import_parser = subparsers.add_parser("import", help="link a PDF into Zotero")
    import_parser.add_argument("--path", required=True, help="absolute path to the PDF")
    import_parser.add_argument("--collection", required=True, help="exact Zotero collection name")
    import_parser.add_argument("--doi", help="DOI used for metadata retrieval and duplicate checks")
    import_parser.add_argument("--title", help="fallback title used for duplicate checks")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        config = load_config(args.config)
        result = run_health(config) if args.command == "health" else run_import(config, args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("status") in {"ok", "created", "reused", "partially_created"} else 1
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
