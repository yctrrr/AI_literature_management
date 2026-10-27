---
name: zotero-docx-paper-writing
description: Orchestrate evidence-backed academic paper drafting and revision when the requested deliverable is a Word/DOCX manuscript with Zotero-managed citations. Use for new or existing .docx papers that require Zotero citation insertion or refresh, bibliography maintenance, targeted prose revision, native Word equations, equation numbering, tables, captions, supplementary Word documents, backup, change auditing, or final rendered verification.
---

# Zotero DOCX Paper Writing

Coordinate the full paper workflow without replacing specialist literature, writing, DOCX, or Zotero skills. Treat an existing manuscript as the authoritative content source and preserve every part outside the user's explicit request.

## Hard Gates

Before changing any manuscript:

1. Read the nearest `AGENTS.md` in the target document's directory or its parents.
2. Write an edit-scope allowlist containing target files, headings or paragraph anchors, citation permission, bibliography permission, supplementary-file permission, and builder permission.
3. Save the current document and run `scripts/backup_docx.ps1` on every authorized DOCX.
4. Draft revised prose outside the final DOCX before applying it to an existing manuscript.
5. For equation, table, figure, caption, or heading changes, record the existing structure and numbering; follow `references/word-equation-layout-harness.md`.

Never:

- Change text outside the declared scope.
- Run a manuscript builder unless explicitly authorized for the current task.
- Replace the current manuscript with output from a stale source script.
- Construct or edit `ADDIN ZOTERO_*` fields or `ZOTERO_PREF_*` properties manually, unless the user explicitly requests background/scripted insertion and you follow `references/background-zotero-insertion.md` end-to-end with `scripts/zotero_field_builder.py` (backup, library verification, field-balance checks, mandatory post-insertion refresh).
- Copy Zotero dynamic fields between documents by OOXML, COM `FormattedText`, or clipboard automation.
- Invoke `$word.Run('ZoteroRefresh')` directly from automation; use `scripts/invoke_zotero_refresh_guarded.ps1`.
- Continue automated Zotero operations after the first integration error.

## Route The Task

- **New draft:** build the evidence base, draft by section, create the DOCX, then add citations natively.
- **Targeted revision:** preserve the current DOCX, define exact anchors, revise only those ranges, and audit every difference.
- **Citation maintenance:** edit one target document through the Zotero Word plugin and verify downstream numbering and bibliography entries.
- **Background (scripted) insertion:** only when the user explicitly asks to convert plain-text references into Zotero fields programmatically (后台插入). Follow `references/background-zotero-insertion.md`; prefer the reusable `scripts/zotero_field_builder.py` (config-driven CLI or library) for field construction, verify the output, then refresh; never use it for ordinary citation editing, and never present cached numbers as final before a Zotero refresh.
- **Submission check:** audit scope, fields, references, styles, and every rendered page without broadening the prose task.
- **Math and layout:** use editable native Word equations. For numbered display equations, use a borderless two-column table with the equation on the left and number on the right; follow `references/word-equation-layout-harness.md` for numbering, captions, tables, and headings.

### User-authorized background mode

When the user explicitly authorizes background Zotero insertion, use the scripted background route for that task and do not control the Word or Zotero foreground UI. Unrelated Word documents may remain open and must stay unchanged. Before a required refresh, ensure only the target DOCX is closed; the guard must also prove that its controlled Word process is isolated from every pre-existing Word process. If the target is open/locked or isolation cannot be proved, preserve the verified background output and stop without saving; do not close unrelated documents or switch to UI automation unless the user later requests it.

Read [references/workflow.md](references/workflow.md) for every task. Read [references/zotero-word-safety.md](references/zotero-word-safety.md) whenever the document contains or will receive Zotero citations. Read [references/background-zotero-insertion.md](references/background-zotero-insertion.md) only when background/scripted insertion is explicitly requested.
Read [references/word-equation-layout-harness.md](references/word-equation-layout-harness.md) whenever creating, editing, or reviewing equations, equation numbers, data tables, figures, captions, or headings. Its examples are reusable conventions, not files to load in future projects.

## Coordinate Specialist Skills

Use available specialist skills rather than duplicating them:

- Use `literature-search` and `literature-locator` for external and local evidence discovery.
- Use `literature-ingest` and `zotero-link-import` when sources must be acquired or organized.
- Use `research-paper-writing` for section logic, paragraph roles, and claim-evidence alignment.
- Use `docx` or the environment's document skill for Word editing and render verification.

Follow every selected skill's instructions. This skill supplies the sequencing and mutation boundaries.

## Backup And Audit

Create a verified backup:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\backup_docx.ps1" `
  -Path "<manuscript.docx>", "<supplement.docx>" `
  -Label "before_targeted_revision"
```

Audit a targeted paragraph replacement:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\audit_docx_scope.ps1" `
  -Before "<backup.docx>" `
  -After "<edited.docx>" `
  -AllowedAnchor "<original paragraph opening>" `
  -AllowCitationChanges `
  -AllowBibliographyChanges
```

Use `-AllowedSection` for an explicitly authorized whole section. Treat exit code `2` as an unauthorized-change failure.
Use `-AllowedPartPattern` only for explicitly authorized non-body package changes such as a named header, style, or metadata part.
Use `-AllowCitationFieldCountChanges` only when native Zotero operations intentionally added or removed citation fields; ordinary prose scope does not authorize field loss.

Run an automated Zotero refresh only through the serialized guard:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\invoke_zotero_refresh_guarded.ps1" `
  -Path "<manuscript.docx>" `
  -ReportPath "<refresh-report.json>"
```

The guard requires Zotero to be running and the target DOCX to be closed. Other Word instances may remain open: the guard records their process IDs, refuses to attach to them, verifies that its controlled Word process is new and isolated, invokes refresh once, waits for asynchronous field processing to settle, and saves only on success.

## Delivery Gate

Deliver only after all checks pass:

- Every changed block maps to an allowed anchor or section, necessary citation renumbering, or an authorized bibliography update.
- Zotero citations and the bibliography agree; newly cited items appear in the references.
- The document field count is plausible and no field displays an error.
- Every page has been rendered and visually inspected.
- Changed equations remain editable native Word math; equation numbers, captions, tables, headings, and relevant cross-references pass the layout checks.
- The final report identifies modified anchors, citation changes, backup location, and verification results.

If a gate fails, retain the verified backup, stop mutation, and report the unresolved condition.

For DOCX files containing Zotero fields on Windows, render with
`scripts/render_docx_without_zotero.ps1`. Only the target DOCX must be closed
and unlocked; unrelated Word documents may remain open and must stay unchanged.
The renderer must prove that its Word automation process is newly owned before
changing add-in state or opening a document. If isolation cannot be proved, it
must stop without quitting a pre-existing Word process. It unloads `Zotero.dotm`
only in its isolated Word session, uses Word's PDF `SaveAs2` path, restores the
add-in state, and verifies that rendering did not change the source DOCX hashes. Do not use
`ExportAsFixedFormat` after a normal Zotero-enabled Word session has hung or
triggered field processing.
