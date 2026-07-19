from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from prepare_endnote_import import DEFAULT_GROUP, export_endnote_import
from src.archive_manager import PENDING_SUMMARY_DIR, ArchiveManager
from src.article_fetcher import ArticleFetcher
from src.models import Candidate, Classification, FetchResult
from src.summary_manager import SummaryManager
import run_summary


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


def test_pending_summary_remains_retryable_after_index_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    categories = tmp_path / "categories"
    archive_root = tmp_path / "archive"
    (categories / "Energy").mkdir(parents=True)
    (categories / "others").mkdir()
    archive = ArchiveManager(categories, archive_root)
    archive.ensure_layout()
    pending_pdf = archive.pending_summary_dir / "paper.pdf"
    pending_pdf.write_bytes(b"%PDF-test")
    pending_metadata = archive.pending_summary_dir / "paper.metadata.json"
    pending_metadata.write_text(
        json.dumps(
            {
                "title": "Retry Paper",
                "source_url": "https://example.test/retry",
                "pdf_path": str(pending_pdf),
            }
        ),
        encoding="utf-8",
    )

    class LLM:
        max_pdf_chars = 100
        category = "Energy"

        @classmethod
        def classify(cls, *_args):
            return Classification(cls.category, 1.0, "match", "classified")

        @staticmethod
        def summarize(*_args):
            return "Summary"

    manager = SummaryManager(archive_root, archive.categories())
    manager.ensure_index()
    original_upsert = manager.upsert_article
    monkeypatch.setattr(run_summary, "extract_pdf_text", lambda *_args, **_kwargs: "text")
    monkeypatch.setattr(manager, "upsert_article", lambda *_args: (_ for _ in ()).throw(OSError("disk")))

    with pytest.raises(OSError, match="disk"):
        run_summary.summarize_pending_article(
            pending_metadata,
            archive,
            archive.categories(),
            LLM(),
            manager,
        )

    assert pending_metadata.exists()
    queued = json.loads(pending_metadata.read_text(encoding="utf-8"))
    assert Path(queued["pdf_path"]).parent.name == "Energy"

    monkeypatch.setattr(manager, "upsert_article", original_upsert)
    run_summary.summarize_pending_article(
        pending_metadata,
        archive,
        archive.categories(),
        LLM(),
        manager,
    )

    assert not pending_metadata.exists()
    assert len(list((archive_root / "Energy").glob("*.pdf"))) == 1
    assert len(list((archive_root / "Energy").glob("*.metadata.json"))) == 1


def test_summary_batch_returns_failure_when_any_article_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    categories = tmp_path / "categories"
    archive_root = tmp_path / "archive"
    (categories / "Energy").mkdir(parents=True)
    monkeypatch.setenv("TEST_LLM_KEY", "test")
    config = SimpleNamespace(
        paths=SimpleNamespace(category_source=categories, archive_root=archive_root),
        llm=SimpleNamespace(api_key_env="TEST_LLM_KEY"),
    )
    pending = [tmp_path / "ok.metadata.json", tmp_path / "bad.metadata.json"]
    monkeypatch.setattr(
        run_summary,
        "parse_args",
        lambda: Namespace(config=None, limit=None, rebuild_summary=False),
    )
    monkeypatch.setattr(run_summary, "load_config", lambda _path: config)
    monkeypatch.setattr(run_summary, "LLMClient", lambda _config: object())
    monkeypatch.setattr(run_summary, "pending_metadata_paths", lambda _root: pending)

    def summarize(metadata_path, *_args):
        if metadata_path.name.startswith("bad"):
            raise OSError("failed article")

    monkeypatch.setattr(run_summary, "summarize_pending_article", summarize)

    assert run_summary.main() == 1


def test_finalize_restores_moved_pdf_when_metadata_write_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    categories = tmp_path / "categories"
    archive_root = tmp_path / "archive"
    (categories / "Energy").mkdir(parents=True)
    (categories / "others").mkdir()
    archive = ArchiveManager(categories, archive_root)
    archive.ensure_layout()
    original_pdf = tmp_path / "paper.pdf"
    original_pdf.write_bytes(b"%PDF-test")
    fetched = FetchResult(original_pdf, None, {"title": "Rollback Paper"})
    candidate = Candidate(
        url="https://example.test/rollback",
        title="Rollback Paper",
        keyword="energy",
        source="test",
    )
    monkeypatch.setattr(
        "src.archive_manager.atomic_write_json",
        lambda *_args: (_ for _ in ()).throw(OSError("metadata write failed")),
    )

    with pytest.raises(OSError, match="metadata write failed"):
        archive.finalize_article(
            candidate,
            fetched,
            Classification("Energy", 1.0, "match", "classified"),
        )

    assert original_pdf.exists()
    assert fetched.pdf_path == original_pdf
    assert not list((archive_root / "Energy").glob("*.pdf"))


