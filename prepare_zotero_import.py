from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from prepare_endnote_import import load_records
from src.config import default_config_path, load_config
from src.utils import atomic_write_json


DEFAULT_PREFIX = "AI_literature_management_zotero"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare a read-only Zotero linked-import review manifest."
    )
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--archive-root", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--since-days",
        type=int,
        default=7,
        help="Only include records added or updated within this many days.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include the full finalized archive.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.since_days < 0:
        print("ERROR: --since-days must be zero or greater")
        return 2
    archive_root = args.archive_root
    if archive_root is None:
        archive_root = load_config(args.config or default_config_path()).paths.archive_root
    since_days = None if args.all else args.since_days
    export_zotero_plan(archive_root, args.output_dir, since_days=since_days)
    return 0


def export_zotero_plan(
    archive_root: Path,
    output_dir: Path | None = None,
    *,
    since_days: int | None = 7,
) -> dict[str, Path | int]:
    archive_root = archive_root.expanduser().resolve()
    output_dir = (output_dir or archive_root / "_zotero_import").expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = [
        prepare_record(record)
        for record in load_records(
            archive_root,
            since_days=since_days,
            include_pending=False,
        )
        if is_finalized_record(record, archive_root)
    ]
    records.sort(key=lambda record: (record["proposed_collection"].lower(), record["title"].lower()))
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    document = {
        "version": 1,
        "generated_at": generated_at,
        "archive_root": str(archive_root),
        "since_days": since_days if since_days is not None else "all",
        "record_count": len(records),
        "records": records,
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"{DEFAULT_PREFIX}_{timestamp}.json"
    csv_path = output_dir / f"{DEFAULT_PREFIX}_{timestamp}.csv"
    latest_json = output_dir / f"{DEFAULT_PREFIX}_latest.json"
    latest_csv = output_dir / f"{DEFAULT_PREFIX}_latest.csv"

    atomic_write_json(json_path, document)
    atomic_write_json(latest_json, document)
    write_csv(csv_path, records)
    write_csv(latest_csv, records)

    print(f"records: {len(records)}")
    print(f"since_days: {since_days if since_days is not None else 'all'}")
    print(f"json: {json_path}")
    print(f"csv: {csv_path}")
    print(f"latest_json: {latest_json}")
    print(f"latest_csv: {latest_csv}")
    print("zotero_access: not_run")
    return {
        "records": len(records),
        "since_days": since_days if since_days is not None else -1,
        "json": json_path,
        "csv": csv_path,
        "latest_json": latest_json,
        "latest_csv": latest_csv,
    }


def is_finalized_record(record: dict, archive_root: Path) -> bool:
    metadata_path = Path(record.get("_metadata_path") or "")
    try:
        relative = metadata_path.resolve().relative_to(archive_root)
    except (OSError, ValueError):
        return False
    return bool(relative.parts and not any(part.startswith("_") for part in relative.parts))


def prepare_record(record: dict) -> dict:
    metadata_path = Path(record["_metadata_path"]).resolve()
    category = metadata_path.parent.name
    identity = (
        str(record.get("doi") or "").strip().lower()
        or str(record.get("source_url") or "").strip()
        or str(Path(record.get("pdf_path") or "").resolve())
    )
    record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {
        "record_id": record_id,
        "status": "ready_for_review",
        "zotero_duplicate_check": "not_run",
        "proposed_collection": category,
        "title": str(record.get("title") or Path(record.get("pdf_path") or "").stem),
        "authors": list(record.get("authors") or []),
        "year": str(record.get("year") or ""),
        "journal": str(record.get("journal") or ""),
        "doi": str(record.get("doi") or ""),
        "source_url": str(record.get("source_url") or ""),
        "pdf_path": str(Path(record.get("pdf_path") or "").resolve()),
        "attachment_paths": [
            str(Path(path).resolve()) for path in (record.get("attachment_paths") or [])
        ],
        "metadata_path": str(metadata_path),
        "source_timestamp": str(record.get("_source_timestamp") or ""),
        "attachment_issue": str(record.get("_attachment_issue") or ""),
    }


def write_csv(path: Path, records: list[dict]) -> None:
    fields = [
        "record_id",
        "status",
        "zotero_duplicate_check",
        "proposed_collection",
        "title",
        "authors",
        "year",
        "journal",
        "doi",
        "source_url",
        "pdf_path",
        "attachment_paths",
        "metadata_path",
        "source_timestamp",
        "attachment_issue",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key, "") for key in fields}
            row["authors"] = "; ".join(record.get("authors") or [])
            row["attachment_paths"] = "; ".join(record.get("attachment_paths") or [])
            writer.writerow(row)


if __name__ == "__main__":
    raise SystemExit(main())
