# -*- coding: utf-8 -*-
"""
Reusable helpers for background (scripted) Zotero field insertion in DOCX.

Companion to references/background-zotero-insertion.md. Field/JSON formats are
verified against Zotero 9.0.6 integration.js and a real Word/Zotero round-trip.

Use as a library:
    from zotero_field_builder import (
        build_item_data, make_citation_json, make_bibliography_json,
        citation_field_runs, replace_marker_with_field, remove_first_field,
        strip_run_tail, strip_run_head, insert_runs_after, run_text,
        validate_document, make_gb7714_entry,
    )

Use as a CLI (config-driven marker + parenthetical + bibliography replacement):
    python zotero_field_builder.py --docx in.docx --out out.docx --config cfg.json [--verify]

The input DOCX is never modified; write to --out (backup separately, e.g. with
backup_docx.ps1, before any mutation workflow).
"""
import argparse
import copy
import io
import json
import random
import re
import string
import sys
import zipfile

try:
    from docx import Document
    from lxml import etree
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency (python-docx / lxml): %s" % exc
    )

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

TYPE_MAP = {
    "journalArticle": "article-journal",
    "conferencePaper": "paper-conference",
    "preprint": "article",
}

CSL_SCHEMA = (
    "https://github.com/citation-style-language/schema/raw/master/csl-citation.json"
)

CITATION_RESULT_RPR = (
    '<w:rPr xmlns:w="%s">'
    '<w:rFonts w:cs="Times New Roman"/><w:kern w:val="0"/>'
    '<w:vertAlign w:val="superscript"/></w:rPr>' % W
)


def w(tag):
    return "{%s}%s" % (W, tag)


# --------------------------------------------------------------------------
# CSL / field JSON builders
# --------------------------------------------------------------------------

def parse_date_parts(s):
    """'2016-09-02 2016-09-02' -> [2016, 9, 2]; '2021' -> [2021]; '' -> None."""
    if not s:
        return None
    first = s.split(" ")[0]
    parts = [int(p) for p in first.split("-") if p and p != "00"]
    return parts or None


def build_item_data(zotero_type, item_id, fields, creators):
    """Zotero item fields/creators -> CSL JSON itemData (fallback cache)."""
    d = {"id": item_id, "type": TYPE_MAP.get(zotero_type, "article-journal")}
    if fields.get("title"):
        d["title"] = fields["title"]
    ct = fields.get("publicationTitle") or fields.get("proceedingsTitle")
    if ct:
        d["container-title"] = ct
    if zotero_type == "conferencePaper" and fields.get("conferenceName"):
        d["event-title"] = fields["conferenceName"]
    for zk, ck in (("volume", "volume"), ("issue", "issue"), ("pages", "page")):
        if fields.get(zk):
            d[ck] = fields[zk]
    dp = parse_date_parts(fields.get("date", ""))
    if dp:
        d["issued"] = {"date-parts": [dp]}
    for zk, ck in (("DOI", "DOI"), ("ISSN", "ISSN"), ("url", "URL"),
                   ("language", "language"), ("abstractNote", "abstract")):
        if fields.get(zk):
            d[ck] = fields[zk]
    authors = []
    for cr in creators or []:
        if len(cr) >= 3 and cr[2] == "author":
            authors.append({"family": cr[0], "given": cr[1]})
    if authors:
        d["author"] = authors
    return d


def item_uri(library_key, item_key):
    return "http://zotero.org/users/local/%s/items/%s" % (library_key, item_key)


def build_citation_item(item_key, item_id, item_data, library_key):
    return {
        "id": item_id,
        "uris": [item_uri(library_key, item_key)],
        "itemData": item_data,
    }


def make_citation_json(citation_items, cached_text, citation_id):
    """cached_text like '[1,2]'; formattedCitation stores \\super ... \\nosupersub{}."""
    return {
        "citationID": citation_id,
        "properties": {
            "unsorted": False,
            "formattedCitation": "\\super %s\\nosupersub{}" % cached_text,
            "plainCitation": cached_text,
            "noteIndex": 0,
        },
        "citationItems": citation_items,
        "schema": CSL_SCHEMA,
    }


def make_bibliography_json(uncited_uris, omitted_uris=None, custom=None):
    """uncited_uris: list of URI-strings (one per uncited item, in desired order)."""
    return {
        "uncited": [[u] for u in uncited_uris],
        "omitted": [[u] for u in (omitted_uris or [])],
        "custom": custom or [],
    }


# --------------------------------------------------------------------------
# OOXML field run builders
# --------------------------------------------------------------------------

def make_run():
    return etree.Element(w("r"))


def make_fldchar_run(fldtype):
    r = make_run()
    fc = etree.SubElement(r, w("fldChar"))
    fc.set(w("fldCharType"), fldtype)
    return r


