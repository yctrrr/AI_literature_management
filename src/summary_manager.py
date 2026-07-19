from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from src.models import Classification, FetchResult
from src.utils import atomic_write_json, now_iso


class SummaryManager:
    UNMATCHED_SUMMARY = "No matching summary was found in the previous index."

    def __init__(self, archive_root: Path, categories: list[str]):
        self.archive_root = archive_root
        self.categories = categories
        self.summary_dir = archive_root / "_summaries"
        self.summary_path = self.summary_dir / "summary.md"
        self.backup_path = self.summary_dir / "summary.backup.md"
        self.index_path = self.summary_dir / "summary_index.json"
        self.summary_dir.mkdir(parents=True, exist_ok=True)

    def rebuild_from_archive(self) -> None:
        index = self._load_index_if_exists()
        old_entries = self._flatten_entries(index)
        old_sections = self._parse_old_summary()
        rebuilt = self._empty_index()

        for metadata_path in self._metadata_paths():
            metadata = self._read_metadata(metadata_path)
            if not metadata:
                continue
            entry = self._entry_from_metadata(metadata_path, metadata)
            existing = self._find_existing(old_entries, entry)
            if existing and existing.get("summary"):
                entry["summary"] = existing["summary"]
                entry["created_at"] = existing.get("created_at") or entry["created_at"]
            else:
                entry["summary"] = self._match_old_summary(entry, old_sections) or self.UNMATCHED_SUMMARY
            self._upsert_entry(rebuilt, entry)

        self._write_index(rebuilt)
        self.render()

    def upsert_article(self, fetched: FetchResult, classification: Classification, summary_text: str) -> None:
        index = self.ensure_index()
        metadata = dict(fetched.metadata)
        metadata["category"] = classification.category
        metadata["pdf_path"] = str(fetched.pdf_path) if fetched.pdf_path else metadata.get("pdf_path", "")
        metadata_path = self._metadata_path_for_pdf(fetched.pdf_path)
        entry = self._entry_from_metadata(metadata_path, metadata)
        entry["summary"] = summary_text.strip()
        self._upsert_entry(index, entry)
        self._write_index(index)
        self.render(index)

    def ensure_index(self) -> dict[str, Any]:
        if self.index_path.exists():
            return self._load_index()
        self.rebuild_from_archive()
        return self._load_index()

    def render(self, index: dict[str, Any] | None = None) -> None:
        index = index or self._load_index()
        lines = ["# Literature Summary", ""]
        rendered_categories = self._ordered_categories(index)
        for category in rendered_categories:
            entries = index.get("categories", {}).get(category, [])
            if not entries:
                continue
            lines.extend([f"## {category}", ""])
            for idx, entry in enumerate(entries, 1):
                lines.extend(
                    [
                        f"### {idx}. {entry.get('title') or Path(entry.get('pdf_path', '')).stem or 'Untitled'}",
                        "",
                        self._normalize_summary(entry.get("summary", "").strip() or self.UNMATCHED_SUMMARY),
                        "",
                    ]
                )
        self.summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _parse_old_summary(self) -> dict[str, str]:
        if not self.summary_path.exists():
            return {}
        if not self.backup_path.exists():
            shutil.copy2(self.summary_path, self.backup_path)
        text = self.summary_path.read_text(encoding="utf-8")
        matches = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", text))
        sections: dict[str, str] = {}
        for idx, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if title and body:
                sections[title] = body
        return sections

    def _metadata_paths(self) -> list[Path]:
        paths = []
        for metadata_path in self.archive_root.glob("*/*.metadata.json"):
            if metadata_path.parent.name.startswith("_"):
                continue
            paths.append(metadata_path)
        return sorted(paths, key=lambda p: (p.parent.name.lower(), p.name.lower()))

    @staticmethod
    def _read_metadata(path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _entry_from_metadata(self, metadata_path: Path | None, metadata: dict[str, Any]) -> dict[str, Any]:
        raw_pdf_path = metadata.get("pdf_path") or ""
        pdf_path = Path(raw_pdf_path) if raw_pdf_path else None
        if pdf_path is None and metadata_path:
            pdf_path = metadata_path.with_name(metadata_path.name.replace(".metadata.json", ".pdf"))
        category = metadata.get("category") or (metadata_path.parent.name if metadata_path else "others")
        if category not in self.categories:
            category = "others" if "others" in self.categories else category
        now = now_iso()
        return {
            "title": (pdf_path.stem if pdf_path else "") or metadata.get("title") or "Untitled",
            "category": category,
            "pdf_path": str(pdf_path) if pdf_path else "",
            "metadata_path": str(metadata_path) if metadata_path else "",
            "source_url": metadata.get("source_url", ""),
            "doi": metadata.get("doi", ""),
            "summary": metadata.get("summary", ""),
            "created_at": metadata.get("created_at") or now,
            "updated_at": now,
        }

    def _match_old_summary(self, entry: dict[str, Any], sections: dict[str, str]) -> str:
        title = entry.get("title", "")
        if title in sections:
            return sections[title]
        metadata_title = Path(entry.get("metadata_path", "")).name.replace(".metadata.json", "")
        if metadata_title in sections:
            return sections[metadata_title]
        for section_title, body in sections.items():
            if title and (title in section_title or section_title in title):
                return body
        doi = entry.get("doi", "")
        source_url = entry.get("source_url", "")
        for body in sections.values():
            if doi and doi in body:
                return body
            if source_url and source_url in body:
                return body
        return ""

    def _upsert_entry(self, index: dict[str, Any], entry: dict[str, Any]) -> None:
        categories = index.setdefault("categories", {})
        for category, entries in categories.items():
            for idx, existing in enumerate(entries):
                if self._same_entry(existing, entry):
                    entry["created_at"] = existing.get("created_at") or entry["created_at"]
                    entry["updated_at"] = now_iso()
                    entries[idx] = entry
                    if category != entry["category"]:
                        entries.pop(idx)
                        categories.setdefault(entry["category"], []).append(entry)
                    index["updated_at"] = now_iso()
                    return
        categories.setdefault(entry["category"], []).append(entry)
        index["updated_at"] = now_iso()

    @staticmethod
    def _same_entry(left: dict[str, Any], right: dict[str, Any]) -> bool:
        for key in ("doi", "source_url"):
            if left.get(key) and right.get(key) and left[key] == right[key]:
                return True
        left_stem = Path(left.get("pdf_path", "")).stem
        right_stem = Path(right.get("pdf_path", "")).stem
        return bool(left_stem and right_stem and left_stem == right_stem)

    def _find_existing(self, entries: list[dict[str, Any]], entry: dict[str, Any]) -> dict[str, Any] | None:
        for existing in entries:
            if self._same_entry(existing, entry):
                return existing
        return None

    def _ordered_categories(self, index: dict[str, Any]) -> list[str]:
        present = list(index.get("categories", {}).keys())
        ordered = [category for category in self.categories if category in present]
        ordered.extend(sorted(category for category in present if category not in ordered))
        return ordered

    @staticmethod
    def _flatten_entries(index: dict[str, Any]) -> list[dict[str, Any]]:
        entries = []
        for category_entries in index.get("categories", {}).values():
            entries.extend(category_entries)
        return entries

    def _empty_index(self) -> dict[str, Any]:
        return {"version": 1, "updated_at": now_iso(), "categories": {}}

    def _load_index_if_exists(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return self._empty_index()
        return self._load_index()

    def _load_index(self) -> dict[str, Any]:
        try:
            index = json.loads(self.index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed summary index: {self.index_path}") from exc
        if not isinstance(index, dict) or not isinstance(index.get("categories"), dict):
            raise ValueError(f"Malformed summary index: {self.index_path}")
        return index

    def _write_index(self, index: dict[str, Any]) -> None:
        atomic_write_json(self.index_path, index)

    @staticmethod
    def _metadata_path_for_pdf(pdf_path: Path | None) -> Path | None:
        if not pdf_path:
            return None
        return pdf_path.with_name(f"{pdf_path.stem}.metadata.json")

    @staticmethod
    def _normalize_summary(summary: str) -> str:
        return re.sub(r"(?m)^#{1,6}\s+", "#### ", summary.strip())
