# Zotero linked-file plugin: download and setup

[中文说明](./zotero-plugin-setup.zh.md)

This optional plugin links existing PDFs into an exact Zotero collection. It does not install Zotero or the Zotero Word add-in. Install it only when you intend to use linked-file imports and have authorized changes to your Zotero profile.

## 1. Get the plugin source

Install [Python 3.10 or newer](https://www.python.org/downloads/) and [Zotero from its official download page](https://www.zotero.org/downloads). Then clone this repository, or download and extract its GitHub ZIP. The plugin source is in `skills/zotero-link-import/assets/zotero-plugin`; the installer builds the XPI locally. There is no separate prebuilt XPI to download. This linked-file plugin is part of this project, not an official Zotero extension.

```powershell
git clone https://github.com/yctrrr/AI_literature_management.git
cd AI_literature_management
python .\skills\zotero-link-import\scripts\install_plugin.py --help
```

If you installed this skill with `npx skills add`, you can run the same scripts from the installed `zotero-link-import` skill directory instead of cloning the whole repository. Keep the generated client configuration and XPI private; both contain the local access token.

## 2. Check the target before installation

- Choose an **existing** directory that contains the PDFs you will link. The plugin rejects files outside this allowed root.
- Confirm the exact Zotero collection already exists. The import command does not create collections.
- Check the Zotero `profiles.ini` you intend to use. The installer selects the profile marked `Default=1`; if none is marked, it selects the first profile entry. It cannot identify the currently open profile. If several profiles make the choice uncertain, stop and resolve that before installing. `--profiles-ini` selects a different configuration file, not an individual profile within it.
- Save your work and close Zotero before changing its profile. Leave unrelated Word documents alone.

Run the installer with your actual PDF root:

```powershell
python .\skills\zotero-link-import\scripts\install_plugin.py `
  --allowed-root "<absolute-path-to-existing-PDF-library>"
```

For a nonstandard installation, add `--profiles-ini "<path-to-profiles.ini>"` and, if needed, `--zotero-exe "<path-to-zotero-executable>"`. The installer creates a token-bearing XPI in the selected profile's `extensions` directory and writes a private client configuration in the current user's application configuration directory. Its output names the selected profile and paths; check them before restarting Zotero. The default installation does not write a Zotero distribution policy.

## 3. Restart and verify

Start Zotero in the selected profile, make sure the plugin is enabled, and run:

```powershell
python .\skills\zotero-link-import\scripts\zotero_link_import.py health
```

Require `status: ok` and the expected allowed root before importing. If health fails, check the profile selection, plugin state, and Zotero restart; do not run an import until it succeeds. The client reads the private configuration produced by the installer. If you passed `--config` during installation, pass the same path as `--config` **before** `health` or `import`, or set `ZOTERO_LINK_CONFIG`.

Only if the normal profile installation does not activate and you have separately authorized a distribution-policy fallback, rerun the installer with `--install-policy`, restart Zotero, and repeat `health`. That option may need elevated filesystem access. After a successful restart and health check, remove the one-time policy with `python .\skills\zotero-link-import\scripts\install_plugin.py --finalize`; this keeps the installed profile plugin and client configuration.

## 4. Import one approved PDF

Use a PDF already inside the allowed root and an exact, unambiguous collection name. Supply a verified DOI when available:

```powershell
python .\skills\zotero-link-import\scripts\zotero_link_import.py import `
  --path "<absolute-path-to-PDF-inside-allowed-root>" `
  --collection "<exact-existing-collection-name>" `
  --doi "10.xxxx/example"
```

Check the returned parent item, linked attachment path, `linkMode`, and collection. Repeating the same import should return `reused` without creating another attachment. Stop on the first integration error. The source PDF stays in place; the plugin does not write directly to `zotero.sqlite`.

The Word citation workflow is separate. Zotero [bundles the Word processor integration](https://www.zotero.org/support/word_processor_plugin_installation); if it is missing from Word, check Zotero's **Cite → Word Processors** settings. To insert or refresh Zotero-managed citations in DOCX, follow [`zotero-docx-paper-writing`](../skills/zotero-docx-paper-writing/SKILL.md) with a verified backup and a target-document scope.

## Privacy

Never commit or share the generated client JSON, XPI, token, personal `profiles.ini`, or private PDF library paths. The repository's plugin source and generic instructions are public; the installer generates credentials locally.
