# AI Literature Management

<!-- README-I18N:START -->

**English** | [中文](./README.zh.md)

<!-- README-I18N:END -->

AI Literature Management is a local-first workflow for discovering, downloading, organizing, locating, summarizing, and citing academic literature. The automated crawler currently targets Nature-platform articles, while bundled agent skills support broader DOI, arXiv, publisher, local-library, Zotero, and DOCX workflows.

## Features

- Discovers Nature articles from configurable feeds and controlled search fallback.
- Filters journal names before applying the per-run article limit.
- Downloads accessible PDFs and the first real supplementary attachment.
- Separates crawl/EndNote export from LLM classification and summary generation.
- Places new papers in `_pending_summary` until the summary task processes them.
- Maintains a structured `summary_index.json` and categorized Markdown summary.
- Produces recent or full RIS/ENW import packages and attachment reports.
- Avoids duplicate downloads using DOI, source URL, metadata, and filenames.
- Includes four reusable agent skills for ingestion, local search, Zotero linked imports, and citation-safe DOCX writing.
- Uses initialized local configuration instead of machine-specific default paths.

## Architecture

```text
AI_literature_management/
  config.example.yaml
  init_project.py
  run_weekly.py
  run_summary.py
  prepare_endnote_import.py
  scheduler_crawl_endnote.ps1
  scheduler_summary.ps1
  src/
  skills/
    literature-ingest/
    literature-locator/
    zotero-link-import/
    zotero-docx-paper-writing/
  tests/
```

## Setup

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
pip install -r requirements.txt
playwright install chromium
python .\init_project.py
```

The initializer asks for:

- Main literature-library root.
- Existing category-source directory.
- Automated archive directory.
- Optional persistent browser profile.
- LLM provider, model, base URL, and API-key environment-variable name.
- Optional Zotero linked-file root.

It creates a local `config.yaml`. The file is ignored by Git. API keys and Zotero tokens are never written into the public template.

Set the environment variable selected during initialization before summary runs:

```powershell
$env:LLM_API_KEY = "..."
```

## Configuration

`config.example.yaml` documents every setting. Explicit environment overrides are available:

- `AI_LITERATURE_CONFIG`
- `AI_LITERATURE_LIBRARY_ROOT`
- `AI_LITERATURE_CATEGORY_SOURCE`
- `AI_LITERATURE_ARCHIVE_ROOT`
- `AI_LITERATURE_BROWSER_PROFILE`
- `ZOTERO_LINK_ALLOWED_ROOT`

Command-line path arguments take precedence over environment and project configuration.

## Commands

Discover candidates without downloading:

```powershell
python .\run_weekly.py --config .\config.yaml --dry-run
```

Download new papers, leave them pending, and refresh the recent EndNote package:

```powershell
python .\run_weekly.py --config .\config.yaml --headless false
```

Classify and summarize pending papers:

```powershell
python .\run_summary.py --config .\config.yaml
```

Run crawl, classification, and summary together for debugging:

```powershell
python .\run_weekly.py --config .\config.yaml --headless false --summarize
```

Rebuild the summary index without crawling or calling an LLM:

```powershell
python .\run_weekly.py --config .\config.yaml --rebuild-summary
```

Export recent EndNote records:

```powershell
python .\prepare_endnote_import.py --config .\config.yaml --since-days 7
```

Export the full archive:

```powershell
python .\prepare_endnote_import.py --config .\config.yaml --all
```

## Agent Skills

The repository includes:

- `literature-ingest`: resolve, duplicate-check, classify, and download literature after confirmation.
- `literature-locator`: find local papers and likely supplements without modifying files.
- `zotero-link-import`: link an existing PDF into an exact Zotero collection after confirmation.
- `zotero-docx-paper-writing`: coordinate scoped Word manuscript edits with backups, Zotero safety, and package audits.

Install the repository skills after the GitHub repository is renamed:

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

Zotero integration is opt-in. Read `skills/zotero-link-import/SKILL.md` and authorize installation before running its installer. Local endpoint tokens and generated XPI files remain outside Git.

## Scheduler

Register the Monday 09:00 crawl and EndNote task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scheduler_crawl_endnote.ps1
```

Register the Monday 11:00 summary task:

```powershell
powershell -ExecutionPolicy Bypass -File .\scheduler_summary.ps1
```

Both scripts derive the project root from their own location. Override `-ProjectRoot`, `-PythonExe`, `-WeeklyDay`, or `-At` when needed.

## Outputs

- `_pending_summary\*.pdf` and `*.metadata.json`
- `<Category>\*.pdf` and matching supplements
- `_state\*.jsonl`
- `_summaries\summary_index.json`
- `_summaries\summary.md`
- `_summaries\summary.backup.md`
- `_endnote_import\AI_literature_management_latest.ris`
- `_endnote_import\AI_literature_management_latest.enw`
- Timestamped manifests and attachment reports

## Boundaries

- Do not put API keys in YAML.
- Keep browser profiles, downloaded literature, generated summaries, runtime state, Zotero client configuration, and generated XPI files local.
- The crawler downloads only public or user-authorized files and does not bypass access controls.
- Zotero changes always require explicit confirmation.
- DOCX changes follow an explicit edit-scope allowlist and verified backup workflow.

## Tests

```powershell
python -m pytest -q
```

The test suite is network-free and does not start Zotero, Word, a browser, or an LLM.
