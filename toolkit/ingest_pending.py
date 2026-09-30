"""Add citation-chasing survivors as pending full-text records.

    python ingest_pending.py --project <dir> [--decisions citation_chase_human_decisions.csv]

Which candidates enter: rows marked Include in the reviewer's exported
decisions file (default ``citation_chase_human_decisions.csv``). The file is required. They
are appended to title_screening.csv (human_decision Include, source
citation_chasing), fulltext_recommendations.csv (Retain, final decision
blank) and the PDF manifest (PDF pending), and listed in
``citation_chase_fulltext_queue.csv``. They do not count toward the corpus
until full-text screened.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_files import MANIFEST_FIELDS, load_manifest, save_manifest  # noqa: E402
from lib import norm_doi, read_csv, read_csv_with_fields, write_csv  # noqa: E402
from merge_screen import SCREEN_FIELDS  # noqa: E402
from project_config import CFG  # noqa: E402
from recommend_fulltext import FIELDS as REC_FIELDS  # noqa: E402

NOTE = ("Identified via citation chasing; passed title/abstract screening only; awaiting PDF "
        "retrieval and full-text eligibility screening before any inclusion.")


def main() -> None:
    CFG.guard_writable()
    drafts = read_csv(CFG.file("citation_chase_decisions.csv"))
    if not drafts:
        sys.exit("citation_chase_decisions.csv missing; run chase_screen.py")
    human_path = CFG.file("citation_chase_human_decisions.csv")
    if "--decisions" in sys.argv:
        human_path = Path(sys.argv[sys.argv.index("--decisions") + 1])
    human = read_csv(human_path) if human_path.exists() else []
    if human:
        wanted = {(r.get("record_id") or "").strip() or norm_doi(r.get("doi")) for r in human
                  if (r.get("decision") or "") == "Include"}
        chosen = [d for d in drafts if d["record_id"] in wanted or norm_doi(d.get("doi")) in wanted]
        print(f"{len(chosen)} human Includes from {human_path.name}")
    else:
        sys.exit("No exported reviewer decisions found. Review the supplementary page and save citation_chase_human_decisions.csv first.")

    sc_fields, sc_rows = read_csv_with_fields(CFG.file("title_screening.csv"))
    rc_fields, rc_rows = read_csv_with_fields(CFG.file("fulltext_recommendations.csv"))
    mn_fields, mn_rows = load_manifest()
    sc_fields = sc_fields or SCREEN_FIELDS
    rc_fields = rc_fields or REC_FIELDS
    existing_ids = {r["record_id"] for r in sc_rows}
    existing_doi = {norm_doi(r.get("doi")) for r in sc_rows if r.get("doi")}
    queue, added = [], 0
    for c in chosen:
        rid, doi = c["record_id"], norm_doi(c.get("doi"))
        if rid in existing_ids or (doi and doi in existing_doi):
            continue
        sc_rows.append({k: "" for k in sc_fields} | {
            "record_id": rid, "suggested_decision": "Include", "exclusion_code": "",
            "screen_reason": "Citation chasing: passed title/abstract screening; full text pending.",
            "human_decision": "Include", "human_notes": "citation_chasing supplementary search",
            "title": c["title"], "authors": c.get("authors", ""), "year": c.get("year", ""), "doi": doi,
            "journal": c.get("journal", ""), "sources": "citation_chasing", "has_abstract": c.get("has_abstract", "no"),
            "abstract": c.get("abstract", ""),
        })
        rc_rows.append({k: "" for k in rc_fields} | {
            "record_id": rid, "fulltext_recommendation": "Retain",
            "fulltext_confidence": c.get("confidence") or "moderate",
            "fulltext_evidence_status": "Metadata / abstract (citation chasing) - PDF pending",
            "fulltext_reason": c.get("reason", ""), "fulltext_url": f"https://doi.org/{doi}" if doi else "",
            "fulltext_access_note": "Supplementary search; PDF retrieval pending", "fulltext_reviewed": "no",
            "fulltext_analysis_status": "pending_fulltext_screening", "fulltext_final_notes": NOTE,
        })
        mn_rows.append({k: "" for k in MANIFEST_FIELDS} | {"record_id": rid, "title": c["title"], "status": "supplementary_pdf_pending"})
        queue.append({"record_id": rid, "provisional_tier": c.get("assess_tier", ""),
                      "provisional_link": c.get("assess_decision_link", ""),
                      "provisional_primary_domain": c.get("assess_primary_domain", ""),
                      "year": c.get("year", ""), "title": c["title"], "authors": c.get("authors", ""), "doi": doi})
        added += 1
    write_csv(CFG.file("title_screening.csv"), sc_rows, sc_fields)
    write_csv(CFG.file("fulltext_recommendations.csv"), rc_rows, rc_fields)
    save_manifest(mn_rows, mn_fields)
    write_csv(CFG.file("citation_chase_fulltext_queue.csv"), queue)
    print(f"added {added} pending records; next: python pdfs.py oa / browser, analyse_fulltexts.py, recommend_fulltext.py")


if __name__ == "__main__":
    main()
