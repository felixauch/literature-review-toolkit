"""Citation-network recall of the database search.  [network]

    python recall_check.py --project <dir>

For the database-arm final Includes with a DOI, fetches OpenAlex
``referenced_works`` and reports the share that cite, or are cited by,
another Include, i.e. the share that citation chasing would have recovered
had the database search missed them. Writes recall_check.json.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import get_json, index_by, norm_doi, read_csv  # noqa: E402
from project_config import CFG  # noqa: E402


def main() -> None:
    CFG.guard_writable()
    meta = index_by(read_csv(CFG.file("title_screening.csv")))
    recs = read_csv(CFG.file("fulltext_recommendations.csv"))
    targets = {r["record_id"]: norm_doi(meta.get(r["record_id"], {}).get("doi")) for r in recs
               if r.get("fulltext_final_decision") == "Include" and not r["record_id"].startswith(CFG.supplementary_prefix)}
    targets = {k: v for k, v in targets.items() if v}
    print(f"database-arm includes with DOI: {len(targets)}")
    dois = list(targets.values())
    oa_id: dict[str, str] = {}
    refs: dict[str, set[str]] = {}
    for i in range(0, len(dois), 40):
        batch = dois[i:i + 40]
        flt = "|".join("https://doi.org/" + d for d in batch)
        url = (f"https://api.openalex.org/works?per-page=50&mailto={CFG.contact_email}"
               "&select=id,doi,referenced_works&filter=doi:" + urllib.parse.quote(flt, safe="|:/."))
        for w in get_json(url, CFG.user_agent).get("results", []):
            wid = w["id"].rsplit("/", 1)[-1]
            oa_id[norm_doi(w.get("doi"))] = wid
            refs[wid] = {r.rsplit("/", 1)[-1] for r in w.get("referenced_works") or []}
        time.sleep(0.3)
        print(f"  fetched {min(i + 40, len(dois))}/{len(dois)}")
    seeds = set(refs)
    cited_by_seed: set[str] = set()
    for wid, rs in refs.items():
        cited_by_seed |= rs & (seeds - {wid})
    rediscovered, unresolved = [], []
    for rid, d in targets.items():
        wid = oa_id.get(d)
        if not wid:
            unresolved.append(rid)
            continue
        if (refs.get(wid, set()) & (seeds - {wid})) or wid in cited_by_seed:
            rediscovered.append(rid)
    resolved = len(targets) - len(unresolved)
    out = {"run": time.strftime("%Y-%m-%d %H:%M"), "targets": len(targets), "resolved_in_openalex": resolved,
           "rediscoverable": len(rediscovered), "share_of_resolved": round(len(rediscovered) / resolved, 3) if resolved else None,
           "unresolved": unresolved, "not_rediscoverable": sorted(set(targets) - set(rediscovered) - set(unresolved))}
    CFG.file("recall_check.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"rediscoverable {len(rediscovered)}/{resolved} resolved ({out['share_of_resolved']}); unresolved {len(unresolved)}")


if __name__ == "__main__":
    main()
