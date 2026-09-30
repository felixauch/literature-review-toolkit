"""Backward + forward citation chasing from the included records.  [network]

    python citation_chase.py --project <dir>

Backward: reference lists of the included DOIs (Crossref). Forward: works
citing them (OpenAlex). Candidates already in title_screening.csv are
dropped; the rest are filtered to the configured languages, ``min_year`` and
the ``chase_population`` + ``chase_technology`` patterns. Writes
``citation_chase_candidates.csv`` and ``citation_chase_summary.md``. Adds
nothing to the corpus; ``chase_screen.py`` drafts decisions next.
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import get_json, norm_doi, norm_title, openalex_abstract, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402


def main() -> None:
    CFG.guard_writable()
    screen = read_csv(CFG.file("title_screening.csv"))
    recs = read_csv(CFG.file("fulltext_recommendations.csv"))
    seen_doi = {norm_doi(r.get("doi")) for r in screen if r.get("doi")} - {""}
    seen_title = {norm_title(r.get("title")) for r in screen if r.get("title")}
    meta = {r["record_id"]: r for r in screen}
    includes = [r["record_id"] for r in recs if r.get("fulltext_final_decision") == "Include"]
    inc_doi = {rid: norm_doi(meta.get(rid, {}).get("doi")) for rid in includes}
    inc_doi = {k: v for k, v in inc_doi.items() if v}
    print(f"includes with DOI: {len(inc_doi)} / {len(includes)}")
    ua, mailto = CFG.user_agent, CFG.contact_email
    pop, tech = CFG.rx("chase_population"), CFG.rx("chase_technology")
    langs = {l.lower() for l in CFG.languages}

    candidates: dict[str, dict] = {}

    def consider(doi, title, year, lang, abstract, source, via):
        doi = norm_doi(doi)
        nt = norm_title(title)
        if not title or (doi and doi in seen_doi) or (nt and nt in seen_title):
            return
        try:
            yr = int(re.search(r"\d{4}", str(year or "")).group(0))
        except Exception:  # noqa: BLE001
            yr = 0
        if yr and CFG.min_year and yr < CFG.min_year:
            return
        if lang and langs and lang.lower() not in langs:
            return
        hay = f"{title} {abstract}"
        if not pop.search(hay) or not tech.search(hay):
            return
        key = doi or nt
        if key in candidates:
            candidates[key]["cited_by"].add(via)
            candidates[key]["source"].add(source)
            return
        candidates[key] = {"doi": doi, "title": re.sub(r"\s+", " ", title).strip()[:300], "year": yr or "",
                           "abstract": abstract or "", "source": {source}, "cited_by": {via}}

    # resolve OpenAlex IDs
    dois = list(inc_doi.values())
    id_by_doi: dict[str, str] = {}
    for i in range(0, len(dois), 40):
        batch = dois[i:i + 40]
        flt = "|".join("https://doi.org/" + d for d in batch)
        url = f"https://api.openalex.org/works?per-page=50&mailto={mailto}&filter=doi:" + urllib.parse.quote(flt, safe="|:/.")
        try:
            for w in get_json(url, ua).get("results", []):
                d = norm_doi(w.get("doi"))
                if d:
                    id_by_doi[d] = w["id"].rsplit("/", 1)[-1]
        except Exception as exc:  # noqa: BLE001
            print("openalex id batch error", repr(exc))
        time.sleep(0.3)
    print(f"resolved OpenAlex IDs: {len(id_by_doi)}")

    fwd = 0
    for n, (rid, d) in enumerate(inc_doi.items(), 1):
        oaid = id_by_doi.get(d)
        if not oaid:
            continue
        cursor = "*"
        while cursor:
            url = (f"https://api.openalex.org/works?per-page=100&mailto={mailto}"
                   "&select=id,doi,title,publication_year,language,abstract_inverted_index"
                   f"&filter=cites:{oaid}&cursor={cursor}")
            try:
                data = get_json(url, ua)
            except Exception as exc:  # noqa: BLE001
                print("forward error", rid, repr(exc))
                break
            for w in data.get("results", []):
                fwd += 1
                consider(w.get("doi"), w.get("title"), w.get("publication_year"), w.get("language"),
                         openalex_abstract(w.get("abstract_inverted_index")), "forward", rid)
            cursor = data.get("meta", {}).get("next_cursor")
            time.sleep(0.25)
        if n % 25 == 0:
            print(f"  forward {n}/{len(inc_doi)} · candidates {len(candidates)}")
    print(f"forward citing works seen: {fwd}")

    ref_dois: dict[str, str] = {}
    for n, (rid, d) in enumerate(inc_doi.items(), 1):
        try:
            data = get_json(f"https://api.crossref.org/works/{d}", ua)
        except Exception:  # noqa: BLE001
            continue
        for ref in data.get("message", {}).get("reference", []):
            rd = norm_doi(ref.get("DOI"))
            if rd and rd not in seen_doi and rd not in ref_dois:
                ref_dois[rd] = rid
        time.sleep(0.2)
        if n % 25 == 0:
            print(f"  backward {n}/{len(inc_doi)} · new reference DOIs {len(ref_dois)}")
    print(f"backward unique new reference DOIs: {len(ref_dois)}")

    refs = list(ref_dois)
    for i in range(0, len(refs), 40):
        batch = refs[i:i + 40]
        flt = "|".join("https://doi.org/" + d for d in batch)
        url = (f"https://api.openalex.org/works?per-page=50&mailto={mailto}"
               "&select=id,doi,title,publication_year,language,abstract_inverted_index"
               "&filter=doi:" + urllib.parse.quote(flt, safe="|:/."))
        try:
            for w in get_json(url, ua).get("results", []):
                d = norm_doi(w.get("doi"))
                consider(w.get("doi"), w.get("title"), w.get("publication_year"), w.get("language"),
                         openalex_abstract(w.get("abstract_inverted_index")), "backward", ref_dois.get(d, "?"))
        except Exception as exc:  # noqa: BLE001
            print("reference metadata error", repr(exc))
        time.sleep(0.3)

    rows = sorted(candidates.values(), key=lambda c: (-len(c["cited_by"]), str(c["year"])))
    out = [{"doi": c["doi"], "title": c["title"], "year": c["year"], "abstract": c["abstract"],
            "source": "+".join(sorted(c["source"])), "n_links": len(c["cited_by"]),
            "linked_records": "; ".join(sorted(c["cited_by"]))[:300]} for c in rows]
    write_csv(CFG.file("citation_chase_candidates.csv"), out,
              ["doi", "title", "year", "abstract", "source", "n_links", "linked_records"])
    summary = [
        f"# Citation chasing — {CFG.name}", "", f"_Run {datetime.now():%Y-%m-%d %H:%M}._", "",
        f"- Seeds (final Includes with DOI): {len(inc_doi)}",
        f"- Forward citing works seen: {fwd}", f"- Backward new reference DOIs: {len(ref_dois)}",
        f"- Candidates after dedupe and filters: {len(out)}", "",
        "Live services change; this file and the candidates CSV are the archived result.",
    ]
    CFG.file("citation_chase_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(f"{len(out)} candidates -> citation_chase_candidates.csv")


if __name__ == "__main__":
    main()
