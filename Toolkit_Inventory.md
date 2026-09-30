# Literature review toolkit inventory

![Workflow and included scripts](Toolkit%20workflow.svg)

An empty, configurable toolkit for literature searches, screening, classification, evidence extraction and synthesis. It includes reusable scripts, blank templates, documentation and tests.

All **123 packaged files** are described below and listed individually in `Toolkit_File_Inventory.csv`. The workflow includes all **76 script and command files**. Paths are relative to the package root.

## Workflow and full inventory

| File | Purpose |
|---|---|
| `Toolkit inventory.html` | Readable workflow figure followed by the complete inventory; opens without installation. |
| `Toolkit workflow.pdf` | Vector workflow figure showing every script, shared helper and test. |
| `Toolkit workflow.png` | Raster copy of the workflow figure for compatible image viewers. |
| `Toolkit workflow.svg` | Scalable workflow figure used at the beginning of the inventory. |
| `Toolkit_File_Inventory.csv` | One-row-per-file inventory describing every file in this release. |
| `Toolkit_Inventory.md` | Markdown version of the workflow figure and full inventory. |

## Launchers and workflow

| File | Purpose |
|---|---|
| `Setup.cmd` | Starts Python environment setup on Windows. |
| `Start review.cmd` | Opens browser setup for a new or saved review. |
| `bootstrap_env.py` | Creates or repairs the Python environment and installs dependencies. |
| `handoff.py` | Transfers human full-text Include decisions and PDF links into a new review run. |
| `toolkit.py` | Provides commands to create, check, list and run review projects. |
| `workflow.py` | Starts the browser setup server from the package root. |

## Search, screening and draft reports

| File | Purpose |
|---|---|
| `toolkit/analyse_fulltexts.py` | Extracts PDF text and suggests eligibility with page-linked excerpts. |
| `toolkit/apply_adjudications.py` | Applies recorded reviewer corrections and logs when each change was applied. |
| `toolkit/assess_corpus.py` | Drafts domains, technology tier, decision link and contribution notes. |
| `toolkit/audit_dedup.py` | Reports suspected false merges and missed duplicates without changing records. |
| `toolkit/backcheck_classifier.py` | Uses completed human decisions to train an optional SVM and suggest undecided cases. |
| `toolkit/build_fulltext_audit.py` | Collects supporting passages and flags mismatches between draft labels and source text. |
| `toolkit/build_overview.py` | Creates a provisional corpus CSV and count summary from screening records. |
| `toolkit/build_supplementary_review.py` | Creates a standalone page for reviewing citation-chasing candidates. |
| `toolkit/build_synthesis.py` | Creates a template-based draft summary of the charted corpus. |
| `toolkit/chase_screen.py` | Suggests decisions and a review shortlist for citation-chasing candidates. |
| `toolkit/citation_chase.py` | Finds cited and citing papers through Crossref and OpenAlex. |
| `toolkit/completeness_check.py` | Compares OpenAlex or manually collected search hits with the review records. |
| `toolkit/core_domains.py` | Proposes core versus secondary domains and applies reviewer choices to the draft export. |
| `toolkit/corpus_files.py` | Maintains project PDF copies, their manifest and full-text decision records. |
| `toolkit/export_bibtex.py` | Exports kept or included records as BibTeX references. |
| `toolkit/export_latex_listing.py` | Creates a draft LaTeX corpus listing grouped by tier and primary domain. |
| `toolkit/import_pdf_manifest.py` | Copies PDFs using an explicit record-to-file mapping. |
| `toolkit/ingest_pending.py` | Adds human-selected citation candidates to the pending full-text queue. |
| `toolkit/lib.py` | Provides shared import, CSV, text-extraction, matching and network helpers. |
| `toolkit/merge_abstracts.py` | Fills missing abstracts from additional exports matched by DOI or title. |
| `toolkit/merge_screen.py` | Imports database exports, removes duplicates and suggests title/abstract decisions. |
| `toolkit/organise_folders.py` | Copies included PDFs into folders by technology tier and core domain. |
| `toolkit/pdfs.py` | Collects PDFs, matches them to records and checks their first-page title or DOI. |
| `toolkit/project_config.py` | Loads and validates project paths, search vocabulary, rules and taxonomy. |
| `toolkit/recall_check.py` | Checks citation links among database Includes as a search-coverage probe. |
| `toolkit/recommend_fulltext.py` | Combines metadata and full-text rules into preliminary eligibility recommendations. |
| `toolkit/recover_csv.py` | Backs up a damaged screening CSV and rebuilds missing rows from deduplicated records. |

## Screening interface

