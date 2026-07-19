from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from prepare_endnote_import import DEFAULT_GROUP, export_endnote_import
from src.archive_manager import PENDING_SUMMARY_DIR, ArchiveManager
from src.article_fetcher import ArticleFetcher
from src.config import default_config_path, load_config
from src.llm import LLMClient
from src.models import Classification
from src.pdf_utils import extract_pdf_text
from src.source_discovery import SourceDiscovery
from src.state_manager import StateManager
from src.summary_manager import SummaryManager
from src.utils import JsonlLogger, now_iso


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Weekly Nature literature crawler")
    parser.add_argument("--config", type=Path, default=None, help="Initialized project configuration")
    parser.add_argument("--dry-run", action="store_true", help="Discover only; do not download or call OpenAI")
    parser.add_argument("--limit", type=int, default=None, help="Maximum new candidate articles to process")
    parser.add_argument("--headless", choices=["true", "false"], default=None, help="Override browser headless mode")
    parser.add_argument("--delay-seconds", type=int, default=None, help="Override request delay for this run")
    parser.add_argument("--summarize", action="store_true", help="Classify and summarize during crawl. Requires LLM API key.")
    parser.add_argument("--no-summarize", action="store_true", help="Deprecated; crawl only and leave new PDFs pending summary")
    parser.add_argument("--rebuild-summary", action="store_true", help="Rebuild categorized summary without crawling")
    parser.add_argument("--skip-search-fallback", action="store_true", help="Disable /search fallback for this run")
    parser.add_argument("--skip-endnote-export", action="store_true", help="Do not refresh EndNote RIS/ENW import files")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config or default_config_path())
    if args.headless is not None:
        config.browser.headless = args.headless == "true"
    if args.skip_search_fallback:
        config.nature.search_fallback = False
    if args.delay_seconds is not None:
        config.nature.delay_seconds = args.delay_seconds

    archive = ArchiveManager(config.paths.category_source, config.paths.archive_root)
    archive.ensure_layout()
    summary_manager = SummaryManager(config.paths.archive_root, archive.categories())
    if args.rebuild_summary:
        summary_manager.rebuild_from_archive()
        print(f"Rebuilt summary: {summary_manager.summary_path}")
        return 0

    state = StateManager(config.paths.archive_root / "_state")
    run_logger = JsonlLogger(config.paths.archive_root / "_state" / "run_log.jsonl")

    run_id = now_iso().replace(":", "-")
    run_logger.write({"event": "run_start", "run_id": run_id, "dry_run": args.dry_run})

    discovery = SourceDiscovery(config.nature)
    summarize = (args.summarize or config.llm.summarize_by_default) and not args.no_summarize
    candidates = discovery.discover(config.keywords)
    unprocessed_candidates = [c for c in candidates if not state.is_processed(c.doi, c.url)]
    process_limit = args.limit or config.download.max_articles_per_run

    print(
        f"Discovered {len(candidates)} candidates; "
        f"{len(unprocessed_candidates)} unprocessed candidates before journal filtering."
    )

    if not args.dry_run and summarize and not os.environ.get(config.llm.api_key_env):
        message = f"Missing {config.llm.api_key_env}; aborting before downloads because summarization is enabled."
        run_logger.write({"event": "run_aborted", "run_id": run_id, "reason": "missing_llm_api_key"})
        print(message, file=sys.stderr)
        return 2

    fetcher = ArticleFetcher(config)
    llm = LLMClient(config.llm)
    run_mode = "full"

    try:
        with fetcher:
            new_candidates = select_journal_candidates(fetcher, state, unprocessed_candidates, process_limit)
            print(
                f"Selected {len(new_candidates)} journal-matched candidates "
                f"for limit {process_limit}."
            )
            if args.dry_run:
                run_mode = "dry_run"
                for idx, candidate in enumerate(new_candidates, 1):
                    print(f"{idx}. [{candidate.keyword}] {candidate.title} - {candidate.url}")
                run_logger.write(
                    {"event": "run_complete", "run_id": run_id, "mode": "dry_run", "selected": len(new_candidates)}
                )
                return 0
            for candidate in new_candidates:
                process_candidate(candidate, archive, state, fetcher, llm, summary_manager, summarize, run_id)
    finally:
        if run_mode != "dry_run":
            run_logger.write({"event": "run_complete", "run_id": run_id, "mode": run_mode})

    if not args.skip_endnote_export:
        try:
            export_result = export_endnote_import(config.paths.archive_root, DEFAULT_GROUP, since_days=7)
        except Exception as exc:
            run_logger.write({"event": "endnote_export_failed", "run_id": run_id, "error": str(exc)})
            print(f"ENDNOTE EXPORT FAILED: {exc}", file=sys.stderr)
            return 3
        run_logger.write(
            {
                "event": "endnote_export_complete",
                "run_id": run_id,
                "records": export_result["records"],
                "since_days": export_result["since_days"],
                "ris": str(export_result["ris"]),
                "enw": str(export_result["enw"]),
                "manifest": str(export_result["manifest"]),
                "attachment_report": str(export_result["attachment_report"]),
            }
        )

    return 0


