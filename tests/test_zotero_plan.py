from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

import prepare_zotero_import
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
    assert rows[0]["plan_id"] == second_document["plan_id"]


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


def test_zotero_plan_normalizes_mixed_case_doi_prefix(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "Energy",
        "first",
        title="First Copy",
        doi="DOI: 10.1000/ABC",
        source_url="https://example.test/first",
        category="Energy",
    )
    write_record(
        archive / "Climate",
        "second",
        title="Second Copy",
        doi="10.1000/abc",
        source_url="https://example.test/second",
        category="Climate",
    )

    result = export_zotero_plan(archive, since_days=None)

    assert result["records"] == 1


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


def test_root_duplicate_cannot_shadow_finalized_record(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive,
        "000-root-copy",
        title="Unfinalized Copy",
        doi="10.1000/shadow",
        source_url="https://example.test/shadow",
        category="not-finalized",
    )
    write_record(
        archive / "Energy",
        "final-copy",
        title="Finalized Copy",
        doi="10.1000/shadow",
        source_url="https://example.test/shadow",
        category="Energy",
    )

    result = export_zotero_plan(archive, since_days=None)
    document = json.loads(Path(result["latest_json"]).read_text(encoding="utf-8"))

    assert result["records"] == 1
    assert document["records"][0]["title"] == "Finalized Copy"
    assert document["records"][0]["proposed_collection"] == "Energy"


def test_malformed_root_metadata_is_ignored_before_parsing(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "000-broken.metadata.json").write_text("{broken", encoding="utf-8")
    write_record(
        archive / "Energy",
        "valid",
        title="Valid Paper",
        doi="10.1000/valid",
        source_url="https://example.test/valid",
        category="Energy",
    )

    result = export_zotero_plan(archive, since_days=None)

    assert result["records"] == 1


def test_doi_url_query_is_ignored_for_identity(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "Energy",
        "first",
        title="First DOI Copy",
        doi="https://doi.org/10.1000/ABC?tracking=1#fragment",
        source_url="https://example.test/first",
        category="Energy",
    )
    write_record(
        archive / "Climate",
        "second",
        title="Second DOI Copy",
        doi="10.1000/abc",
        source_url="https://example.test/second",
        category="Climate",
    )

    result = export_zotero_plan(archive, since_days=None)

    assert result["records"] == 1


def test_source_url_default_port_is_ignored_for_identity(tmp_path: Path) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "Energy",
        "first",
        title="First URL Copy",
        doi="",
        source_url="https://example.test:443/paper#first",
        category="Energy",
    )
    write_record(
        archive / "Climate",
        "second",
        title="Second URL Copy",
        doi="",
        source_url="https://example.test/paper",
        category="Climate",
    )

    result = export_zotero_plan(archive, since_days=None)

    assert result["records"] == 1


def test_plan_files_are_not_published_when_staging_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    archive = tmp_path / "archive"
    write_record(
        archive / "Energy",
        "paper",
        title="Paper",
        doi="10.1000/paper",
        source_url="https://example.test/paper",
        category="Energy",
    )
    output = tmp_path / "output"
    monkeypatch.setattr(
        prepare_zotero_import,
        "write_csv",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("csv failed")),
    )

    with pytest.raises(OSError, match="csv failed"):
        export_zotero_plan(archive, output, since_days=None)

    assert list(output.iterdir()) == []


@pytest.mark.parametrize("failure_index", range(4))
def test_plan_publication_rolls_back_each_failed_replace(
    tmp_path: Path,
    monkeypatch,
    failure_index: int,
) -> None:
    archive = tmp_path / "archive"
    _, metadata_path = write_record(
        archive / "Energy",
        "paper",
        title="Original Paper",
        doi="10.1000/paper",
        source_url="https://example.test/paper",
        category="Energy",
    )
    output = tmp_path / "output"
    export_zotero_plan(archive, output, since_days=None)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["title"] = "Updated Paper"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    original_replace = prepare_zotero_import.os.replace
    publication_count = 0
    failed = False

    def fail_selected_publish(source, destination):
        nonlocal publication_count, failed
        if not failed and str(source).endswith(".staged"):
            if publication_count == failure_index:
                failed = True
                raise OSError("publish failed")
            publication_count += 1
        return original_replace(source, destination)

    monkeypatch.setattr(prepare_zotero_import.os, "replace", fail_selected_publish)

    with pytest.raises(OSError, match="publish failed"):
        export_zotero_plan(archive, output, since_days=None)

    after = {path.name: path.read_bytes() for path in output.iterdir()}
    assert after == before


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


@pytest.mark.parametrize("content", ["- item\n", "paths: invalid\n"])
def test_archive_only_config_rejects_non_mapping_sections(
    tmp_path: Path,
    content: str,
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text(content, encoding="utf-8")

    with pytest.raises(RuntimeError, match="must be a mapping"):
        resolve_archive_root(config_path=config)
