# AI Literature Management

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](./requirements.txt)
[![skills.sh](https://skills.sh/b/yctrrr/AI_literature_management)](https://skills.sh/yctrrr/AI_literature_management)

<!-- README-I18N:START -->

**English** | [中文](./README.zh.md)

<!-- README-I18N:END -->

AI Literature Management is a local-first workflow for turning scattered academic papers into an organized, usable research and personal knowledge base. It connects literature discovery, file organization, local search, AI-assisted understanding, reference-library workflows, and citation-safe manuscript writing without moving a user's library or runtime data to a hosted service.

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
Link approved PDFs to Zotero and write citation-managed DOCX files
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

| Skill | Outcome |
| --- | --- |
| [`weekly-literature-crawl`](./skills/weekly-literature-crawl/SKILL.md) | Validate, preview, and run approved scheduled collection, pending-summary processing, and EndNote exports. |
| [`literature-ingest`](./skills/literature-ingest/SKILL.md) | Resolve, duplicate-check, classify, and download a paper from DOI, arXiv, publisher, or other supported sources after confirmation. |
| [`literature-locator`](./skills/literature-locator/SKILL.md) | Find local papers and likely supplementary files without changing the library. |
| [`zotero-link-import`](./skills/zotero-link-import/SKILL.md) | Link an existing local PDF to a specific Zotero collection only after confirmation. |
| [`zotero-docx-paper-writing`](./skills/zotero-docx-paper-writing/SKILL.md) | Make evidence-backed, scoped DOCX changes with backups and citation safety checks. |

Install all of them in a supported agent environment:

```powershell
npx skills add yctrrr/AI_literature_management -g -y
```

Browse the published skill catalog at [skills.sh](https://skills.sh/yctrrr/ai_literature_management).

## Quick Start

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
pip install -r requirements.txt
playwright install chromium
python .\init_project.py
```

The initializer creates a local, Git-ignored `config.yaml`. It asks for your library and archive locations, optional browser profile and Zotero linked-file root, and LLM provider settings. Keep the selected LLM API key in an environment variable rather than the configuration file.

```powershell
$env:LLM_API_KEY = "..."
```

The example configuration documents the available options and environment overrides: [`config.example.yaml`](./config.example.yaml).

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
