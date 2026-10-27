# Background (Scripted) Zotero Field Insertion

Use only when the user **explicitly requests** scripted/background conversion of
plain-text references into Zotero fields (e.g., 后台插入, "convert the
plain-text references to Zotero fields programmatically"). This path is an
exception to the native-plugin-only rule. Ordinary citation editing still goes
through the Zotero Word plugin.

## Hard Preconditions

1. User explicitly asked for background/scripted insertion.
2. Zotero is running; every cited item exists in the active Zotero library.
3. The DOCX already has valid `ZOTERO_PREF_1` in `docProps/custom.xml` with the
   intended style (e.g., `china-national-standard-gb-t-7714-2015-numeric`).
4. A verified backup exists (`scripts/backup_docx.ps1`).
5. After insertion, the document must receive a Zotero refresh before it is
   presented as final (guarded script, or the user clicks Refresh once).

## Workflow

1. **Inventory markers.** Scan body paragraphs for plain-text markers
   (`\[\d+(?:[,–—-]\d+)*\]`) and locate the reference-list paragraphs. Keep
   working notes that merely describe literature untouched unless asked.
2. **Resolve items in the Zotero library.**
   - Zotero locks `zotero.sqlite` while running: copy it to a temp file first
     (`shutil.copy2`), then query the copy.
   - Zotero 7/9 schema: `itemData` has no `value` column; join
     `itemDataValues v ON v.valueID = id.valueID`.
   - Missing items: import metadata via
     `POST http://127.0.0.1:23119/connector/saveItems` (expect 201), then
     re-extract the new item keys.
   - Record each item's key and numeric `itemID`, plus library key
     (e.g., a synthetic eight-character test key) for URIs.
3. **Compute citation numbering.** Numeric styles number items by **first
   appearance in document order**. Within a multi-item field, display numbers
   ascending, comma-separated (GB/T 7714-2015: `[1,2]`, `[4,5,6,7]` — no range
   dashes). Reused items keep their first number. Items in the reference list
   but never cited go to the bibliography `uncited` array, appended last.
4. **Insert citation fields.** Replace each marker run with five runs
   (`begin` → `instrText` → `separate` → superscript result → `end`). When
   scanning for later markers, **skip runs inside an already-inserted field**
   (a marker text like `[6]` can collide with an earlier field's cached result
   `[6]`; track `fldCharType="begin"/"end"` while scanning).
5. **Replace the reference list** with one bibliography field spanning
   paragraphs: `begin` + `instrText` + `separate` in the first paragraph, one
   paragraph per pre-rendered entry, and a final paragraph containing only the
   `end` run. Pre-render entries in the document's citation style, renumbered
   by appearance order with uncited items last.
6. **Verify.** Re-open with python-docx; `json.loads` every field code; check
   document-wide begin/end balance (the bibliography field legitimately spans
   paragraphs). Open in Word via COM (read-only) and confirm no repair prompt,
   field count, and rendered text. Confirm `ZOTERO_PREF_1` survived the save.
7. **Refresh.** Run `scripts/invoke_zotero_refresh_guarded.ps1`, or instruct
   the user to click Zotero → Refresh. Cached numbers are best-effort until
   Zotero re-renders them; never present the document as final pre-refresh.

## Recommended Tool: `scripts/zotero_field_builder.py`

The workflow above is automated by the reusable script
`scripts/zotero_field_builder.py` (library of field builders plus a
config-driven CLI). It was verified against Zotero 9.0.6 and a real
Word/Zotero round-trip.

### CLI usage

```powershell
python "<skill-dir>\scripts\zotero_field_builder.py" `
  --docx "input.docx" --out "output.docx" --config "config.json" --verify
```

- `--docx` input is never modified; `--out` receives the converted document
  (backup separately with `backup_docx.ps1` first).
- `--config` is the JSON operation plan; `--items-file` overrides the item-data
  path inside the config.
- `--verify` re-opens the output, parses every field code as JSON, checks
  document-wide begin/end balance, and fails on `json_bad != []`,
  `total_balance != 0`, or `zotero_bibl_fields != 1`. The bibliography field
  legitimately spans paragraphs, so its begin/end live on different paragraph
  indices; the validator reports them as the expected unbalanced pair.

### Config structure

```json
{
  "library": "EXAMPLE0",
  "items_file": "<path-to-items-data.json>",
  "citations": [
    {"paragraph": 6, "type": "marker", "marker": "[1,2]",
     "keys": ["EXAMPLE1", "EXAMPLE2"], "cached": "[1,2]"},
    {"paragraph": 9, "type": "remove_field"},
    {"paragraph": 28, "type": "parenthetical",
     "anchor_run": 18, "strip_tail_run": 18, "strip_head_run": 22,
     "delete_runs": [19, 20, 21],
     "keys": ["EXAMPLE3", "EXAMPLE4"], "cached": "[3,4]"}
  ],
  "bibliography": {
    "start": 38, "end": 55,
    "uncited": ["EXAMPLE5", "EXAMPLE6"],
    "entries": {"1": "[1] Author A, ...", "2": "[2] Author B, ..."}
  }
}
```

- `paragraph` is 0-based; `anchor_run`/`strip_tail_run`/`strip_head_run` are
  0-based run indices *within the paragraph at operation time*.
- `marker` replaces a `[n]`/`[n,m]` plain-text marker run with a citation
  field; `remove_field` removes a stale field at the paragraph; `parenthetical`
  strips `（`/`）` run tails/heads, deletes the runs between them, and inserts
  the field after `anchor_run`.
- `bibliography.entries` are pre-rendered GB/T 7714 strings numbered by first
  appearance with uncited items last; `bibliography.uncited` are item keys
  appended after cited entries.
- `items_file` is the extracted Zotero item data:

```json
{
  "EXAMPLE1": {
    "itemID": 1234, "key": "EXAMPLE1", "zoteroType": "journalArticle",
    "fields": {"title": "...", "publicationTitle": "...", "volume": "16",
               "pages": "11497-11519", "date": "2016-09-02 2016-09-02",
               "DOI": "10.5194/acp-16-11497-2016", "url": "...", "issue": "17"},
    "creators": [["Fioletov", "Vitali E.", "author"], ["McLinden", "C. A.", "author"]]
  }
}
```

  Extract it from a copy of `zotero.sqlite` (Workflow step 2); the script never
  touches the live database.

### Use as a library

```python
from zotero_field_builder import (
    build_item_data, make_citation_json, make_bibliography_json,
    citation_field_runs, bibliography_field_runs, replace_marker_with_field,
    remove_first_field, make_gb7714_entry, validate_document,
)
```

Run with the skill directory on `sys.path` (or copy the module next to your
script); it requires `python-docx` and `lxml`.

## Field Code Formats (verified against Zotero 9.0.6 `integration.js`)

The fenced examples omit an invisible final ASCII space. The actual `instrText`
must begin and end with U+0020; `zotero_field_builder.py` adds both spaces.

Citation field `instrText` (leading/trailing spaces matter):

```text
 ADDIN ZOTERO_ITEM CSL_CITATION {"citationID":"Ab12cdEf","properties":{"unsorted":false,"formattedCitation":"\\super [1,2]\\nosupersub{}","plainCitation":"[1,2]","noteIndex":0},"citationItems":[{"id":1234,"uris":["http://zotero.org/users/local/EXAMPLE0/items/EXAMPLE1"],"itemData":{"id":1234,"type":"article-journal","title":"...","container-title":"Atmospheric Chemistry and Physics","volume":"16","issue":"17","page":"11497-11519","issued":{"date-parts":[[2016,9,2]]},"DOI":"10.5194/acp-16-11497-2016","author":[{"family":"Fioletov","given":"Vitali E."}]}}],"schema":"https://github.com/citation-style-language/schema/raw/master/csl-citation.json"}
```

- `formattedCitation` stores `\super [n]\nosupersub{}` (JSON-escaped as
  `\\super ... \\nosupersub{}`); `plainCitation` must equal the field result
  text or Zotero prompts "citation changed" on refresh.
- `citationItems[].id` is the library `itemID`; `uris` is
  `http://zotero.org/users/local/<LIBKEY>/items/<ITEMKEY>`. `itemData` is a
  fallback that Zotero replaces from the library on refresh — keep it valid
  CSL JSON but do not rely on it.
- CSL type map: `journalArticle`→`article-journal`,
  `conferencePaper`→`paper-conference`, `preprint`→`article`. Field map:
  `publicationTitle`/`proceedingsTitle`→`container-title`,
  `conferenceName`→`event-title`, `pages`→`page`, `date`→`issued.date-parts`
  (drop `00` parts), `url`→`URL`, creators→`author:[{family,given}]`.

Bibliography field `instrText`:

```text
 ADDIN ZOTERO_BIBL {"uncited":[["http://zotero.org/users/local/EXAMPLE0/items/EXAMPLE3"],["http://zotero.org/users/local/EXAMPLE0/items/EXAMPLE4"]],"omitted":[],"custom":[]} CSL_BIBLIOGRAPHY
```

- `uncited` is an array of URI-arrays (one entry per uncited item, in the order
  they should appear after cited items). `omitted`/`custom` stay empty unless
  the bibliography dialog set them.

Citation field OOXML layout (one run per line):

```xml
<w:r><w:fldChar w:fldCharType="begin"/></w:r>
<w:r><w:instrText xml:space="preserve"> ADDIN ZOTERO_ITEM CSL_CITATION {...} </w:instrText></w:r>
<w:r><w:fldChar w:fldCharType="separate"/></w:r>
<w:r><w:rPr><w:rFonts w:cs="Times New Roman"/><w:kern w:val="0"/><w:vertAlign w:val="superscript"/></w:rPr><w:t>[1,2]</w:t></w:r>
<w:r><w:fldChar w:fldCharType="end"/></w:r>
```

## Windows / Encoding Pitfalls

- Non-ASCII (Chinese) paths are corrupted when piped through PowerShell stdin;
  write Python scripts with
  `[System.IO.File]::WriteAllText(path, $content, [System.Text.UTF8Encoding]::new($false))`
  and pass paths as arguments or embed them in the script file.
- PowerShell 5.1 reads `.ps1` as ANSI without a BOM: write Word COM scripts
  with a UTF-8 BOM (`UTF8Encoding::new($true)`) when they contain Chinese paths.
- `Remove-Item` may be blocked by policy; delete files from Python
  (`os.remove` / `shutil`).
- The Zotero database is locked while Zotero runs; always query a copy.

## Verification Checklist

- [ ] Backup verified before mutation.
- [ ] Every field code parses as JSON.
- [ ] Document-wide `begin`/`end` field balance is zero.
- [ ] Word COM opens the file with no repair prompt; field count matches
      expected (`#citations + 1 bibliography`).
- [ ] `ZOTERO_PREF_1` unchanged in `docProps/custom.xml`.
- [ ] After refresh: bibliography entries and in-text numbers agree; newly
      cited items appear; uncited items still present.
