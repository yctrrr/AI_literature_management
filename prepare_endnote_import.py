from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.config import default_config_path, load_config


DEFAULT_GROUP = "AI_literature_management"
ENDNOTE_INCLUDED_INTERNAL_DIRS = {"_pending_summary"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare an EndNote RIS import package for crawled PDFs.")
    parser.add_argument("--config", type=Path, default=None, help="Initialized project configuration")
    parser.add_argument("--archive-root", type=Path, default=None)
    parser.add_argument("--group", default=DEFAULT_GROUP, help="Keyword/group label added to every imported record.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--since-days", type=int, default=7, help="Only export records added/updated within this many days.")
    parser.add_argument("--all", action="store_true", help="Export the full archive instead of only recent records.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    since_days = None if args.all else args.since_days
    archive_root = args.archive_root
    if archive_root is None:
        archive_root = load_config(args.config or default_config_path()).paths.archive_root
    export_endnote_import(archive_root, args.group, args.output_dir, since_days=since_days)
    return 0


def export_endnote_import(
    archive_root: Path,
    group: str = DEFAULT_GROUP,
    output_dir: Path | None = None,
    since_days: int | None = 7,
) -> dict[str, Path | int]:
    archive_root = archive_root.resolve()
    output_dir = (output_dir or archive_root / "_endnote_import").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    records = load_records(archive_root, since_days=since_days)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ris_path = output_dir / f"{group}_{timestamp}.ris"
    enw_path = output_dir / f"{group}_{timestamp}.enw"
    manifest_path = output_dir / f"{group}_{timestamp}_manifest.csv"
    attachment_report_path = output_dir / f"{group}_{timestamp}_attachment_report.csv"
    latest_ris = output_dir / f"{group}_latest.ris"
    latest_enw = output_dir / f"{group}_latest.enw"

    write_ris(ris_path, records, group)
    write_enw(enw_path, records, group)
    write_manifest(manifest_path, records, group)
    write_attachment_report(attachment_report_path, records)
    latest_ris.write_text(ris_path.read_text(encoding="utf-8"), encoding="utf-8")
    latest_enw.write_text(enw_path.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"records: {len(records)}")
    print(f"since_days: {since_days if since_days is not None else 'all'}")
    print(f"ris: {ris_path}")
    print(f"enw: {enw_path}")
    print(f"latest_ris: {latest_ris}")
    print(f"latest_enw: {latest_enw}")
    print(f"manifest: {manifest_path}")
    print(f"attachment_report: {attachment_report_path}")
    return {
        "records": len(records),
        "since_days": since_days if since_days is not None else -1,
        "ris": ris_path,
        "enw": enw_path,
        "latest_ris": latest_ris,
        "latest_enw": latest_enw,
        "manifest": manifest_path,
        "attachment_report": attachment_report_path,
    }


def load_records(archive_root: Path, since_days: int | None = None) -> list[dict]:
    records: list[dict] = []
    seen: dict[str, dict] = {}
    cutoff = recent_cutoff(since_days)
    for metadata_path in sorted(archive_root.rglob("*.metadata.json")):
        if is_internal_metadata_excluded(metadata_path, archive_root):
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_timestamp = record_timestamp(metadata, metadata_path)
        if cutoff and source_timestamp < cutoff:
            continue
        pdf_path = resolve_pdf_path(metadata, metadata_path)
        attachment_paths = resolve_attachment_paths(metadata, metadata_path)
        key = metadata.get("doi") or metadata.get("source_url") or str(pdf_path)
        if key in seen:
            merge_attachment_paths(seen[key], attachment_paths)
            continue
        if not pdf_path.is_file():
            continue
        metadata["_metadata_path"] = str(metadata_path)
        metadata["_source_timestamp"] = source_timestamp.isoformat(timespec="seconds")
        metadata["_attachment_issue"] = attachment_issue(metadata, attachment_paths)
        metadata["pdf_path"] = str(pdf_path)
        metadata["attachment_paths"] = [str(path) for path in attachment_paths]
        seen[key] = metadata
        records.append(metadata)
    return records


def is_internal_metadata_excluded(metadata_path: Path, archive_root: Path) -> bool:
    for part in metadata_path.relative_to(archive_root).parts:
        if part.startswith("_") and part not in ENDNOTE_INCLUDED_INTERNAL_DIRS:
            return True
    return False


def recent_cutoff(since_days: int | None) -> datetime | None:
    if since_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=since_days)


def record_timestamp(metadata: dict, metadata_path: Path) -> datetime:
    value = metadata.get("updated_at") or metadata.get("created_at") or ""
    if value:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(metadata_path.stat().st_mtime, tz=timezone.utc)


def attachment_issue(metadata: dict, attachment_paths: list[Path]) -> str:
    if attachment_paths:
        raw_attachment_path = metadata.get("attachment_path") or ""
        attachment_path = Path(raw_attachment_path)
        if raw_attachment_path and not attachment_path.is_file():
            return "metadata_attachment_path_stale_resolved_by_sibling"
        return "downloaded"
    if metadata.get("attachment_url"):
        if metadata.get("attachment_error"):
            return f"download_failed: {metadata.get('attachment_error')}"
        return "attachment_url_detected_but_no_local_file"
    return "no_attachment_detected"


def resolve_pdf_path(metadata: dict, metadata_path: Path) -> Path:
    pdf_path = Path(metadata.get("pdf_path") or "")
    if pdf_path.is_file():
        return pdf_path
    if metadata_path.name.endswith(".metadata.json"):
        sibling_pdf = metadata_path.with_name(metadata_path.name[: -len(".metadata.json")] + ".pdf")
        if sibling_pdf.is_file():
            return sibling_pdf
    file_stem = metadata.get("file_stem")
    if file_stem:
        sibling_pdf = metadata_path.with_name(f"{file_stem}.pdf")
        if sibling_pdf.is_file():
            return sibling_pdf
    return pdf_path


def resolve_attachment_paths(metadata: dict, metadata_path: Path) -> list[Path]:
    candidates: list[Path] = []
    attachment_path = Path(metadata.get("attachment_path") or "")
    if attachment_path.is_file():
        candidates.append(attachment_path)

    stems = [metadata_path.name[: -len(".metadata.json")]]
    if metadata.get("file_stem"):
        stems.append(str(metadata["file_stem"]))
    for stem in dict.fromkeys(stems):
        candidates.extend(sorted(metadata_path.parent.glob(f"Supp-{stem}.*")))

    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate.is_file():
            continue
        key = str(candidate.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def merge_attachment_paths(record: dict, attachment_paths: list[Path]) -> None:
    existing = list(record.get("attachment_paths") or [])
    seen = {file_signature(Path(path)) for path in existing if Path(path).is_file()}
    for attachment_path in attachment_paths:
        key = file_signature(attachment_path)
        if key not in seen:
            existing.append(str(attachment_path))
            seen.add(key)
    record["attachment_paths"] = existing


def file_signature(path: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return path.stat().st_size, hasher.hexdigest()


def write_ris(path: Path, records: list[dict], group: str) -> None:
    chunks = []
    for record in records:
        chunks.extend(record_to_ris(record, group))
        chunks.append("")
    path.write_text("\n".join(chunks), encoding="utf-8")


def write_enw(path: Path, records: list[dict], group: str) -> None:
    chunks = []
    for record in records:
        chunks.extend(record_to_enw(record, group))
        chunks.append("")
    path.write_text("\n".join(chunks), encoding="utf-8")


def record_to_ris(record: dict, group: str) -> list[str]:
    lines = ["TY  - JOUR"]
    add(lines, "TI", record.get("title"))
    for author in record.get("authors") or []:
        add(lines, "AU", author)
    add(lines, "T2", record.get("journal"))
    add(lines, "PY", record.get("year"))
    add(lines, "DA", record.get("published"))
    add(lines, "DO", record.get("doi"))
    add(lines, "AB", clean_text(record.get("abstract")))
    add(lines, "UR", record.get("source_url") or record.get("pdf_url"))
    add(lines, "L1", record.get("pdf_path"))
    for attachment_path in record.get("attachment_paths") or []:
        add(lines, "L1", attachment_path)
    add(lines, "KW", group)
    if record.get("keyword"):
        add(lines, "KW", record.get("keyword"))
    if record.get("category"):
        add(lines, "N1", f"Literature archive category: {record.get('category')}")
    add(lines, "N1", f"Literature archive metadata: {record.get('_metadata_path')}")
    lines.append("ER  -")
    return lines


def record_to_enw(record: dict, group: str) -> list[str]:
    lines = ["%0 Journal Article"]
    add_endnote(lines, "%T", record.get("title"))
    for author in record.get("authors") or []:
        add_endnote(lines, "%A", author)
    add_endnote(lines, "%J", record.get("journal"))
    add_endnote(lines, "%D", record.get("year"))
    add_endnote(lines, "%8", record.get("published"))
    add_endnote(lines, "%R", record.get("doi"))
    add_endnote(lines, "%X", clean_text(record.get("abstract")))
    add_endnote(lines, "%U", record.get("source_url") or record.get("pdf_url"))
    add_endnote(lines, "%>", record.get("pdf_path"))
    for attachment_path in record.get("attachment_paths") or []:
        add_endnote(lines, "%>", attachment_path)
    add_endnote(lines, "%K", group)
    if record.get("keyword"):
        add_endnote(lines, "%K", record.get("keyword"))
    if record.get("category"):
        add_endnote(lines, "%Z", f"Literature archive category: {record.get('category')}")
    add_endnote(lines, "%Z", f"Literature archive metadata: {record.get('_metadata_path')}")
    return lines


def write_manifest(path: Path, records: list[dict], group: str) -> None:
    fields = [
        "group",
        "source_timestamp",
        "title",
        "authors",
        "year",
        "journal",
        "doi",
        "category",
        "pdf_path",
        "attachment_paths",
        "attachment_issue",
        "source_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "group": group,
                    "source_timestamp": record.get("_source_timestamp", ""),
                    "title": record.get("title", ""),
                    "authors": "; ".join(record.get("authors") or []),
                    "year": record.get("year", ""),
                    "journal": record.get("journal", ""),
                    "doi": record.get("doi", ""),
                    "category": record.get("category", ""),
                    "pdf_path": record.get("pdf_path", ""),
                    "attachment_paths": "; ".join(record.get("attachment_paths") or []),
                    "attachment_issue": record.get("_attachment_issue", ""),
                    "source_url": record.get("source_url", ""),
                }
            )


def write_attachment_report(path: Path, records: list[dict]) -> None:
    fields = [
        "source_timestamp",
        "title",
        "doi",
        "category",
        "attachment_issue",
        "attachment_status",
        "attachment_url",
        "attachment_error",
        "metadata_attachment_path",
        "resolved_attachment_paths",
        "pdf_path",
        "metadata_path",
        "source_url",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "source_timestamp": record.get("_source_timestamp", ""),
                    "title": record.get("title", ""),
                    "doi": record.get("doi", ""),
                    "category": record.get("category", ""),
                    "attachment_issue": record.get("_attachment_issue", ""),
                    "attachment_status": record.get("attachment_status", ""),
                    "attachment_url": record.get("attachment_url", ""),
                    "attachment_error": record.get("attachment_error", ""),
                    "metadata_attachment_path": record.get("attachment_path", ""),
                    "resolved_attachment_paths": "; ".join(record.get("attachment_paths") or []),
                    "pdf_path": record.get("pdf_path", ""),
                    "metadata_path": record.get("_metadata_path", ""),
                    "source_url": record.get("source_url", ""),
                }
            )


def add(lines: list[str], tag: str, value: object) -> None:
    text = clean_text(value)
    if text:
        lines.append(f"{tag}  - {text}")


def add_endnote(lines: list[str], tag: str, value: object) -> None:
    text = clean_text(value)
    if text:
        lines.append(f"{tag} {text}")


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


if __name__ == "__main__":
    raise SystemExit(main())
