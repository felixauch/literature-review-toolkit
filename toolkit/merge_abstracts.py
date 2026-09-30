"""Fill missing abstracts from additional exports.

    python merge_abstracts.py --project <dir> [extra.bib ...]

Uses ``abstract_supplements`` from project.json (plus any files given on the
command line). Records are matched by DOI, then by normalised title. Only
empty abstracts are filled; nothing else changes. Run
``merge_screen.py --rescreen`` afterwards so the drafts see the new text.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import norm_doi, norm_title, parse_export, read_csv_with_fields, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402


def main() -> None:
    CFG.guard_writable()
    items = list(CFG.abstract_supplements)
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.suffix.lower() == ".bib":
            items.append({"file": arg, "path": p, "format": "bibtex", "source": "supplement"})
        elif p.suffix.lower() == ".csv":
            items.append({"file": arg, "path": p, "format": "csv", "source": "supplement"})
    if not items:
        sys.exit("no abstract supplements configured or given")

    by_doi: dict[str, str] = {}
    by_title: dict[str, str] = {}
    for item in items:
        if not item["path"].is_file():
            print(f"skip missing {item['file']}")
            continue
        for rec in parse_export(item):
            ab = (rec.get("abstract") or "").strip()
            if not ab:
                continue
            if rec["doi"]:
                by_doi.setdefault(norm_doi(rec["doi"]), ab)
            nt = norm_title(rec["title"])
            if nt:
                by_title.setdefault(nt, ab)
    print(f"abstracts available: {len(by_doi)} by DOI, {len(by_title)} by title")

    for name in ("title_screening.csv", "corpus_deduped.csv"):
        path = CFG.file(name)
        fields, rows = read_csv_with_fields(path)
        if not rows:
            continue
        filled = 0
        for r in rows:
            if (r.get("abstract") or "").strip():
                continue
            ab = by_doi.get(norm_doi(r.get("doi") or "")) or by_title.get(norm_title(r.get("title") or ""))
            if ab:
                r["abstract"] = ab
                if "has_abstract" in fields:
                    r["has_abstract"] = "yes"
                filled += 1
        write_csv(path, rows, fields)
        print(f"{name}: filled {filled} abstracts")
    print("next: python merge_screen.py --rescreen")


if __name__ == "__main__":
    main()
