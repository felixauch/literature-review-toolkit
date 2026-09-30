"""Extract and cache PDF text; draft Retain / Exclude from the full text.

    python analyse_fulltexts.py --project <dir>

For every PDF listed in the manifest, extracts page text (pypdf) into
``fulltext_cache/<record_id>.txt`` and searches it with the ``ft_*`` regex
families from project.json (population, decision, operation, management
variable, monitoring, method-only, out-of-scope). Writes
``fulltext_analysis.csv`` with a draft recommendation, confidence, reason and
page-numbered excerpts. This is automated text analysis, not the reviewer's
decision.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import evidence_for, extract_pages, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

FIELDS = [
    "record_id", "analysis_status", "extracted_pages", "total_pages", "text_characters",
    "analysis_recommendation", "analysis_confidence", "analysis_reason", "analysis_evidence",
    "analysis_evidence_pages", "analysis_error",
]


def classify(pages: list[str]) -> tuple[str, str, str, str, str]:
    """Rule ladder over the extracted text. Returns (decision, confidence, reason, evidence, pages)."""
    P = CFG.rx
    pop, dec, op = P("ft_population"), P("ft_decision"), P("ft_operation")
    var, mon, meth, oos = P("ft_management_variable"), P("ft_monitoring"), P("ft_method_only"), P("ft_out_of_scope")
    label = CFG.population_label
    text = "\n".join(pages)
    has = {
        "pop": bool(pop.search(text)), "dec": bool(dec.search(text)), "op": bool(op.search(text)),
        "var": bool(var.search(text)), "mon": bool(mon.search(text)), "meth": bool(meth.search(text)),
        "oos": bool(oos.search(text)),
    }
    relevant = has["dec"] or has["op"] or has["var"]

    def out(decision, conf, reason, pats):
        ev, pg = evidence_for(pages, pats)
        return decision, conf, reason, ev, pg

    if not has["pop"]:
        return out("Exclude", "high", f"Full text does not establish a {label}-specific study setting.", [oos, meth])
    if has["oos"] and not relevant:
        return out("Exclude", "high", f"Out-of-scope focus without a {label} management link.", [oos, pop])
    if has["dec"] and (has["op"] or has["var"]):
        return out("Retain", "high", "Explicit decision/advisory element tied to a management variable or operation.", [dec, op, var])
    if has["op"]:
        return out("Retain", "high", f"Describes a concrete {label} management or field operation.", [op, pop])
    if has["var"] and has["mon"]:
        return out("Retain", "moderate", "Monitors, forecasts, or estimates a management variable (decision-relevant information).", [var, mon])
    if has["meth"] and not relevant:
        return out("Exclude", "moderate", "Perception/model method with no decision, operation, or management-variable link.", [meth, pop])
    if has["var"]:
        return out("Retain", "low", "Addresses a management-relevant variable; decision relevance plausible but not explicit.", [var, pop])
    return out("Exclude", "low", f"{label.capitalize()} setting established but no decision, operation, or management-variable link.", [pop, meth])


def main() -> None:
    CFG.guard_writable()
    manifest = read_csv(CFG.file("fulltext_pdf_manifest.csv"))
    items = [m for m in manifest if m.get("corpus_pdf") and (CFG.root / m["corpus_pdf"]).exists()]
    if not items:
        sys.exit("no local PDFs in the manifest; run pdfs.py first")
    results = []
    for i, item in enumerate(items, start=1):
        pages, total, error = extract_pages(CFG.cache_dir, item["record_id"], CFG.root / item["corpus_pdf"])
        extracted = [p for p in pages if p]
        if error or not extracted:
            status, rec, conf = "unreadable_or_no_extractable_text", "Needs verification", "low"
            reason, ev, pg = "The PDF could not be text-extracted; inspect the file manually.", "", ""
        else:
            status = "automated_fulltext_analysis"
            rec, conf, reason, ev, pg = classify(extracted)
        results.append({
            "record_id": item["record_id"], "analysis_status": status,
            "extracted_pages": str(len(extracted)), "total_pages": str(total),
            "text_characters": str(sum(len(p) for p in extracted)),
            "analysis_recommendation": rec, "analysis_confidence": conf, "analysis_reason": reason,
            "analysis_evidence": ev, "analysis_evidence_pages": pg, "analysis_error": error,
        })
        print(f"[{i}/{len(items)}] {item['record_id']}: {status} -> {rec}", flush=True)
    write_csv(CFG.file("fulltext_analysis.csv"), results, FIELDS)
    print(f"wrote fulltext_analysis.csv ({len(results)} rows); next: python recommend_fulltext.py")


if __name__ == "__main__":
    main()
