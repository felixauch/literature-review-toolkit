"""Core vs side test for secondary domain tags.

    python core_domains.py --project <dir>            # draft review sheet
    python core_domains.py --project <dir> --apply    # write reviewer's calls into the corpus CSV

A secondary domain is *core* when the paper's system supports or executes a
decision in that domain, *side* when the domain is only a sensing pathway,
outcome variable or passing mention. Each domain in project.json may carry a
``decision_phrases`` regex; the draft counts its hits in title and cached
full text: title hit or >=2 hits -> core, 0 -> side, exactly 1 -> borderline.

The sheet ``core_domain_review.csv`` has a ``final`` column for the reviewer
(core/side). ``--apply`` writes ``report_core_domains`` (primary + accepted
core secondaries) into screening_corpus_draft.csv.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import evidence_for, index_by, read_cached_pages, read_csv, read_csv_with_fields, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

FIELDS = ["record_id", "primary_domain", "secondary_domain", "hits_title", "hits_text", "draft", "final", "evidence", "title"]


def draft_sheet() -> None:
    corpus = read_csv(CFG.file("screening_corpus_draft.csv"))
    if not corpus:
        sys.exit("screening_corpus_draft.csv missing; run build_overview.py")
    previous = {(r["record_id"], r["secondary_domain"]): r for r in read_csv(CFG.file("core_domain_review.csv"))}
    phrases = {d["name"]: re.compile(d["decision_phrases"], re.I) for d in CFG.domains if d.get("decision_phrases")}
    rows = []
    for r in corpus:
        primary = r.get("report_primary_domain") or ""
        secondaries = [d.strip() for d in (r.get("report_secondary_domains") or "").split(";") if d.strip() and d.strip() != primary]
        if not secondaries:
            continue
        pages = read_cached_pages(CFG.cache_dir, r["record_id"])
        text = "\n".join(pages)
        for dom in secondaries:
            pat = phrases.get(dom)
            ht = len(pat.findall(r.get("title") or "")) if pat else 0
            hx = len(pat.findall(text)) if pat else 0
            draft = "core" if (ht or hx >= 2) else "side" if hx == 0 else "borderline"
            ev = evidence_for(pages, [pat], limit=2)[0] if (pat and pages) else ""
            prev = previous.get((r["record_id"], dom), {})
            rows.append({"record_id": r["record_id"], "primary_domain": primary, "secondary_domain": dom,
                         "hits_title": str(ht), "hits_text": str(hx), "draft": draft,
                         "final": prev.get("final", ""), "evidence": ev, "title": r.get("title") or ""})
    write_csv(CFG.file("core_domain_review.csv"), rows, FIELDS)
    c = Counter(r["draft"] for r in rows)
    lines = [f"# Core/side review of secondary domains — {CFG.name}", "",
             f"{len(rows)} secondary tags across {len({r['record_id'] for r in rows})} papers: {dict(c)}.", "",
             "Fill the `final` column (core/side) in core_domain_review.csv, then run `core_domains.py --apply`.", "",
             "## Borderline", ""]
    lines += [f"- {r['record_id']} · {r['secondary_domain']} · {r['title'][:80]}" for r in rows if r["draft"] == "borderline"]
    CFG.file("core_domain_review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(rows)} secondary tags: {dict(c)} -> core_domain_review.csv")


def apply() -> None:
    review = read_csv(CFG.file("core_domain_review.csv"))
    fields, corpus = read_csv_with_fields(CFG.file("screening_corpus_draft.csv"))
    if "report_core_domains" not in fields:
        fields.append("report_core_domains")
    accepted: dict[str, list[str]] = {}
    for r in review:
        call = (r.get("final") or r.get("draft") or "").strip().lower()
        if call == "core":
            accepted.setdefault(r["record_id"], []).append(r["secondary_domain"])
    for r in corpus:
        primary = r.get("report_primary_domain") or ""
        cores = [primary] + [d for d in accepted.get(r["record_id"], []) if d != primary]
        r["report_core_domains"] = "; ".join(d for d in cores if d)
    write_csv(CFG.file("screening_corpus_draft.csv"), corpus, fields)
    matrix = Counter()
    for r in corpus:
        for d in (r.get("report_core_domains") or "").split(";"):
            if d.strip():
                matrix[(r.get("report_tier"), d.strip())] += 1
    print(f"applied core domains; {sum(matrix.values())} tier x core-domain entries across {len(corpus)} papers")


def main() -> None:
    CFG.guard_writable()
    apply() if "--apply" in sys.argv else draft_sheet()


if __name__ == "__main__":
    main()
