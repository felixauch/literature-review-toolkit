"""Apply reviewer adjudications recorded as data, not code.

    python apply_adjudications.py --project <dir> [--dry-run]

``adjudications.csv`` in the project folder has one row per change::

    record_id,target,field,value,reason,date,applied_at

target  screening   -> title_screening.csv          (e.g. human_decision, exclusion_code, human_notes)
        fulltext    -> fulltext_recommendations.csv (fulltext_final_decision moves/deletes the PDF copy)
        assessment  -> corpus_assessment.csv + persistent override in corpus_assessment_backcheck.csv
                       (assess_tier, assess_decision_link, assess_band, assess_relevance, assess_domains,
                        assess_primary_domain, assess_secondary_domains -> also corpus_taxonomy.csv)
        corpus      -> screening_corpus_draft.csv    (report_* fields)

Rows with a non-empty ``applied_at`` are skipped; the script fills it in.
There are no one-off override scripts: the audit trail is the CSV itself.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_files import apply_fulltext_decisions  # noqa: E402
from lib import read_csv_with_fields, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

ADJ_FIELDS = ["record_id", "target", "field", "value", "reason", "date", "applied_at"]
TARGET_FILES = {
    "screening": "title_screening.csv",
    "fulltext": "fulltext_recommendations.csv",
    "assessment": "corpus_assessment.csv",
    "corpus": "screening_corpus_draft.csv",
}
BACKCHECK_FIELDS = ["record_id", "assess_domains", "assess_tier", "assess_decision_link", "assess_relevance",
                    "assess_band", "backcheck_exclude", "backcheck_exclude_reason"]
TAX_FIELDS = ["record_id", "assess_primary_domain", "assess_secondary_domains"]


def set_field(path: Path, record_id: str, field: str, value: str) -> bool:
    fields, rows = read_csv_with_fields(path)
    if not rows:
        raise FileNotFoundError(path.name)
    if field not in fields:
        fields.append(field)
    hit = False
    for r in rows:
        if r.get("record_id") == record_id:
            r[field] = value
            hit = True
    if hit:
        write_csv(path, rows, fields)
    return hit


def upsert(path: Path, record_id: str, patch: dict, default_fields: list[str]) -> None:
    fields, rows = read_csv_with_fields(path)
    fields = fields or list(default_fields)
    for k in patch:
        if k not in fields:
            fields.append(k)
    for r in rows:
        if r.get("record_id") == record_id:
            r.update(patch)
            break
    else:
        rows.append({"record_id": record_id, **patch})
    write_csv(path, rows, fields)


def main() -> None:
    CFG.guard_writable()
    dry = "--dry-run" in sys.argv
    path = CFG.file("adjudications.csv")
    fields, rows = read_csv_with_fields(path)
    if not rows:
        sys.exit("adjudications.csv is empty or missing")
    for f in ADJ_FIELDS:
        if f not in fields:
            fields.append(f)
    applied = skipped = 0
    for a in rows:
        if (a.get("applied_at") or "").strip():
            skipped += 1
            continue
        target, field, value, rid = a.get("target", ""), a.get("field", ""), a.get("value", ""), a.get("record_id", "")
        if target not in TARGET_FILES:
            print(f"  ! {rid}: unknown target {target!r}")
            continue
        print(f"  {rid}: {target}.{field} = {value!r}  ({a.get('reason', '')})")
        if dry:
            continue
        ok = True
        if target == "fulltext" and field == "fulltext_final_decision":
            ok = apply_fulltext_decisions({rid: {"fulltext_final_decision": value,
                                                 "fulltext_final_notes": f"Adjudication {a.get('date', '')}: {a.get('reason', '')}"}}) > 0
        else:
            ok = set_field(CFG.file(TARGET_FILES[target]), rid, field, value)
            if target == "assessment":
                if field in ("assess_primary_domain", "assess_secondary_domains"):
                    upsert(CFG.file("corpus_taxonomy.csv"), rid, {field: value}, TAX_FIELDS)
                else:
                    upsert(CFG.file("corpus_assessment_backcheck.csv"), rid, {field: value}, BACKCHECK_FIELDS)
        if not ok:
            print(f"  ! {rid} not found in {TARGET_FILES[target]}")
            continue
        a["applied_at"] = time.strftime("%Y-%m-%d %H:%M")
        applied += 1
    if not dry:
        write_csv(path, rows, fields)
    print(f"applied {applied}, skipped {skipped} already applied" + (" (dry run)" if dry else ""))


if __name__ == "__main__":
    main()
