"""Build a provisional screening overview, never a final classification export.

    python build_overview.py --project <dir>

Writes ``screening_corpus_draft.csv`` (one row per final Include with the
draft domains, tier, decision link and relevance; confirmation is not established here) and
``screening_overview_draft.md`` (decision counts, primary domain x tier matrix,
provenance). An existing ``report_core_domains`` column is preserved.
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import index_by, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

FIELDS = ["classification_status", "record_id", "title", "authors", "year", "doi", "report_domains", "report_primary_domain",
          "report_core_domains", "report_secondary_domains", "report_tier", "relevance_score", "relevance_band",
          "decision_link", "fulltext_confidence", "fulltext_evidence_status", "fulltext_reason", "fulltext_local_pdf"]


def main() -> None:
    CFG.guard_writable()
    meta = index_by(read_csv(CFG.file("title_screening.csv")))
    recs = read_csv(CFG.file("fulltext_recommendations.csv"))
    assessment = index_by(read_csv(CFG.file("corpus_assessment.csv")))
    manifest = read_csv(CFG.file("fulltext_pdf_manifest.csv"))
    previous = index_by(read_csv(CFG.file("screening_corpus_draft.csv")))
    finals = Counter(r.get("fulltext_final_decision") or "Undecided" for r in recs)
    included = [r for r in recs if r.get("fulltext_final_decision") == "Include"]
    tiers = CFG.tier_names

    rows, matrix, tier_tot, dom_tot = [], Counter(), Counter(), Counter()
    for r in included:
        rid = r["record_id"]
        rec, a = meta.get(rid, {}), assessment.get(rid, {})
        if a:
            domains = [d.strip() for d in a["assess_domains"].split(";") if d.strip()]
            tier = a["assess_tier"]
            primary = a.get("assess_primary_domain") or (domains[0] if domains else CFG.default_domain)
            secondary = a.get("assess_secondary_domains") or ""
        else:
            domains, tier = CFG.categorise(rec.get("title") or "", rec.get("abstract") or "")
            primary, secondary = domains[0], "; ".join(domains[1:])
        tier_tot[tier] += 1
        matrix[(primary, tier)] += 1
        dom_tot[primary] += 1
        prev_core = (previous.get(rid) or {}).get("report_core_domains") or primary
        rows.append({
            "classification_status": "unconfirmed", "record_id": rid, "title": rec.get("title") or "", "authors": rec.get("authors") or "",
            "year": rec.get("year") or "", "doi": rec.get("doi") or "", "report_domains": "; ".join(domains),
            "report_primary_domain": primary, "report_core_domains": prev_core,
            "report_secondary_domains": secondary, "report_tier": tier,
            "relevance_score": a.get("assess_relevance") or "", "relevance_band": a.get("assess_band") or "",
            "decision_link": a.get("assess_decision_link") or "", "fulltext_confidence": r.get("fulltext_confidence") or "",
            "fulltext_evidence_status": r.get("fulltext_evidence_status") or "", "fulltext_reason": r.get("fulltext_reason") or "",
            "fulltext_local_pdf": r.get("fulltext_local_pdf") or "",
        })
    write_csv(CFG.file("screening_corpus_draft.csv"), rows, FIELDS)

    arms = Counter("citation_chasing" if r["record_id"].startswith(CFG.supplementary_prefix) else "database" for r in rows)
    L = [f"# Screening overview (unconfirmed classifications) — {CFG.name}", "", f"_Generated {datetime.now():%Y-%m-%d %H:%M}._", "",
         "Classification fields in this report are provisional. Export confirmed labels from the combined review interface.", "", "## Full-text eligibility decisions", "", "| Decision | Count |", "| --- | ---: |"]
    L += [f"| {k} | {finals[k]} |" for k in ("Include", "Exclude", "Undecided") if finals.get(k)]
    L += [f"| **Kept at title/abstract** | **{len(recs)}** |", "",
          f"Included by arm: " + ", ".join(f"{k} {v}" for k, v in arms.items()), "",
          "## Draft primary domain x tier (screened Includes)", "",
          "| Domain | " + " | ".join(tiers) + " | Total |", "| --- | " + " | ".join(["---:"] * (len(tiers) + 1)) + " |"]
    for d in sorted(dom_tot, key=lambda d: -dom_tot[d]):
        L.append(f"| {d} | " + " | ".join(str(matrix.get((d, t), 0)) for t in tiers) + f" | {dom_tot[d]} |")
    L.append("| **Total** | " + " | ".join(str(tier_tot.get(t, 0)) for t in tiers) + f" | **{len(rows)}** |")
    L += ["", "## Evidence provenance", "", "| Status | Count |", "| --- | ---: |"]
    L += [f"| {s} | {n} |" for s, n in Counter(r.get("fulltext_evidence_status") or "unknown" for r in included).most_common()]
    L += ["", "## PDF manifest", "", "| Status | Count |", "| --- | ---: |"]
    L += [f"| {s} | {n} |" for s, n in Counter(r.get("status") or "unknown" for r in manifest).most_common()]
    CFG.file("screening_overview_draft.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(rows)} screened Includes -> screening_corpus_draft.csv (unconfirmed labels); tiers {dict(tier_tot)}")


if __name__ == "__main__":
    main()
