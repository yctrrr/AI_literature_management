# Weekly Literature Crawl Skill Design

## Goal

Add a reusable `weekly-literature-crawl` skill under `skills/` and update the
English and Chinese project READMEs. The skill orchestrates the repository's
existing weekly crawl, summary, rebuild, and EndNote commands without copying
the crawler implementation.

## Structure

```text
skills/weekly-literature-crawl/
  SKILL.md
  agents/openai.yaml
  scripts/weekly_literature_crawl.py
```

The wrapper resolves the application root in this order:

1. Explicit `--project-root`.
2. `AI_LITERATURE_PROJECT_ROOT`.
3. The current directory when it contains the required entry-point scripts.

It resolves configuration from explicit `--config`,
`AI_LITERATURE_CONFIG`, or `<project-root>/config.yaml`.

## Commands

- `check`: validate the project root, initialized configuration, and required
  entry points without network access.
- `dry-run`: invoke candidate discovery without downloading or calling an LLM.
- `crawl`: run the weekly crawler and recent EndNote export.
- `summary`: process the pending-summary queue.
- `rebuild`: rebuild the summary index without crawling or LLM calls.
- `endnote`: generate recent or full EndNote packages.

The wrapper uses subprocess argument lists, preserves child exit codes, and
does not shell-expand user input.

## Safety

- Never store credentials, browser profiles, downloaded files, or runtime
  configuration inside the skill.
- Require explicit user approval before a live crawl that downloads files.
- Require separate approval before registering or changing scheduled tasks.
- Do not run summary mode unless the configured API-key environment variable
  is available.
- Do not bypass publisher access controls.

## Documentation

Update `README.md` and `README.zh.md` symmetrically to explain:

- the project's local-first literature-management purpose;
- the crawl, pending-summary, EndNote, locator, ingestion, Zotero, and DOCX
  workflow;
- all five bundled skills and their intended triggers;
- initialization and weekly command examples through the new wrapper;
- privacy and authorization boundaries.

## Validation

- Add network-free tests for project/config discovery and forwarded commands.
- Run the repository test suite, Python compilation, PowerShell parsing, all
  skill validators, the DOCX regression suite, and the external privacy audit.
- Forward-test only non-mutating `check`, `rebuild`, or empty-archive commands;
  do not start a browser, download literature, call an LLM, or register tasks.
