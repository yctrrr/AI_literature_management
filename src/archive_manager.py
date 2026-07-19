from __future__ import annotations

import shutil
from pathlib import Path

from src.models import Candidate, Classification, FetchResult
from src.utils import atomic_write_json, now_iso, unique_path


PENDING_SUMMARY_DIR = "_pending_summary"


class ArchiveManager:
    def __init__(self, category_source: Path, archive_root: Path):
        self.category_source = category_source
        self.archive_root = archive_root
        self.state_dir = archive_root / "_state"
        self.summary_dir = archive_root / "_summaries"
        self.download_dir = archive_root / "_download"
        self.pending_summary_dir = archive_root / PENDING_SUMMARY_DIR

    def ensure_layout(self) -> None:
        self.archive_root.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.pending_summary_dir.mkdir(parents=True, exist_ok=True)
        for category in self.categories():
            (self.archive_root / category).mkdir(parents=True, exist_ok=True)

    def categories(self) -> list[str]:
        if not self.category_source.exists():
            raise FileNotFoundError(f"Category source does not exist: {self.category_source}")
        return sorted([p.name for p in self.category_source.iterdir() if p.is_dir()])

    def staging_dir(self, run_id: str, slug: str) -> Path:
        return self.download_dir

    def finalize_article(self, candidate: Candidate, fetched: FetchResult, classification: Classification) -> Path:
        if classification.category == PENDING_SUMMARY_DIR:
            category = PENDING_SUMMARY_DIR
        else:
            category = classification.category if classification.category in self.categories() else "others"
        category_dir = self.archive_root / category
        category_dir.mkdir(parents=True, exist_ok=True)

        source_pdf = None
        if fetched.pdf_path:
            source_pdf = fetched.pdf_path.resolve()
            pdf_target = (
                fetched.pdf_path
                if source_pdf.parent == category_dir.resolve()
                else unique_path(category_dir / fetched.pdf_path.name)
            )
            if fetched.pdf_path.resolve() != pdf_target.resolve():
                shutil.move(str(fetched.pdf_path), str(pdf_target))
            fetched.pdf_path = pdf_target

        if fetched.attachment_path:
            source_attachment = fetched.attachment_path.resolve()
            attachment_target = (
                fetched.attachment_path
                if source_attachment.parent == category_dir.resolve()
                else unique_path(category_dir / fetched.attachment_path.name)
            )
            if fetched.attachment_path.resolve() != attachment_target.resolve():
                shutil.move(str(fetched.attachment_path), str(attachment_target))
            fetched.attachment_path = attachment_target

        metadata = {
            **fetched.metadata,
            "source_url": candidate.url,
            "keyword": candidate.keyword,
            "category": category,
            "classification": {
                "confidence": classification.confidence,
                "rationale": classification.rationale,
                "status": classification.status,
            },
            "pdf_path": str(fetched.pdf_path) if fetched.pdf_path else "",
            "attachment_path": str(fetched.attachment_path) if fetched.attachment_path else "",
            "updated_at": now_iso(),
        }
        metadata_name = f"{Path(fetched.pdf_path).stem}.metadata.json" if fetched.pdf_path else "metadata.json"
        metadata_path = category_dir / metadata_name
        if not metadata_path.exists() or source_pdf is None or source_pdf.parent != category_dir.resolve():
            metadata_path = unique_path(metadata_path)
        atomic_write_json(metadata_path, metadata)

        return category_dir
