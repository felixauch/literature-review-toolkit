"""Export the project's screening CSV (+ pass tags, drafts) to data.json for the UI."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

UI = Path(__file__).resolve().parent
sys.path.insert(0, str(UI.parent))
sys.path.insert(0, str(UI))
from project_config import CFG  # noqa: E402
from evidence import evidence_quote  # noqa: E402

ROOT = CFG.root
CONTESTED = CFG.contested_ids


def categorise_domains(title: str, abstract: str) -> list[str]:
    """Draft domain tags from title + abstract (taxonomy regexes in project.json)."""
    return CFG.categorise(title, abstract)[0]


def categorise_record(title: str, abstract: str) -> tuple[list[str], str]:
    """Draft domain tags plus a tier from title + abstract."""
    return CFG.categorise(title, abstract)


def research_summary(
    title: str, abstract: str, primary_domain: str, tier: str
) -> str:
    """Short note on what the paper researches (abstract-led)."""
    text = re.sub(r"\s+", " ", (abstract or "").strip())
    if text:
        sentences: list[str] = []
        for raw in re.split(r"(?<=[.!?])\s+", text):
            s = raw.strip()
            if len(s) < 40:
                continue
            sentences.append(s)
            if len(sentences) >= 2 or len(" ".join(sentences)) > 280:
                break
        if sentences:
            out = " ".join(sentences)
            return out[:320] + ("…" if len(out) > 320 else "")
    domain = (primary_domain or CFG.default_domain).lower()
    return (
        f"Investigates {domain} using {tier or CFG.default_tier} approaches "
        f"in a {CFG.population_label} context: {(title or 'untitled')[:140]}."
    )


def results_summary(assess_use: str, analysis_evidence: str) -> str:
    """Short note on reported outcomes (contribution sentence preferred)."""
    if (assess_use or "").strip():
        return assess_use.strip()[:320]
    evidence = (analysis_evidence or "").strip()
    if not evidence:
        return ""
    part = evidence.split("|", 1)[0].strip()
    if part.lower().startswith("p.") and ":" in part:
        part = part.split(":", 1)[1].strip()
    return part[:320] + ("…" if len(part) > 320 else "")


def ai_pass_bucket(suggested: str, record_id: str) -> str:
    if suggested == "Exclude":
        return "A2_contested" if record_id in CONTESTED else "A1_clear"
    if suggested == "Include":
        return "B_include"
    return "C_maybe"


def pass_bucket(
    suggested: str,
    record_id: str,
    human_decision: str = "",
    backcheck_decision: str = "",
    backcheck_batch: str = "",
) -> str:
    # Human Maybe → abstract / revisit queue (C), regardless of AI pass
    if (human_decision or "").strip() == "Maybe":
        return "C_maybe"
    if not (human_decision or "").strip() and backcheck_batch:
        return {
            "Include": "D1_backcheck_include",
            "Exclude": "D2_backcheck_exclude",
            "Maybe": "D3_backcheck_uncertain",
        }.get(backcheck_decision, "D3_backcheck_uncertain")
    return ai_pass_bucket(suggested, record_id)


def main() -> None:
    csv_path = ROOT / "title_screening.csv"
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    recommendations_path = ROOT / "fulltext_recommendations.csv"
    recommendations = (
        {
            row["record_id"]: row
            for row in csv.DictReader(recommendations_path.open(encoding="utf-8"))
        }
        if recommendations_path.exists()
        else {}
    )
    assessment_path = ROOT / "corpus_assessment.csv"
    assessment = (
        {
            row["record_id"]: row
            for row in csv.DictReader(assessment_path.open(encoding="utf-8"))
        }
        if assessment_path.exists()
        else {}
    )
    records = []
    for r in rows:
        rid = r["record_id"]
        sug = r["suggested_decision"]
        human = r.get("human_decision") or ""
        backcheck = r.get("backcheck_decision") or ""
        backcheck_reason = r.get("backcheck_reason") or ""
        effective_suggestion = backcheck if not human and backcheck else sug
        effective_reason = backcheck_reason if not human and backcheck else (
            r.get("screen_reason") or ""
        )
        quote = evidence_quote(
            r.get("title") or "",
            r.get("abstract") or "",
            effective_suggestion,
            r.get("backcheck_exclusion_code")
            or r.get("exclusion_code")
            or "",
            effective_reason,
        )
        r["evidence_quote"] = quote
        ai_pass = ai_pass_bucket(sug, rid)
        report_domains, report_tier = categorise_record(
            r.get("title") or "", r.get("abstract") or ""
        )
        fulltext = recommendations.get(rid, {})
        assess = assessment.get(rid, {})
        primary_domain = assess.get("assess_primary_domain") or report_domains[0]
        records.append(
            {
                "record_id": rid,
                "search_arm": "citation_chasing" if rid.startswith(CFG.supplementary_prefix) else "database",
                "title": r["title"],
                "authors": r["authors"],
                "year": r["year"],
                "doi": r["doi"],
                "journal": r["journal"],
                "sources": r["sources"],
                "has_abstract": r["has_abstract"] == "yes",
                "abstract": r.get("abstract") or "",
                "suggested_decision": sug,
                "backcheck_decision": backcheck,
                "backcheck_confidence": r.get("backcheck_confidence") or "",
                "backcheck_score": r.get("backcheck_score") or "",
                "backcheck_reason": backcheck_reason,
                "backcheck_exclusion_code": (
                    r.get("backcheck_exclusion_code") or ""
                ),
                "backcheck_nearest_include": (
                    r.get("backcheck_nearest_include") or ""
                ),
                "backcheck_nearest_exclude": (
                    r.get("backcheck_nearest_exclude") or ""
                ),
                "backcheck_batch": r.get("backcheck_batch") or "",
                "exclusion_code": r.get("exclusion_code") or "",
                "screen_reason": r.get("screen_reason") or "",
                "evidence_quote": quote,
                "human_decision": human,
                "human_notes": r.get("human_notes") or "",
                # report_domain is kept as the first tag for backwards
                # compatibility; report_domains is the report's authoritative
                # multi-label field.
                "report_domain": report_domains[0],
                "report_domains": report_domains,
                "report_tier": report_tier,
                "fulltext_recommendation": (
                    fulltext.get("fulltext_recommendation") or ""
                ),
                "fulltext_confidence": fulltext.get("fulltext_confidence") or "",
                "fulltext_evidence_status": (
                    fulltext.get("fulltext_evidence_status") or ""
                ),
                "fulltext_reason": fulltext.get("fulltext_reason") or "",
                "fulltext_local_pdf": fulltext.get("fulltext_local_pdf") or "",
                "fulltext_url": fulltext.get("fulltext_url") or "",
                "fulltext_oa_url": fulltext.get("fulltext_oa_url") or "",
                "fulltext_access_note": (
                    fulltext.get("fulltext_access_note") or ""
                ),
                "fulltext_reviewed": fulltext.get("fulltext_reviewed") or "",
                "fulltext_analysis_status": (
                    fulltext.get("fulltext_analysis_status") or ""
                ),
                "fulltext_analysis_evidence": (
                    fulltext.get("fulltext_analysis_evidence") or ""
                ),
                "fulltext_analysis_pages": (
                    fulltext.get("fulltext_analysis_pages") or ""
                ),
                "fulltext_analysis_error": (
                    fulltext.get("fulltext_analysis_error") or ""
                ),
                "fulltext_final_decision": (
                    fulltext.get("fulltext_final_decision") or ""
                ),
                "fulltext_final_notes": (
                    fulltext.get("fulltext_final_notes") or ""
                ),
                "assess_relevance": assess.get("assess_relevance") or "",
                "assess_band": assess.get("assess_band") or "",
                "assess_domains": (
                    [d.strip() for d in assess.get("assess_domains", "").split(";") if d.strip()]
                    if assess.get("assess_domains") else []
                ),
                "assess_primary_domain": assess.get("assess_primary_domain") or "",
                "assess_secondary_domains": (
                    [d.strip() for d in assess.get("assess_secondary_domains", "").split(";") if d.strip()]
                    if assess.get("assess_secondary_domains") else []
                ),
                "assess_tier": assess.get("assess_tier") or "",
                "assess_decision_link": assess.get("assess_decision_link") or "",
                "assess_contribution_type": assess.get("assess_contribution_type") or "",
                "assess_use": assess.get("assess_use") or "",
                "assess_exclude_candidate": assess.get("assess_exclude_candidate") or "",
                "assess_exclude_reason": assess.get("assess_exclude_reason") or "",
                "assess_evidence": assess.get("assess_evidence") or "",
                "assess_evidence_pages": assess.get("assess_evidence_pages") or "",
                "assess_reasoning": assess.get("assess_reasoning") or "",
                "research_summary": research_summary(
                    r.get("title") or "",
                    r.get("abstract") or "",
                    primary_domain,
                    assess.get("assess_tier") or report_tier,
                ),
                "results_summary": results_summary(
                    assess.get("assess_use") or "",
                    fulltext.get("fulltext_analysis_evidence") or "",
                ),
                "ai_pass": ai_pass,
                "pass": pass_bucket(
                    sug,
                    rid,
                    human,
                    backcheck,
                    r.get("backcheck_batch") or "",
                ),
            }
        )

    out = {
        "meta": {
            "total": len(records),
            "generated_from": "title_screening.csv",
            "exclusion_codes": CFG.exclusion_codes,
            "project_name": CFG.name,
            "project_slug": CFG.slug,
            "frozen": CFG.frozen,
            "ui_title": CFG.ui.get("title") or "Title screening",
            "ui_subtitle": CFG.ui.get("subtitle") or "Scripts suggest, you decide.",
            "taxonomy": {
                "domains": CFG.domain_names,
                "default_domain": CFG.default_domain,
                "tiers": CFG.tier_names,
                "default_tier": CFG.default_tier,
                "operational_tiers": CFG.operational_tiers,
                "tier_labels": {t: CFG.tier_label(t) for t in CFG.tier_names},
                "link_labels": CFG.link_labels,
            },
        },
        "records": records,
    }
    path = CFG.ui_data
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {path} ({len(records)} records)")


if __name__ == "__main__":
    main()
