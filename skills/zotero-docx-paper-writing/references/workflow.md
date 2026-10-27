# Paper Workflow

## 1. Establish Authority And Scope

1. Read the user's latest request and the nearest governing `AGENTS.md`.
2. Treat the current DOCX as authoritative unless the user explicitly authorizes regeneration from a named source.
3. Record an allowlist:
   - Target DOCX files.
   - Editable headings, paragraph openings, captions, tables, or metadata.
   - Whether citation insertion and bibliography refresh are allowed.
   - Whether supplementary files may change.
   - Whether a builder may run.
4. Keep every unlisted file and range read-only.

## 2. Capture A Baseline

1. Ensure the user-visible Word document is saved.
2. Run `backup_docx.ps1` and retain its manifest.
3. Record paragraph text, page count, Zotero field count, and bibliography presence.
4. For math or layout work, capture a read-only structural baseline with `scripts/audit_word_math_layout.py`: native equations, numbered equation tables, captions, data tables, and heading styles.
5. Do not use a backup created after mutation as the baseline.

## 3. Build The Evidence Base

1. Locate relevant local sources before adding external sources.
2. Search externally for missing claim support.
3. Verify titles, DOIs, study units, methods, and the exact claim each source supports.
4. Add required sources to Zotero before inserting citations.
5. Maintain a compact claim-evidence map; weaken or remove claims that remain unsupported.

## 4. Draft Or Revise

### New Draft

1. Establish the paper story, target journal, section outline, and terminology.
2. Draft one paragraph role at a time.
3. Create the DOCX only after the section structure is stable.
4. Add Zotero citations through the native Word integration.

### Existing Manuscript

1. Extract the requested section and adjacent paragraphs for context.
2. Draft the replacement outside the final DOCX.
3. Check paragraph role, flow, terminology, and claim support.
4. Replace only the declared Word range while preserving styles.
5. Do not rebuild the document to make a local edit.
6. For equations, tables, figures, captions, and headings, follow `word-equation-layout-harness.md` and preserve established styles outside the authorized edit.

## 5. Manage Zotero Citations

1. Read `zotero-word-safety.md`.
2. Open one target document in one Word instance.
3. Insert or edit citations through the Zotero Word plugin.
4. For automation, close the target DOCX and run `scripts/invoke_zotero_refresh_guarded.ps1`; unrelated Word documents may remain open and must stay unchanged. The guard must use a newly owned Word process and must never attach to or quit a pre-existing one. Never call `$word.Run('ZoteroRefresh')` directly. For an interactive session, click Zotero Refresh once after citation operations are complete and wait for it to finish.
5. Verify citation order, later citations, and the bibliography.
6. For background/scripted conversion of plain-text references (only when explicitly requested), follow `background-zotero-insertion.md` instead of the plugin dialog, then refresh exactly once and re-verify.

## 6. Audit The Mutation

1. Run `audit_docx_scope.ps1` against the verified backup.
2. Review every changed block, including headings, captions, tables, references, and supplementary files.
3. Review every changed package part, including styles, headers, footers, media, relationships, and metadata. Authorize a part pattern only when the request requires it.
4. Allow only:
   - Declared prose or object changes.
   - Necessary Zotero citation-number changes.
   - Authorized bibliography changes.
5. Restore the backup when unexplained changes cannot be removed safely.
6. For math or layout work, compare structural audits before and after editing; investigate missing native equations, changed numbers, caption movement, and unexpected table or style changes.

## 7. Verify The Deliverable

1. Validate the DOCX package and Zotero field presence.
2. On Windows, render Zotero-enabled DOCX files with `scripts/render_docx_without_zotero.ps1`; otherwise use the applicable document skill.
3. Inspect for clipping, overlap, broken fields, unexpected blank pages, and formatting drift.
4. Confirm changed equations remain editable in Word; inspect the borderless equation table, right-side number, captions, and tables in the final render.
5. Report the exact files changed, allowed anchors used, citation impact, backup path, and tests performed.

## Skill Regression Test

Run `scripts/test_skill.ps1` after changing the backup, audit, or guarded-refresh logic. It builds disposable DOCX packages in a temporary directory and does not open Word or Zotero.

## Mode Boundaries

- A prose-review request does not authorize DOCX mutation.
- A main-manuscript request does not authorize supplementary-file changes.
- Citation permission does not authorize replacing citation fields manually, except when the user explicitly requests background/scripted insertion and `background-zotero-insertion.md` is followed end-to-end.
- Builder permission must name the builder or clearly authorize whole-document regeneration.
- A Zotero error ends automated citation mutation for that attempt.
