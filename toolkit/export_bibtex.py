"""Export records as BibTeX for a reference manager.

    python export_bibtex.py --project <dir> [--scope final|kept]

``final`` (default): records with fulltext_final_decision == Include ->
exports/final_corpus.bib. ``kept``: records with human_decision == Include
-> exports/kept_records.bib. Fields come from the original database exports
when a DOI or title matches, otherwise from the screening CSV.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import norm_doi, norm_title, parse_export, read_csv, short_author  # noqa: E402
from project_config import CFG  # noqa: E402


def bib_escape(s: str) -> str:
    return (s or "").replace("{", "").replace("}", "").replace("&", r"\&").replace("%", r"\%")


def main() -> None:
    scope = "final"
    if "--scope" in sys.argv:
        scope = sys.argv[sys.argv.index("--scope") + 1]
    screen = read_csv(CFG.file("title_screening.csv"))
    if scope == "final":
        recs = read_csv(CFG.file("fulltext_recommendations.csv"))
        ids = {r["record_id"] for r in recs if r.get("fulltext_final_decision") == "Include"}
        out = CFG.root / "exports" / "final_corpus.bib"
    else:
        ids = {r["record_id"] for r in screen if r.get("human_decision") == "Include"}
        out = CFG.root / "exports" / "kept_records.bib"
    rows = [r for r in screen if r["record_id"] in ids]

    originals: dict[str, dict] = {}
    for item in CFG.exports:
        if not item["path"].is_file():
            continue
        for rec in parse_export(item):
            key = rec["doi"] or norm_title(rec["title"])
            originals.setdefault(key, rec)

    entries = []
    for r in rows:
        orig = originals.get(norm_doi(r.get("doi") or "")) or originals.get(norm_title(r.get("title") or "")) or {}
        year = r.get("year") or orig.get("year") or "nd"
        key = f"{r['record_id']}_{short_author(r.get('authors') or orig.get('authors') or '')}_{year}"
        key = re.sub(r"[^A-Za-z0-9_]", "", key)
        fields = {
            "title": r.get("title") or orig.get("title"),
            "author": orig.get("authors") or r.get("authors"),
            "year": year,
            "journal": r.get("journal") or orig.get("journal"),
            "doi": r.get("doi") or orig.get("doi"),
            "abstract": r.get("abstract") or orig.get("abstract"),
            "note": f"record {r['record_id']}; sources {r.get('sources', '')}",
        }
        body = ",\n".join(f"  {k} = {{{bib_escape(v)}}}" for k, v in fields.items() if v)
        entries.append(f"@article{{{key},\n{body}\n}}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
