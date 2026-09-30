"""Audit the deduplication: possible false merges and missed duplicates.

    python audit_dedup.py --project <dir>

Re-reads the raw exports and compares them with corpus_deduped.csv:

* false merge suspects  -- one DOI, clearly different titles;
* missed duplicates     -- same normalised title but different DOIs or years
                           that ended up as separate records;
* cosmetic DOI conflicts -- DOIs that differ only in case or escaping.

Writes dedup_audit_report.md. Nothing is changed.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import norm_doi, norm_title, parse_export, read_csv  # noqa: E402
from project_config import CFG  # noqa: E402


def main() -> None:
    raw: list[dict] = []
    for item in CFG.exports:
        if item["path"].is_file():
            raw.extend(parse_export(item))
    master = read_csv(CFG.file("corpus_deduped.csv"))
    if not raw or not master:
        sys.exit("need exports and corpus_deduped.csv")

    by_doi: dict[str, list[dict]] = defaultdict(list)
    for r in raw:
        if r["doi"]:
            by_doi[r["doi"]].append(r)
    false_merges = []
    for doi, recs in by_doi.items():
        titles = {norm_title(r["title"]) for r in recs}
        if len(titles) > 1:
            a, b = sorted(titles)[:2]
            if SequenceMatcher(None, a, b).ratio() < 0.6:
                false_merges.append((doi, [r["title"] for r in recs][:3]))

    by_title: dict[str, list[dict]] = defaultdict(list)
    for r in master:
        nt = norm_title(r["title"])
        if len(nt) >= 25:
            by_title[nt].append(r)
    missed = [(nt, recs) for nt, recs in by_title.items() if len(recs) > 1]

    raw_dois: dict[str, set[str]] = defaultdict(set)
    for r in raw:
        if r["doi"]:
            raw_dois[r["doi"].lower().replace("\\", "")].add(r["doi"])
    cosmetic = [(k, sorted(v)) for k, v in raw_dois.items() if len(v) > 1]

    lines = [
        f"# Deduplication audit — {CFG.name}", "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M}. Raw records {len(raw)}, unique {len(master)}._", "",
        f"## Possible false merges (same DOI, different titles): {len(false_merges)}", "",
    ]
    for doi, titles in false_merges:
        lines.append(f"- `{doi}`: " + " | ".join(t[:90] for t in titles))
    lines += ["", f"## Possible missed duplicates (same title, separate records): {len(missed)}", ""]
    for nt, recs in missed:
        lines.append("- " + "; ".join(f"{r['record_id']} ({r['year']}, {r['doi'] or 'no DOI'})" for r in recs)
                     + f" — {recs[0]['title'][:90]}")
    lines += ["", f"## Cosmetic DOI variants in the raw exports: {len(cosmetic)}", ""]
    for _, variants in cosmetic[:50]:
        lines.append("- " + " / ".join(variants))
    CFG.file("dedup_audit_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"false-merge suspects {len(false_merges)}, missed-duplicate suspects {len(missed)}, "
          f"cosmetic DOI variants {len(cosmetic)} -> dedup_audit_report.md")


if __name__ == "__main__":
    main()
