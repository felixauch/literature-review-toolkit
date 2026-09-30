"""Preliminary full-text recommendation per kept record.

    python recommend_fulltext.py --project <dir> [--openalex]

Combines the title/abstract rules with the automated full-text analysis
(``fulltext_analysis.csv``) into ``fulltext_recommendations.csv``: one row per
record the reviewer kept at title--abstract, with a Retain/Exclude draft,
confidence, reason, evidence status, local PDF path and (optionally) an
open-access link from OpenAlex. Human final decisions already in the file are
preserved. Never changes title--abstract decisions.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import index_by, openalex_work_by_doi, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

FIELDS = [
    "record_id", "fulltext_recommendation", "fulltext_confidence", "fulltext_evidence_status",
    "fulltext_reason", "fulltext_local_pdf", "fulltext_url", "fulltext_oa_url", "fulltext_access_note",
    "fulltext_reviewed", "fulltext_analysis_status", "fulltext_analysis_evidence",
    "fulltext_analysis_pages", "fulltext_analysis_error", "fulltext_final_decision", "fulltext_final_notes",
]


def preliminary(title: str, abstract: str) -> tuple[str, str, str]:
    """Binary recommendation from metadata alone (title + abstract rule ladder)."""
    P = CFG.rx
    pop, dec, op, agent = P("ft_population"), P("ft_decision"), P("ft_operation"), P("agent")
    var, mon, meth, oos = P("ft_management_variable"), P("ft_monitoring"), P("ft_method_only"), P("ft_out_of_scope")
    label = CFG.population_label
    text = f"{title} {abstract}"
    relevant = bool(dec.search(text) or op.search(text) or agent.search(text) or var.search(text))
    if not abstract.strip():
        if pop.search(title) and (dec.search(title) or op.search(title) or agent.search(title) or var.search(title)):
            return "Retain", "low", f"No abstract; the title indicates a {label} management or decision-relevant focus."
        if pop.search(title):
            return "Retain", "low", f"No abstract; the title is {label}-specific. Retained pending full text."
        return "Exclude", "low", f"No abstract and the title is not clearly {label}-specific."
    if oos.search(text) and not pop.search(title) and not relevant:
        return "Exclude", "moderate", f"Abstract indicates an out-of-scope focus rather than a {label} management application."
    if not pop.search(text):
        return "Exclude", "low", f"The {label} is not explicit in the metadata."
    if dec.search(text) and (op.search(text) or agent.search(text) or var.search(text)):
        return "Retain", "high", "Abstract describes a decision-support or operational workflow linked to a management variable or action."
    if agent.search(text) and op.search(text):
        return "Retain", "moderate", "Abstract describes an autonomous or robotic capability linked to a management operation."
    if var.search(text) and mon.search(text):
        return "Retain", "moderate", "Abstract monitors, forecasts, or estimates a management variable (decision-relevant information)."
    if meth.search(text) and not relevant:
        return "Exclude", "moderate", "Abstract presents a perception/model method without a decision, operation, or management-variable link."
    if var.search(text) or op.search(text):
        return "Retain", "low", "Abstract addresses a management-relevant variable; decision relevance is plausible."
    return "Exclude", "low", f"{label.capitalize()} present, but no decision, operation, or management-variable link in the metadata."


def main() -> None:
    CFG.guard_writable()
    discover = "--openalex" in sys.argv
    screen = read_csv(CFG.file("title_screening.csv"))
    kept = [r for r in screen if (r.get("human_decision") or "") == "Include"]
    previous = index_by(read_csv(CFG.file("fulltext_recommendations.csv")))
    manifest = {r["record_id"]: r["corpus_pdf"] for r in read_csv(CFG.file("fulltext_pdf_manifest.csv"))
                if r.get("corpus_pdf") and (CFG.root / r["corpus_pdf"]).exists()}
    analyses = index_by(read_csv(CFG.file("fulltext_analysis.csv")))

    rows = []
    for r in kept:
        rid = r["record_id"]
        rec, conf, reason = preliminary(r.get("title") or "", r.get("abstract") or "")
        status, local = "Metadata / abstract only", ""
        if rid in manifest:
            status, local = "Local PDF available (not reviewed)", manifest[rid]
        a = analyses.get(rid, {})
        if a.get("analysis_status") == "automated_fulltext_analysis":
            rec, conf, reason = a["analysis_recommendation"], a["analysis_confidence"], a["analysis_reason"]
            status = "Automated full-text analysis (human review pending)"
        elif a.get("analysis_status") == "unreadable_or_no_extractable_text":
            status = "Local PDF not text-extractable; decided from metadata"
            reason = f"{reason} (local PDF was not text-extractable)"
        prev = previous.get(rid, {})
        doi = (r.get("doi") or "").strip()
        oa_url, note = prev.get("fulltext_oa_url") or "", prev.get("fulltext_access_note") or "OA discovery not run"
        if discover and doi:
            work = openalex_work_by_doi(doi, CFG.user_agent)
            loc = (work or {}).get("best_oa_location") or {}
            oa_url = loc.get("pdf_url") or loc.get("landing_page_url") or ""
            note = "Open-access link discovered (not reviewed)" if oa_url else "No OpenAlex OA link found"
        if prev.get("fulltext_final_decision") == "Include":
            reviewed = prev.get("fulltext_reviewed") or "no"
        else:
            reviewed = prev.get("fulltext_reviewed") or "no"
        rows.append({
            "record_id": rid, "fulltext_recommendation": rec, "fulltext_confidence": conf,
            "fulltext_evidence_status": prev.get("fulltext_evidence_status") if reviewed == "yes" else status,
            "fulltext_reason": reason, "fulltext_local_pdf": local or prev.get("fulltext_local_pdf") or "",
            "fulltext_url": f"https://doi.org/{doi}" if doi else "", "fulltext_oa_url": oa_url,
            "fulltext_access_note": note, "fulltext_reviewed": reviewed,
            "fulltext_analysis_status": a.get("analysis_status") or prev.get("fulltext_analysis_status") or "",
            "fulltext_analysis_evidence": a.get("analysis_evidence") or prev.get("fulltext_analysis_evidence") or "",
            "fulltext_analysis_pages": a.get("analysis_evidence_pages") or prev.get("fulltext_analysis_pages") or "",
            "fulltext_analysis_error": a.get("analysis_error") or "",
            "fulltext_final_decision": prev.get("fulltext_final_decision") or "",
            "fulltext_final_notes": prev.get("fulltext_final_notes") or "",
        })
    # keep rows for records no longer marked Include? drop them; the human decision governs
    write_csv(CFG.file("fulltext_recommendations.csv"), rows, FIELDS)
    from collections import Counter
    print(f"{len(rows)} kept records; drafts {dict(Counter(r['fulltext_recommendation'] for r in rows))}")


if __name__ == "__main__":
    main()
