from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
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
    if not metadata.get("queue_id"):
        metadata["queue_id"] = uuid.uuid4().hex
        atomic_write_json(metadata_path, metadata)
    validated_cleanup_metadata_path(metadata, metadata_path)
    recovered_metadata_path = None
    pdf_path = resolve_pdf_path(metadata, metadata_path)
    if not pdf_path.is_file():
        recovered = find_finalized_metadata(metadata, metadata_path)
        if recovered:
            recovered_metadata_path, recovered_metadata = recovered
            metadata.update(recovered_metadata)
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
    if (
        recovered_metadata_path
        and recovered_metadata_path.parent.resolve() != fetched.pdf_path.parent.resolve()
    ):
        metadata["cleanup_metadata_path"] = str(recovered_metadata_path)
    cleanup_metadata_path = validated_cleanup_metadata_path(metadata, metadata_path)
    if (
        cleanup_metadata_path
        and cleanup_metadata_path.parent.resolve() == fetched.pdf_path.parent.resolve()
    ):
        metadata.pop("cleanup_metadata_path", None)
        cleanup_metadata_path = None
    atomic_write_json(metadata_path, metadata)
    summary_manager.upsert_article(fetched, classification, summary_text)
    if cleanup_metadata_path:
        cleanup_metadata_path.unlink(missing_ok=True)
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


def find_finalized_metadata(metadata: dict, pending_path: Path) -> tuple[Path, dict] | None:
    archive_root = pending_path.parent.parent
    queue_id = str(metadata.get("queue_id") or "").strip()
    doi = str(metadata.get("doi") or "").strip().lower()
    source_url = str(metadata.get("source_url") or "").strip()
    title = str(metadata.get("title") or "").strip()
    candidates: list[tuple[Path, dict]] = []
    for candidate_path in sorted(archive_root.glob("*/*.metadata.json")):
        if candidate_path.parent.name.startswith("_"):
            continue
        try:
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidate_pdf = Path(candidate.get("pdf_path") or "")
        if not candidate_pdf.is_file():
            continue
        candidates.append((candidate_path, candidate))

    matchers = [
        lambda item: bool(queue_id and str(item[1].get("queue_id") or "") == queue_id),
        lambda item: bool(
            doi and str(item[1].get("doi") or "").strip().lower() == doi
        ),
        lambda item: bool(
            source_url
            and str(item[1].get("source_url") or "").strip() == source_url
        ),
        lambda item: bool(
            title
            and item[0].name == pending_path.name
            and str(item[1].get("title") or "").strip() == title
        ),
    ]
    for matcher in matchers:
        matches = [item for item in candidates if matcher(item)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


def validated_cleanup_metadata_path(metadata: dict, pending_path: Path) -> Path | None:
    value = str(metadata.get("cleanup_metadata_path") or "").strip()
    if not value:
        return None
    cleanup_path = Path(value).resolve()
    archive_root = pending_path.parent.parent.resolve()
    if (
        archive_root not in cleanup_path.parents
        or not cleanup_path.name.endswith(".metadata.json")
        or cleanup_path.parent.name.startswith("_")
    ):
        raise ValueError("Invalid pending metadata cleanup path")
    if cleanup_path.is_file():
        try:
            cleanup_metadata = json.loads(cleanup_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Pending metadata cleanup target is unreadable") from error
        queue_id = str(metadata.get("queue_id") or "").strip()
        target_queue_id = str(cleanup_metadata.get("queue_id") or "").strip()
        doi = str(metadata.get("doi") or "").strip().lower()
        target_doi = str(cleanup_metadata.get("doi") or "").strip().lower()
        source_url = str(metadata.get("source_url") or "").strip()
        target_source_url = str(cleanup_metadata.get("source_url") or "").strip()
        same_queue = bool(queue_id and target_queue_id and queue_id == target_queue_id)
        same_legacy_identity = bool(
            not target_queue_id
            and ((doi and doi == target_doi) or (source_url and source_url == target_source_url))
        )
        if not same_queue and not same_legacy_identity:
            raise ValueError("Pending metadata cleanup target belongs to another article")
    return cleanup_path


if __name__ == "__main__":
    raise SystemExit(main())
