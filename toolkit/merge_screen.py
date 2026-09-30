"""Merge database exports, remove duplicates, draft title--abstract decisions.

    python merge_screen.py --project <dir>            # first run
    python merge_screen.py --project <dir> --rescreen # re-run rules on undecided rows

Reads the exports listed in project.json, merges duplicates (DOI, then
normalised title + year, then title-prefix within a year, then any manual DOI
pairs from the config), assigns record IDs, and applies the ordered
``screening_rules`` from project.json. Writes:

    corpus_deduped.csv      one row per unique record
    title_screening.csv     draft suggestion + empty human decision per record
    dedup_log.csv           merged groups
    merge_summary.md        counts
    title_screening_suggested_{include,exclude}.csv, title_screening_needs_abstract.csv

The first run refuses to overwrite a screening file that already holds human
decisions unless ``--force`` is given. ``--rescreen`` keeps every human
decision and only refreshes the draft columns of undecided rows.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import index_by, norm_doi, norm_title, parse_export, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

SCREEN_FIELDS = [
    "record_id", "suggested_decision", "exclusion_code", "screen_reason",
    "human_decision", "human_notes", "title", "authors", "year", "doi", "journal",
    "sources", "has_abstract", "abstract", "evidence_quote",
]
MASTER_FIELDS = ["record_id", "title", "authors", "year", "doi", "journal", "sources", "source_files", "abstract"]


def merge_records(records: list[dict], manual_pairs: list[list[str]]) -> tuple[list[dict], list[dict]]:
    merged = [{**r, "sources": {r["source_db"]}, "source_files": {r["source_file"]}} for r in records]
    by_doi: dict[str, list[int]] = defaultdict(list)
    by_title_year: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(merged):
        if rec["doi"]:
            by_doi[rec["doi"]].append(i)
        nt = norm_title(rec["title"])
        if nt:
            by_title_year[f"{nt}|{(rec['year'] or '').strip()}"].append(i)

    parent = list(range(len(merged)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int, how: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
            pairs.append({"match": how, "a": a, "b": b})

    pairs: list[dict] = []
    for idxs in by_doi.values():
        for j in idxs[1:]:
            union(idxs[0], j, "doi")
    for idxs in by_title_year.values():
        for j in idxs[1:]:
            union(idxs[0], j, "title_year")

    by_year: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(merged):
        y = (rec.get("year") or "").strip()
        if y and norm_title(rec["title"]):
            by_year[y].append(i)
    for idxs in by_year.values():
        nts = [(i, norm_title(merged[i]["title"])) for i in idxs]
        nts = [(i, nt) for i, nt in nts if len(nt) >= 40]
        for a in range(len(nts)):
            for b in range(a + 1, len(nts)):
                i, ti = nts[a]
                j, tj = nts[b]
                if find(i) == find(j) or not (ti.startswith(tj) or tj.startswith(ti)):
                    continue
                di, dj = merged[i]["doi"], merged[j]["doi"]
                if di and dj and di != dj:
                    continue
                union(i, j, "title_prefix")

    doi_index: dict[str, list[int]] = defaultdict(list)
    for i, rec in enumerate(merged):
        if rec["doi"]:
            doi_index[rec["doi"]].append(i)
    for pair in manual_pairs or []:
        idxs = [i for d in pair for i in doi_index.get(norm_doi(d), [])]
        for j in idxs[1:]:
            union(idxs[0], j, "manual")

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(len(merged)):
        groups[find(i)].append(i)

    deduped: list[dict] = []
    log: list[dict] = []
    prefix = CFG.record_prefix
    for members in groups.values():
        members = sorted(set(members))
        base = dict(merged[members[0]])
        sources, files = set(), set()
        best_abstract = base.get("abstract") or ""
        doi = base.get("doi") or ""
        for idx in members:
            sources |= merged[idx]["sources"]
            files |= merged[idx]["source_files"]
            if len(merged[idx].get("abstract") or "") > len(best_abstract):
                best_abstract = merged[idx]["abstract"]
            doi = doi or merged[idx].get("doi") or ""
        base.update(sources=sorted(sources), source_files=sorted(files), abstract=best_abstract, doi=doi)
        base["record_id"] = f"{prefix}{len(deduped) + 1:04d}"
        if len(members) > 1:
            log.append({
                "record_id": base["record_id"], "merged_count": len(members),
                "sources": ";".join(base["sources"]), "doi": base["doi"],
                "title": base["title"], "year": base["year"],
            })
        deduped.append(base)
    return deduped, log


def draft(rec: dict) -> None:
    decision, code, reason = CFG.screen(rec.get("title") or "", rec.get("abstract") or "", rec.get("year") or "")
    rec["suggested_decision"] = decision
    rec["exclusion_code"] = code
    rec["screen_reason"] = reason


def write_sheets(rows: list[dict]) -> None:
    for name, decision in (
        ("title_screening_suggested_include.csv", "Include"),
        ("title_screening_suggested_exclude.csv", "Exclude"),
        ("title_screening_needs_abstract.csv", "Maybe"),
    ):
        write_csv(CFG.file(name), [r for r in rows if r["suggested_decision"] == decision], SCREEN_FIELDS)


def first_run(force: bool) -> None:
    screening_path = CFG.file("title_screening.csv")
    if screening_path.exists() and not force:
        existing = read_csv(screening_path)
        decided = sum(1 for r in existing if (r.get("human_decision") or "").strip())
        if decided:
            sys.exit(
                f"{screening_path.name} already holds {decided} human decisions. "
                "Use --rescreen to refresh drafts, or --force to start over."
            )

    records: list[dict] = []
    raw_counts: dict[str, int] = defaultdict(int)
    for item in CFG.exports:
        if not item["path"].is_file():
            sys.exit(f"export not found: {item['path']}")
        parsed = parse_export(item)
        records.extend(parsed)
        raw_counts[item.get("source", "db")] += len(parsed)
        print(f"  {item['file']}: {len(parsed)} records")
    if not records:
        sys.exit("no records parsed from exports")

    deduped, log = merge_records(records, CFG.data.get("manual_doi_merges") or [])
    for rec in deduped:
        draft(rec)
        rec["human_decision"] = ""
        rec["human_notes"] = ""
        rec["evidence_quote"] = ""
        rec["sources_str"] = ";".join(rec["sources"])

    rows = []
    for rec in deduped:
        rows.append({**rec, "sources": ";".join(rec["sources"]),
                     "has_abstract": "yes" if (rec.get("abstract") or "").strip() else "no"})
    write_csv(screening_path, rows, SCREEN_FIELDS)
    write_csv(CFG.file("corpus_deduped.csv"),
              [{**rec, "sources": ";".join(rec["sources"]), "source_files": ";".join(rec["source_files"])} for rec in deduped],
              MASTER_FIELDS)
    write_csv(CFG.file("dedup_log.csv"), log, ["record_id", "merged_count", "sources", "doi", "title", "year"])
    write_sheets(rows)

    counts = defaultdict(int)
    for r in rows:
        counts[r["suggested_decision"]] += 1
    lines = [
        f"# Merge summary — {CFG.name}", "",
        f"_Generated {datetime.now():%Y-%m-%d %H:%M}._", "",
        "## Records identified", "",
        *[f"- {src}: {n}" for src, n in sorted(raw_counts.items())],
        f"- **Total identified: {len(records)}**",
        f"- **After deduplication: {len(deduped)}** ({len(records) - len(deduped)} merged)", "",
        "## Draft suggestions", "",
        *[f"- {d}: {counts.get(d, 0)}" for d in ("Include", "Maybe", "Exclude")], "",
        "## Files", "",
        "- `corpus_deduped.csv` — master deduplicated corpus",
        "- `title_screening.csv` — fill `human_decision` (Include/Maybe/Exclude) in the interface",
        "- `dedup_log.csv` — merged duplicate groups",
    ]
    CFG.file("merge_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(records)} -> {len(deduped)} unique records; drafts: {dict(counts)}")


def rescreen() -> None:
    path = CFG.file("title_screening.csv")
    rows = read_csv(path)
    if not rows:
        sys.exit("title_screening.csv not found; run without --rescreen first")
    changed = 0
    for r in rows:
        if (r.get("human_decision") or "").strip():
            continue
        before = (r["suggested_decision"], r["exclusion_code"], r["screen_reason"])
        draft(r)
        r["has_abstract"] = "yes" if (r.get("abstract") or "").strip() else "no"
        if before != (r["suggested_decision"], r["exclusion_code"], r["screen_reason"]):
            changed += 1
    fields = list(rows[0].keys())
    for f in SCREEN_FIELDS:
        if f not in fields:
            fields.append(f)
    write_csv(path, rows, fields)
    write_sheets(rows)
    print(f"re-drafted {changed} undecided rows")


def main() -> None:
    CFG.guard_writable()
    CFG.ensure_dirs()
    if "--rescreen" in sys.argv:
        rescreen()
    else:
        first_run(force="--force" in sys.argv)


if __name__ == "__main__":
    main()
