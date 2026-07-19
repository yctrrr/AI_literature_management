from __future__ import annotations

import json
from pathlib import Path

from src.models import Candidate, Classification, FetchResult
from src.archive_manager import PENDING_SUMMARY_DIR
from src.utils import JsonlLogger, read_jsonl


class StateManager:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.archive_root = state_dir.parent
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.processed_path = self.state_dir / "processed_articles.jsonl"
        self.pending_path = self.state_dir / "pending_no_pdf.jsonl"
        self.filtered_path = self.state_dir / "filtered_articles.jsonl"
        self.failures_path = self.state_dir / "failed_downloads.jsonl"
        self._processed = read_jsonl(self.processed_path)
        self._filtered = read_jsonl(self.filtered_path)
        self.processed_logger = JsonlLogger(self.processed_path)
        self.pending_logger = JsonlLogger(self.pending_path)
        self.filtered_logger = JsonlLogger(self.filtered_path)
        self.failure_logger = JsonlLogger(self.failures_path)
        self._archived = self._scan_archive()

    def is_processed(self, doi: str, url: str) -> bool:
        for row in self._processed:
            if doi and row.get("doi") == doi:
                return True
            if url and row.get("url") == url:
                return True
        for row in self._filtered:
            if doi and row.get("doi") == doi:
                return True
            if url and row.get("url") == url:
                return True
        for row in self._archived:
            if doi and row.get("doi") == doi:
                return True
            if url and row.get("url") == url:
                return True
        return False

    def write_processed(
        self,
        candidate: Candidate,
        fetched: FetchResult,
        classification: Classification,
        article_dir: Path,
        summary_status: str,
    ) -> None:
        row = {
            "doi": candidate.doi or fetched.metadata.get("doi", ""),
            "url": candidate.url,
            "title": candidate.title,
            "keyword": candidate.keyword,
            "category": classification.category,
            "classification_confidence": classification.confidence,
            "classification_status": classification.status,
            "summary_status": summary_status,
            "article_dir": str(article_dir),
            "pdf_path": str(fetched.pdf_path) if fetched.pdf_path else "",
            "attachment_path": str(fetched.attachment_path) if fetched.attachment_path else "",
        }
        self.processed_logger.write(row)
        self._processed.append(row)
        self._archived.append(row)

    def write_pending_no_pdf(self, candidate: Candidate, metadata: dict, reason: str) -> None:
        self.pending_logger.write(
            {
                "doi": candidate.doi or metadata.get("doi", ""),
                "url": candidate.url,
                "title": candidate.title,
                "keyword": candidate.keyword,
                "reason": reason,
                "metadata": metadata,
            }
        )

    def write_filtered(self, candidate: Candidate, metadata: dict, reason: str) -> None:
        row = {
            "doi": candidate.doi or metadata.get("doi", ""),
            "url": candidate.url,
            "title": metadata.get("title") or candidate.title,
            "keyword": candidate.keyword,
            "reason": reason,
            "journal": metadata.get("journal", ""),
            "required_term": metadata.get("journal_filter_required_term", ""),
        }
        self.filtered_logger.write(row)
        self._filtered.append(row)

    def write_failure(self, candidate: Candidate, error_type: str, message: str) -> None:
        self.failure_logger.write(
            {
                "doi": candidate.doi,
                "url": candidate.url,
                "title": candidate.title,
                "keyword": candidate.keyword,
                "error_type": error_type,
                "message": message,
            }
        )

    def _scan_archive(self) -> list[dict]:
        rows: list[dict] = []
        if not self.archive_root.exists():
            return rows
        for metadata_path in self.archive_root.glob("*/*.metadata.json"):
            if metadata_path.parent.name.startswith("_") and metadata_path.parent.name != PENDING_SUMMARY_DIR:
                continue
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            rows.append(
                {
                    "doi": metadata.get("doi", ""),
                    "url": metadata.get("source_url", ""),
                    "pdf_path": metadata.get("pdf_path", ""),
                }
            )
        return rows
