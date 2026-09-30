"""Export the included corpus as a LaTeX appendix listing.

    python export_latex_listing.py --project <dir> [--out path.tex]

Groups ``screening_corpus_draft.csv`` by tier, then primary domain, and writes
one longtable per group (ID, year, decision link, authors, title with extra
core domains in parentheses). Default output: exports/screening_corpus_draft.tex.
Requires ``longtable`` and ``array`` in the including document.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import read_csv, short_author, tex_escape  # noqa: E402
from project_config import CFG  # noqa: E402


def short_title(title: str, limit: int = 88) -> str:
    t = re.sub(r"\s+", " ", (title or "").strip())
    t = re.sub(r"</?scp>", "", t, flags=re.I)
    if len(t) <= limit:
        return t
    return t[: limit - 1].rsplit(" ", 1)[0] + "..."


def main() -> None:
    rows = read_csv(CFG.file("screening_corpus_draft.csv"))
    if not rows:
        sys.exit("screening_corpus_draft.csv missing; run build_overview.py")
    out = CFG.root / "exports" / "screening_corpus_draft.tex"
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    labels = CFG.link_labels
    domain_order = CFG.domain_names + [CFG.default_domain]
    by: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by[r.get("report_primary_domain") or CFG.default_domain][r.get("report_tier") or ""].append(r)
    for d in by:
        for t in by[d]:
            by[d][t].sort(key=lambda r: (r.get("year") or "", r["record_id"]))
    extra_domains = [d for d in by if d not in domain_order]

    L = [r"\chapter{Screening corpus draft}", r"\label{app:corpus}", "",
         rf"Draft only: classifications are not confirmed in the combined review. Each of the {len(rows)} screened sources is listed once, by tier and primary domain. Additional core domains follow "
         r"the title in parentheses. Decision link is recorded as " + ", ".join(sorted(set(labels.values()))) + ".", ""]
    for i, tier in enumerate(CFG.tier_names):
        n_tier = sum(len(by[d].get(tier, [])) for d in by)
        if not n_tier:
            continue
        if i:
            L.append(r"\clearpage")
        L += [rf"\section{{{tex_escape(tier)}}}", rf"\label{{app:corpus:{re.sub(r'[^a-z]+', '', tier.lower())}}}", "",
              f"{n_tier} sources in this tier.", ""]
        for domain in domain_order + extra_domains:
            papers = by.get(domain, {}).get(tier, [])
            if not papers:
                continue
            L += [rf"\subsection*{{{tex_escape(domain)} ($n={len(papers)}$)}}", r"\begingroup", r"\footnotesize",
                  r"\setlength{\LTleft}{0pt}", r"\setlength{\LTright}{0pt}",
                  r"\begin{longtable}{@{}p{0.08\linewidth}p{0.07\linewidth}p{0.15\linewidth}p{0.17\linewidth}>{\raggedright\arraybackslash}p{0.45\linewidth}@{}}",
                  r"\hline", r"\textbf{ID} & \textbf{Year} & \textbf{Link} & \textbf{Authors} & \textbf{Title} \\", r"\hline",
                  r"\endfirsthead", rf"\multicolumn{{5}}{{@{{}}l}}{{\emph{{Continued: {tex_escape(tier)} / {tex_escape(domain)}}}}} \\",
                  r"\hline", r"\textbf{ID} & \textbf{Year} & \textbf{Link} & \textbf{Authors} & \textbf{Title} \\", r"\hline",
                  r"\endhead", r"\hline", r"\endfoot"]
            for r in papers:
                link = labels.get((r.get("decision_link") or "").strip(), r.get("decision_link") or "")
                cores = [c.strip() for c in (r.get("report_core_domains") or "").split(";") if c.strip() and c.strip() != domain]
                extra = f" (+{'; '.join(cores)})" if cores else ""
                L.append(f"{tex_escape(r['record_id'])} & {tex_escape(r.get('year') or '')} & {tex_escape(link)} & "
                         f"{tex_escape(short_author(r.get('authors') or ''))}{' et al.' if ' and ' in (r.get('authors') or '') or ';' in (r.get('authors') or '') else ''} & "
                         f"{tex_escape(short_title(r.get('title') or ''))}{tex_escape(extra)} \\\\")
            L += [r"\end{longtable}", r"\endgroup", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(rows)} sources)")


if __name__ == "__main__":
    main()
