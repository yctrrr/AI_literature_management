from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from prepare_zotero_import import (
    export_zotero_plan,
    resolve_archive_root,
    safe_csv_cell,
)


def write_record(
    directory: Path,
    name: str,
    *,
    title: str,
    doi: str,
    source_url: str,
    category: str,
    attachment: bool = False,
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    pdf = directory / f"{name}.pdf"
    pdf.write_bytes(b"%PDF-test")
    attachment_path = directory / f"Supp-{name}.csv"
    if attachment:
        attachment_path.write_text("value\n1\n", encoding="utf-8")
    metadata = {
        "title": title,
        "authors": ["Example Author"],
        "year": "2026",
        "doi": doi,
        "source_url": source_url,
        "category": category,
        "pdf_path": str(pdf),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    metadata_path = directory / f"{name}.metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    return pdf, metadata_path


def test_zotero_plan_includes_only_finalized_records(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    final_pdf, _ = write_record(
        archive / "Energy",
        "energy-paper",
        title="Energy Paper",
        doi="10.1000/energy",
        source_url="https://example.test/energy",
        category="Energy",
        attachment=True,
    )
    write_record(
        archive / "_pending_summary",
        "pending-paper",
        title="Pending Paper",
        doi="10.1000/pending",
        source_url="https://example.test/pending",
        category="_pending_summary",
    )

    result = export_zotero_plan(archive, since_days=None)
    document = json.loads(Path(result["latest_json"]).read_text(encoding="utf-8"))

    assert result["records"] == 1
    assert document["record_count"] == 1
    record = document["records"][0]
    assert record["title"] == "Energy Paper"
    assert record["proposed_collection"] == "Energy"
    assert record["status"] == "ready_for_review"
    assert record["zotero_duplicate_check"] == "not_run"
    assert record["pdf_path"] == str(final_pdf.resolve())
    assert len(record["attachment_paths"]) == 1
    assert "token" not in json.dumps(document).lower()


def test_zotero_plan_writes_csv_and_stable_ids(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "Climate",
        "climate-paper",
        title="Climate Paper",
        doi="10.1000/climate",
        source_url="https://example.test/climate",
        category="Climate",
    )

    first = export_zotero_plan(archive, since_days=None)
    first_document = json.loads(Path(first["latest_json"]).read_text(encoding="utf-8"))
    second = export_zotero_plan(archive, since_days=None)
    second_document = json.loads(Path(second["latest_json"]).read_text(encoding="utf-8"))

    assert first_document["records"][0]["record_id"] == second_document["records"][0]["record_id"]
    assert first["json"] != second["json"]
    with Path(second["latest_csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["proposed_collection"] == "Climate"
    assert rows[0]["zotero_duplicate_check"] == "not_run"


def test_zotero_plan_skips_missing_pdf(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    directory = archive / "Energy"
    directory.mkdir(parents=True)
    (directory / "missing.metadata.json").write_text(
        json.dumps(
            {
                "title": "Missing PDF",
                "doi": "10.1000/missing",
                "category": "Energy",
                "pdf_path": str(directory / "missing.pdf"),
            }
        ),
        encoding="utf-8",
    )

    result = export_zotero_plan(archive, since_days=None)

    assert result["records"] == 0


def test_zotero_plan_prefers_finalized_duplicate_over_pending(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "_pending_summary",
        "pending-copy",
        title="Same Paper",
        doi="10.1000/same",
        source_url="https://example.test/same",
        category="_pending_summary",
    )
    write_record(
        archive / "Final Category",
        "final-copy",
        title="Same Paper",
        doi="10.1000/same",
        source_url="https://example.test/same",
        category="stale-category-value",
    )

    result = export_zotero_plan(archive, since_days=None)
    document = json.loads(Path(result["latest_json"]).read_text(encoding="utf-8"))

    assert result["records"] == 1
    assert document["records"][0]["proposed_collection"] == "Final Category"


def test_zotero_plan_normalizes_doi_before_deduplication(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "Energy",
        "first",
        title="First Copy",
        doi="10.1000/ABC",
        source_url="https://example.test/first",
        category="Energy",
    )
    write_record(
        archive / "Climate",
        "second",
        title="Second Copy",
        doi=" https://doi.org/10.1000/abc ",
        source_url="https://example.test/second",
        category="Climate",
    )

    result = export_zotero_plan(archive, since_days=None)
    document = json.loads(Path(result["latest_json"]).read_text(encoding="utf-8"))

    assert result["records"] == 1
    assert len({record["record_id"] for record in document["records"]}) == 1


def test_zotero_plan_excludes_archive_root_metadata(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive,
        "root-paper",
        title="Root Paper",
        doi="10.1000/root",
        source_url="https://example.test/root",
        category="not-finalized",
    )

    result = export_zotero_plan(archive, since_days=None)

    assert result["records"] == 0


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_zotero_plan_neutralizes_csv_formula_prefixes(prefix: str) -> None:
    value = prefix + "dangerous"
    assert safe_csv_cell(value) == "'" + value


def test_archive_only_config_ignores_zotero_settings(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "paths": {"archive_root": "./archive"},
                "zotero": {"enabled": True, "allowed_root": ""},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    assert resolve_archive_root(config_path=config) == archive.resolve()
