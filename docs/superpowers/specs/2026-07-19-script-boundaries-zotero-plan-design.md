# Script Boundaries And Zotero Plan Design

## Goal

Keep application entry points at the repository root, move Windows scheduler
implementations into `weekly-literature-crawl`, remove the duplicate scheduler
alias, and add a read-only `prepare_zotero_import.py` application entry point.

## Repository Boundaries

Keep these application entry points at the repository root:

- `init_project.py`
- `run_weekly.py`
- `run_summary.py`
- `prepare_endnote_import.py`
- `prepare_zotero_import.py`

Move the scheduler implementations to:

```text
skills/weekly-literature-crawl/scripts/scheduler_crawl_endnote.ps1
skills/weekly-literature-crawl/scripts/scheduler_summary.ps1
```

Retain `scheduler_crawl_endnote.ps1` and `scheduler_summary.ps1` at the root as
compatibility wrappers that forward parameters to the skill scripts. Delete
the duplicate `scheduler.ps1` alias.

## Zotero Import Plan

`prepare_zotero_import.py` reuses the archive record and attachment discovery
logic from `prepare_endnote_import.py`. It never loads Zotero client
configuration and never calls Zotero.

Supported inputs:

- `--config`
- `--archive-root`
- `--output-dir`
- `--since-days`
- `--all`

Default output directory:

```text
<archive-root>/_zotero_import/
```

Generated files:

- `AI_literature_management_zotero_<timestamp>.json`
- `AI_literature_management_zotero_<timestamp>.csv`
- `AI_literature_management_zotero_latest.json`
- `AI_literature_management_zotero_latest.csv`

Each record contains:

- stable record identifier;
- title, DOI, source URL, and year;
- resolved PDF path and supplementary attachment paths;
- proposed Zotero collection derived from the final archive category;
- `status: ready_for_review`;
- `zotero_duplicate_check: not_run`.

Only finalized category records are included. Internal directories, including
`_pending_summary`, are excluded. Missing PDFs remain excluded by the shared
archive loader.

## Skill Integration

Add `zotero-plan` to `weekly_literature_crawl.py`. It forwards only to
`prepare_zotero_import.py` and supports recent or full plan generation. It
does not require a Zotero token, plugin, or confirmation because it does not
modify Zotero.

Update `weekly-literature-crawl/SKILL.md`, `README.md`, and `README.zh.md` with
the new command, scheduler locations, compatibility wrappers, and the
separation between plan generation and confirmed Zotero import.

## Safety

- Do not read or emit Zotero endpoint tokens.
- Do not query or modify Zotero.
- Do not copy, move, rename, or delete literature files.
- Write generated manifests only under the selected output directory.
- Require a separate confirmed `zotero-link-import` operation for actual
  Zotero changes.

## Validation

- Add network-free tests for record filtering, category mapping, JSON/CSV
  output, latest-file refresh, and `zotero-plan` forwarding.
- Parse all PowerShell scripts and test wrapper parameter forwarding without
  registering a task.
- Run the full repository tests, all skill validators, the DOCX safety suite,
  a staged release privacy audit, and a read-only code review.
- Do not start Zotero, a browser, an LLM, or Windows Task Scheduler.
