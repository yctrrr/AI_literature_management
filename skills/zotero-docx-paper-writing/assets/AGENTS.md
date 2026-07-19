# Paper Project Rules

Do not change any text, object, file, citation, or metadata beyond the user's explicit requirements.

## Project

- Target journal: `<journal>`
- Main manuscript: `<absolute-or-project-relative-path>`
- Supplementary document: `<path-or-not-applicable>`

## Allowed Scope

- Editable sections or paragraph anchors: `<explicit allowlist>`
- Citation insertion or editing allowed: `<yes-or-no>`
- Bibliography refresh allowed: `<yes-or-no>`
- Supplementary-file changes allowed: `<yes-or-no>`
- Manuscript builder execution allowed: `<no, or exact authorized builder>`

## Protected Scope

- Protected files or sections: `<explicit list; default is everything outside Allowed Scope>`
- Figures, tables, captions, and metadata are protected unless listed in Allowed Scope.
- Treat the current DOCX as authoritative. Do not replace it with generated output unless builder execution is explicitly authorized.

## Writing Requirements

- Terminology: `<project terminology>`
- Citation style: `<Zotero style>`
- Additional journal or project requirements: `<requirements>`

## Zotero And DOCX

- Use Zotero's native Word integration for dynamic citations and the bibliography.
- Never synthesize, edit, or copy Zotero fields or `ZOTERO_PREF_*` properties.
- Create a verified backup before mutation.
- Audit the final DOCX against the backup and reject unexplained differences outside Allowed Scope.
- Stop after the first Zotero integration error and diagnose on a disposable copy.
