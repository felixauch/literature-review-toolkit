"""PDF folder, manifest and decision bookkeeping shared by scripts and the UI.

Project layout (all relative to the project root)::

    pdfs/01_not_reviewed/   copied PDFs awaiting a full-text decision
    pdfs/02_final_included/ PDFs of final Includes
    fulltext_pdf_manifest.csv   record_id -> corpus_pdf (+ provenance)
    fulltext_recommendations.csv

PDF files are named ``<record_id>__<title-slug>.pdf``. Only copies inside the
project are ever moved or deleted; source files (e.g. Zotero) are untouched.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import read_csv_with_fields, slugify, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

MANIFEST_FIELDS = ["record_id", "title", "corpus_pdf", "source_pdf", "match_score", "runner_up_score", "status"]


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(CFG.root.resolve())).replace("\\", "/")


def pdf_name(record_id: str, title: str) -> str:
    return f"{record_id}__{slugify(title)}.pdf"


def find_local_pdf(record_id: str) -> Path | None:
    for folder in (CFG.pdf_included, CFG.pdf_pending):
        hits = sorted(folder.glob(f"{record_id}__*.pdf"))
        if hits:
            return hits[0]
    return None


# --------------------------------------------------------------------------
# manifest
# --------------------------------------------------------------------------
def load_manifest() -> tuple[list[str], list[dict]]:
    fields, rows = read_csv_with_fields(CFG.file("fulltext_pdf_manifest.csv"))
    return (fields or MANIFEST_FIELDS), rows


def save_manifest(rows: list[dict], fields: list[str] | None = None) -> None:
    write_csv(CFG.file("fulltext_pdf_manifest.csv"), rows, fields or MANIFEST_FIELDS)


def upsert_manifest(record_id: str, title: str, corpus_pdf: Path | None, source: str, status: str,
                    score: str = "", runner_up: str = "") -> None:
    fields, rows = load_manifest()
    for row in rows:
        if row.get("record_id") == record_id:
            row.update(corpus_pdf=rel(corpus_pdf) if corpus_pdf else "", source_pdf=source, status=status)
            if score:
                row["match_score"] = score
            if runner_up:
                row["runner_up_score"] = runner_up
            break
    else:
        rows.append({"record_id": record_id, "title": title, "corpus_pdf": rel(corpus_pdf) if corpus_pdf else "",
                     "source_pdf": source, "match_score": score, "runner_up_score": runner_up, "status": status})
    save_manifest(rows, fields)


def update_manifest_status(record_id: str, path: Path | None, status: str) -> None:
    fields, rows = load_manifest()
    if not rows:
        return
    for row in rows:
        if row.get("record_id") != record_id:
            continue
        row["status"] = status
        row["corpus_pdf"] = rel(path) if path else ""
    save_manifest(rows, fields)


# --------------------------------------------------------------------------
# moving PDFs with decisions
# --------------------------------------------------------------------------
def organise_local_pdf(record_id: str, final_decision: str, local_pdf: str) -> str:
    """Move a final Include into the included folder; delete the copy of a final Exclude."""
    candidates: list[Path] = []
    if local_pdf:
        cand = (CFG.root / local_pdf).resolve()
        if CFG.pdf_dir.resolve() in cand.parents:
            candidates.append(cand)
    candidates.extend(CFG.pdf_pending.glob(f"{record_id}__*.pdf"))
    candidates.extend(CFG.pdf_included.glob(f"{record_id}__*.pdf"))
    source = next((p for p in candidates if p.exists()), None)

    if final_decision == "Include" and source:
        CFG.pdf_included.mkdir(parents=True, exist_ok=True)
        target = CFG.pdf_included / source.name
        if source.resolve() != target.resolve():
            shutil.move(str(source), str(target))
        update_manifest_status(record_id, target, "final_included")
        return rel(target)
    if final_decision == "Exclude":
        if source:
            source.unlink()
        update_manifest_status(record_id, None, "final_excluded_deleted")
        return ""
    return local_pdf


def apply_fulltext_decisions(decisions: dict[str, dict]) -> int:
    """Persist final full-text decisions {record_id: {fulltext_final_decision, fulltext_final_notes}}."""
    path = CFG.file("fulltext_recommendations.csv")
    fields, rows = read_csv_with_fields(path)
    if not rows:
        raise FileNotFoundError("Run recommend_fulltext.py before saving full-text decisions.")
    for f in ("fulltext_final_decision", "fulltext_final_notes"):
        if f not in fields:
            fields.append(f)
    updated = 0
    for row in rows:
        d = decisions.get(row["record_id"])
        if not d:
            continue
        final = d.get("fulltext_final_decision") or ""
        row["fulltext_final_decision"] = final
        if "fulltext_final_notes" in d:
            row["fulltext_final_notes"] = d.get("fulltext_final_notes") or ""
        row["fulltext_local_pdf"] = organise_local_pdf(row["record_id"], final, row.get("fulltext_local_pdf") or "")
        updated += 1
    write_csv(path, rows, fields)
    return updated


# --------------------------------------------------------------------------
# rescan
# --------------------------------------------------------------------------
def rescan_pdfs() -> dict:
    """Relink PDFs found in the project folders to manifest and recommendations."""
    CFG.pdf_pending.mkdir(parents=True, exist_ok=True)
    CFG.pdf_included.mkdir(parents=True, exist_ok=True)
    found: dict[str, Path] = {}
    for folder in (CFG.pdf_included, CFG.pdf_pending):
        for pdf in sorted(folder.glob("*__*.pdf")):
            rid = pdf.name.split("__", 1)[0]
            found.setdefault(rid, pdf)

    mfields, manifest = load_manifest()
    by_id = {r["record_id"]: r for r in manifest if r.get("record_id")}
    rfields, recs = read_csv_with_fields(CFG.file("fulltext_recommendations.csv"))
    titles = {r["record_id"]: r for r in recs}
    linked = added = cleared = 0
    for rid, pdf in found.items():
        status = "final_included" if pdf.parent == CFG.pdf_included else "not_reviewed"
        row = by_id.get(rid)
        if row is None:
            row = {"record_id": rid, "title": "", "corpus_pdf": "", "source_pdf": "rescan",
                   "match_score": "", "runner_up_score": "", "status": status}
            manifest.append(row)
            by_id[rid] = row
            added += 1
        if row.get("corpus_pdf") != rel(pdf) or row.get("status") != status:
            row["corpus_pdf"] = rel(pdf)
            row["status"] = status
            linked += 1
    for row in manifest:
        cp = row.get("corpus_pdf") or ""
        if cp and not (CFG.root / cp).exists() and row["record_id"] not in found:
            row["corpus_pdf"] = ""
            if row.get("status") in ("not_reviewed", "final_included"):
                row["status"] = "pdf_missing"
            cleared += 1
    save_manifest(manifest, mfields)

    if recs:
        for r in recs:
            pdf = found.get(r["record_id"])
            r["fulltext_local_pdf"] = rel(pdf) if pdf else ""
            if pdf and r.get("fulltext_evidence_status", "").startswith("Metadata"):
                r["fulltext_evidence_status"] = "Local PDF available (not reviewed)"
        write_csv(CFG.file("fulltext_recommendations.csv"), recs, rfields)
    return {"found": len(found), "linked": linked, "added": added, "cleared": cleared}


def records_needing_pdf() -> list[dict]:
    """Records the reviewer kept at title--abstract that have no local PDF yet."""
    from lib import read_csv
    screen = read_csv(CFG.file("title_screening.csv"))
    recs = {r["record_id"]: r for r in read_csv(CFG.file("fulltext_recommendations.csv"))}
    out = []
    for r in screen:
        if (r.get("human_decision") or "") != "Include":
            continue
        rec = recs.get(r["record_id"], {})
        if (rec.get("fulltext_final_decision") or "") == "Exclude":
            continue
        if find_local_pdf(r["record_id"]):
            continue
        out.append({**r, "fulltext_oa_url": rec.get("fulltext_oa_url", ""),
                    "final": rec.get("fulltext_final_decision", "")})
    return out
