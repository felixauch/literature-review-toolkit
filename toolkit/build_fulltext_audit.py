"""Full-text audit data for the review interface.

    python build_fulltext_audit.py --project <dir> [--bib refs.bib --tex-dir chapters/]

For every final Include, reads the cached text (extracting from the PDF when
the cache is empty), counts hits for each tier, domain and decision-link
pattern, pulls supporting quotes, and flags mismatches between the charted
labels and the text:

    tier_mismatch       charted tier has no hits while another tier dominates
    domain_mismatch     charted primary domain has no hits while another has >=3
    coupling_violation  operational link on a tier not listed in operational_tiers
    weak_operational    operational link but no operational phrases in the text
    unreadable_or_empty no text available

Tier/domain patterns come from ``audit_pattern`` (falling back to
``pattern``) of each taxonomy entry; links use ft_operation, ft_decision and
ft_monitoring. With ``--bib`` and ``--tex-dir`` the script also maps
manuscript citations to records. Writes audit_data.json (served by the UI),
fulltext_audit.csv and fulltext_audit_flags.csv.
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_files import find_local_pdf  # noqa: E402
from lib import compact, extract_pages, norm_doi, read_cached_pages, read_csv, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

SECTION_HEAD = re.compile(
    r"^\s*(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z0-9 ,/\-&]{3,80})\s*$|"
    r"^\s*(Abstract|Introduction|Materials?\s+and\s+Methods|Results?(?:\s+and\s+Discussion)?|Discussion|Conclusions?|Keywords)\b",
    re.I | re.M)


def compiled(entries: list[dict]) -> dict[str, re.Pattern]:
    out = {}
    for e in entries:
        pat = e.get("audit_pattern") or e.get("pattern")
        if pat:
            out[e["name"]] = re.compile(pat, re.I)
    return out


def quote_for(pattern: re.Pattern, pages: list[str], label: str) -> dict | None:
    for page_no, text in enumerate(pages, start=1):
        m = pattern.search(text)
        if not m:
            continue
        start = max(text.rfind(".", 0, m.start()) + 1, m.start() - 220)
        end = text.find(".", m.end())
        end = min(end if end >= 0 else len(text), m.end() + 260)
        q = compact(text[start:end]).strip(" \"'“”")
        if q:
            return {"label": label, "quote": q[:360], "page": page_no, "match": m.group(0)}
    return None


def abstract_summary(pages: list[str], max_len: int = 420) -> str:
    if not pages:
        return ""
    m = re.search(r"Abstract\.?\s*(.+?)(?:Keywords|Introduction|1\s+Introduction)", pages[0], re.I | re.S)
    return compact(m.group(1))[:max_len] if m else compact(pages[0])[:max_len]


def citations(bib_path: Path | None, tex_dir: Path | None, rows: list[dict]) -> dict[str, list[dict]]:
    if not bib_path or not bib_path.is_file() or not tex_dir or not tex_dir.is_dir():
        return {}
    text = bib_path.read_text(encoding="utf-8", errors="replace")
    key_to_rid: dict[str, str] = {}
    doi_to_rid = {norm_doi(r["doi"]): r["record_id"] for r in rows if norm_doi(r.get("doi") or "")}
    for m in re.finditer(r"@\w+\{([^,]+),([\s\S]*?)\n\}", text):
        fm = re.search(r"\bdoi\s*=\s*\{([^}]*)\}", m.group(2), re.I)
        rid = doi_to_rid.get(norm_doi(fm.group(1))) if fm else None
        if rid:
            key_to_rid[m.group(1).strip()] = rid
    out: dict[str, list[dict]] = {}
    for tex in sorted(tex_dir.glob("*.tex")):
        body = tex.read_text(encoding="utf-8", errors="replace")
        for cm in re.finditer(r"\\\w*cite\w*(?:\[[^\]]*\])*\{([^}]+)\}", body):
            for key in cm.group(1).split(","):
                rid = key_to_rid.get(key.strip())
                if rid:
                    ctx = compact(body[max(0, cm.start() - 120): cm.end() + 60])
                    out.setdefault(rid, []).append({"file": tex.name, "context": ctx})
    return out


def main() -> None:
    CFG.guard_writable()
    rows = read_csv(CFG.file("screening_corpus_draft.csv"))
    if not rows:
        sys.exit("screening_corpus_draft.csv missing; run build_overview.py")
    args = sys.argv
    bib = Path(args[args.index("--bib") + 1]) if "--bib" in args else None
    tex_dir = Path(args[args.index("--tex-dir") + 1]) if "--tex-dir" in args else None
    tier_pat, dom_pat = compiled(CFG.tiers), compiled(CFG.domains)
    link_pat = {"operational": CFG.rx("ft_operation"), "explicit": CFG.rx("ft_decision"), "implicit": CFG.rx("ft_monitoring")}
    cites = citations(bib, tex_dir, rows)
    t0 = time.time()
    audits, flag_rows = [], []
    for i, row in enumerate(rows, start=1):
        rid = row["record_id"]
        pages = read_cached_pages(CFG.cache_dir, rid)
        source = "cache"
        if not pages:
            pdf = find_local_pdf(rid)
            if pdf:
                pages, _, _ = extract_pages(CFG.cache_dir, rid, pdf)
                pages = [p for p in pages if p]
                source = "pdf"
        joined = "\n".join(pages)
        tier, primary, link = row.get("report_tier") or "", row.get("report_primary_domain") or "", row.get("decision_link") or ""
        tier_hits = {k: len(p.findall(joined)) for k, p in tier_pat.items()} if pages else {}
        dom_hits = {k: len(p.findall(joined)) for k, p in dom_pat.items()} if pages else {}
        s_tier = max(tier_hits, key=tier_hits.get) if tier_hits and max(tier_hits.values()) else ""
        s_dom = max(dom_hits, key=dom_hits.get) if dom_hits and max(dom_hits.values()) else ""
        op, ex = (len(link_pat["operational"].findall(joined)), len(link_pat["explicit"].findall(joined))) if pages else (0, 0)
        s_link = ("operational" if tier in CFG.operational_tiers and op >= 2 else "explicit" if ex >= 2 else "implicit") if pages else ""
        flags = []
        if pages:
            if tier and tier_hits.get(tier, 0) == 0 and s_tier and tier_hits[s_tier] >= 3:
                flags.append(f"tier_mismatch: charted {tier}, text leans {s_tier}")
            if primary and dom_hits.get(primary, 0) == 0 and s_dom and dom_hits[s_dom] >= 3:
                flags.append(f"domain_mismatch: charted {primary}, text leans {s_dom}")
            if link == "operational" and tier not in CFG.operational_tiers:
                flags.append(f"coupling_violation: operational link on tier {tier}")
            if link == "operational" and op == 0:
                flags.append("weak_operational: no operational phrases found")
        else:
            flags.append("unreadable_or_empty")
        quotes, seen = [], set()
        for pat, label in ((tier_pat.get(tier), f"Tier · {tier}"), (dom_pat.get(primary), f"domain · {primary}"),
                           (link_pat.get(link), f"decision link · {link}"),
                           (dom_pat.get(s_dom) if s_dom != primary else None, f"also mentions · {s_dom}"),
                           (tier_pat.get(s_tier) if s_tier != tier else None, f"also signals · {s_tier}")):
            q = quote_for(pat, pages, label) if (pat and pages) else None
            if q and q["quote"][:120] not in seen:
                seen.add(q["quote"][:120])
                quotes.append(q)
        sections = [compact(m.group(0)) for m in SECTION_HEAD.finditer("\n".join(pages[:2]))][:8] if pages else []
        rec = {
            "record_id": rid, "title": row.get("title") or "", "authors": row.get("authors") or "",
            "year": row.get("year") or "", "doi": row.get("doi") or "", "tier": tier, "primary_domain": primary,
            "core_domains": [c.strip() for c in (row.get("report_core_domains") or "").split(";") if c.strip()],
            "secondary_domains": [c.strip() for c in (row.get("report_secondary_domains") or "").split(";") if c.strip()],
            "decision_link": link, "relevance_score": row.get("relevance_score") or "",
            "relevance_band": row.get("relevance_band") or "", "pages_extracted": len(pages),
            "chars": len(joined), "text_source": source, "summary": abstract_summary(pages), "sections": sections,
            "quotes": quotes[:6], "suggested_tier": s_tier, "suggested_domain": s_dom, "suggested_link": s_link,
            "domain_hits": {k: v for k, v in dom_hits.items() if v}, "tier_hits": {k: v for k, v in tier_hits.items() if v},
            "flags": flags, "flag_count": len(flags), "manuscript_citations": cites.get(rid, []),
            "cited_in_manuscript": bool(cites.get(rid)), "pdf": row.get("fulltext_local_pdf") or "",
        }
        audits.append(rec)
        if flags:
            flag_rows.append({"record_id": rid, "title": rec["title"], "tier": tier, "primary_domain": primary,
                              "decision_link": link, "suggested_tier": s_tier, "suggested_domain": s_dom,
                              "suggested_link": s_link, "flags": "; ".join(flags),
                              "cited_in_manuscript": "yes" if rec["cited_in_manuscript"] else "no"})
        if i % 25 == 0 or i == len(rows):
            print(f"[{i}/{len(rows)}] audited · flags so far {len(flag_rows)}", flush=True)
    flag_counter = Counter(f.split(":")[0] for r in audits for f in r["flags"])
    payload = {"meta": {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "corpus_size": len(audits),
                        "with_flags": len(flag_rows), "cited_in_manuscript": sum(1 for r in audits if r["cited_in_manuscript"]),
                        "elapsed_sec": round(time.time() - t0, 1), "flag_counts": dict(flag_counter),
                        "project": CFG.name, "refresh_pdfs": False,
                        "note": f"Project {CFG.name}: {len(audits)} included papers checked against tier, domain and link patterns."},
               "records": audits}
    CFG.file("audit_data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    write_csv(CFG.file("fulltext_audit.csv"), [{**{k: v for k, v in r.items() if not isinstance(v, (list, dict))},
                                                "flags": "; ".join(r["flags"])} for r in audits])
    write_csv(CFG.file("fulltext_audit_flags.csv"), flag_rows)
    print(f"{len(audits)} audited, {len(flag_rows)} flagged: {dict(flag_counter)} -> audit_data.json")


if __name__ == "__main__":
    main()
