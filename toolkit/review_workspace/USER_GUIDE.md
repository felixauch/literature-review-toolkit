# User guide

## Project setup

Run **Start review.cmd** in the package root. Its HTML setup page configures your project name and:

- Category names and definitions. Each paper can receive several labels, each Yes / No / unresolved.
- Domain names and matching terms. Multiple core domains and secondary side topics are supported; one selected core domain is primary.
- Extraction field IDs, titles, groups/tabs, guidance and required/optional status. Mark author-interpretation fields separately from source-extraction fields.
- Domain-level synthesis-note headings, such as questions or connections you want to discuss. These are your headings; none are required by the application.

Terms are separated by semicolons. A trailing `*` is a word-stem wildcard (`predict*` matches `prediction`). Other punctuation is literal. `require_any` requires one of its terms in the same passage; `exclude_terms` suppresses a positive suggestion. Blank terms mean manual assessment. Definitions guide the reviewer; the rules do not interpret their meaning.

Use the browser form or import a settings JSON before preparing a run to adjust settings. Context switches control conservative suppression of future wording, background, attribution and negation. These English-language heuristics can miss relevant passages. Matching terms can use other languages, but section/context detection is English-oriented and requires additional testing for other languages. `overview_fields` can list the extraction field IDs to show as synthesis columns; omit it to show all fields.

Validate with `python project_setup.py --mode review --check project.json`. Settings are copied into the run. To change definitions after review starts, create a new run and explicitly reconcile existing decisions. Do not silently change a run's schema.

## Input CSV and preparation

The only required columns are `record_id` and a local PDF path in `fulltext_local_pdf` or `pdf_path`. IDs must be unique and use letters, numbers, underscores or hyphens. Optional columns are title, authors, year, doi, report_categories, report_primary_domain, report_core_domains, report_secondary_domains and decision_link. Separate category/domain labels with semicolons. Existing domain names must belong to your configured taxonomy before confirmation.

PDF paths can be absolute or relative to the supplied PDF root. Every PDF must resolve inside that local root. No URL fetching or OCR is included. Existing labels are context; a new generic run does not automatically confirm them.

```text
python prepare_review.py --config project.json --csv records.csv --pdf-root "C:/Research/PDFs" --out "C:/Research/runs/review-01"
python start.py --run "C:/Research/runs/review-01"
```

Preparation extracts PDFs once, creates local category/domain proposals, and leaves human extraction fields empty. The output folder must be new. Missing/poorly extracted sources are flagged for manual reading. Their absence of matches is not an exclusion decision.

## One paper, two independent review states

The **Screening & categories** tab shows your labels, rule suggestions and supporting passages. Choose Yes, No or ? for each category. Select Core, Secondary or Not assigned for each domain, then a primary domain. Check the domain-review box and confirm after checking the evidence. All No categories exclude a paper from the confirmed corpus; you can still retain extraction notes for it. If an included paper has no matching domain, explain why in the domain note.

The Evidence & synthesis view shows all configured groups together on one page. Fields can use dropdowns, multiple-choice checkboxes or text according to your project settings. Search the local text, open PDF page links, attach passages and write or edit entries. No automatically ranked passage feed is shown.

**Abstract and conclusions** is an expandable panel on each paper. Python extracts sections using headings and the next section boundary, without an LLM. Page links and original extracted text are retained. Not found, empty, uncertain-boundary, combined-section and truncated cases are marked. A successful heading match does not guarantee perfect reading order or complete visual transcription. For an existing run, prepare these panels with `python paper_sections.py --run RUN_FOLDER`. Optional project `sections` settings can specify different heading names; defaults are abstract/summary and common conclusion headings.

Field states are Unchecked, Recorded, Not reported, Not applicable and Unclear. Empty does not mean Not reported. Before confirmation, required fields must be assessed; recorded source fields need a quote or manual page reference. For text fields, explain Not applicable and Unclear. Choice fields retain those explicit states without requiring invented detail. Author-interpretation fields are kept distinct from source findings.

Classification and extraction have separate confirmations. You can record evidence while screening without completing all extraction fields. Editing returns the relevant saved work to draft. Switching views or papers saves pending classification/extraction drafts; final confirmation is always explicit. Enter the reviewer name in the bottom bar. Revision checks prevent a second window from silently overwriting newer work.

## Synthesis

The synthesis map displays saved extraction choices. It omits papers currently excluded by classification. Filter by category or core domain; compare domains or categories against any configured choice measure. Bar charts show option counts, while matrix cells show counts and shares within each row. Click a bar, cell or row to inspect its papers. Counts use the selected cohort, rather than the clicked detail-table subset. Missing choices remain visible. Multiple labels and choices can overlap, so totals need not add up to the number of papers.

Completed extraction entries display Assessed; category decisions display Classified. Drafts remain separate. The display does not change saved verification states or history.

## Save, export and move work

The menu exports classification/history, a confirmed included-corpus CSV, extraction CSV, and extraction/synthesis JSON. The confirmed corpus export requires all category/domain decisions to be confirmed. It never overwrites your input CSV. The assessment summary CSV omits technical origin and reviewer columns. Complete JSON exports preserve origins, verification states and revision history.

Preserve the entire run folder, original CSV and PDFs. Code ZIPs do not back up your decisions. Exports are records, not an automatic restore/import mechanism. Source hashes detect changed PDFs/metadata and block confirmation. Run manifests contain local source paths; moving computers requires retaining those paths or a deliberate relinking/migration, not deleting hash checks.

## Troubleshooting

- Install dependencies with the same Python interpreter used to start the app.
- Select a free port if another review uses the default port.
- Check the PDF directly when extraction is fragmented, scanned or table-heavy.
- Keep the page open after a save failure; fix the error before navigating away.
- Reload after a stale-revision warning; another window saved newer work.
- A missing domain suggestion means unresolved, not that the domain is absent.

For tests: `python -m pip install -r requirements-tests.txt`, then `python -m unittest test_configurable test_paper_sections test_reading_choices -v`.

See the complete PDF guide in the package root, and STRUCTURED_REVIEW.md for configurable choices, reading priorities, brief checks, preserved earlier notes and source verification.

For faster review, configure fewer measures and shorter choice lists during setup. No count is fixed at eight or twelve. Reading priorities and their selectable reasons can now be entered in the setup wizard, using the exact category and metadata labels for your review.

The extraction form uses **Confirm & next** as its single confirmation action; there is no additional source-check checkbox. Save draft and Later do not confirm an entry. Source-page links remain visible; assistance notes remain in saved records and exports.

Keyboard: **Enter** confirms and advances when no input or other control has focus; **Ctrl+Enter** works from a field too (**Cmd+Enter** on macOS). Holding a key does not repeatedly confirm papers.

