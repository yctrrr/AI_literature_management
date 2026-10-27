#!/usr/bin/env python3
"""Export a supplementary DOCX to a linked-import-ready PDF with isolated Word."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import uuid
import zipfile
from pathlib import Path


SUPP_NAME = re.compile(r"^Supp-[^-]+-[^-]+-(?:19|20)\d{2}-.+\.pdf$", re.I)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_source(path: Path) -> None:
    if not path.is_file() or path.suffix.lower() != ".docx":
        raise ValueError("Source must be an existing DOCX file")
    with zipfile.ZipFile(path) as package:
        if "word/document.xml" not in package.namelist() or package.testzip():
            raise ValueError("Source is not an intact DOCX package")


def validate_pdf(path: Path) -> int:
    from pypdf import PdfReader

    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError("Word did not produce a usable PDF")
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise ValueError("Export is not a PDF")
    pages = len(PdfReader(str(path)).pages)
    if pages < 1:
        raise ValueError("Exported PDF has no pages")
    return pages


def export_with_isolated_word(source: Path, staging: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("This converter requires Windows Word; use a verified headless converter on this host")

    import psutil
    import pythoncom
    import win32com.client

    def word_processes() -> dict[int, str]:
        result = {}
        for process in psutil.process_iter(["name", "cmdline"]):
            if (process.info["name"] or "").lower() == "winword.exe":
                result[process.pid] = " ".join(process.info["cmdline"] or [])
        return result

    before = set(word_processes())
    application = None
    document = None
    owned = False
    pythoncom.CoInitialize()
    try:
        application = win32com.client.DispatchEx("Word.Application")
        for _ in range(20):
            new_processes = {
                pid: command for pid, command in word_processes().items()
                if pid not in before and ("/automation" in command.lower() or "-embedding" in command.lower())
            }
            if new_processes:
                break
            time.sleep(0.2)
        if len(new_processes) != 1:
            raise RuntimeError("Word did not provide a new isolated process; existing Word sessions were left untouched")
        owned = True
        application.Visible = False
        application.DisplayAlerts = 0
        application.AutomationSecurity = 3  # Disable macros for this automation instance.
        document = application.Documents.Open(
            FileName=str(source), ReadOnly=True, AddToRecentFiles=False,
            ConfirmConversions=False, Visible=False,
        )
        document.ExportAsFixedFormat(OutputFileName=str(staging), ExportFormat=17)
    finally:
        if owned:
            try:
                if document is not None:
                    document.Close(SaveChanges=0)
            finally:
                application.Quit(SaveChanges=0)
        document = None
        application = None
        pythoncom.CoUninitialize()


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert a DOCX supplement to a Supp-... PDF")
    parser.add_argument("--source", required=True, help="source DOCX path")
    parser.add_argument("--output", required=True, help="new standardized Supp-... PDF path")
    args = parser.parse_args()
    staging = None
    try:
        source = Path(args.source).expanduser().resolve(strict=True)
        output = Path(args.output).expanduser().resolve(strict=False)
        validate_source(source)
        if not SUPP_NAME.fullmatch(output.name):
            raise ValueError("Output name must be Supp-<journal>-<author>-<year>-<short-title>.pdf")
        if not output.parent.is_dir() or output.exists():
            raise ValueError("Output directory must exist and the PDF must not already exist")
        staging = output.with_name(f".{output.stem}.{uuid.uuid4().hex}.pdf")
        export_with_isolated_word(source, staging)
        pages = validate_pdf(staging)
        os.rename(staging, output)  # On Windows, this fails rather than replacing an existing file.
        print(json.dumps({"status": "created", "source": str(source), "output": str(output),
                          "pages": pages, "source_sha256": sha256(source),
                          "pdf_sha256": sha256(output)}, ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    finally:
        if staging is not None and staging.exists():
            staging.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
