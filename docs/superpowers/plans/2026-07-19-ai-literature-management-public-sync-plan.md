# AI Literature Management Public Sync Implementation Plan

## 1. Establish The Public Baseline

- Record the current test and syntax status.
- Add temporary-directory fixtures for archive, category, and configuration tests.
- Preserve the existing Git history and do not push or rename the remote.

## 2. Generalize Configuration And Initialization

Files:

- `config.example.yaml`
- `init_project.py`
- `src/config.py`
- `.gitignore`
- `tests/test_config.py`
- `tests/test_init_project.py`

Work:

- Replace the committed runtime config with a generic example.
- Add interactive initialization with a non-interactive input layer for tests.
- Add environment overrides and relative-path resolution.
- Fail clearly when runtime configuration is missing or incomplete.
- Keep secrets out of configuration values.

## 3. Sync The Updated Processing Pipeline

Files:

- `run_weekly.py`
- `run_summary.py`
- `prepare_endnote_import.py`
- `src/archive_manager.py`
- `src/article_fetcher.py`
- `src/state_manager.py`
- `src/summary_manager.py`
- `scheduler.ps1`
- `scheduler_crawl_endnote.ps1`
- `scheduler_summary.ps1`

Work:

- Add the pending-summary queue and standalone summary runner.
- Add summary-index migration and categorized rendering.
- Add recent/full EndNote exports and attachment reports.
- Improve supplementary-link filtering.
- Derive scheduler roots from `$PSScriptRoot`.
- Rename generated groups and task labels to `AI Literature Management`.

## 4. Package The Four Skills

Files:

- `skills/literature-ingest/**`
- `skills/literature-locator/**`
- `skills/zotero-link-import/**`
- `skills/zotero-docx-paper-writing/**`

Work:

- Copy only source, references, scripts, metadata, and reusable assets.
- Remove caches, local configuration, tokens, prebuilt XPI files, and local state.
- Replace hard-coded roots with CLI/environment/project-config resolution.
- Make the Zotero installer accept or discover profile, executable, allowed root, and local config output.
- Inject the allowed root into the locally built plugin.
- Retain confirmation and mutation-safety gates.

## 5. Update Documentation And Tests

Files:

- `README.md`
- `README.zh.md`
- `.github/workflows/validate.yml`
- `tests/**`

Work:

- Use the new project name and bilingual language selector.
- Document initialization, crawl, summary, EndNote, and skill workflows.
- Add network-free tests for config, initialization, summary, EndNote, locator, and ingest helpers.
- Add skill structure and PowerShell parser checks where the platform supports them.

## 6. Validate And Review

- Run Python syntax checks and the full local test suite.
- Run PowerShell parser checks.
- Run each skill's available regression tests that do not mutate Zotero or Word.
- Execute initialization and archive workflows in temporary directories.
- Run the external privacy review against tracked files and generated public artifacts.
- Confirm no runtime config, token, profile, cache, download, or personal absolute path is tracked.
- Commit implementation locally without pushing.
