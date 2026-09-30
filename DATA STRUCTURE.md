# Package and review data

The distributed package contains reusable code and blank templates. Project data is created only when you configure and use a review.

| Included location | Purpose |
|---|---|
| toolkit/ | Import, screening, PDF and reporting scripts, plus the browser interfaces. |
| toolkit/review_workspace/ | Configurable classification, evidence extraction and synthesis. |
| projects/_template/project.json | Blank search-project configuration. |
| toolkit/review_workspace/project.template.json | Blank category, domain and evidence-field configuration. |
| toolkit/review_workspace/records_template.csv | Metadata column headers; no paper records. |
| pdf_import_template.csv; search_log_template.csv | Empty import and search-log templates. |

## Files created during a review

Search projects keep their own settings, imported records and screening decisions. A prepared review run creates `manifest.csv`, `classification/catalog.csv`, CSV decision histories, `*_current.csv` views and local page-text/section caches. These generated files are not part of the empty package.

Use the interface to edit decisions. Export ordinary summary CSVs for analysis; do not edit internal typed journals in a spreadsheet. Back up the whole review folder and keep externally stored source files separately. See CSV_STORAGE.md for details.