def select_journal_candidates(fetcher, state, candidates, limit: int) -> list:
    selected = []
    for candidate in candidates:
        if len(selected) >= limit:
            break
        try:
            inspected = fetcher.inspect(candidate)
        except Exception as exc:
            state.write_failure(candidate, "prefilter_error", str(exc))
            print(f"PREFILTER FAILED: {candidate.url} ({exc})")
            continue

        if inspected.error == "journal_filtered":
            state.write_filtered(candidate, inspected.metadata, inspected.error)
            print(
                "FILTERED: "
                f"{candidate.url} "
                f"(journal '{inspected.metadata.get('journal', '')}' does not contain "
                f"'{inspected.metadata.get('journal_filter_required_term', '')}')"
            )
            continue
        if inspected.error:
            state.write_failure(candidate, "prefilter_error", inspected.error)
            print(f"PREFILTER FAILED: {candidate.url} ({inspected.error})")
            continue
        selected.append(candidate)
    return selected


def process_candidate(candidate, archive, state, fetcher, llm, summary_manager, summarize: bool, run_id: str) -> None:
    staging_dir = archive.staging_dir(run_id, "")
    staging_dir.mkdir(parents=True, exist_ok=True)
    try:
        fetched = fetcher.fetch(candidate, staging_dir)
    except Exception as exc:
        state.write_failure(candidate, "fetch_error", str(exc))
        print(f"FETCH FAILED: {candidate.url} ({exc})")
        return

    if not fetched.pdf_path:
        if fetched.error == "journal_filtered":
            state.write_filtered(candidate, fetched.metadata, fetched.error)
            print(
                "FILTERED: "
                f"{candidate.url} "
                f"(journal '{fetched.metadata.get('journal', '')}' does not contain "
                f"'{fetched.metadata.get('journal_filter_required_term', '')}')"
            )
            return
        state.write_pending_no_pdf(candidate, fetched.metadata, fetched.error or "no_pdf")
        print(f"NO PDF: {candidate.url}")
        return

    try:
        text_excerpt = extract_pdf_text(fetched.pdf_path, max_chars=llm.max_pdf_chars)
    except Exception as exc:
        text_excerpt = ""
        fetched.metadata["pdf_text_error"] = str(exc)
        state.write_failure(candidate, "pdf_text_error", str(exc))
        print(f"PDF TEXT FAILED: {candidate.url} ({exc})")
    categories = archive.categories()
    if summarize:
        classification = llm.classify(candidate, fetched.metadata, text_excerpt, categories)
    else:
        classification = Classification(
            PENDING_SUMMARY_DIR,
            0.0,
            "Crawl-only run; pending standalone summary/classification.",
            "pending_summary",
        )
    article_dir = archive.finalize_article(candidate, fetched, classification)

    summary_text = ""
    summary_status = "skipped"
    if summarize:
        try:
            summary_text = llm.summarize(candidate, fetched.metadata, text_excerpt, classification)
            summary_manager.upsert_article(fetched, classification, summary_text)
            summary_status = "completed"
        except Exception as exc:
            summary_status = "failed"
            state.write_failure(candidate, "summary_error", str(exc))
            print(f"SUMMARY FAILED: {candidate.url} ({exc})")

    state.write_processed(candidate, fetched, classification, article_dir, summary_status)
    print(f"DONE: {classification.category} - {candidate.title}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        raise SystemExit(130)
