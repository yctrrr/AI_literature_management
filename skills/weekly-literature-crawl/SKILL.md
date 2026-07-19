---
name: weekly-literature-crawl
description: Orchestrate a configured AI Literature Management project for weekly Nature-platform discovery, controlled PDF and supplement downloads, pending-summary processing, summary-index rebuilding, EndNote export, and read-only Zotero import planning. Use when a user asks to check, run, troubleshoot, or schedule the weekly literature crawl; refresh a literature archive; process the pending-summary queue; regenerate EndNote packages; or prepare a reviewable Zotero import manifest without modifying Zotero.
---

# Weekly Literature Crawl

Run the repository's canonical workflow without duplicating crawler code.

## Required Workflow

1. Locate the project with `--project-root`, `AI_LITERATURE_PROJECT_ROOT`, or the current directory.
2. Run `check` before every operation except `zotero-plan`. For `zotero-plan`,
   skip `check`; the command validates only the archive path and must not inspect
   unrelated Zotero settings.
3. Use `dry-run` before a live crawl when filters or configuration changed.
4. Obtain explicit approval before `crawl`; pass `--confirm-download` only after approval.
5. Keep `summary` separate unless the user explicitly requests combined crawl and summary.
6. Obtain separate approval before running either scheduler registration script.
7. Report child-process failures and preserve their exit codes.

## Commands

Set `<skill-dir>` to this skill folder and `<project-root>` to the cloned AI Literature Management repository.

```powershell
python "<skill-dir>\scripts\weekly_literature_crawl.py" `
  --project-root "<project-root>" check
```

Discover candidates without downloading:

```powershell
python "<skill-dir>\scripts\weekly_literature_crawl.py" `
  --project-root "<project-root>" dry-run --limit 10
```

Run the approved weekly download and recent EndNote export:

```powershell
python "<skill-dir>\scripts\weekly_literature_crawl.py" `
  --project-root "<project-root>" crawl --confirm-download
```

Process the pending-summary queue:

```powershell
python "<skill-dir>\scripts\weekly_literature_crawl.py" `
  --project-root "<project-root>" summary
```

Use `rebuild` for a network-free summary-index rebuild. Use `endnote --all` for a full export or `endnote --since-days 7` for a recent export.

Generate a read-only Zotero review plan:

```powershell
python "<skill-dir>\scripts\weekly_literature_crawl.py" `
  --project-root "<project-root>" zotero-plan --all
```

This command writes JSON/CSV manifests only. Delegate actual imports separately to `zotero-link-import` after explicit confirmation.

## Configuration

Resolve configuration from `--config`, `AI_LITERATURE_CONFIG`, or `<project-root>/config.yaml`. Initialize the project with `python init_project.py` when configuration is absent. Keep API keys in the configured environment variable, never in YAML.

## Scheduling

After explicit approval, use the scheduler implementations in this skill. Pass the project root when the skill is installed elsewhere:

```powershell
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\scheduler_crawl_endnote.ps1" `
  -ProjectRoot "<project-root>"
powershell -ExecutionPolicy Bypass -File "<skill-dir>\scripts\scheduler_summary.ps1" `
  -ProjectRoot "<project-root>"
```

Do not register, replace, or remove scheduled tasks without approval.

## Safety

- Do not bypass publisher access controls.
- Do not store browser profiles, credentials, downloads, or runtime state in this skill.
- Do not pass `--confirm-download` until the user approves a live crawl.
- Do not run an LLM-backed operation when its configured API Key environment variable is missing.
- Treat `zotero-plan` as preparation only; do not claim that it checks Zotero duplicates.
- Do not modify Zotero through this skill; delegate separately to `zotero-link-import` after confirmation.