def make_text_run(text, rpr_xml=None):
    r = make_run()
    if rpr_xml:
        r.append(etree.fromstring(rpr_xml))
    t = etree.SubElement(r, w("t"))
    t.set(XML_SPACE, "preserve")
    t.text = text
    return r


def citation_field_runs(cached_text, citation_json):
    """Five runs: begin -> instrText -> separate -> superscript result -> end."""
    code = " ADDIN ZOTERO_ITEM CSL_CITATION " + json.dumps(
        citation_json, ensure_ascii=False
    ) + " "
    runs = [make_fldchar_run("begin")]
    r = make_run()
    it = etree.SubElement(r, w("instrText"))
    it.set(XML_SPACE, "preserve")
    it.text = code
    runs.append(r)
    runs.append(make_fldchar_run("separate"))
    runs.append(make_text_run(cached_text, CITATION_RESULT_RPR))
    runs.append(make_fldchar_run("end"))
    return runs


def bibliography_field_runs(bibl_json):
    code = " ADDIN ZOTERO_BIBL " + json.dumps(
        bibl_json, ensure_ascii=False
    ) + " CSL_BIBLIOGRAPHY "
    runs = [make_fldchar_run("begin")]
    r = make_run()
    it = etree.SubElement(r, w("instrText"))
    it.set(XML_SPACE, "preserve")
    it.text = code
    runs.append(r)
    runs.append(make_fldchar_run("separate"))
    return runs


# --------------------------------------------------------------------------
# Paragraph / run manipulation
# --------------------------------------------------------------------------

def run_text(r):
    return "".join(t.text or "" for t in r.findall(w("t")))


def iter_runs_outside_fields(p):
    """Yield direct text runs, skipping fldChar/instrText runs and runs inside fields."""
    in_field = False
    for r in p.findall(w("r")):
        fc = r.find(w("fldChar"))
        if fc is not None:
            ft = fc.get(w("fldCharType"))
            if ft == "begin":
                in_field = True
            elif ft == "end":
                in_field = False
            continue
        if r.find(w("instrText")) is not None:
            continue
        if in_field:
            continue
        yield r


def find_marker_run(p, marker):
    for r in iter_runs_outside_fields(p):
        if run_text(r).strip() == marker:
            return r
    return None


def find_inline_marker_run(p, marker):
    for r in iter_runs_outside_fields(p):
        text = run_text(r)
        if marker in text:
            return r, text
    return None, None


def clone_text_run(r, text):
    clone = copy.deepcopy(r)
    for child in list(clone):
        if child.tag != w("rPr"):
            clone.remove(child)
    t = etree.SubElement(clone, w("t"))
    t.set(XML_SPACE, "preserve")
    t.text = text
    return clone


def replace_marker_with_field(p, marker, citation_json, cached_text):
    """Replace the plain-text marker run with a citation field. Returns bool."""
    hit = find_marker_run(p, marker)
    original_text = None
    if hit is None:
        hit, original_text = find_inline_marker_run(p, marker)
        if hit is None:
            return False
    parent = hit.getparent()
    idx = parent.index(hit)
    parent.remove(hit)
    replacement = []
    if original_text is not None:
        left, right = original_text.split(marker, 1)
        if left:
            replacement.append(clone_text_run(hit, left))
        replacement.extend(citation_field_runs(cached_text, citation_json))
        if right:
            replacement.append(clone_text_run(hit, right))
    else:
        replacement = citation_field_runs(cached_text, citation_json)
    for i, ne in enumerate(replacement):
        parent.insert(idx + i, ne)
    return True


def remove_first_field(p):
    """Remove the first field (begin..end) in the paragraph. Returns bool."""
    runs = p.findall(w("r"))
    start = None
    for i, r in enumerate(runs):
        fc = r.find(w("fldChar"))
        if fc is not None and fc.get(w("fldCharType")) == "begin":
            start = i
            break
    if start is None:
        return False
    end = None
    for j in range(start, len(runs)):
        fc = runs[j].find(w("fldChar"))
        if fc is not None and fc.get(w("fldCharType")) == "end":
            end = j
            break
    if end is None:
        raise RuntimeError("field without matching end run")
    for r in runs[start:end + 1]:
        r.getparent().remove(r)
    return True


def strip_run_tail(r, ch):
    t = r.find(w("t"))
    if t is not None and t.text and t.text.endswith(ch):
        t.text = t.text[:-1]
        return True
    return False


def strip_run_head(r, ch):
    t = r.find(w("t"))
    if t is not None and t.text and t.text.startswith(ch):
        t.text = t.text[1:]
        return True
    return False


def delete_runs(runs):
    for r in runs:
        if r.getparent() is not None:
            r.getparent().remove(r)


def insert_runs_after(anchor, new_runs):
    parent = anchor.getparent()
    idx = parent.index(anchor)
    for i, ne in enumerate(new_runs):
        parent.insert(idx + 1 + i, ne)


