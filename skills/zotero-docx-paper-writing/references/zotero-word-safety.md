# Zotero Word Safety

## Supported Path

Use Zotero's native Word integration to create, edit, refresh, and remove citations and bibliographies. Ensure every cited library item exists in the active Zotero library before insertion.

Use one isolated, automation-owned Word instance and one target manuscript for each automated Zotero operation. The target DOCX must be closed before refresh. Unrelated documents may remain open in pre-existing Word instances; never attach to, save, close, or quit those instances.

`Word.Application.Run('ZoteroRefresh')` returning does not prove that Zotero has finished. The integration continues asynchronously and a second command during that interval can display "A word processor integration command is already running." Serialize automated commands globally and use `scripts/invoke_zotero_refresh_guarded.ps1` for refresh. The guard refuses concurrent commands, an open/locked target, pre-existing Zotero warning windows, and any Word COM instance whose process ID is not newly owned by the guard. It permits unrelated Word instances to remain open, invokes refresh exactly once, waits at least five seconds, requires a stable field fingerprint across multiple samples, and saves only after successful settling.

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

Exception — background (scripted) insertion: the synthesis prohibition is lifted only when the user explicitly requests scripted/background conversion of plain-text references and `background-zotero-insertion.md` is followed end-to-end. That procedure still requires a verified backup, library-item verification, field-balance validation, and a mandatory guarded (or interactive) refresh afterward. Inserted numbers are cached best-effort renders; treat the document as unfinished until Zotero refresh re-renders citations and the bibliography and they agree.

## Preflight

Before a citation operation:

1. Confirm Zotero is running and the required items exist.
2. Confirm the target document is closed and is the only document receiving Zotero commands. Unrelated Word documents may remain open.
3. Confirm the document has valid Zotero preferences and existing citations are readable.
4. Create and verify a backup.
5. Record the initial field count and bibliography presence.

The automated guard must check the target's Word owner file and exclusive file access before launching Word, then compare Word process IDs before and after COM creation. Exactly one new process must appear and its command line must identify it as an automation instance (`/Automation` or `-Embedding`). If ownership cannot be proved, release the COM reference without calling `Quit()` and fail without saving. After opening the target, also fail if Word reports it as read-only.

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

Use `scripts/render_docx_without_zotero.ps1` after closing only the target DOCX.
Unrelated Word documents may remain open and must not be touched. The renderer
starts a separate worker process for each DOCX so add-in state and COM objects
cannot leak between files. The script must:

1. Check the target's Word owner file and exclusive file access. Record existing
   Word process IDs before COM creation; prove that the COM instance belongs to
   exactly one new Word automation process (`/Automation` or `-Embedding`) before
   changing add-in state or opening the target. If ownership cannot be proved,
   release the COM reference without calling `Quit()`.
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
