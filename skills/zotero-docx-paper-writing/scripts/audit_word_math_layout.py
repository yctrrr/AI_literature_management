#!/usr/bin/env python3
"""Read-only structural inventory of Word equations, tables, captions, and headings."""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from zipfile import BadZipFile, ZipFile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def tag(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def text_of(element: ET.Element) -> str:
    return "".join(node.text or "" for node in element.iter(tag(W, "t")))


def math_count(element: ET.Element) -> int:
    return sum(1 for _ in element.iter(tag(M, "oMath")))


def style_of(paragraph: ET.Element) -> str:
    style = paragraph.find(f"{tag(W, 'pPr')}/{tag(W, 'pStyle')}")
    return style.get(tag(W, "val"), "") if style is not None else ""


def border_state(table: ET.Element) -> tuple[bool | None, dict[str, str]]:
    borders = table.find(f"{tag(W, 'tblPr')}/{tag(W, 'tblBorders')}")
    if borders is None:
        return None, {}
    values = {
        edge.tag.rsplit("}", 1)[-1]: edge.get(tag(W, "val"), "")
        for edge in borders
    }
    needed = ("top", "bottom", "left", "right", "insideH", "insideV")
    if not all(edge in values for edge in needed):
        return None, values
    return all(values[edge] in {"none", "nil"} for edge in needed), values


CAPTION = re.compile(
    r"^\s*(?P<scope>Supplementary\s+)?(?P<kind>Fig(?:ure)?\.?|Table)\s+"
    r"(?P<number>\d+[A-Za-z]?)\b|^\s*(?P<kind_zh>图|表)\s*(?P<number_zh>\d+[A-Za-z]?)"
)
EQUATION_NUMBER = re.compile(r"^\s*\(\s*([A-Za-z]?\d+(?:[.\-]\d+)?)\s*\)\s*$")


def caption_of(text: str) -> dict[str, str] | None:
    match = CAPTION.match(text)
    if match is None:
        return None
    if match.group("kind_zh"):
        kind = "figure" if match.group("kind_zh") == "图" else "table"
        scope = ""
        number = match.group("number_zh")
    else:
        kind = "figure" if match.group("kind").startswith("Fig") else "table"
        scope = "supplementary" if match.group("scope") else "main"
        number = match.group("number")
    return {"kind": kind, "scope": scope, "number": number}


def table_inventory(table: ET.Element, index: int) -> dict:
    rows = table.findall(tag(W, "tr"))
    borderless, borders = border_state(table)
    grid = table.find(tag(W, "tblGrid"))
    widths = (
        [col.get(tag(W, "w"), "") for col in grid.findall(tag(W, "gridCol"))]
        if grid is not None
        else []
    )
    result = {
        "table_index": index,
        "row_count": len(rows),
        "column_widths_twips": widths,
        "explicitly_borderless": borderless,
        "borders": borders,
        "first_row_cells": [],
        "equation_rows": [],
    }
    for row_index, row in enumerate(rows, 1):
        cells = row.findall(tag(W, "tc"))
        if row_index == 1:
            result["first_row_cells"] = [text_of(cell)[:100] for cell in cells]
        if len(cells) != 2:
            continue
        left_math = math_count(cells[0])
        right_math = math_count(cells[1])
        right_text = text_of(cells[1]).strip()
        number_match = EQUATION_NUMBER.fullmatch(right_text)
        # An ordinary data table can contain math. Treat it as an equation
        # layout only when the two-cell pattern and numbering/border cues agree.
        if not left_math or right_math or (number_match is None and borderless is not True):
            continue
        result["equation_rows"].append(
            {
                "row": row_index,
                "cell_count": len(cells),
                "left_native_math_count": left_math,
                "right_text": right_text[:100],
                "number": number_match.group(1) if number_match else None,
            }
        )
    return result


def meaningful_neighbors(sequence: list[dict], at: int) -> tuple[str | None, str | None]:
    previous = next((item["kind"] for item in reversed(sequence[:at]) if item["kind"] != "blank"), None)
    following = next((item["kind"] for item in sequence[at + 1 :] if item["kind"] != "blank"), None)
    return previous, following


def audit(path: Path) -> dict:
    with ZipFile(path) as package:
        root = ET.fromstring(package.read("word/document.xml"))
    body = root.find(f"{tag(W, 'body')}")
    if body is None:
        raise ValueError("word/document.xml has no w:body")

    all_tables = [table_inventory(table, index) for index, table in enumerate(root.iter(tag(W, "tbl")), 1)]
    formula_tables = [table for table in all_tables if table["equation_rows"]]
    data_tables = [
        {key: value for key, value in table.items() if key != "equation_rows"}
        for table in all_tables
        if not table["equation_rows"]
    ]
    sequence: list[dict] = []
    headings: list[dict] = []
    captions: list[dict] = []
    for child in body:
        if child.tag == tag(W, "p"):
            content = text_of(child).strip()
            style = style_of(child)
            drawing = any(node.tag in {tag(W, "drawing"), tag(W, "pict")} for node in child.iter())
            caption = caption_of(content)
            kind = "figure" if drawing else "caption" if caption else "heading" if style.lower().startswith("heading") else "paragraph" if content else "blank"
            item = {"kind": kind, "text": content[:180], "style": style}
            sequence.append(item)
            if style.lower().startswith("heading"):
                headings.append({"text": content[:180], "style": style})
            if caption:
                captions.append({**caption, "text": content[:180], "style": style, "sequence_index": len(sequence) - 1, "same_paragraph_image": drawing})
        elif child.tag == tag(W, "tbl"):
            kind = "equation_table" if math_count(child) else "data_table"
            sequence.append({"kind": kind})

    for caption in captions:
        previous, following = meaningful_neighbors(sequence, caption["sequence_index"])
        caption["previous_kind"] = previous
        caption["next_kind"] = following
        del caption["sequence_index"]

    warnings: list[str] = []
    numbers: list[str] = []
    for table in formula_tables:
        if table["explicitly_borderless"] is False:
            warnings.append(f"Equation table {table['table_index']} has visible border settings")
        for row in table["equation_rows"]:
            if row["cell_count"] != 2 or row["left_native_math_count"] == 0:
                warnings.append(f"Equation table {table['table_index']} row {row['row']} is not native math in the left cell of two columns")
            if row["number"] is None:
                warnings.append(f"Equation table {table['table_index']} row {row['row']} lacks a simple right-cell number")
            else:
                numbers.append(row["number"])
    for number, count in Counter(numbers).items():
        if count > 1:
            warnings.append(f"Equation number ({number}) occurs {count} times; review numbering scope")
    for key, count in Counter((cap["scope"], cap["kind"], cap["number"]) for cap in captions).items():
        if count > 1:
            warnings.append(f"Caption number {key} occurs {count} times; review numbering scope")

    return {
        "path": str(path.resolve()),
        "native_math_count": math_count(root),
        "native_math_in_equation_tables": sum(row["left_native_math_count"] for table in formula_tables for row in table["equation_rows"]),
        "equation_tables": formula_tables,
        "data_tables": data_tables,
        "captions": captions,
        "headings": headings,
        "review_flags": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("docx", nargs="+", type=Path, help="DOCX files to inspect without editing")
    args = parser.parse_args()
    reports = []
    for path in args.docx:
        try:
            reports.append(audit(path))
        except (OSError, BadZipFile, KeyError, ET.ParseError, ValueError) as error:
            print(f"Cannot audit {path}: {error}", file=sys.stderr)
            return 2
    print(json.dumps(reports[0] if len(reports) == 1 else reports, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
