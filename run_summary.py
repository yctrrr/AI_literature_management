from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from src.archive_manager import PENDING_SUMMARY_DIR, ArchiveManager
from src.config import default_config_path, load_config
from src.llm import LLMClient
from src.models import Candidate, FetchResult
from src.pdf_utils import extract_pdf_text
from src.summary_manager import SummaryManager
from src.utils import JsonlLogger, atomic_write_json, now_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify and summarize pending crawled literature.")
    parser.add_argument("--config", type=Path, default=None, help="Initialized project configuration")
    parser.add_argument("--limit", type=int, default=None, help="Maximum pending articles to summarize")
    parser.add_argument("--rebuild-summary", action="store_true", help="Rebuild summary index after summarizing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config or default_config_path())
    if not os.environ.get(config.llm.api_key_env):
        print(
            f"Missing {config.llm.api_key_env}; summary task requires an LLM API key.",
            file=sys.stderr,
        )
        return 2

    archive = ArchiveManager(config.paths.category_source, config.paths.archive_root)
    archive.ensure_layout()
    categories = archive.categories()
    summary_manager = SummaryManager(config.paths.archive_root, categories)
    llm = LLMClient(config.llm)
    run_logger = JsonlLogger(config.paths.archive_root / "_state" / "run_log.jsonl")
    run_id = now_iso().replace(":", "-")
    run_logger.write({"event": "summary_run_start", "run_id": run_id})

    pending_paths = pending_metadata_paths(config.paths.archive_root)
    if args.limit is not None:
        pending_paths = pending_paths[: args.limit]

    completed = 0
    failed = 0
    for metadata_path in pending_paths:
        try:
            summarize_pending_article(metadata_path, archive, categories, llm, summary_manager)
            completed += 1
            print(f"DONE: {metadata_path.name}")
        except Exception as exc:
            failed += 1
            run_logger.write(
                {
                    "event": "summary_article_failed",
                    "run_id": run_id,
                    "metadata_path": str(metadata_path),
                    "error": str(exc),
                }
            )
            print(f"FAILED: {metadata_path} ({exc})")

    if args.rebuild_summary:
        summary_manager.rebuild_from_archive()

    run_logger.write(
        {
            "event": "summary_run_complete",
            "run_id": run_id,
            "completed": completed,
            "failed": failed,
        }
    )
    return 1 if failed else 0


def pending_metadata_paths(archive_root: Path) -> list[Path]:
    pending_dir = archive_root / PENDING_SUMMARY_DIR
    if not pending_dir.exists():
        return []
    return sorted(pending_dir.glob("*.metadata.json"), key=lambda path: path.stat().st_mtime)


def summarize_pending_article(
    metadata_path: Path,
    archive: ArchiveManager,
    categories: list[str],
    llm: LLMClient,
    summary_manager: SummaryManager,
) -> None:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    pdf_path = resolve_pdf_path(metadata, metadata_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"Missing PDF for metadata: {metadata_path}")

    candidate = Candidate(
        url=metadata.get("source_url", ""),
        title=metadata.get("title") or pdf_path.stem,
        keyword=metadata.get("keyword", ""),
        source="pending_summary",
        published=metadata.get("published", ""),
        doi=metadata.get("doi", ""),
    )
    text_excerpt = extract_pdf_text(pdf_path, max_chars=llm.max_pdf_chars)
    classification = llm.classify(candidate, metadata, text_excerpt, categories)
    summary_text = llm.summarize(candidate, metadata, text_excerpt, classification)

    fetched = FetchResult(
        pdf_path=pdf_path,
        attachment_path=resolve_attachment_path(metadata),
        metadata=metadata,
    )
    summary_manager.ensure_index()
    archive.finalize_article(candidate, fetched, classification)
    metadata["pdf_path"] = str(fetched.pdf_path) if fetched.pdf_path else ""
    metadata["attachment_path"] = str(fetched.attachment_path) if fetched.attachment_path else ""
    atomic_write_json(metadata_path, metadata)
    summary_manager.upsert_article(fetched, classification, summary_text)
    metadata_path.unlink(missing_ok=True)


def resolve_pdf_path(metadata: dict, metadata_path: Path) -> Path:
    pdf_path = Path(metadata.get("pdf_path") or "")
    if pdf_path.is_file():
        return pdf_path
    sibling = metadata_path.with_name(metadata_path.name[: -len(".metadata.json")] + ".pdf")
    return sibling


def resolve_attachment_path(metadata: dict) -> Path | None:
    attachment_path = Path(metadata.get("attachment_path") or "")
    if attachment_path.is_file():
        return attachment_path
    return None


if __name__ == "__main__":
    raise SystemExit(main())
