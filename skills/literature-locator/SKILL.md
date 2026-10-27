---
name: literature-locator
description: Locate local literature files and related attachments by paper title or partial filename in a configured library. Use when a user asks to find or identify a paper, author-year fragment, DOI-like filename fragment, topic-folder match, or supplemental files such as Supplement, Supporting Information, Appendix, ESM, or Additional file.
---

# Literature Locator

Search a configured literature library without modifying files or Zotero.

## Quick Start

```powershell
python "<skill-dir>\scripts\locate_literature.py" "paper title or keywords" `
  --root "<literature-root>"
```

The script resolves the root from `--root`, `AI_LITERATURE_LIBRARY_ROOT`, `AI_LITERATURE_CONFIG`, an optional skill-local `config.local.json`, or the current project's `config.yaml`. Keep personal paths in configuration, not in this skill.

## Workflow

1. Search the configured root.
2. Return main matches with score, path, parent topic, and file type.
3. Return likely supplements for the best match.
4. Ask the user when multiple main matches are plausible.
5. Use the appropriate specialist skill only if the user asks to inspect content.

## Options

- Use `--limit N` for more main candidates.
- Use `--attachments N` to control supplemental matches.
- Use `--root` for a one-time alternate library.
- Use `--extensions` to change the searched file types.

This skill is read-only. Do not write notes, move literature, or modify Zotero.
