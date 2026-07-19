# Zotero Word Safety

## Supported Path

Use Zotero's native Word integration to create, edit, refresh, and remove citations and bibliographies. Ensure every cited library item exists in the active Zotero library before insertion.

Use one Word instance and one target manuscript for each Zotero operation. Close disposable source documents before refreshing the target.

`Word.Application.Run('ZoteroRefresh')` returning does not prove that Zotero has finished. The integration continues asynchronously and a second command during that interval can display "A word processor integration command is already running." Serialize automated commands globally and use `scripts/invoke_zotero_refresh_guarded.ps1` for refresh. The guard refuses concurrent commands and existing Word or warning windows, invokes refresh exactly once, waits at least five seconds, requires a stable field fingerprint across multiple samples, and saves only after successful settling.

## Prohibited Operations

Do not:

- Synthesize `ADDIN ZOTERO_ITEM CSL_CITATION` or `ADDIN ZOTERO_BIBL` field codes.
- Create, concatenate, split, or edit `ZOTERO_PREF_*` custom properties.
- Copy dynamic citation fields from another DOCX by OOXML, COM, or clipboard automation.
- Write directly to `zotero.sqlite`.
- Repeatedly invoke refresh in hidden Word instances.
- Call `$word.Run('ZoteroRefresh')` outside the guarded refresh script.
- Delete and recreate a bibliography through automation after an integration error.

These operations can leave valid-looking cached numbers while Zotero's citation processor and bibliography remain stale.

## Preflight

Before a citation operation:

1. Confirm Zotero is running and the required items exist.
2. Confirm the target document is the only document receiving Zotero commands.
3. Confirm the document has valid Zotero preferences and existing citations are readable.
4. Create and verify a backup.
5. Record the initial field count and bibliography presence.

## Postflight

After native insertion or editing:

1. Refresh once. Automated refresh must use `scripts/invoke_zotero_refresh_guarded.ps1`; do not interpret the macro return as completion.
2. Confirm newly cited works appear in the bibliography.
3. Confirm citations after the edit were renumbered consistently.
4. Confirm citation fields remain Word ADDIN fields and no field displays an error.
5. Save, close, reopen, and recheck the document when risk is material.

When the scope audit reports a citation-field count change, authorize it only if the native Zotero operation intentionally added or removed citations. A prose-edit anchor must not silently authorize field loss.
Do not automatically ignore `ZOTERO_PREF_*` changes. If the native plugin updates `docProps/custom.xml`, review that part explicitly before authorizing it with `-AllowedPartPattern`.

## Isolated Rendering

Do not render a Zotero-enabled manuscript through `ExportAsFixedFormat` in a
normal Word COM session. Some installations route printing or export through
the loaded `Zotero.dotm` template even when fields are locked, which can hang
Word or alter field-related package parts.

Use `scripts/render_docx_without_zotero.ps1` after closing all Word windows. It
starts a separate worker process for each DOCX so add-in state and COM objects
cannot leak between files. The script must:

1. Refuse to attach to an existing Word process.
2. Record the source DOCX SHA-256 hashes.
3. Temporarily set the Zotero Word add-in to not installed and verify the
   add-in reports `Installed = false`. Do not enumerate `Word.Templates` after
   unloading it; retained template COM references can block PDF conversion.
4. Open each source read-only and create PDF through `SaveAs2` with format 17.
   Give the PDF a `.rendered.pdf` suffix; using the DOCX basename unchanged can
   leave Word blocked inside `SaveAs2` on affected installations.
5. Close without saving, restore the add-in state, quit Word, and verify the
   source hashes are unchanged.

Treat a missing PDF, changed source hash, failure to disable the add-in, or
failure to restore the add-in as a delivery-gate failure.

## First-Error Rule

On the first Zotero integration error:

1. Stop all automated citation commands.
2. Preserve the pre-edit backup.
3. Save a diagnostic copy only when it cannot overwrite the baseline.
4. Record the visible error, operation, active document, and field count.
5. Check for multiple Word instances, manually generated fields, copied fields, missing library items, stale bibliography content, and malformed Zotero preferences.
6. Diagnose on a disposable copy.
7. Restore the verified backup when citation numbers or the bibliography are inconsistent.

The guard reads `MozillaDialogClass` windows through UI Automation. A window whose text matches the known busy or error message ends the attempt immediately. An unlabelled Zotero progress window may exist temporarily, but it must close before field stability can pass; if it remains open, the guard times out and closes the document without saving. Do not dismiss a warning and retry within the same automation attempt.

Do not describe the manuscript as complete until citation fields, visible numbers, and bibliography entries agree.
