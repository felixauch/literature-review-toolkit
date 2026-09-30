"""Draft decisions for citation-chasing candidates.

    python chase_screen.py --project <dir> [--fetch]

Reads ``citation_chase_candidates.csv`` and writes
``citation_chase_decisions.csv`` (one row per candidate, with a stable
supplementary record ID) plus ``citation_chase_shortlist.csv`` for the review
page. ``--fetch`` fills missing abstracts, authors and journals from OpenAlex
(network; cached in ``citation_chase_meta.json``).

Per candidate:
* bucket    review | offtopic | screenable   (title/abstract regexes)
* recommendation, confidence, reason         (same ladder as recommend_fulltext)
* draft domain(s), tier, decision link       (taxonomy from project.json)
* strict    strong | review_by_hand | weak_monitoring | drop_kind
* decision  Include if recommendation is Retain and the strict bar is met
            (``chase_strict_bar`` in project.json, default true), else Exclude
* core      yes when Include and (explicit/operational link or operational tier)

Nothing here is final: the reviewer screens the shortlist in the browser.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import get_json, norm_doi, openalex_abstract, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402
from recommend_fulltext import preliminary  # noqa: E402

FIELDS = [
    "record_id", "decision", "reason", "bucket", "strict", "core", "recommendation", "confidence",
    "assess_primary_domain", "assess_domains", "assess_tier", "assess_decision_link",
    "has_abstract", "year", "title", "authors", "journal", "doi", "n_links", "linked_records", "abstract",
]


def fetch_meta(dois: list[str]) -> dict[str, dict]:
    cache_path = CFG.file("citation_chase_meta.json")
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    todo = [d for d in dois if d and d not in cache]
    for i in range(0, len(todo), 40):
        batch = todo[i:i + 40]
        flt = "|".join("https://doi.org/" + d for d in batch)
        url = (f"https://api.openalex.org/works?per-page=50&mailto={CFG.contact_email}"
               "&select=doi,title,authorships,primary_location,abstract_inverted_index,publication_year"
               "&filter=doi:" + urllib.parse.quote(flt, safe="|:/."))
        try:
            for w in get_json(url, CFG.user_agent).get("results", []):
                d = norm_doi(w.get("doi"))
                authors = "; ".join(a.get("author", {}).get("display_name", "") for a in w.get("authorships", [])[:8])
                journal = ((w.get("primary_location") or {}).get("source") or {}).get("display_name", "")
                cache[d] = {"authors": authors, "journal": journal,
                            "abstract": openalex_abstract(w.get("abstract_inverted_index")),
                            "year": w.get("publication_year") or ""}
        except Exception as exc:  # noqa: BLE001
            print("openalex error", repr(exc))
        time.sleep(0.3)
        print(f"  metadata {min(i + 40, len(todo))}/{len(todo)}")
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return cache


def decision_link(title: str, abstract: str, tier: str) -> str:
    P = CFG.rx
    ta = f"{title}\n{abstract}"
    dec, op, var, mon = P("ft_decision").search(ta), P("ft_operation").search(ta), P("ft_management_variable").search(ta), P("ft_monitoring").search(ta)
    if tier in CFG.operational_tiers and (op or P("agent").search(ta)):
        return "operational"
    if dec and (op or var):
        return "explicit"
    if op:
        return "operational"
    if var and mon:
        return "implicit"
    return "none"


def main() -> None:
    CFG.guard_writable()
    cands = read_csv(CFG.file("citation_chase_candidates.csv"))
    if not cands:
        sys.exit("citation_chase_candidates.csv missing; run citation_chase.py")
    meta = fetch_meta([norm_doi(c.get("doi")) for c in cands]) if "--fetch" in sys.argv else (
        json.loads(CFG.file("citation_chase_meta.json").read_text(encoding="utf-8"))
        if CFG.file("citation_chase_meta.json").exists() else {})
    previous = {r.get("doi") or r.get("title"): r for r in read_csv(CFG.file("citation_chase_decisions.csv"))}
    strict_bar = CFG.data.get("chase_strict_bar", True)
    P = CFG.rx
    prefix = CFG.supplementary_prefix

    rows = []
    for i, c in enumerate(cands, start=1):
        doi = norm_doi(c.get("doi"))
        m = meta.get(doi, {})
        title = c.get("title") or ""
        abstract = c.get("abstract") or m.get("abstract") or ""
        prev = previous.get(doi or title, {})
        rid = prev.get("record_id") or f"{prefix}{i:04d}"
        hay = f"{title} {abstract}"
        if P("review").search(title):
            bucket = "review"
        elif (P("wrong_population").search(hay) or P("out_of_scope").search(hay)) and not P("population").search(hay):
            bucket = "offtopic"
        else:
            bucket = "screenable"
        rec, conf, reason = preliminary(title, abstract)
        domains, tier = CFG.categorise(title, abstract)
        link = decision_link(title, abstract, tier)
        n_links = int(c.get("n_links") or 0)
        if bucket != "screenable" or (P("ft_method_only").search(hay) and link == "none"):
            strict = "drop_kind"
        elif link in ("explicit", "operational") or tier in CFG.operational_tiers:
            strict = "strong"
        elif n_links >= 3:
            strict = "review_by_hand"
        else:
            strict = "weak_monitoring"
        if bucket == "review":
            decision, why = "Exclude", "Review article (context only)."
        elif bucket == "offtopic":
            decision, why = "Exclude", "Off-topic population or scope."
        elif rec != "Retain":
            decision, why = "Exclude", reason
        elif strict_bar and strict not in ("strong", "review_by_hand"):
            decision, why = "Exclude", f"Retain draft but below the decision-coupled bar ({strict}). {reason}"
        else:
            decision, why = "Include", reason
        core = "yes" if decision == "Include" and (link in ("explicit", "operational") or tier in CFG.operational_tiers) else ""
        rows.append({
            "record_id": rid, "decision": decision, "reason": why, "bucket": bucket, "strict": strict, "core": core,
            "recommendation": rec, "confidence": conf,
            "assess_primary_domain": domains[0], "assess_domains": "; ".join(domains), "assess_tier": tier,
            "assess_decision_link": link, "has_abstract": "yes" if abstract.strip() else "no",
            "year": c.get("year") or m.get("year") or "", "title": title,
            "authors": m.get("authors") or c.get("authors") or "", "journal": m.get("journal") or c.get("journal") or "",
            "doi": doi, "n_links": str(n_links), "linked_records": c.get("linked_records") or "", "abstract": abstract,
        })
    write_csv(CFG.file("citation_chase_decisions.csv"), rows, FIELDS)
    shortlist = [r for r in rows if r["strict"] in ("strong", "review_by_hand")]
    write_csv(CFG.file("citation_chase_shortlist.csv"), shortlist, FIELDS)
    print(f"{len(rows)} candidates: {dict(Counter(r['decision'] for r in rows))}; "
          f"strict {dict(Counter(r['strict'] for r in rows))}; shortlist {len(shortlist)}; core {sum(1 for r in rows if r['core'])}")
    print("next: python build_supplementary_review.py, screen in the browser, then ingest_pending.py")


if __name__ == "__main__":
    main()