# --------------------------------------------------------------------------
# GB/T 7714 entry generator (convenience; config may override with 'entries')
# --------------------------------------------------------------------------

def _initials(given):
    out = []
    for part in given.replace(".", " ").split():
        if part:
            out.append(part[0].upper())
    return " ".join(out)


def make_gb7714_entry(item_key, num, items, max_authors=3):
    """Generate '[n] Authors. Title [J]. Journal, Year, Vol(Iss): Pages.' from item data."""
    it = items[item_key]
    f = it["fields"]
    crs = [c for c in it.get("creators", []) if len(c) >= 3 and c[2] == "author"]
    parts = [cr[0] + " " + _initials(cr[1]) for cr in crs[:max_authors]]
    if len(crs) > max_authors:
        parts.append("et al.")
    authors = ", ".join(parts)
    if not authors.endswith("."):
        authors += "."
    title = f.get("title", "")
    journal = f.get("publicationTitle", "")
    year = (f.get("date") or "")[:4]
    vol = f.get("volume", "")
    iss = f.get("issue", "")
    pg = f.get("pages", "")
    volpart = vol
    if iss and iss != "00":
        volpart = "%s(%s)" % (vol, iss)
    body = "%s %s [J]. %s, %s, %s: %s." % (authors, title, journal, year, volpart, pg)
    return "[%d] %s" % (num, body)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def validate_document(path):
    """Return a report dict; raises on structural problems."""
    z = zipfile.ZipFile(path)
    xml_bytes = z.read("word/document.xml")
    xml = xml_bytes.decode("utf-8")
    root = etree.fromstring(xml_bytes)
    instrs = []
    in_field = False
    code_parts = []
    for r in root.iter(w("r")):
        fc = r.find(w("fldChar"))
        if fc is not None:
            ft = fc.get(w("fldCharType"))
            if ft == "begin":
                in_field = True
                code_parts = []
            elif ft == "separate" and in_field:
                instrs.append("".join(code_parts))
            elif ft == "end":
                in_field = False
                code_parts = []
            continue
        if in_field:
            for instruction in r.findall(w("instrText")):
                code_parts.append(instruction.text or "")
    n_item = xml.count("ADDIN ZOTERO_ITEM")
    n_bibl = xml.count("ADDIN ZOTERO_BIBL")
    json_ok = 0
    json_bad = []
    for s in instrs:
        s2 = s.strip()
        try:
            if s2.startswith("ADDIN ZOTERO_ITEM"):
                j = s2[len("ADDIN ZOTERO_ITEM CSL_CITATION "):].rstrip()
                d = json.loads(j)
                assert d.get("citationItems"), "empty citationItems"
                json_ok += 1
            elif s2.startswith("ADDIN ZOTERO_BIBL"):
                j = s2[len("ADDIN ZOTERO_BIBL "):]
                j = j[:j.rfind(" CSL_BIBLIOGRAPHY")]
                d = json.loads(j)
                assert "uncited" in d and "omitted" in d and "custom" in d
                json_ok += 1
        except Exception as exc:
            json_bad.append((s2[:60], str(exc)))
    # field balance
    doc = Document(path)
    ns = {"w": W}
    total = 0
    begins = ends = 0
    per_para = []
    for i, para in enumerate(doc.paragraphs):
        depth = 0
        for r in para._p.findall(".//w:r", ns):
            fc = r.find(w("fldChar"))
            if fc is not None:
                ft = fc.get(w("fldCharType"))
                if ft == "begin":
                    begins += 1
                    depth += 1
                    total += 1
                elif ft == "end":
                    ends += 1
                    depth -= 1
                    total -= 1
        if depth != 0:
            per_para.append(i)
    report = {
        "zotero_item_fields": n_item,
        "zotero_bibl_fields": n_bibl,
        "json_valid": json_ok,
        "json_bad": json_bad,
        "begins": begins,
        "ends": ends,
        "total_balance": total,
        "unbalanced_paragraphs": per_para,
    }
    return report


# --------------------------------------------------------------------------
# Config-driven CLI
# --------------------------------------------------------------------------

def _load_items(config, items_file_arg):
    if items_file_arg:
        with open(items_file_arg, encoding="utf-8") as fh:
            return json.load(fh)
    if config.get("items_file"):
        with open(config["items_file"], encoding="utf-8") as fh:
            return json.load(fh)
    if config.get("items"):
        return config["items"]
    raise SystemExit("config must provide 'items' or 'items_file'")


