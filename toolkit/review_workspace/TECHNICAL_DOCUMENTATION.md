# Technical documentation

## Data flow

Project settings + metadata CSV + local PDFs -> immutable text extraction and category/domain rule proposals -> unified browser review -> separate classification and extraction CSV histories -> corpus/extraction exports and author synthesis notes.

## Rules and extraction

Category/domain rules use configurable literal terms, trailing-stem wildcards, required co-occurring terms and exclusions. Section/context checks suppress some background, future, attributed and negated matches. Multiple labels are supported. No trained classifier is used. No automatic No is inferred from a missing match. Ranking and quoted evidence are reading aids, not semantic proof. The generic toolkit does not embed a subject-specific category engine.

PDFium is the default text parser; pypdf is an optional alternative for extraction. Page text and exact offsets remain local. PDFium initializes before PDF access; after initialization a Python audit hook blocks network and child processes during extraction. This is a process guard, not an OS sandbox. No OCR is included.

The synthesis engine now provides text normalization, literal search, quotation IDs and extraction warnings only. It does not rank keyword passages or produce prose.

## Files and persistence

- manifest.csv: settings snapshot, input/PDF/parser/code hashes and paper metadata.
- papers/<ID>.json: extracted pages and source warnings.
- classification/catalog.csv: configured categories/domains, rule proposals and quotation spans.
- classification/classification.csv: current category/domain decisions and append-only history.
- extraction.csv + domain_notes.csv: extraction fields, states, confirmations, revision history and domain synthesis notes/history.
- paper_sections/: heading-based abstract/conclusion excerpts, source hashes and coverage counts. No LLM is used.

The live metadata shown in extraction/synthesis reflects saved category and domain decisions. Excluded records remain accessible for notes but are omitted from the default synthesis map and included-corpus export. Original input CSVs and PDFs are never rewritten. Confirmation checks source freshness and exact attached quotations. Changes and conflicts use atomic CSV replacement, file locks and revision numbers.

Each server process serves one run/configuration. The interface uses loopback HTTP, Host/Origin/token checks, escaped text and local static assets. It makes no external network calls. A browser opening a DOI is outside the processing script. Cloud synchronization of a run folder is also outside its control.

## Validation and limits

Synthetic unit and integration tests cover configurable fields/labels, term boundaries, attribution/reference warnings, exact quotations, source preservation, save conflicts, exports. Browser checks cover combined classification/domain editing, manual search, extraction, synthesis notes, independent confirmations, persistence and narrow layout.

These checks verify software behavior, not scientific recall, classification accuracy. The package makes no legal certification or guarantee of exhaustive evidence extraction. Source languages, scans, figures, tables and complex reasoning require reviewer attention.

## Structured review update

choices.py validates configured options; reading_plan.py assigns metadata-based reading priorities and stores separate human brief-check history. The HTTP API validates every saved choice, preserves old field payloads separately after schema changes and rejects stale revisions. Neither module reads papers or calls a model. reading.csv and reading_plan.json travel with the run.

