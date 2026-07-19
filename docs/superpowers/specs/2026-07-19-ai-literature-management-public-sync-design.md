# AI Literature Management Public Sync Design

## Objective

Update the local public project with the latest reusable processing methods from the private project while excluding personal paths, credentials, local runtime state, and research-specific material. Prepare the codebase for a later GitHub repository rename from `AI_literature_crawl` to `AI_literature_management`, but do not change or push the remote repository in this phase.

## Product Scope

The public project remains an incremental literature-management application:

- Preserve the existing Nature discovery and download workflow.
- Add the newer separated crawl, EndNote export, classification, and summary workflow.
- Add four independently callable agent skills under `skills/`.
- Do not expand the crawler to additional publishers or general DOI/arXiv ingestion in this phase.
- Use the display name `AI Literature Management` in public documentation, task names, generated-file defaults, and examples.

## Repository Architecture

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

The application and skills remain separate:

- `src/` owns the automated Nature crawl, archive, state, EndNote, and summary pipeline.
- `skills/` owns agent-facing procedures and deterministic helpers.
- Skills may coordinate with the application through documented configuration and command-line arguments, but they do not duplicate application internals.
- Each skill remains usable outside this repository after installation.

## Configuration And Initialization

The repository commits `config.example.yaml` and ignores the generated `config.yaml`.

`python init_project.py` interactively asks for:

- Main literature-library root.
- Category-source directory.
- Automated archive root.
- Whether Zotero integration is enabled.
- Zotero linked-file allowed root when enabled.
- Browser profile directory or an empty value for an isolated local profile.
- LLM provider, model, base URL, and API-key environment-variable name.

The initializer:

1. Resolves paths without requiring them to use a specific drive or home directory.
2. Verifies required input directories and writable output parents.
3. Rejects overlapping directory selections that could mix source taxonomy with generated archives.
4. Validates environment-variable names without reading or storing secret values.
5. Writes `config.yaml` atomically only after all checks pass.

Path resolution order for reusable helpers is:

1. Explicit command-line argument.
2. Documented environment variable.
3. Project `config.yaml`.
4. A clear error directing the user to initialize the project.

There are no personal absolute-path fallbacks.

Documented environment overrides are:

- `AI_LITERATURE_CONFIG`
- `AI_LITERATURE_LIBRARY_ROOT`
- `AI_LITERATURE_CATEGORY_SOURCE`
- `AI_LITERATURE_ARCHIVE_ROOT`
- `AI_LITERATURE_BROWSER_PROFILE`
- `ZOTERO_LINK_ALLOWED_ROOT`

## Private-To-Public Feature Sync

Sync these reusable behaviors:

- Separate crawling/EndNote export from LLM classification and summary generation.
- Place newly downloaded papers in `_pending_summary`.
- Add `run_summary.py` for processing pending PDFs.
- Maintain `_summaries/summary_index.json` as the structured source of truth.
- Render categorized, category-local numbered entries to `summary.md`.
- Preserve `summary.backup.md` during summary-index migration.
- Export recent RIS/ENW records and attachment reports after successful crawl runs.
- Retain an explicit full-archive EndNote rebuild option.
- Provide separate crawl/EndNote and summary task-scheduler scripts.

Do not sync:

- Browser profiles.
- Local or generated configuration.
- API keys or Zotero endpoint tokens.
- Runtime state, downloaded literature, summaries, or EndNote outputs.
- Python caches, temporary research directories, or private design notes.
- Research-specific categories or paper-selection rules beyond generic examples.

Generated EndNote files use the `AI_literature_management` prefix. Scheduled-task defaults use `AI Literature Management` terminology rather than `AI_crawl` or private directory names.

## Agent Skills

### literature-ingest

- Accept title, DOI, arXiv, publisher, repository, and preprint inputs.
- Inspect existing categories and duplicates before downloading.
- Require confirmation before downloads, writes outside the configured library root, or Zotero changes.
- Resolve the literature root from arguments, environment, or project configuration.
- Keep classification guidance generic and configurable.

### literature-locator

- Search a configured literature root for main papers and likely supplementary attachments.
- Require `--root`, an environment setting, or initialized project configuration.
- Remain read-only and never modify Zotero or literature files.

### zotero-link-import

- Remain opt-in and confirmation-gated.
- Verify source PDFs are under the configured allowed root.
- Never write `zotero.sqlite` directly or move the source PDF.
- Include plugin source and installer logic.
- Exclude local `config.json`, endpoint tokens, profiles, and prebuilt local plugin state.
- Build the XPI locally only after the user authorizes installation.

### zotero-docx-paper-writing

- Preserve edit-scope allowlists, verified backups, DOCX package audits, guarded Zotero refresh, and isolated Word rendering.
- Keep specialist-skill routing and delivery gates.
- Use relative skill-directory examples and placeholders instead of local machine paths.
- Do not bundle manuscripts, citation databases, or document backups.

## Scheduler Design

Scheduler scripts derive the default project root from `$PSScriptRoot`. Users may override it explicitly.

Default task roles:

- `AI Literature Management - Crawl and EndNote`
- `AI Literature Management - Summary`

The crawl task does not require an LLM key when summary processing is deferred. The summary task checks the configured API-key environment variable before processing. Both scripts quote paths and use the initialized configuration.

## Error Handling

- Missing `config.yaml`: stop and direct the user to `python init_project.py`.
- Missing source directories: report the exact configuration key and path.
- Unwritable output location: fail before creating partial state.
- Missing LLM key: stop only workflows that require the LLM.
- Duplicate literature item: report candidates and require a user decision before downloading.
- Ambiguous Zotero collection or path conflict: stop without mutation.
- First Zotero integration error: stop further automated Zotero operations.
- Malformed summary index: retain existing files and report the repair requirement.

## Validation

Repository tests cover:

- Interactive initialization through a testable input layer.
- Atomic configuration generation and invalid path combinations.
- Configuration loading with relative and absolute user-selected paths.
- Pending-summary transitions.
- Summary-index rebuild, migration, and categorized rendering.
- Duplicate detection and recent/full EndNote export behavior.
- Literature locator scoring and supplemental-file grouping.
- Literature ingest inspection and filename generation.
- Skill structure and Python/PowerShell syntax.

An integration test uses temporary directories to run initialization, a network-free dry run, summary rebuild, and EndNote export without Zotero, Word, external downloads, or an LLM call.

GitHub Actions may run only network-independent tests that do not install a Zotero plugin, modify Zotero, start Word, or access private literature.

Privacy verification is performed as an external release gate during this migration. No privacy-audit implementation is added to the public repository.

## Migration And Compatibility

- Existing public source files are updated in place rather than replaced wholesale.
- Existing public history remains intact.
- Existing `config.yaml` is not treated as a public template; the public repository moves to `config.example.yaml` plus initialization.
- Where practical, old command-line flags remain available.
- Generated output prefixes change to `AI_literature_management`; documentation identifies the change.
- The local repository remote remains `AI_literature_crawl` during this phase.
- Remote rename and push are a separate, explicitly authorized operation after local review.

## Acceptance Criteria

- The local public project contains the approved private workflow improvements.
- The four sanitized, self-contained skills are present and pass their tests.
- A new user can initialize the project without editing source code.
- No committed default requires a specific user name, drive letter, library directory, browser profile, Zotero token, or private research topic.
- Local automated tests and the external privacy review pass.
- No GitHub remote rename or push occurs in this phase.
