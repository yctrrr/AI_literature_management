#!/usr/bin/env python3
"""Locate literature files and likely attachments by fuzzy filename matching."""

from __future__ import annotations

import argparse
import json
import os
import re
from difflib import SequenceMatcher
from pathlib import Path


DEFAULT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".ris",
    ".enw",
    ".enl",
    ".csv",
    ".txt",
    ".md",
}
ATTACHMENT_PREFIX_RE = re.compile(
    r"^(supp|supplement|supplementary|supporting|si|appendix|appendices|"
    r"esm|extended\s+data|additional\s+file)[\s._\-\u2013\u2014]*",
    re.IGNORECASE,
)


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


def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[_\-\u2013\u2014]+", " ", text)
    text = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_attachment_prefix(text: str) -> str:
    previous = text
    current = ATTACHMENT_PREFIX_RE.sub("", text).strip()
    while current != previous:
        previous = current
        current = ATTACHMENT_PREFIX_RE.sub("", current).strip()
    return current


def is_attachment(path: Path) -> bool:
    return bool(ATTACHMENT_PREFIX_RE.match(normalize(path.stem)))


def tokens(text: str) -> set[str]:
    return {token for token in normalize(text).split() if len(token) > 1}


def score(query: str, candidate: str) -> float:
    query_normalized = normalize(query)
    candidate_normalized = normalize(candidate)
    if not query_normalized or not candidate_normalized:
        return 0.0
    query_tokens = tokens(query)
    candidate_tokens = tokens(candidate)
    token_score = (
        len(query_tokens & candidate_tokens) / len(query_tokens) if query_tokens else 0.0
    )
    sequence_score = SequenceMatcher(
        None, query_normalized, candidate_normalized
    ).ratio()
    substring_bonus = 0.15 if query_normalized in candidate_normalized else 0.0
    return min(1.0, 0.65 * token_score + 0.35 * sequence_score + substring_bonus)


def iter_files(root: Path, extensions: set[str]):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


def format_match(rank: int, match_score: float, path: Path, root: Path) -> str:
    relative_parent = path.parent.relative_to(root) if path.parent != root else Path(".")
    return "\n".join(
        [
            f"{rank}. score={match_score:.3f}",
            f"   title: {path.stem}",
            f"   type: {path.suffix.lower()}",
            f"   topic: {relative_parent}",
            f"   path: {path}",
        ]
    )


def find_attachments(
    primary_path: Path,
    all_paths: list[Path],
    limit: int,
    threshold: float,
):
    primary_base = strip_attachment_prefix(primary_path.stem)
    candidates = []
    for path in all_paths:
        if path == primary_path or not is_attachment(path):
            continue
        attachment_base = strip_attachment_prefix(path.stem)
        match_score = score(primary_base, attachment_base)
        if path.parent == primary_path.parent:
            match_score += 0.20
        if path.suffix.lower() == primary_path.suffix.lower():
            match_score += 0.03
        match_score = min(1.0, match_score)
        if match_score >= threshold:
            candidates.append((match_score, path))
    candidates.sort(
        key=lambda item: (item[0], item[1].parent == primary_path.parent),
        reverse=True,
    )
    return candidates[:limit]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find likely literature files in a configured local library."
    )
    parser.add_argument("query", help="Paper title, author-year fragment, or filename keywords")
    parser.add_argument("--root", help="Literature root directory")
    parser.add_argument("--limit", type=int, default=5, help="Number of matches to return")
    parser.add_argument(
        "--attachments",
        type=int,
        default=5,
        help="Likely attachments to show for the best main match",
    )
    parser.add_argument(
        "--attachment-threshold",
        type=float,
        default=0.70,
        help="Minimum fuzzy score for supplemental attachment matches",
    )
    parser.add_argument(
        "--extensions",
        default=",".join(sorted(DEFAULT_EXTENSIONS)),
        help="Comma-separated file extensions to search",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = configured_root(args.root)
    except RuntimeError as error:
        print(f"ERROR: {error}")
        return 2
    if not root.exists():
        print(f"ERROR: root does not exist: {root}")
        return 2

    extensions = {
        value if value.startswith(".") else f".{value}"
        for value in (item.strip().lower() for item in args.extensions.split(","))
        if value
    }
    all_paths = list(iter_files(root, extensions))
    main_matches = []
    attachment_matches = []
    for path in all_paths:
        match_score = score(args.query, f"{path.stem} {path.parent.name}")
        if match_score <= 0:
            continue
        target = attachment_matches if is_attachment(path) else main_matches
        target.append((match_score, path))

    main_matches.sort(key=lambda item: (item[0], -len(str(item[1]))), reverse=True)
    attachment_matches.sort(key=lambda item: (item[0], -len(str(item[1]))), reverse=True)
    if not main_matches:
        main_matches = attachment_matches
    main_matches = main_matches[: max(1, args.limit)]
    if not main_matches:
        print("No matching literature files found.")
        return 1

    print("Main matches")
    print("============")
    for rank, (match_score, path) in enumerate(main_matches, start=1):
        print(format_match(rank, match_score, path, root))

    if args.attachments > 0:
        attachments = find_attachments(
            main_matches[0][1],
            all_paths,
            args.attachments,
            args.attachment_threshold,
        )
        if attachments:
            print("\nLikely attachments for best main match")
            print("======================================")
            for rank, (match_score, path) in enumerate(attachments, start=1):
                print(format_match(rank, match_score, path, root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
