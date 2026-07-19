from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from prepare_endnote_import import canonical_record_identity, load_records
from src.utils import atomic_write_json


DEFAULT_PREFIX = "AI_literature_management_zotero"
CONFIG_ENV = "AI_LITERATURE_CONFIG"
ARCHIVE_ENV = "AI_LITERATURE_ARCHIVE_ROOT"


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
    try:
        archive_root = resolve_archive_root(args.archive_root, args.config)
        since_days = None if args.all else args.since_days
        export_zotero_plan(archive_root, args.output_dir, since_days=since_days)
        return 0
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as error:
        print(f"ERROR: {error}")
        return 2


def resolve_archive_root(
    explicit_archive: Path | None = None,
    config_path: Path | None = None,
) -> Path:
    if explicit_archive:
        archive_root = explicit_archive.expanduser().resolve()
    elif os.environ.get(ARCHIVE_ENV):
        archive_root = Path(os.environ[ARCHIVE_ENV]).expanduser().resolve()
    else:
        selected_config = config_path or (
            Path(os.environ[CONFIG_ENV])
            if os.environ.get(CONFIG_ENV)
            else Path("config.yaml")
        )
        selected_config = selected_config.expanduser().resolve()
        if not selected_config.is_file():
            raise RuntimeError(f"Initialized configuration not found: {selected_config}")
        raw = yaml.safe_load(selected_config.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise RuntimeError("Configuration root must be a mapping")
        paths = raw.get("paths") or {}
        if not isinstance(paths, dict):
            raise RuntimeError("Configuration paths must be a mapping")
        value = paths.get("archive_root")
        if not value:
            raise RuntimeError("Configuration is missing paths.archive_root")
        archive_root = Path(str(value)).expanduser()
        if not archive_root.is_absolute():
            archive_root = selected_config.parent / archive_root
        archive_root = archive_root.resolve()
    if not archive_root.is_dir():
        raise RuntimeError(f"Archive root does not exist: {archive_root}")
    return archive_root


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
            metadata_path_filter=lambda path: is_finalized_metadata_path(
                path, archive_root
            ),
        )
    ]
    records.sort(key=lambda record: (record["proposed_collection"].lower(), record["title"].lower()))
    generated = datetime.now(timezone.utc)
    generated_at = generated.isoformat(timespec="microseconds")
    plan_id = generated.strftime("%Y%m%dT%H%M%S%fZ")
    document = {
        "version": 1,
        "plan_id": plan_id,
        "generated_at": generated_at,
        "archive_root": str(archive_root),
        "since_days": since_days if since_days is not None else "all",
        "record_count": len(records),
        "records": records,
    }
    timestamp = generated.astimezone().strftime("%Y%m%d_%H%M%S_%f")
    json_path = output_dir / f"{DEFAULT_PREFIX}_{timestamp}.json"
    csv_path = output_dir / f"{DEFAULT_PREFIX}_{timestamp}.csv"
    latest_json = output_dir / f"{DEFAULT_PREFIX}_latest.json"
    latest_csv = output_dir / f"{DEFAULT_PREFIX}_latest.csv"

    publish_plan_artifacts(
        document,
        records,
        plan_id,
        json_path=json_path,
        csv_path=csv_path,
        latest_json=latest_json,
        latest_csv=latest_csv,
    )

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


def is_finalized_metadata_path(metadata_path: Path, archive_root: Path) -> bool:
    try:
        relative = metadata_path.resolve().relative_to(archive_root)
    except (OSError, ValueError):
        return False
    return bool(
        len(relative.parts) >= 2
        and not any(part.startswith("_") for part in relative.parts)
    )


def publish_plan_artifacts(
    document: dict,
    records: list[dict],
    plan_id: str,
    *,
    json_path: Path,
    csv_path: Path,
    latest_json: Path,
    latest_csv: Path,
) -> None:
    targets = [json_path, csv_path, latest_json, latest_csv]
    staged = [create_staging_path(target) for target in targets]
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        atomic_write_json(staged[0], document)
        write_csv(staged[1], records, plan_id=plan_id)
        atomic_write_json(staged[2], document)
        write_csv(staged[3], records, plan_id=plan_id)
        for staged_path, target in zip(staged, targets, strict=True):
            if target.exists():
                backup = create_staging_path(target, suffix=".backup")
                os.replace(target, backup)
                backups[target] = backup
            os.replace(staged_path, target)
            published.append(target)
    except Exception:
        for target in reversed(targets):
            if target in published:
                target.unlink(missing_ok=True)
            backup = backups.get(target)
            if backup and backup.exists():
                os.replace(backup, target)
        raise
    finally:
        for temporary_path in [*staged, *backups.values()]:
            temporary_path.unlink(missing_ok=True)


def create_staging_path(target: Path, *, suffix: str = ".staged") -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=suffix, dir=target.parent
    )
    os.close(descriptor)
    return Path(temp_name)


def prepare_record(record: dict) -> dict:
    metadata_path = Path(record["_metadata_path"]).resolve()
    category = metadata_path.parent.name
    identity = canonical_record_identity(record, Path(record.get("pdf_path") or ""))
    record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    raw_authors = record.get("authors") or []
    authors = (
        [str(author) for author in raw_authors]
        if isinstance(raw_authors, (list, tuple, set))
        else [str(raw_authors)]
    )
    return {
        "record_id": record_id,
        "status": "ready_for_review",
        "zotero_duplicate_check": "not_run",
        "proposed_collection": category,
        "title": str(record.get("title") or Path(record.get("pdf_path") or "").stem),
        "authors": authors,
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


def write_csv(path: Path, records: list[dict], *, plan_id: str = "") -> None:
    fields = [
        "plan_id",
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
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(descriptor)
    try:
        with Path(temp_name).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for record in records:
                row = {key: safe_csv_cell(record.get(key, "")) for key in fields}
                row["plan_id"] = plan_id
                row["authors"] = safe_csv_cell("; ".join(record.get("authors") or []))
                row["attachment_paths"] = safe_csv_cell(
                    "; ".join(record.get("attachment_paths") or [])
                )
                writer.writerow(row)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        Path(temp_name).unlink(missing_ok=True)
        raise


def safe_csv_cell(value: object) -> str:
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


if __name__ == "__main__":
    raise SystemExit(main())
