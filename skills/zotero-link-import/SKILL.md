---
name: zotero-link-import
description: Link existing local PDF files into named Zotero collections without copying them into Zotero storage. Use when a user asks to import, attach, or place an already-downloaded PDF in Zotero, provides a PDF path and collection, requests a linked-file import, or when literature-ingest delegates a separately confirmed Zotero operation.
---

# Zotero Linked Import

Create or reuse a Zotero parent item, add it to an exact collection, and attach an existing PDF with linked-file mode.

## Workflow

1. Require explicit confirmation before changing Zotero.
2. Verify the PDF is under the initialized Zotero allowed root.
3. Require an unambiguous exact collection name.
4. Run the health check:

```powershell
python "<skill-dir>\scripts\zotero_link_import.py" health
```

5. Import the linked file:

```powershell
python "<skill-dir>\scripts\zotero_link_import.py" import `
  --path "<allowed-root>\<category>\paper.pdf" `
  --collection "Exact collection name" `
  --doi "10.xxxx/example"
```

6. Accept `created`, `reused`, or an explained `partially_created` response.
7. For a new installation, repeat the same import once and require `reused` without another attachment.

Set `ZOTERO_LINK_CONFIG` or pass `--config` before the subcommand when using a non-default local client configuration.

## Installation

Install only after the user authorizes plugin installation:

```powershell
python "<skill-dir>\scripts\install_plugin.py" `
  --allowed-root "<literature-root>"
```

The installer discovers the active Zotero profile, builds an XPI locally with a new token and allowed root, installs it into that profile, and stores the client configuration in the user's configuration directory. Pass `--profiles-ini` or `--zotero-exe` when automatic discovery is insufficient.

The optional `--install-policy` flag writes a one-time Zotero distribution policy and may require elevated filesystem access. Use it only when the user explicitly authorizes that installation method. After a successful restart and health check, remove that policy:

```powershell
python "<skill-dir>\scripts\install_plugin.py" --finalize
```

## Safety

- Never write `zotero.sqlite` directly.
- Never copy or move the source PDF.
- Never print or expose the local client configuration because it contains the endpoint token.
- Stop on an ambiguous collection, DOI/path conflict, unavailable plugin, or path outside the allowed root.
- Stop after the first integration error.
- Use Zotero's read-only local API to verify results when needed.
