"""Build the self-contained review page for citation-chasing candidates.

    python build_supplementary_review.py --project <dir> [--all]

Embeds ``citation_chase_shortlist.csv`` (or every row of
``citation_chase_decisions.csv`` with ``--all``) into
``supplementary_review.html`` in the project folder. The page works without
the server; decisions are kept in the browser and exported as
``citation_chase_human_decisions.csv`` for ``ingest_pending.py``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import read_csv  # noqa: E402
from project_config import CFG  # noqa: E402

TEMPLATE = (Path(__file__).resolve().parent / "ui" / "supplementary_review_template.html")


def main() -> None:
    CFG.guard_writable()
    src = CFG.file("citation_chase_decisions.csv" if "--all" in sys.argv else "citation_chase_shortlist.csv")
    rows = read_csv(src)
    if not rows:
        sys.exit(f"{src.name} missing or empty; run chase_screen.py")
    data = [{
        "id": r["record_id"], "bucket": r.get("strict", ""), "decision_link": r.get("assess_decision_link", ""),
        "recommendation": r.get("recommendation", ""), "confidence": r.get("confidence", ""),
        "draft": r.get("decision", ""), "n_links": int(r.get("n_links") or 0), "year": r.get("year", ""),
        "title": r.get("title", ""), "authors": r.get("authors", ""), "journal": r.get("journal", ""),
        "doi": r.get("doi", ""), "abstract": r.get("abstract", ""), "linked_records": r.get("linked_records", ""),
        "tier": r.get("assess_tier", ""), "domain": r.get("assess_primary_domain", ""),
    } for r in rows]
    page = TEMPLATE.read_text(encoding="utf-8")
    page = page.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    page = page.replace("__TOOLKIT_THEME__", (TEMPLATE.parent / "theme.css").read_text(encoding="utf-8"))
    page = page.replace("__PROJECT__", CFG.name)
    page = page.replace("__N_TOTAL__", str(len(data)))
    page = page.replace("__N_STRONG__", str(sum(1 for d in data if d["bucket"] == "strong")))
    page = page.replace("__N_REVIEW__", str(sum(1 for d in data if d["bucket"] == "review_by_hand")))
    out = CFG.file("supplementary_review.html")
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(data)} candidates)")


if __name__ == "__main__":
    main()
