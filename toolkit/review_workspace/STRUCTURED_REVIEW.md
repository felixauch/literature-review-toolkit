# Structured review and reading priorities

## Choices on one page

Project fields use `type: single`, `type: multi` or `type: text`. Single/multi fields need an `options` list. Optional `exclusive_options` identify answers that cannot be combined with other answers. The setup wizard asks for these settings. Define all groups and measures for your own review; the template contains none.

All extraction groups appear together. A choice automatically sets the field to Recorded. Unchecked, Not reported, Not applicable and Unclear remain separate states; selecting these clears previous choices. No answer is inferred from an empty search. Recorded source fields require an exact attached passage or a source-page reference before confirmation. Author fields describe your interpretation, not a study finding.

Use Source search to expand the local passage search. Sources are not prefilled into the codes. Exact effect sizes and conditions must still be checked in the source before quantitative claims are written.

The synthesis map uses the configured choice measures, with no fixed taxonomy. Bar charts show choices; an interactive matrix compares domains or categories with a selected measure. Counts and missing choices are shown explicitly. Click a count to inspect its papers. Multiple-choice counts and domain/category rows can overlap. Completed extraction entries share the neutral Assessed display label; category decisions display Classified. Drafts stay separate. These display labels do not alter verification history. Domain-level notes are synthesis, not extra observations.

## Reading plan (optional)

The setup wizard can create reading priorities, matching conditions and selectable reasons. You define the titles and order of the groups, whether each receives brief or detailed reading, and the criteria based on your own category labels and metadata values. You can also add or edit a `reading_plan` object in project JSON before preparing a run. It contains ordered `groups`, each with `id`, `title`, `depth` (brief or detailed) and a `match` object. Matching uses metadata only: `decision_links`, `categories_any` and `categories_exact`. Conditions within a group are combined; the first matching group wins. A group with an empty match is a fallback. No source text or model is used to set reading order.

An existing run can instead receive a separate `reading_plan.json` with the same object. Preserve a dated copy when changing its rules. Example using an unrelated topic:

```json
{"groups":[
 {"id":"field","title":"Field evaluations","depth":"detailed","match":{"decision_links":["field"]}},
 {"id":"bench","title":"Bench studies","depth":"brief","match":{"categories_any":["Bench testing"]}}
],"reason_choices":["Independent validation","Important limitation","Comparable evidence already selected"]}
```

Reading priority changes neither eligibility nor labels. Unmatched records remain visible for manual checking. Read high-priority groups first. In brief groups, inspect the abstract/conclusion and open the PDF if needed, select a reading reason and explicitly confirm your check. Choose Brief check sufficient, Select for detailed extraction or Decide later. Selecting detailed reading does not confirm any extraction fields. Brief checks are counted separately from confirmed detailed extractions. A change of labels or source hashes requires rechecking the reading choice.

## Persistence and earlier notes

`reading.csv` holds brief-check choices and append-only history. Extraction and classification have separate CSV histories. Exports include reading reasons, status, reviewer and configuration. Reading drafts autosave; confirmation is explicit. Save before changing servers or closing a window.

Changing an established extraction schema requires deliberate migration and a backup. When a new schema has different field IDs, the interface preserves previous fields under Earlier saved notes. It does not interpret or convert them, and the new fields remain unchecked. JSON history retains the original data. A prior confirmation does not confirm the new schema. Use a new server process after changing configuration; do not assume an already-running process has reloaded it.

## Interpretation limits

A reading priority is not a quality score. Briefly checked sources remain part of the corpus, but they do not support unexamined detailed claims. Purposively selected detailed studies cannot establish whole-corpus percentages for validation/adoption or universal claims of absence. Define selection criteria and report actual completed coverage separately from the planned reading groups.

Subject-specific extraction schemes belong in separate project configurations. No subject-specific fields, labels, reading groups or answer lists are bundled as defaults. A new project may use any number of groups/measures supported by the configuration limits. Required/optional flags, author-interpretation flags, single/multiple choice and mutually exclusive answers are set during setup.

A project may combine test setting and farm use into a single Evidence of testing and use field. A compact example has three choices: Concept / laboratory only (including offline datasets and simulation), Field trial, and Operational management use. Choose the highest level supported by the source. Research at a commercial farm remains a field trial. Operational use requires reported management use by growers or advisers; availability or participation in beta testing alone is insufficient. Routine use may be observed during a research study, without proving that use continued afterwards. Record the scope and limits in notes and leave unclear cases unresolved. These choices are examples, not a preloaded taxonomy.