| File | Purpose |
|---|---|
| `toolkit/ui/app.js` | Handles screening filters, paper cards, decisions and draft assessment views. |
| `toolkit/ui/audit.css` | Formats the full-text audit page. |
| `toolkit/ui/audit.js` | Displays flagged label/source mismatches and records reviewer responses. |
| `toolkit/ui/build_data.py` | Converts screening records, draft labels and evidence into browser data. |
| `toolkit/ui/evidence.py` | Selects short title/abstract quotations supporting screening suggestions. |
| `toolkit/ui/fulltext_audit.html` | Defines the full-text audit page. |
| `toolkit/ui/index.html` | Defines the screening and corpus-review page. |
| `toolkit/ui/runner.py` | Runs review stages and reports project files, progress and status. |
| `toolkit/ui/serve.py` | Serves the local screening interface and saves reviewer decisions. |
| `toolkit/ui/setup.html` | Defines the search-project settings and stage-control page. |
| `toolkit/ui/setup.js` | Edits project settings, tests rules and controls stage execution. |
| `toolkit/ui/styles.css` | Formats the screening and assessment interface. |
| `toolkit/ui/supplementary_review_template.html` | Supplies the standalone citation-candidate page and decision export. |
| `toolkit/ui/theme.css` | Provides the shared appearance used across browser stages. |
| `toolkit/ui/workflow.html` | Explains how to transfer screened papers to the combined review workspace. |

## Combined review workspace

| File | Purpose |
|---|---|
| `toolkit/review_workspace/assessment_browser.py` | Exports a portable, read-only corpus explorer with summary CSV and settings. |
| `toolkit/review_workspace/choices.py` | Validates single-choice, multiple-choice and mutually exclusive answers. |
| `toolkit/review_workspace/classification_store.py` | Validates and saves category/domain decisions, confirmations and exports. |
| `toolkit/review_workspace/csv_storage.py` | Stores typed CSV revisions with checksums, atomic saves, locks and archive export. |
| `toolkit/review_workspace/domain_rules.py` | Suggests labels from configured terms and context checks in source passages. |
| `toolkit/review_workspace/launch.py` | Starts or reconnects to a saved review without re-extracting its sources. |
| `toolkit/review_workspace/migrate_legacy.py` | Copies older SQLite/JSON reviews into a new CSV run while preserving the originals. |
| `toolkit/review_workspace/paper_sections.py` | Finds abstracts and conclusions and saves their source passages and boundary status. |
| `toolkit/review_workspace/passages.py` | Divides page text into passages while preserving page numbers and exact text positions. |
| `toolkit/review_workspace/prepare_review.py` | Prepares PDF text, category/domain suggestions and blank review forms. |
| `toolkit/review_workspace/project_setup.py` | Validates review settings and provides optional command-line configuration. |
| `toolkit/review_workspace/reading_plan.py` | Assigns configured reading priorities and saves brief-check decisions separately. |
| `toolkit/review_workspace/run_synthesis.py` | Runs the extraction command or starts the local evidence-review server. |
| `toolkit/review_workspace/setup_server.py` | Checks inputs, prepares new reviews and opens saved reviews through browser setup. |
| `toolkit/review_workspace/start.py` | Opens browser setup or resumes a specified review run. |

## Evidence, storage and synthesis services

| File | Purpose |
|---|---|
| `toolkit/review_workspace/synthesis/__init__.py` | Defines the combined review module's software version. |
| `toolkit/review_workspace/synthesis/engine.py` | Searches local passages and assigns stable identifiers to exact quotations. |
| `toolkit/review_workspace/synthesis/extract.py` | Creates a new evidence run with extracted page text, source hashes and warnings. |
| `toolkit/review_workspace/synthesis/schema.py` | Defines configurable evidence fields, answer states and blank review records. |
| `toolkit/review_workspace/synthesis/server.py` | Serves the combined interface, local PDFs, source search and review/export endpoints. |
| `toolkit/review_workspace/synthesis/store.py` | Validates and saves evidence and synthesis notes; checks sources and prepares exports. |

## Review setup interface

| File | Purpose |
|---|---|
| `toolkit/review_workspace/setup_ui/index.html` | Defines the setup wizard for files, categories, domains and evidence fields. |
| `toolkit/review_workspace/setup_ui/setup.css` | Formats the review setup wizard. |
| `toolkit/review_workspace/setup_ui/setup.js` | Handles file selection, configuration, input checks and preparation progress. |

## Combined review and explorer interface

