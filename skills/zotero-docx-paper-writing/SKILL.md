---
name: zotero-docx-paper-writing
description: Orchestrate evidence-backed academic paper drafting and revision when the requested deliverable is a Word/DOCX manuscript with Zotero-managed citations. Use for new or existing .docx papers that explicitly require Zotero citation insertion or refresh, bibliography maintenance, targeted prose revision with dynamic references, supplementary Word documents, backup, change auditing, or final rendered verification.
---

# Zotero DOCX Paper Writing

Coordinate the full paper workflow without replacing specialist literature, writing, DOCX, or Zotero skills. Treat an existing manuscript as the authoritative content source and preserve every part outside the user's explicit request.

## Hard Gates

Before changing any manuscript:

1. Read the nearest `AGENTS.md` in the target document's directory or its parents.
2. Write an edit-scope allowlist containing target files, headings or paragraph anchors, citation permission, bibliography permission, supplementary-file permission, and builder permission.
3. Save the current document and run `scripts/backup_docx.ps1` on every authorized DOCX.
4. Draft revised prose outside the final DOCX before applying it to an existing manuscript.

Never:

- Change text outside the declared scope.
- Run a manuscript builder unless explicitly authorized for the current task.
- Replace the current manuscript with output from a stale source script.
- Construct or edit `ADDIN ZOTERO_*` fields or `ZOTERO_PREF_*` properties manually.
- Copy Zotero dynamic fields between documents by OOXML, COM `FormattedText`, or clipboard automation.
- Invoke `$word.Run('ZoteroRefresh')` directly from automation; use `scripts/invoke_zotero_refresh_guarded.ps1`.
- Continue automated Zotero operations after the first integration error.

## Route The Task

- **New draft:** build the evidence base, draft by section, create the DOCX, then add citations natively.
- **Targeted revision:** preserve the current DOCX, define exact anchors, revise only those ranges, and audit every difference.
- **Citation maintenance:** edit one target document through the Zotero Word plugin and verify downstream numbering and bibliography entries.
- **Submission check:** audit scope, fields, references, styles, and every rendered page without broadening the prose task.

Read [references/workflow.md](references/workflow.md) for every task. Read [references/zotero-word-safety.md](references/zotero-word-safety.md) whenever the document contains or will receive Zotero citations.

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

The guard requires Zotero to be running and all Word instances to be closed. It invokes refresh once, waits for asynchronous field processing to settle, and saves only on success.

## Delivery Gate

Deliver only after all checks pass:

- Every changed block maps to an allowed anchor or section, necessary citation renumbering, or an authorized bibliography update.
- Zotero citations and the bibliography agree; newly cited items appear in the references.
- The document field count is plausible and no field displays an error.
- Every page has been rendered and visually inspected.
- The final report identifies modified anchors, citation changes, backup location, and verification results.

If a gate fails, retain the verified backup, stop mutation, and report the unresolved condition.

For DOCX files containing Zotero fields on Windows, render with
`scripts/render_docx_without_zotero.ps1`. It unloads `Zotero.dotm` only for an
isolated Word session, uses Word's PDF `SaveAs2` path, restores the add-in state,
and verifies that rendering did not change the source DOCX hashes. Do not use
`ExportAsFixedFormat` after a normal Zotero-enabled Word session has hung or
triggered field processing.
