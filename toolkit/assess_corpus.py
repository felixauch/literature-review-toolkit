"""Draft charting for every final Include: domains, tier, decision link, relevance.

    python assess_corpus.py --project <dir>

For each record with ``fulltext_final_decision == Include`` the script reads
the cached full text (or title + abstract) and drafts:

* domain tags and a primary domain, and a technology tier (taxonomy regexes);
* decision link: explicit | operational | implicit | none;
* a 0--100 relevance score and High/Medium/Low band;
* a one-sentence "what we can use" contribution note with page-linked evidence;
* an exclusion-candidate flag with a reason;
* ``assess_reasoning`` listing the signals that fired.

Writes ``corpus_assessment.csv``. Reviewer overrides in
``corpus_assessment_backcheck.csv`` (fields) and ``corpus_taxonomy.csv``
(primary/secondary domains) take precedence, so re-running never erases a
confirmed value. Everything is heuristic and auditable, not a final judgement.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import compact, evidence_for, index_by, read_cached_pages, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

FIELDS = [
    "record_id", "assess_relevance", "assess_band", "assess_domains", "assess_primary_domain",
    "assess_secondary_domains", "assess_tier", "assess_decision_link", "assess_contribution_type",
    "assess_use", "assess_exclude_candidate", "assess_exclude_reason", "assess_evidence",
    "assess_evidence_pages", "assess_analyzable", "assess_reasoning",
]
METRIC = re.compile(r"\b(accuracy|R2|RMSE|MAE|F1|mAP|precision|recall|AUC|%)\b", re.I)


def best_contribution_sentence(pages: list[str], abstract: str) -> str:
    cue, pop, dec, op = CFG.rx("contribution_cue"), CFG.rx("ft_population"), CFG.rx("ft_decision"), CFG.rx("ft_operation")
    candidates: list[str] = []
    for block in ([abstract] if abstract else pages[:1]):
        for raw in re.split(r"(?<=[.!?])\s+", block or ""):
            s = compact(raw)
            if 60 <= len(s) <= 320 and cue.search(s):
                candidates.append(s)
            if len(candidates) >= 6:
                break
        if len(candidates) >= 6:
            break
    if not candidates:
        for raw in re.split(r"(?<=[.!?])\s+", abstract or ""):
            s = compact(raw)
            if 60 <= len(s) <= 320:
                candidates.append(s)
                break
    if not candidates:
        return ""
    candidates.sort(key=lambda s: bool(METRIC.search(s)) + bool(dec.search(s)) + bool(op.search(s)) + bool(pop.search(s)),
                    reverse=True)
    return candidates[0][:300]


def decision_link(sig: dict, tier: str) -> str:
    if tier in CFG.operational_tiers and (sig["op_ta"] or sig["agent_ta"]):
        return "operational"
    if sig["decision_ta"] and (sig["op_ta"] or sig["var_ta"]):
        return "explicit"
    if sig["op_ta"]:
        return "operational"
    if sig["decision_body"] and (sig["op_body"] or sig["var_body"]):
        return "implicit"
    if sig["var_ta"] and sig["mon_ta"]:
        return "implicit"
    return "none"


def relevance(sig: dict, domains: list[str], link: str) -> int:
    score = 30
    score += 30 if sig["decision_ta"] else (10 if sig["decision_body"] else 0)
    score += 18 if sig["agent_ta"] else (5 if sig["agent_body"] else 0)
    score += 14 if sig["op_ta"] else (5 if sig["op_body"] else 0)
    score += 10 if sig["var_ta"] else 0
    score += 8 if sig["pop_ta"] else (3 if sig["pop"] else 0)
    if sig["method_ta"] and not sig["decision_ta"] and not sig["op_ta"]:
        score -= 16
    if link == "none":
        score -= 14
    if sig["oos"] and link == "none":
        score -= 10
    if any(d in CFG.saturated_domains for d in domains) and link in ("none", "implicit") and not sig["decision_ta"] and not sig["op_ta"]:
        score -= 6
    return max(0, min(100, score))


def band(score: int) -> str:
    return "High" if score >= 68 else "Medium" if score >= 45 else "Low"


def exclude_candidate(sig: dict, link: str, score: int) -> tuple[bool, str]:
    label = CFG.population_label
    if not sig["pop"]:
        return True, f"Full text does not establish a {label} study setting."
    if sig["oos"] and link == "none":
        return True, f"Out-of-scope focus with no {label} management link."
    if sig["method_ta"] and link == "none":
        return True, "Perception/benchmarking focus in the abstract with no decision, operation, or management link."
    if link == "none" and score < 40:
        return True, "Low decision relevance: the abstract states no management or operational link."
    return False, ""


def reasoning(sig: dict, domains: list[str], tier: str, link: str) -> str:
    fired = [k for k, v in sig.items() if v is True and k not in ("analyzable",)]
    return f"tier={tier}; domains={'; '.join(domains)}; link={link}; signals={','.join(fired)}"


def main() -> None:
    CFG.guard_writable()
    meta = index_by(read_csv(CFG.file("title_screening.csv")))
    recs = read_csv(CFG.file("fulltext_recommendations.csv"))
    included = [r for r in recs if r.get("fulltext_final_decision") == "Include"]
    if not included:
        sys.exit("no final Includes yet")
    P = CFG.rx
    pop, dec, op, var, mon, meth, oos, agent = (P(k) for k in (
        "ft_population", "ft_decision", "ft_operation", "ft_management_variable", "ft_monitoring",
        "ft_method_only", "ft_out_of_scope", "agent"))

    results = []
    for row in included:
        rid = row["record_id"]
        rec = meta.get(rid, {})
        title, abstract = rec.get("title") or "", rec.get("abstract") or ""
        pages = read_cached_pages(CFG.cache_dir, rid)
        text = "\n".join(pages) if pages else f"{title}\n{abstract}"
        ta = f"{title}\n{abstract}"
        sig = {
            "decision_ta": bool(dec.search(ta)), "op_ta": bool(op.search(ta)), "var_ta": bool(var.search(ta)),
            "mon_ta": bool(mon.search(ta)), "method_ta": bool(meth.search(ta)), "agent_ta": bool(agent.search(ta)),
            "pop_ta": bool(pop.search(ta)), "decision_body": bool(dec.search(text)), "op_body": bool(op.search(text)),
            "var_body": bool(var.search(text)), "agent_body": bool(agent.search(text)), "method": bool(meth.search(text)),
            "oos": bool(oos.search(text)), "pop": bool(pop.search(text)), "analyzable": bool(pages),
        }
        domains, tier = CFG.categorise(title, abstract)
        link = decision_link(sig, tier)
        score = relevance(sig, domains, link)
        is_cand, why = exclude_candidate(sig, link, score)
        ev, pg = evidence_for(pages, [dec, op, var, meth]) if pages else ("", "")
        results.append({
            "record_id": rid, "assess_relevance": str(score), "assess_band": band(score),
            "assess_domains": "; ".join(domains), "assess_primary_domain": domains[0],
            "assess_secondary_domains": "; ".join(domains[1:]), "assess_tier": tier,
            "assess_decision_link": link, "assess_contribution_type": CFG.tier_label(tier),
            "assess_use": best_contribution_sentence(pages, abstract),
            "assess_exclude_candidate": "yes" if is_cand else "", "assess_exclude_reason": why,
            "assess_evidence": ev, "assess_evidence_pages": pg,
            "assess_analyzable": "yes" if pages else "no", "assess_reasoning": reasoning(sig, domains, tier, link),
        })

    overrides = index_by(read_csv(CFG.file("corpus_assessment_backcheck.csv")))
    for r in results:
        o = overrides.get(r["record_id"])
        if not o:
            continue
        for k in ("assess_relevance", "assess_band", "assess_domains", "assess_tier", "assess_decision_link"):
            if o.get(k):
                r[k] = o[k]
        r["assess_contribution_type"] = CFG.tier_label(r["assess_tier"])
        r["assess_exclude_candidate"], r["assess_exclude_reason"] = "", ""
        r["assess_reasoning"] += " | reviewer override applied"
    taxonomy = index_by(read_csv(CFG.file("corpus_taxonomy.csv")))
    for r in results:
        t = taxonomy.get(r["record_id"])
        domains = [d.strip() for d in r["assess_domains"].split(";") if d.strip()]
        if t and t.get("assess_primary_domain"):
            primary = t["assess_primary_domain"]
            secondary = [d.strip() for d in (t.get("assess_secondary_domains") or "").split(";") if d.strip()]
        else:
            primary = domains[0] if domains else CFG.default_domain
            secondary = [d for d in domains if d != primary]
        r["assess_primary_domain"] = primary
        r["assess_secondary_domains"] = "; ".join(secondary)
        r["assess_domains"] = "; ".join([primary] + [d for d in secondary if d != primary])

    write_csv(CFG.file("corpus_assessment.csv"), results, FIELDS)
    print(f"assessed {len(results)}: tiers {dict(Counter(r['assess_tier'] for r in results))}, "
          f"links {dict(Counter(r['assess_decision_link'] for r in results))}, "
          f"exclusion candidates {sum(1 for r in results if r['assess_exclude_candidate'])}")


if __name__ == "__main__":
    main()
