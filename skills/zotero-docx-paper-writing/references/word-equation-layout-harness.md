# Word Equation and Academic Layout Harness

Use this with the parent skill whenever a Zotero-managed manuscript or supplementary DOCX needs equations, equation numbers, data tables, figures, captions, or headings. The current target document and journal instructions control language, typography, and numbering scope. Do not require the two example manuscripts to be present in later projects.

## Provenance of the reusable pattern

The reusable pattern is a borderless two-column table with native Word math (`m:oMath`) in the wide left cell and a parenthesized number in the narrow right cell. In supplementary documents, figure captions commonly follow figures and table titles precede data tables; major sections use heading styles. Table borders, caption style IDs, widths, and numbering depend on the target document. Verify each equation number and cross-reference instead of copying numbers from an example.

## 1. Establish the edit contract

Before editing, define the exact allowed equation, table, figure, caption, and heading anchors under the parent skill's scope allowlist. Identify the existing journal or document convention, the main-text and supplementary numbering sequences, and how cross-references are maintained. Record whether existing equations are native Word math, MathType/OLE, images, or plain text. Preserve existing representations outside the allowed range.

Use the read-only `scripts/audit_word_math_layout.py <target.docx>` on the saved target and its verified backup. The script reports structure and likely anomalies; inspect the document to decide whether a reported difference is intentional. Keep the baseline report with the review artifacts.

## 2. Insert editable Word equations

- Create each new or changed equation through Word's native **Insert > Equation** facility. In controlled Word automation, insert the equation into an exact Word range with `OMaths.Add(range)` and convert it to professional format with `OMath.BuildUp()`; test the notation on a disposable copy before applying it to the manuscript. See Microsoft's [OMaths.Add](https://learn.microsoft.com/en-us/office/vba/api/word.omaths.add) and [OMath.BuildUp](https://learn.microsoft.com/en-us/office/vba/api/word.omath.buildup) documentation.
- A new inline equation remains in its prose paragraph as native Word math. A numbered display equation goes in the left cell of a two-column Word table; its number, for example `(3)`, goes in the right cell. The table has no visible outer or internal borders and no fill. Give the left cell most of the text width and reserve enough width in the right cell for the full number. Align and space the equation consistently with the target document, and keep its row together across pages.
- Do not represent a requested editable equation as a PNG, SVG, text box, pasted screenshot, raw LaTeX, or manually styled ordinary text. Do not silently convert existing MathType objects or older equations outside the edit scope.
- Check each symbol, subscript, superscript, fraction, accent, operator, delimiter, unit, and sign against the approved scientific expression. Confirm the equation can be selected and edited in Word after saving and reopening.
- Maintain a unique, ordered number within each document's applicable sequence. Existing documents may use manual numbers; preserve their method unless the user authorizes a numbering migration. Where the document already uses Word caption/SEQ fields or bookmarks/REF fields, use the same mechanism and verify displayed numbers and references after an update. A structural count alone does not prove mathematical correctness.

## 3. Insert data tables and captions

- Insert data as an editable Word table. Follow the target document's table style and journal rules; do not copy internal style IDs, fixed column widths, or mixed border settings from the examples.
- Put a descriptive table title immediately before its table and a figure caption immediately after its figure, matching the example pattern unless the target journal or established document convention specifies otherwise. Keep each caption visually attached to its object and avoid orphaned titles or captions across pages.
- Give tables meaningful column headings and explicit units. Mark header rows to repeat when a table spans pages, check merged cells and reading order, and allow row heights to grow so text does not clip. Put explanatory notes directly after the table under the target convention.
- Use the document's existing caption language, label syntax, sequence, and paragraph style. For new documents, prefer Word captions/SEQ fields and stable cross-references; for existing documents, preserve their numbering method unless migration is in scope. Verify that each figure or table number is unique in its own sequence and that every in-text reference points to the intended object. Microsoft's [Range.InsertCaption](https://learn.microsoft.com/en-us/office/vba/api/word.range.insertcaption) documents native caption insertion.

## 4. Set headings through styles

Use Word paragraph styles for the document title, section headings, and supplementary section headings. Match the target document's hierarchy and numbering; do not reproduce sample-specific style IDs such as `Heading-Main` or `a9` without checking their definitions in the current document. A visually bold paragraph is not evidence that it has the correct heading style. Keep heading text, level, page placement, and any table of contents or cross-reference effects within the authorized scope.

## 5. Review and delivery gate

1. Re-run the read-only structural audit on the edited DOCX and compare it with the baseline. Explain every added, removed, or converted math object; equation-table row; number; caption; table; and heading in the allowed range. Investigate duplicate or missing numbers. Do not treat the audit's heuristics as a substitute for inspecting Word.
2. Run the parent skill's package and scope audit against the verified backup. Confirm Zotero fields, preferences, bibliography, and unrelated document parts remain intact. Use the guarded Zotero path if citations themselves were intentionally changed.
3. Open the final document in an isolated Word session or the user's authorized editing session, inspect and edit-test representative changed equations, and render every page through the parent skill's Zotero-safe rendering route. Check each changed equation, number, figure caption, table title, heading, and surrounding page break at readable zoom.
4. Report the exact anchors changed, native equation count and numbering impact, table and caption changes, scope-audit result, Word editability check, render result, backup location, and any unresolved formula or cross-reference question.

Stop before publication when the final formula differs from the approved expression, an equation has become an image or plain text, a number/reference is unresolved, the scope audit finds unrelated changes, or a changed page has not been visually checked.
