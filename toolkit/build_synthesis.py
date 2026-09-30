"""Draft a structured synthesis from the charted corpus.

    python build_synthesis.py --project <dir>

Aggregates ``corpus_assessment.csv`` into ``synthesis_draft.md``: corpus at a
glance (tiers, relevance bands, decision links), one section per primary
domain with tier/link mix and representative high-relevance papers, cross-
tier observations computed from the counts, flagged inclusion candidates and
low-relevance papers. The wording is template text for the reviewer to
rewrite; it is not manuscript prose.
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import index_by, read_csv, short_author  # noqa: E402
from project_config import CFG  # noqa: E402

LINK_ORDER = ["explicit", "operational", "implicit", "none"]


def main() -> None:
    CFG.guard_writable()
    meta = index_by(read_csv(CFG.file("title_screening.csv")))
    rows = read_csv(CFG.file("corpus_assessment.csv"))
    if not rows:
        sys.exit("corpus_assessment.csv missing; run assess_corpus.py")
    # only current final Includes (the assessment file may still hold rows excluded later)
    finals = {r["record_id"]: r.get("fulltext_final_decision") for r in read_csv(CFG.file("fulltext_recommendations.csv"))}
    if finals:
        rows = [r for r in rows if finals.get(r["record_id"]) == "Include"]
    n = len(rows)
    labels = CFG.link_labels

    def cite(rid: str) -> str:
        m = meta.get(rid, {})
        return f"{short_author(m.get('authors') or '')} {m.get('year') or 'n.d.'} [{rid}]"

    def score(r: dict) -> int:
        return int(r.get("assess_relevance") or 0)

    tiers = Counter(r["assess_tier"] for r in rows)
    bands = Counter(r["assess_band"] for r in rows)
    links = Counter(r["assess_decision_link"] for r in rows)
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_domain[r.get("assess_primary_domain") or CFG.default_domain].append(r)
    domains = sorted(by_domain, key=lambda d: -len(by_domain[d]))

    L = [f"# Synthesis draft — {CFG.name}", "",
         f"_Generated {datetime.now():%Y-%m-%d %H:%M} from the charting of {n} included papers. Template text for revision._", "",
         "## 1. Corpus at a glance", "",
         f"The corpus comprises **{n} papers**. By tier: " + ", ".join(f"**{tiers.get(t, 0)} {t}** ({CFG.tier_label(t)})" for t in CFG.tier_names) + ".",
         f"Relevance bands: **{bands.get('High', 0)} high**, **{bands.get('Medium', 0)} medium**, **{bands.get('Low', 0)} low**.", "",
         "| Decision link | Papers | Reported as |", "| --- | ---: | --- |"]
    L += [f"| {k} | {links[k]} | {labels.get(k, k)} |" for k in LINK_ORDER if links.get(k)]
    L += ["", "## 2. By primary domain", "",
          "Each paper counts once, under its primary domain; secondary domains stay in the CSV as coverage metadata.", ""]
    for d in domains:
        items = by_domain[d]
        dt, dl = Counter(r["assess_tier"] for r in items), Counter(r["assess_decision_link"] for r in items)
        L += [f"### {d} ({len(items)} papers)", "",
              "Tiers: " + " · ".join(f"{dt.get(t, 0)} {t}" for t in CFG.tier_names) + ". Decision link: "
              + ", ".join(f"{dl.get(k, 0)} {k}" for k in LINK_ORDER if dl.get(k)) + ".", ""]
        for r in sorted(items, key=score, reverse=True)[:4]:
            use = (r.get("assess_use") or "").strip() or "(no extracted takeaway; see PDF)"
            L.append(f"- **{cite(r['record_id'])}** (relevance {r['assess_relevance']}, {r['assess_tier']}, {r['assess_decision_link']} link): {use}")
        L.append("")
    top_tier = tiers.most_common(1)[0][0] if tiers else ""
    explicit_share = (links.get("explicit", 0) + links.get("operational", 0)) / n if n else 0
    L += ["## 3. Cross-tier observations", "",
          f"- **{top_tier} dominates** with {tiers.get(top_tier, 0)} of {n} papers.",
          f"- **{explicit_share:.0%} of papers state an explicit or operational decision link**; the rest provide information (implicit) or no stated link.",
          f"- Operational tiers ({', '.join(CFG.operational_tiers) or 'none configured'}): "
          + f"{sum(tiers.get(t, 0) for t in CFG.operational_tiers)} papers.",
          f"- Largest domain: {domains[0]} ({len(by_domain[domains[0]])}); smallest: {domains[-1]} ({len(by_domain[domains[-1]])})." if domains else "",
          ""]
    cands = [r for r in rows if r.get("assess_exclude_candidate") == "yes"]
    L += ["## 4. Still-questionable inclusions", ""]
    if cands:
        L.append(f"The heuristics flag **{len(cands)}** papers as exclusion candidates; check them in the Assessment view:")
        L.append("")
        L += [f"- **{cite(r['record_id'])}** — {r.get('assess_exclude_reason', '')}" for r in sorted(cands, key=score)]
    else:
        L.append("No papers are flagged as exclusion candidates.")
    lows = sorted((r for r in rows if r.get("assess_band") == "Low"), key=score)
    if lows:
        L += ["", f"A further **{len(lows)}** low-relevance papers: " + ", ".join(cite(r["record_id"]) for r in lows[:10]) + "."]
    L += ["", "## 5. Answer skeleton", "",
          f"> Across {n} eligible sources the field is dominated by {top_tier} contributions; "
          f"{links.get('explicit', 0)} papers provide advisory decision support, {links.get('operational', 0)} execute an operation, "
          f"and {links.get('implicit', 0)} supply monitoring or estimation only. Domain coverage is uneven "
          f"({domains[0]} vs {domains[-1]}). _Rewrite in the manuscript's voice._" if domains else ""]
    CFG.file("synthesis_draft.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote synthesis_draft.md ({n} papers, {len(domains)} domains)")


if __name__ == "__main__":
    main()
