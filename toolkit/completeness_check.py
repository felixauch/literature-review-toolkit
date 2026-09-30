"""Completeness probes: external search hits vs the project.  [network for OpenAlex]

    python completeness_check.py --project <dir> openalex
    python completeness_check.py --project <dir> hits scholar_hits.csv

``openalex``: runs each query in ``completeness_queries`` (project.json)
against OpenAlex full-text search (top 50, configured languages and
min_year) and cross-checks the hits against the screening file, the chasing
decisions and the final corpus. ``hits <csv>``: does the same for a CSV of
manually collected hits (columns: title, year, first_author, doi) such as
Google Scholar result pages typed in by hand.

Matching is by DOI where available, otherwise normalised title. Every hit is
labelled: in_final_corpus | screened_not_included | chased_not_included |
new. New hits are further tagged ``plausible`` when title/abstract match the
population and technology patterns, so the reviewer knows which to judge.
Writes completeness_hits.csv and completeness_report.md.
"""
from __future__ import annotations

import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import get_json, norm_doi, norm_title, openalex_abstract, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402


def build_index() -> tuple[dict, dict]:
    screen = read_csv(CFG.file("title_screening.csv"))
    recs = {r["record_id"]: r for r in read_csv(CFG.file("fulltext_recommendations.csv"))}
    chase = read_csv(CFG.file("citation_chase_decisions.csv"))
    by_doi, by_title = {}, {}
    for r in screen:
        status = "in_final_corpus" if recs.get(r["record_id"], {}).get("fulltext_final_decision") == "Include" else "screened_not_included"
        if r.get("doi"):
            by_doi[norm_doi(r["doi"])] = (status, r["record_id"])
        by_title[norm_title(r["title"])] = (status, r["record_id"])
    for c in chase:
        key = norm_doi(c.get("doi"))
        if key and key not in by_doi:
            by_doi[key] = ("chased_not_included", c.get("record_id", ""))
        nt = norm_title(c.get("title"))
        if nt and nt not in by_title:
            by_title[nt] = ("chased_not_included", c.get("record_id", ""))
    return by_doi, by_title


def label(hit: dict, by_doi: dict, by_title: dict) -> tuple[str, str]:
    d = norm_doi(hit.get("doi") or "")
    if d and d in by_doi:
        return by_doi[d]
    nt = norm_title(hit.get("title") or "")
    if nt and nt in by_title:
        return by_title[nt]
    hay = f"{hit.get('title', '')} {hit.get('abstract', '')}"
    plausible = bool(CFG.rx("population").search(hay) and CFG.rx("technology").search(hay))
    return ("new_plausible" if plausible else "new"), ""


def openalex_hits() -> list[dict]:
    hits = []
    lang = CFG.languages[0] if CFG.languages else "en"
    for q in CFG.completeness_queries:
        flt = f"language:{lang}"
        if CFG.min_year:
            flt += f",publication_year:>{CFG.min_year - 1}"
        url = (f"https://api.openalex.org/works?per-page=50&mailto={CFG.contact_email}&search={urllib.parse.quote(q)}"
               f"&filter={flt}&select=doi,title,publication_year,authorships,abstract_inverted_index")
        try:
            data = get_json(url, CFG.user_agent)
        except Exception as exc:  # noqa: BLE001
            print("openalex error", repr(exc))
            continue
        for w in data.get("results", []):
            first = (w.get("authorships") or [{}])[0].get("author", {}).get("display_name", "")
            hits.append({"query": q, "doi": norm_doi(w.get("doi")), "title": w.get("title") or "",
                         "year": str(w.get("publication_year") or ""), "first_author": first,
                         "abstract": openalex_abstract(w.get("abstract_inverted_index"))})
        time.sleep(0.4)
        print(f"  {q!r}: {len(data.get('results', []))} hits")
    return hits


def main() -> None:
    CFG.guard_writable()
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "openalex":
        hits, source = openalex_hits(), "OpenAlex"
    elif args[0] == "hits" and len(args) > 1:
        hits, source = read_csv(Path(args[1])), Path(args[1]).name
        for h in hits:
            h.setdefault("query", "manual")
    else:
        sys.exit(__doc__)
    by_doi, by_title = build_index()
    seen, rows = set(), []
    for h in hits:
        key = norm_doi(h.get("doi") or "") or norm_title(h.get("title") or "")
        if key in seen:
            continue
        seen.add(key)
        status, rid = label(h, by_doi, by_title)
        rows.append({"query": h.get("query", ""), "status": status, "record_id": rid, "doi": h.get("doi", ""),
                     "title": h.get("title", ""), "year": h.get("year", ""), "first_author": h.get("first_author", "")})
    write_csv(CFG.file("completeness_hits.csv"), rows)
    c = Counter(r["status"] for r in rows)
    L = [f"# Completeness probe ({source}) — {CFG.name}", "", f"_Run {datetime.now():%Y-%m-%d %H:%M}; {len(rows)} unique hits._", "",
         "| Status | Hits |", "| --- | ---: |", *[f"| {k} | {v} |" for k, v in c.most_common()], "",
         "## New, plausible hits to judge against the eligibility criteria", ""]
    L += [f"- {r['first_author']} ({r['year']}): {r['title'][:110]} — {r['doi']}" for r in rows if r["status"] == "new_plausible"] or ["- none"]
    CFG.file("completeness_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"{len(rows)} unique hits: {dict(c)} -> completeness_report.md")


if __name__ == "__main__":
    main()
