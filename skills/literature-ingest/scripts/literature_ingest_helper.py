#!/usr/bin/env python3
"""Local helper for the literature-ingest skill.

The script intentionally handles only deterministic local work: folder scanning,
duplicate detection, filename planning, and downloading explicit file URLs.
Metadata discovery remains with the calling agent because publisher pages vary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path


TEXT_EXTS = {".pdf", ".html", ".htm", ".txt", ".md", ".ris", ".bib"}
ATTACHMENT_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz", ".csv", ".xlsx", ".xls", ".docx", ".pptx"}
SCAN_EXTS = TEXT_EXTS | ATTACHMENT_EXTS


def configured_root(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    environment_root = os.environ.get("AI_LITERATURE_LIBRARY_ROOT")
    if environment_root:
        return Path(environment_root).expanduser().resolve()
    config_value = os.environ.get("AI_LITERATURE_CONFIG")
    config_paths = (
        [Path(config_value).expanduser()] if config_value else [
            Path(__file__).resolve().parent.parent / "config.local.json",
            Path.cwd() / "config.yaml",
        ]
    )
    for config_path in config_paths:
        if not config_path.is_file():
            continue
        if config_path.suffix.lower() == ".json":
            raw = json.loads(config_path.read_text(encoding="utf-8")) or {}
        else:
            try:
                import yaml
            except ImportError as error:
                raise RuntimeError(
                    "PyYAML is required to read project config; pass --root or set "
                    "AI_LITERATURE_LIBRARY_ROOT"
                ) from error
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        value = (raw.get("paths") or {}).get("library_root")
        if value:
            root = Path(str(value)).expanduser()
            return root.resolve() if root.is_absolute() else (config_path.parent / root).resolve()
    raise RuntimeError(
        "Literature root is not configured. Pass --root, set "
        "AI_LITERATURE_LIBRARY_ROOT, or initialize the project."
    )


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"https?://", "", value)
    value = re.sub(r"doi\.org/", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def safe_name(value: str, max_len: int = 120) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    if not value:
        return "untitled"
    return value[:max_len].rstrip(" .")


def short_title(title: str, max_words: int = 10) -> str:
    words = re.findall(r"[A-Za-z0-9]+", title)
    if not words:
        return "Untitled"
    return " ".join(words[:max_words])


def categories(root: Path) -> list[str]:
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir()], key=str.lower)


def iter_candidate_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in SCAN_EXTS:
            files.append(path)
    return files


def duplicate_candidates(root: Path, title: str, doi: str | None, source_url: str | None, limit: int = 20) -> list[dict]:
    title_norm = normalize_text(title)
    doi_norm = normalize_text(doi)
    source_norm = normalize_text(source_url)
    scored: list[dict] = []

    for path in iter_candidate_files(root):
        rel = str(path.relative_to(root))
        name_norm = normalize_text(path.stem)
        haystack = normalize_text(rel)
        score = 0.0
        reasons: list[str] = []

        if doi_norm and doi_norm in haystack:
            score = max(score, 1.0)
            reasons.append("doi")
        if source_norm:
            source_parts = [part for part in source_norm.split() if len(part) >= 5]
            if source_parts and any(part in haystack for part in source_parts[-4:]):
                score = max(score, 0.72)
                reasons.append("source-url-slug")
        if title_norm:
            ratio = SequenceMatcher(None, title_norm, name_norm).ratio()
            if ratio >= 0.55:
                score = max(score, ratio)
                reasons.append("similar-title")
            title_words = set(w for w in title_norm.split() if len(w) > 3)
            name_words = set(name_norm.split())
            if title_words:
                overlap = len(title_words & name_words) / max(len(title_words), 1)
                if overlap >= 0.45:
                    overlap_score = 0.55 + (overlap * 0.25)
                    score = max(score, min(overlap_score, 0.82))
                    reasons.append("title-word-overlap")

        if score >= 0.55:
            stat = path.stat()
            scored.append(
                {
                    "path": str(path),
                    "relative_path": rel,
                    "score": round(score, 3),
                    "reasons": sorted(set(reasons)),
                    "size_bytes": stat.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                }
            )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def planned_stem(title: str, year: str | None, first_author: str | None) -> str:
    parts = []
    if year:
        parts.append(year)
    if first_author:
        parts.append(first_author)
    parts.append(short_title(title))
    return safe_name(" - ".join(parts), 150)


def parse_file_url(value: str) -> tuple[str, str]:
    if "=" in value:
        label, url = value.split("=", 1)
        return safe_name(label.strip(), 40), url.strip()
    return "file", value.strip()


def extension_from_url(url: str, default: str = ".pdf") -> str:
    parsed = urllib.parse.urlparse(url)
    ext = Path(urllib.parse.unquote(parsed.path)).suffix
    if ext and re.fullmatch(r"\.[A-Za-z0-9]{1,8}", ext):
        return ext
    return default


def download_url(url: str, dest: Path, overwrite: bool = False) -> dict:
    if dest.exists() and not overwrite:
        return {"path": str(dest), "status": "exists", "size_bytes": dest.stat().st_size}

    req = urllib.request.Request(url, headers={"User-Agent": "literature-ingest/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"path": str(dest), "status": "downloaded", "size_bytes": len(data)}


def cmd_inspect(args: argparse.Namespace) -> int:
    root = configured_root(args.root)
    cats = categories(root)
    target = root / args.category if args.category else None
    result = {
        "root": str(root),
        "root_exists": root.exists(),
        "categories": cats,
        "requested_category": args.category,
        "target_dir": str(target) if target else None,
        "target_exists": target.exists() if target else None,
        "suggested_stem": planned_stem(args.title, args.year, args.first_author),
        "duplicates": duplicate_candidates(root, args.title, args.doi, args.source_url, args.limit),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    target_dir = Path(args.target_dir)
    stem = planned_stem(args.title, args.year, args.first_author)
    urls = [parse_file_url(item) for item in args.file_url]
    grouped = len(urls) > 1 or args.group_folder
    base_dir = target_dir / stem if grouped else target_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    downloads = []
    for index, (label, url) in enumerate(urls, start=1):
        ext = extension_from_url(url)
        if grouped:
            filename = safe_name(f"{index:02d} - {label}") + ext
        else:
            filename = stem + ext
        dest = base_dir / filename
        downloads.append(download_url(url, dest, args.overwrite))

    manifest = {
        "title": args.title,
        "year": args.year,
        "first_author": args.first_author,
        "source_url": args.source_url,
        "target_dir": str(target_dir),
        "base_dir": str(base_dir),
        "downloads": downloads,
    }
    if args.write_manifest:
        manifest_path = base_dir / "literature-ingest-manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and download literature files.")
    sub = parser.add_subparsers(dest="command", required=True)

    inspect = sub.add_parser("inspect", help="Scan topic folders and find duplicate candidates.")
    inspect.add_argument("--root")
    inspect.add_argument("--title", required=True)
    inspect.add_argument("--doi")
    inspect.add_argument("--source-url")
    inspect.add_argument("--category")
    inspect.add_argument("--year")
    inspect.add_argument("--first-author")
    inspect.add_argument("--limit", type=int, default=20)
    inspect.set_defaults(func=cmd_inspect)

    download = sub.add_parser("download", help="Download explicit file URLs after user confirmation.")
    download.add_argument("--target-dir", required=True)
    download.add_argument("--title", required=True)
    download.add_argument("--year")
    download.add_argument("--first-author")
    download.add_argument("--source-url")
    download.add_argument("--file-url", action="append", required=True, help="URL or label=URL. Repeat for attachments.")
    download.add_argument("--group-folder", action="store_true")
    download.add_argument("--overwrite", action="store_true")
    download.add_argument("--write-manifest", action="store_true")
    download.set_defaults(func=cmd_download)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
