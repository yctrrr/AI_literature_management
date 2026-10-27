---
name: zotero-link-import
description: Link local PDFs into Zotero collections in the background; for supplementary DOCX files, convert a checked Supp-named PDF first. Use for confirmed linked-file imports or when literature-ingest delegates one.
---

# Zotero Linked Import

Create or reuse a Zotero parent item, add it to an exact collection, and attach an existing PDF with linked-file mode.

Prefer the authenticated local client in the background for supported imports and verification. Do not open or control Zotero with Computer Use for a supported operation. The current client accepts PDF files only. For a supplementary DOCX, follow the conversion rule below; for other unsupported attachments, report the limitation. Use the UI only when the user explicitly requests a UI workflow or authorizes that fallback.

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

## Supplementary DOCX fallback

When the confirmed Zotero import includes a supplementary DOCX and direct DOCX import is unsupported, preserve the DOCX and export a PDF in the same literature folder. Name both files `Supp-<journal-abbreviation>-<first-author>-<year>-<short-title>` with their respective extensions; if the DOCX already has that stem, use it unchanged. Never derive the scholarly name from a publisher's opaque download filename. Run `literature-ingest/scripts/convert_docx_supplement.py --source <DOCX> --output <Supp-...pdf>` using an isolated Word process. Do not overwrite an existing PDF; inspect and reuse it only when its provenance and content are verified. Check the PDF page count and the supplement's headings/tables before import. If conversion or fidelity checks fail, keep the DOCX and report the issue.

Import the verified PDF with this skill's background client, passing the paper DOI and exact collection so it attaches to the existing parent. Verify the returned parent, linked path, collection, and `linkMode`; a repeat import must return `reused`. An existing linked DOCX is retained as the source-format attachment. Do not apply this fallback to arbitrary manuscript DOCX files.

Set `ZOTERO_LINK_CONFIG` or pass `--config` before the subcommand when using a non-default local client configuration.

## Installation

Install only after the user authorizes plugin installation:

For the public package, follow the [download and deployment guide](https://github.com/yctrrr/AI_literature_management/blob/main/docs/zotero-plugin-setup.md). Its repository includes the plugin source and installer; build the token-bearing XPI locally instead of using an unrelated prebuilt package. Inspect the installed script's `--help` before applying any installation option.

```powershell
python "<skill-dir>\scripts\install_plugin.py" `
  --allowed-root "<literature-root>"
```

Before installation, inspect the intended Zotero profile. The installer reads `profiles.ini` and selects the entry marked `Default=1`, or the first entry if none is marked; it cannot determine which profile is currently open. `--profiles-ini` selects the configuration file, not an individual profile. If multiple profiles exist and the selected entry is uncertain, stop before installing. The installer builds an XPI with a token and allowed root, installs it into the selected profile, and stores client configuration outside the published file set. Pass `--zotero-exe` when executable discovery is insufficient.

Check `install_plugin.py --help` for the available installation options. A one-time Zotero distribution policy may require elevated filesystem access; authorize that method separately. If one was used, remove it after a successful restart and health check:

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
