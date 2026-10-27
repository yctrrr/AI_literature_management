---
name: literature-ingest
description: Download and organize academic articles, PDFs, supplementary files, datasets, and source-page text into a configured local literature library. Use when a user provides a title, DOI, arXiv identifier, publisher URL, preprint URL, or article page and wants an agent to retrieve files, check duplicates, classify them into existing topic folders, and optionally delegate a confirmed Zotero linked-file import.
---

# Literature Ingest

Acquire and organize literature without assuming a machine-specific library path.

## Required Workflow

1. Resolve metadata and public or user-authorized download links.
2. Resolve the literature root from `--root`, `AI_LITERATURE_LIBRARY_ROOT`, `AI_LITERATURE_CONFIG`, an optional skill-local `config.local.json`, or the current project's `config.yaml`. Keep personal paths in configuration, not in this skill.
3. Run `scripts/literature_ingest_helper.py inspect` before downloading.
4. Stop on plausible duplicates and ask whether to reuse, continue, or cancel.
5. Show the proposed category and files, then obtain confirmation before writing.
6. Download explicit URLs only after confirmation.
7. Obtain separate confirmation before any Zotero operation.

## Inspect

```powershell
python "<skill-dir>\scripts\literature_ingest_helper.py" inspect `
  --root "<literature-root>" `
  --title "Paper title" `
  --doi "10.xxxx/example" `
  --source-url "https://example.org/article" `
  --category "Existing category"
```

Omit `--root` only when the environment, local configuration, or project configuration supplies it.

## Download

```powershell
python "<skill-dir>\scripts\literature_ingest_helper.py" download `
  --target-dir "<literature-root>\<category>" `
  --title "Paper title" `
  --year "2024" `
  --first-author "First author" `
  --source-url "https://example.org/article" `
  --file-url "pdf=https://example.org/paper.pdf" `
  --file-url "supplement=https://example.org/supplement.zip" `
  --write-manifest
```

Create a paper subfolder when multiple files are present or names would collide. Preserve existing files unless overwrite was explicitly approved.

## Classification

- Prefer the best existing topic folder from the configured library.
- Base classification on the paper's methods, evidence, and research question.
- Do not encode a private taxonomy in this reusable skill.
- Use an existing general fallback such as `others` only when no category fits.

## Zotero

After explicit confirmation, delegate an existing local PDF to the background `zotero-link-import` client. Require a `created`, `reused`, or explained `partially_created` response and verify it through the returned receipt or a read-only API. Do not use Computer Use for supported imports or routine verification. The current client supports PDF only. For a supplementary DOCX, keep the original and use `scripts/convert_docx_supplement.py` to export a checked `Supp-<journal-abbreviation>-<first-author>-<year>-<short-title>.pdf` in the same literature folder; preserve the DOCX stem when it is already standardized. Verify pages and headings/tables, then import the PDF with the paper DOI and exact collection, checking that it joins the existing parent and a repeat call returns `reused`. Do not overwrite an existing PDF or convert ordinary manuscript DOCX files. If conversion or verification fails, report the local DOCX and limitation. Use Zotero's UI only when the user explicitly requests or authorizes that fallback. Never edit `zotero.sqlite` directly.

## Safety

- Do not bypass paywalls or access controls.
- Confirm before downloads when duplicates exist.
- Confirm before writing outside the configured root.
- Confirm before any Zotero modification.
- Do not delete, move, or overwrite existing files without explicit approval.