def test_pending_summary_recovers_when_queue_marker_update_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    categories = tmp_path / "categories"
    archive_root = tmp_path / "archive"
    (categories / "Energy").mkdir(parents=True)
    (categories / "others").mkdir()
    archive = ArchiveManager(categories, archive_root)
    archive.ensure_layout()
    pending_pdf = archive.pending_summary_dir / "paper.pdf"
    pending_pdf.write_bytes(b"%PDF-test")
    pending_metadata = archive.pending_summary_dir / "paper.metadata.json"
    pending_metadata.write_text(
        json.dumps(
            {
                "title": "Marker Retry Paper",
                "source_url": "https://example.test/marker-retry",
                "pdf_path": str(pending_pdf),
            }
        ),
        encoding="utf-8",
    )

    class LLM:
        max_pdf_chars = 100
        category = "Energy"

        @classmethod
        def classify(cls, *_args):
            return Classification(cls.category, 1.0, "match", "classified")

        @staticmethod
        def summarize(*_args):
            return "Summary"

    manager = SummaryManager(archive_root, archive.categories())
    manager.ensure_index()
    monkeypatch.setattr(run_summary, "extract_pdf_text", lambda *_args, **_kwargs: "text")
    original_marker_write = run_summary.atomic_write_json
    marker_writes = 0

    def fail_final_marker_write(path, value):
        nonlocal marker_writes
        marker_writes += 1
        if marker_writes == 1:
            return original_marker_write(path, value)
        raise OSError("marker write failed")

    monkeypatch.setattr(run_summary, "atomic_write_json", fail_final_marker_write)

    with pytest.raises(OSError, match="marker write failed"):
        run_summary.summarize_pending_article(
            pending_metadata,
            archive,
            archive.categories(),
            LLM(),
            manager,
        )

    assert pending_metadata.exists()
    assert not pending_pdf.exists()
    collision_dir = archive_root / "A-collision"
    collision_dir.mkdir()
    collision_pdf = collision_dir / "paper.pdf"
    collision_pdf.write_bytes(b"%PDF-unrelated")
    (collision_dir / "paper.metadata.json").write_text(
        json.dumps(
            {
                "title": "Marker Retry Paper",
                "source_url": "https://example.test/unrelated",
                "queue_id": "different-queue",
                "pdf_path": str(collision_pdf),
            }
        ),
        encoding="utf-8",
    )
    LLM.category = "others"
    monkeypatch.setattr(run_summary, "atomic_write_json", original_marker_write)
    original_upsert = manager.upsert_article
    monkeypatch.setattr(
        manager,
        "upsert_article",
        lambda *_args: (_ for _ in ()).throw(OSError("index write failed")),
    )

    with pytest.raises(OSError, match="index write failed"):
        run_summary.summarize_pending_article(
            pending_metadata,
            archive,
            archive.categories(),
            LLM(),
            manager,
        )

    queued = json.loads(pending_metadata.read_text(encoding="utf-8"))
    cleanup_path = Path(queued["cleanup_metadata_path"])
    assert cleanup_path.parent.name == "Energy"
    assert list((archive_root / "Energy").glob("*.metadata.json"))

    monkeypatch.setattr(manager, "upsert_article", original_upsert)
    cleanup_metadata = json.loads(cleanup_path.read_text(encoding="utf-8"))
    expected_queue_id = cleanup_metadata["queue_id"]
    cleanup_metadata["queue_id"] = "another-article"
    cleanup_path.write_text(json.dumps(cleanup_metadata), encoding="utf-8")
    LLM.category = "Energy"

    with pytest.raises(ValueError, match="another article"):
        run_summary.summarize_pending_article(
            pending_metadata,
            archive,
            archive.categories(),
            LLM(),
            manager,
        )

    assert cleanup_path.exists()
    queued_after_rejection = json.loads(pending_metadata.read_text(encoding="utf-8"))
    assert Path(queued_after_rejection["pdf_path"]).parent.name == "others"
    assert len(list((archive_root / "others").glob("*.pdf"))) == 1
    cleanup_metadata["queue_id"] = expected_queue_id
    cleanup_path.write_text(json.dumps(cleanup_metadata), encoding="utf-8")
    LLM.category = "others"

    def replace_cleanup_after_upsert(*args):
        original_upsert(*args)
        replaced = json.loads(cleanup_path.read_text(encoding="utf-8"))
        replaced["queue_id"] = "replaced-after-validation"
        cleanup_path.write_text(json.dumps(replaced), encoding="utf-8")

    monkeypatch.setattr(manager, "upsert_article", replace_cleanup_after_upsert)
    with pytest.raises(ValueError, match="another article"):
        run_summary.summarize_pending_article(
            pending_metadata,
            archive,
            archive.categories(),
            LLM(),
            manager,
        )

    assert cleanup_path.exists()
    cleanup_metadata["queue_id"] = expected_queue_id
    cleanup_path.write_text(json.dumps(cleanup_metadata), encoding="utf-8")
    monkeypatch.setattr(manager, "upsert_article", original_upsert)
    run_summary.summarize_pending_article(
        pending_metadata,
        archive,
        archive.categories(),
        LLM(),
        manager,
    )

    assert not pending_metadata.exists()
    assert collision_pdf.exists()
    assert not list((archive_root / "Energy").glob("*.metadata.json"))
    assert len(list((archive_root / "others").glob("*.pdf"))) == 1
    assert len(list((archive_root / "others").glob("*.metadata.json"))) == 1