def _apply_op(doc, op, items, library, snapshots):
    ptype = op.get("type", "marker")
    p = doc.paragraphs[op["paragraph"]]._p
    if ptype == "remove_field":
        if not remove_first_field(p):
            raise RuntimeError("para %d: no field to remove" % op["paragraph"])
        return ptype, op["paragraph"], "-", "-"
    cached = op["cached"]
    keys = op.get("keys", [])
    citation_items = []
    for k in keys:
        it = items[k]
        citation_items.append(build_citation_item(
            k, it["itemID"], build_item_data(it["zoteroType"], it["itemID"],
                                             it["fields"], it["creators"]),
            library))
    cj = make_citation_json(
        citation_items, cached,
        op.get("citation_id") or
        "".join(random.choices(string.ascii_letters + string.digits, k=8)))
    if ptype == "marker":
        ok = replace_marker_with_field(p, op["marker"], cj, cached)
        if not ok:
            raise RuntimeError("para %d: marker %r not found" %
                               (op["paragraph"], op["marker"]))
    elif ptype == "parenthetical":
        if op["paragraph"] not in snapshots:
            snapshots[op["paragraph"]] = p.findall(w("r"))
        runs = snapshots[op["paragraph"]]
        anchor = runs[op["anchor_run"]]
        if op.get("strip_tail_run") is not None:
            if not strip_run_tail(runs[op["strip_tail_run"]], "\uff08"):
                raise RuntimeError("para %d: tail strip failed at run %d" %
                                   (op["paragraph"], op["strip_tail_run"]))
        if op.get("strip_head_run") is not None:
            if not strip_run_head(runs[op["strip_head_run"]], "\uff09"):
                raise RuntimeError("para %d: head strip failed at run %d" %
                                   (op["paragraph"], op["strip_head_run"]))
        delete_runs([runs[i] for i in op.get("delete_runs", [])])
        insert_runs_after(anchor, citation_field_runs(cached, cj))
    else:
        raise SystemExit("unknown op type %r" % ptype)
    return ptype, op["paragraph"], cached, keys


def _apply_bibliography(doc, cfg, items, library):
    b = cfg["bibliography"]
    start = b["start"]
    end = b["end"]
    entries = b["entries"]  # {str(num): text}
    uncited = b.get("uncited", [])
    bibl_json = make_bibliography_json([item_uri(library, k) for k in uncited])
    # Capture original paragraphs by element reference BEFORE inserting anything,
    # so the deletion below survives index shifts.
    to_delete = [doc.paragraphs[i]._p for i in range(start + 1, end + 1)]
    p_start = doc.paragraphs[start]._p
    ppr = p_start.find(w("pPr"))
    for r in p_start.findall(w("r")):
        p_start.remove(r)
    for r in bibliography_field_runs(bibl_json):
        p_start.append(r)
    p_start.append(make_text_run(entries[str(1)]))
    new_paras = []
    for n in range(2, len(entries) + 1):
        np_ = etree.Element(w("p"))
        if ppr is not None:
            np_.append(etree.fromstring(etree.tostring(ppr)))
        np_.append(make_text_run(entries[str(n)]))
        new_paras.append(np_)
    end_p = etree.Element(w("p"))
    if ppr is not None:
        end_p.append(etree.fromstring(etree.tostring(ppr)))
    end_p.append(make_fldchar_run("end"))
    new_paras.append(end_p)
    anchor = p_start
    for np_ in reversed(new_paras):
        anchor.addnext(np_)
    for p in to_delete:
        p.getparent().remove(p)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Config-driven background Zotero field insertion")
    ap.add_argument("--docx", required=True, help="input DOCX (never modified)")
    ap.add_argument("--out", required=True, help="output DOCX")
    ap.add_argument("--config", required=True, help="JSON config")
    ap.add_argument("--items-file", help="optional item-data JSON override")
    ap.add_argument("--verify", action="store_true",
                    help="validate the output after saving")
    args = ap.parse_args(argv)

    with open(args.config, encoding="utf-8") as fh:
        config = json.load(fh)
    items = _load_items(config, args.items_file)
    library = config.get("library", "local")

    doc = Document(args.docx)
    snapshots = {}
    done = []
    for op in config.get("citations", []):
        done.append(_apply_op(doc, op, items, library, snapshots))
    if config.get("bibliography"):
        _apply_bibliography(doc, config, items, library)
        done.append(("bibliography", "-", "-", "-"))
    doc.save(args.out)

    print("applied %d operations -> %s" % (len(done), args.out))
    for d in done:
        print("  %-14s para=%-3s cached=%-8s keys=%s" % (d[0], d[1], d[2], d[3]))

    if args.verify:
        rep = validate_document(args.out)
        print("verify:", json.dumps(rep, ensure_ascii=False, indent=1))
        ok = (rep["json_bad"] == [] and rep["total_balance"] == 0
              and rep["zotero_bibl_fields"] == 1)
        if not ok:
            raise SystemExit("validation FAILED: " + json.dumps(rep, ensure_ascii=False))
        print("verify: OK")


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace")
    main()
