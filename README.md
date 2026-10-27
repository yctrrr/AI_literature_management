# AI Literature Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](./requirements.txt)
[![skills.sh](https://skills.sh/b/yctrrr/AI_literature_management)](https://skills.sh/yctrrr/AI_literature_management)

<!-- README-I18N:START -->

**English** | [中文](./README.zh.md)

<!-- README-I18N:END -->

AI Literature Management is a local-first workflow for turning scattered academic papers into an organized, usable research and personal knowledge base. It connects literature discovery, file organization, local search, AI-assisted understanding, reference-library workflows.

It is for researchers who need a dependable literature workflow and for AI-tool users building a private, reusable knowledge workflow around their own paper collections.

## Workflow

```text
Discover or provide a paper
          |
          v
Resolve and organize local files
          |
          +--> Locate papers and supplements when needed
          |
          v
Review, classify, and summarize
          |
          +--> Export review manifests or EndNote packages
          |
          v
Link approved PDFs to Zotero and cite literature in DOCX files
```

Every stage stays local by default. Downloads, Zotero updates, and DOCX edits have explicit confirmation boundaries.

## What It Supports

- **Collect**: discover configured sources, download accessible PDFs and supplements, and avoid duplicate files.
- **Organize**: keep papers, metadata, pending-review queues, summaries, and export packages in a controlled local archive.
- **Find**: locate a known paper or related attachment in an existing local library without modifying it.
- **Understand**: queue new papers for separate LLM classification and summary generation, then maintain structured and Markdown indexes.
- **Reuse**: create EndNote packages or read-only Zotero import review manifests before any library mutation.
- **Write**: coordinate scoped, backed-up Word manuscript edits with Zotero-managed citations.

## Included Skills

| Skill                                                                      | Outcome                                                                                                                             |
| -------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| [`weekly-literature-crawl`](./skills/weekly-literature-crawl/SKILL.md)     | Validate, preview, and run approved scheduled collection, pending-summary processing, and EndNote exports.                          |
| [`literature-ingest`](./skills/literature-ingest/SKILL.md)                 | Resolve, duplicate-check, classify, and download a paper from DOI, arXiv, publisher, or other supported sources after confirmation. |
| [`literature-locator`](./skills/literature-locator/SKILL.md)               | Find local papers and likely supplementary files without changing the library.                                                      |
| [`zotero-link-import`](./skills/zotero-link-import/SKILL.md)               | Link an existing local PDF to a specific Zotero collection only after confirmation.                                                 |
| [`zotero-docx-paper-writing`](./skills/zotero-docx-paper-writing/SKILL.md) | Make evidence-backed, scoped DOCX changes with backups and citation safety checks.                                                  |

Install all of them in a supported agent environment:

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

Browse the published skill catalog at [skills.sh](https://skills.sh/yctrrr/ai_literature_management).

Installing a skill does not create a literature library or configure a project. Follow the setup below for the capabilities you intend to use.

## Quick Start

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
pip install -r requirements.txt
playwright install chromium
python .\init_project.py
```

Before running the initializer, choose an existing literature library directory and an existing category-source directory (you can start with `example_taxonomy`). Choose a separate archive directory; the initializer can create it. The initializer then creates a local, Git-ignored `config.yaml` and asks you to confirm these paths, an optional browser profile, an optional Zotero linked-file root, and LLM provider settings. Review the generated `paths`, `browser`, `zotero`, and `llm` sections before running a crawl.

When an installed skill runs outside the cloned repository, point it at this configuration in the current PowerShell session:

```powershell
$env:AI_LITERATURE_CONFIG = (Resolve-Path .\config.yaml).Path
```

Alternatively, pass `--root` to the single-paper ingest and locator helpers, or `--project-root` to `weekly-literature-crawl`. Confirm that the paths refer to your own library; the examples are not defaults for your machine.

Check the project configuration without downloading or changing Zotero:

```powershell
python .\skills\weekly-literature-crawl\scripts\weekly_literature_crawl.py --project-root . check
```

An API key is needed only for LLM-backed summary operations. Set the environment variable named by `llm.api_key_env` in your `config.yaml` (the default is `LLM_API_KEY`); do not put its value in the configuration file.

```powershell
$env:LLM_API_KEY = "..."
```

The example configuration documents the available options and environment overrides: [`config.example.yaml`](./config.example.yaml).

For the full project, `config.yaml` is the only file you normally create. If you use an installed ingest or locator skill without project configuration, you may instead put `{"paths":{"library_root":"<absolute-library-path>"}}` in a `config.local.json` beside **each** installed skill; use forward slashes or escaped backslashes for Windows paths in JSON. Passing `--root` or setting `AI_LITERATURE_LIBRARY_ROOT` avoids these files. The Zotero client configuration is generated by its installer and contains a token; do not edit or share it. Fill the Word project-rules template per manuscript when you need persistent edit boundaries.

### Configure the capabilities you use

| Capability | What to confirm before use | First safe check |
| --- | --- | --- |
| Weekly collection | `config.yaml` paths, Nature feeds, download settings, and optional LLM settings | Run `check`, then `dry-run`; approve a live `crawl` separately. |
| Single-paper ingest and local search | An existing literature root supplied by `--root`, `AI_LITERATURE_LIBRARY_ROOT`, or `AI_LITERATURE_CONFIG` | Use the ingest `inspect` command or a locator search before any download. |
| Zotero linked-file import | Zotero is installed; choose the existing PDF root allowed by the plugin. Review `profiles.ini`: the installer selects `Default=1`, or the first entry if none is marked. Stop if multiple profiles make the target uncertain. Follow the [skill installation steps](./skills/zotero-link-import/SKILL.md#installation) only if you want this optional integration. | Run `install_plugin.py --help` before installation; after installation and restart, run the client `health` command. Approve each import separately. |
| Zotero-managed DOCX writing | For Word automation, use Windows with Microsoft Word and the Zotero Word add-in. Define the target document and allowed edit scope; the [project-rules template](./skills/zotero-docx-paper-writing/assets/AGENTS.md) can help. | Run the offline synthetic check below; then make a verified backup before editing a real document and follow the [Word skill](./skills/zotero-docx-paper-writing/SKILL.md). |

The included public Zotero installer does **not** write a distribution policy unless `--install-policy` is passed. That option may need elevated access and separate approval. Zotero plugin installation changes the user's Zotero setup; Word editing changes the selected document. Neither is part of project initialization.

For the full download, profile installation, restart, health check, optional policy fallback, and first import sequence, see the [Zotero plugin setup guide](./docs/zotero-plugin-setup.md). The plugin source is included in this repository; the installer builds its XPI locally.

To check the Word skill's backup and scope-audit scripts without opening Word or Zotero, use a new disposable output directory:

```powershell
$out = Join-Path $env:TEMP ("zotero-word-skill-check-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
powershell -NoProfile -ExecutionPolicy Bypass -File .\skills\zotero-docx-paper-writing\scripts\test_skill.ps1 -OutputDirectory $out
```

This synthetic check does not validate a live citation refresh or rendered manuscript. Actual Word work also needs a document editing and rendering tool; other specialist skills mentioned by the Word coordinator are used when available.

## Optional Collection Automation

The repository includes an optional automated collector for configured Nature-platform feeds and searches. It handles accessible files only; it is not a paywall bypass and does not claim to cover every publisher.

Use the collector when it fits your workflow, or start directly with `literature-ingest` for an individual paper. Detailed preview, approval, summary, export, and scheduler instructions live in [`weekly-literature-crawl`](./skills/weekly-literature-crawl/SKILL.md).

## Local Outputs

Depending on the capabilities used, the project may create:

- `_pending_summary` for papers awaiting review or LLM processing.
- `_summaries` for structured and Markdown literature indexes.
- `_endnote_import` for RIS/ENW packages and attachment reports.
- `_zotero_import` for read-only JSON/CSV import review manifests.

These directories, downloaded papers, browser profiles, runtime state, generated XPI files, and local configuration remain outside Git by default.

## Safety and Privacy

- Do not put API keys or Zotero tokens in YAML, Markdown, or Git.
- The collector downloads only public or user-authorized files and never bypasses access controls.
- Zotero changes always require explicit confirmation.
- DOCX changes use an explicit edit scope and verified backup workflow.
- No cloud literature database, unattended Zotero mutation, or unattended Word mutation is provided.

## Development

Run the network-free test suite:

```powershell
python -m pytest -q
```

## License

[MIT](./LICENSE)
