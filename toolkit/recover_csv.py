"""Recover a truncated or corrupt title_screening.csv.

    python recover_csv.py --project <dir>

Keeps every row that still parses with the right number of columns, rebuilds
the missing records from corpus_deduped.csv with fresh drafts and empty human
decisions, and writes a byte-for-byte backup of the damaged file first.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import backup, read_csv, write_csv  # noqa: E402
from merge_screen import SCREEN_FIELDS, draft  # noqa: E402
from project_config import CFG  # noqa: E402


def main() -> None:
    CFG.guard_writable()
    path = CFG.file("title_screening.csv")
    master = read_csv(CFG.file("corpus_deduped.csv"))
    if not master:
        sys.exit("corpus_deduped.csv missing; cannot rebuild")
    good: list[dict] = []
    fields = SCREEN_FIELDS
    if path.exists():
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header:
                fields = header
                n = len(header)
                for row in reader:
                    if len(row) != n or not row[0]:
                        break
                    good.append(dict(zip(header, row)))
        dest = backup(path, "corrupt")
        print(f"backup: {dest}")
    have = {r["record_id"] for r in good}
    rebuilt = 0
    for rec in master:
        if rec["record_id"] in have:
            continue
        row = {k: "" for k in fields}
        row.update({k: rec.get(k, "") for k in ("record_id", "title", "authors", "year", "doi", "journal", "sources", "abstract")})
        row["has_abstract"] = "yes" if (rec.get("abstract") or "").strip() else "no"
        draft(row)
        good.append(row)
        rebuilt += 1
    good.sort(key=lambda r: r["record_id"])
    write_csv(path, good, fields)
    print(f"kept {len(good) - rebuilt} rows, rebuilt {rebuilt}; total {len(good)}")


if __name__ == "__main__":
    main()
