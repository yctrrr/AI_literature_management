from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from prepare_endnote_import import DEFAULT_GROUP, export_endnote_import
from src.archive_manager import PENDING_SUMMARY_DIR, ArchiveManager
from src.article_fetcher import ArticleFetcher
from src.models import Candidate, Classification, FetchResult
from src.summary_manager import SummaryManager


def test_pending_queue_and_summary_rebuild(tmp_path: Path) -> None:
    categories = tmp_path / "categories"
    archive_root = tmp_path / "archive"
    (categories / "Energy").mkdir(parents=True)
    (categories / "others").mkdir()
    staging_pdf = tmp_path / "paper.pdf"
    staging_pdf.write_bytes(b"%PDF-test")
    archive = ArchiveManager(categories, archive_root)
    archive.ensure_layout()
    fetched = FetchResult(
        pdf_path=staging_pdf,
        attachment_path=None,
        metadata={"title": "Test Paper", "created_at": datetime.now(timezone.utc).isoformat()},
    )
    candidate = Candidate(
        url="https://example.test/paper",
        title="Test Paper",
        keyword="energy",
        source="test",
    )
    archive.finalize_article(
        candidate,
        fetched,
        Classification(PENDING_SUMMARY_DIR, 0.0, "pending", "pending_summary"),
    )
    assert fetched.pdf_path is not None
    assert fetched.pdf_path.parent.name == PENDING_SUMMARY_DIR

    pending_metadata = next((archive_root / PENDING_SUMMARY_DIR).glob("*.metadata.json"))
    pending = json.loads(pending_metadata.read_text(encoding="utf-8"))
    pending["category"] = "Energy"
    energy_dir = archive_root / "Energy"
    energy_dir.mkdir(exist_ok=True)
    final_pdf = energy_dir / fetched.pdf_path.name
    fetched.pdf_path.replace(final_pdf)
    pending["pdf_path"] = str(final_pdf)
    final_metadata = energy_dir / pending_metadata.name
    final_metadata.write_text(json.dumps(pending), encoding="utf-8")

    manager = SummaryManager(archive_root, archive.categories())
    manager.rebuild_from_archive()
    index = json.loads(manager.index_path.read_text(encoding="utf-8"))
    assert index["categories"]["Energy"][0]["title"] == final_pdf.stem
    assert "## Energy" in manager.summary_path.read_text(encoding="utf-8")


def test_recent_endnote_export_includes_pending_metadata(tmp_path: Path) -> None:
    archive_root = tmp_path / "archive"
    pending = archive_root / PENDING_SUMMARY_DIR
    pending.mkdir(parents=True)
    pdf = pending / "paper.pdf"
    pdf.write_bytes(b"%PDF-test")
    metadata = {
        "title": "Recent Paper",
        "authors": ["Example Author"],
        "year": "2026",
        "doi": "10.1000/example",
        "source_url": "https://example.test/paper",
        "pdf_path": str(pdf),
        "category": PENDING_SUMMARY_DIR,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (pending / "paper.metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )

    result = export_endnote_import(archive_root, DEFAULT_GROUP, since_days=7)
    assert result["records"] == 1
    assert Path(result["latest_ris"]).name == f"{DEFAULT_GROUP}_latest.ris"
    assert "Recent Paper" in Path(result["latest_ris"]).read_text(encoding="utf-8")


def test_attachment_parser_ignores_figure_pages() -> None:
    html = """
    <a href="/articles/example/figures/1">Supplementary figure</a>
    <a href="https://static-content.springer.com/esm/art1.zip">Supplementary files</a>
    """
    selected = ArticleFetcher._find_attachment_url(
        html,
        "https://www.nature.com/articles/example",
    )
    assert selected == "https://static-content.springer.com/esm/art1.zip"