| File | Purpose |
|---|---|
| `toolkit/review_workspace/synthesis/static/app.js` | Controls paper navigation, evidence forms, source search, saving and synthesis views. |
| `toolkit/review_workspace/synthesis/static/choices.js` | Builds choice controls and summaries and displays earlier saved notes. |
| `toolkit/review_workspace/synthesis/static/classification.js` | Displays category/domain forms, source suggestions and classification maps. |
| `toolkit/review_workspace/synthesis/static/index.html` | Defines the combined paper, evidence, classification, synthesis and export views. |
| `toolkit/review_workspace/synthesis/static/reading.js` | Displays reading priorities and saves brief or detailed reading choices. |
| `toolkit/review_workspace/synthesis/static/snapshot.css` | Applies the read-only explorer presentation. |
| `toolkit/review_workspace/synthesis/static/snapshot.js` | Adapts exported summary CSVs to the shared interface without a server or editing. |
| `toolkit/review_workspace/synthesis/static/style.css` | Formats the combined review interface and its maps. |
| `toolkit/review_workspace/synthesis/static/synthesis-map.js` | Computes unique-paper counts, matrices and filters linking map cells to papers. |

## Automated tests

| File | Purpose |
|---|---|
| `toolkit/review_workspace/test_configurable.py` | Tests configurable categories, fields and review integration using synthetic papers. |
| `toolkit/review_workspace/test_confirmed_exports.py` | Tests that incomplete or stale classifications cannot be exported as confirmed. |
| `toolkit/review_workspace/test_csv_storage.py` | Tests CSV round trips, competing saves, corruption, backups and migration. |
| `toolkit/review_workspace/test_paper_sections.py` | Tests section boundaries, exact quotation positions and missing-section handling. |
| `toolkit/review_workspace/test_reading_choices.py` | Tests reading depth, structured answers and preservation of earlier notes. |
| `toolkit/review_workspace/test_setup.py` | Tests input validation, setup access checks and protection against duplicate preparation. |
| `toolkit/review_workspace/test_snapshot.cjs` | Tests CSV parsing, preserved review states and the read-only explorer adapter. |
| `toolkit/review_workspace/test_synthesis_map.cjs` | Tests unique-paper counts, overlapping labels, missing answers and map filters. |

## Package documentation, templates and dependencies

| File | Purpose |
|---|---|
| `.gitignore` | Keeps local environments, generated records and user projects out of version control. |
| `CSV_STORAGE.md` | Explains CSV histories, current views, backups, migration and explorer export. |
| `DATA STRUCTURE.md` | Explains package folders and the data created when a user starts a review. |
| `LICENSE` | States the MIT licence, copyright notice and conditions for using, modifying and distributing the toolkit. |
| `Literature review toolkit - complete guide.pdf` | Provides the illustrated guide from project setup to review and export. |
| `NETWORK_AND_MODEL_AUDIT.md` | Documents network access, model-related behaviour and recorded checks. |
| `PACKAGE_MANIFEST.json` | Records the empty software release, its checks and packaged file hashes. |
| `README.md` | Introduces the empty toolkit and links to setup instructions and documentation. |
| `SCRIPT_INVENTORY.md` | Summarises scripts and interface assets included in the package. |
| `START_HERE.md` | Gives installation and first-use instructions. |
| `TECHNICAL_DOCUMENTATION.md` | Explains architecture, data flow, commands and operational behaviour. |
| `pdf_import_template.csv` | Provides an empty record-ID-to-PDF-path import template. |
| `projects/_template/project.json` | Provides an empty search-project configuration. |
| `requirements-optional-ml.txt` | Lists dependencies for the optional title/abstract SVM backcheck. |
| `requirements-test.txt` | Adds the PDF-generation dependency used by synthetic tests. |
| `requirements.txt` | Lists the toolkit's PDF and HTTP runtime dependencies. |
| `search_log_template.csv` | Provides fields for recording databases, queries, dates, filters and exports. |

## Workspace documentation, templates and dependencies

| File | Purpose |
|---|---|
| `toolkit/review_workspace/.gitignore` | Excludes generated environments, caches, runs, logs and local settings from Git. |
| `toolkit/review_workspace/README.md` | Introduces the combined review module and its entry points. |
| `toolkit/review_workspace/SCRIPT_INVENTORY.md` | Points to the package-level script inventory. |
| `toolkit/review_workspace/START_HERE.md` | Explains how to start or resume a combined review. |
| `toolkit/review_workspace/STRUCTURED_REVIEW.md` | Explains answer choices, reading priorities, synthesis maps and saved states. |
| `toolkit/review_workspace/TECHNICAL_DOCUMENTATION.md` | Describes extraction, passage rules, persistence and review services. |
| `toolkit/review_workspace/USER_GUIDE.md` | Explains review forms, source checking, decisions and exports. |
| `toolkit/review_workspace/project.template.json` | Provides an empty configuration for categories, domains and evidence fields. |
| `toolkit/review_workspace/records_template.csv` | Shows the required metadata columns with an example record. |
| `toolkit/review_workspace/requirements-tests.txt` | Adds the pinned PDF-generation dependency for module tests. |
| `toolkit/review_workspace/requirements.txt` | Pins the PDF parsers used by this module. |
