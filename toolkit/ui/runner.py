"""Run stage scripts from the interface and describe the project state."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

UI = Path(__file__).resolve().parent
TOOLKIT = UI.parent
sys.path.insert(0, str(TOOLKIT))
from project_config import REPO_DIR, TEMPLATE_DIR, ConfigError, Project  # noqa: E402

# Stage catalogue shown on the setup page. ``network`` stages call external services.
STAGES = [
    {"group": "1 Title-abstract", "id": "merge_screen", "script": "merge_screen.py", "label": "Merge exports, dedupe, draft screening",
     "args": [], "network": False, "creates": ["title_screening.csv", "corpus_deduped.csv"]},
    {"group": "1 Title-abstract", "id": "merge_abstracts", "script": "merge_abstracts.py", "label": "Fill abstracts from supplements",
     "args": [], "network": False, "creates": []},
    {"group": "1 Title-abstract", "id": "rescreen", "script": "merge_screen.py", "label": "Re-draft undecided rows",
     "args": ["--rescreen"], "network": False, "creates": []},
    {"group": "1 Title-abstract", "id": "backcheck", "script": "backcheck_classifier.py", "label": "SVM second opinion for Maybes",
     "args": [], "network": False, "creates": []},
    {"group": "1 Title-abstract", "id": "audit_dedup", "script": "audit_dedup.py", "label": "Audit deduplication",
     "args": [], "network": False, "creates": ["dedup_audit_report.md"]},
    {"group": "2 Full text", "id": "pdf_import", "script": "import_pdf_manifest.py", "label": "Import PDFs from pdf_import.csv", "args": ["pdf_import.csv"], "network": False, "creates": []},
    {"group": "2 Full text", "id": "pdf_rescan", "script": "pdfs.py", "label": "Relink PDFs already in project folders", "args": ["rescan"], "network": False, "creates": []},
    {"group": "2 Full text", "id": "pdf_status", "script": "pdfs.py", "label": "PDF status", "args": ["status"], "network": False, "creates": []},
    {"group": "2 Full text", "id": "pdf_zotero", "script": "pdfs.py", "label": "Copy PDFs from Zotero", "args": ["zotero"], "network": False, "creates": []},
    {"group": "2 Full text", "id": "pdf_oa", "script": "pdfs.py", "label": "Download open-access PDFs", "args": ["oa"], "network": True, "creates": []},
    {"group": "2 Full text", "id": "pdf_open", "script": "pdfs.py", "label": "Open next 10 DOI pages in browser", "args": ["browser", "--open", "10"], "network": True, "creates": []},
    {"group": "2 Full text", "id": "pdf_harvest", "script": "pdfs.py", "label": "File PDFs from Downloads folder", "args": ["browser", "--harvest"], "network": False, "creates": []},
    {"group": "2 Full text", "id": "pdf_verify", "script": "pdfs.py", "label": "Verify PDFs match records", "args": ["verify"], "network": False, "creates": []},
    {"group": "2 Full text", "id": "analyse", "script": "analyse_fulltexts.py", "label": "Extract text, draft Retain/Exclude",
     "args": [], "network": False, "creates": ["fulltext_analysis.csv"]},
    {"group": "2 Full text", "id": "recommend", "script": "recommend_fulltext.py", "label": "Preliminary full-text recommendation",
     "args": [], "network": False, "creates": ["fulltext_recommendations.csv"]},
    {"group": "3 Citation chasing", "id": "chase", "script": "citation_chase.py", "label": "Crossref + OpenAlex chasing",
     "args": [], "network": True, "creates": ["citation_chase_candidates.csv"]},
    {"group": "3 Citation chasing", "id": "chase_screen", "script": "chase_screen.py", "label": "Draft candidate decisions (+fetch metadata)",
     "args": ["--fetch"], "network": True, "creates": ["citation_chase_decisions.csv"]},
    {"group": "3 Citation chasing", "id": "supp_review", "script": "build_supplementary_review.py", "label": "Build supplementary review page",
     "args": [], "network": False, "creates": ["supplementary_review.html"]},
    {"group": "3 Citation chasing", "id": "ingest", "script": "ingest_pending.py", "label": "Ingest survivors as pending full text",
     "args": [], "network": False, "creates": []},
    {"group": "Optional single-label reports", "id": "assess", "script": "assess_corpus.py", "label": "Draft charting per Include",
     "args": [], "network": False, "creates": ["corpus_assessment.csv"]},
    {"group": "Optional single-label reports", "id": "overview", "script": "build_overview.py", "label": "Screening overview (unconfirmed labels)",
     "args": [], "network": False, "creates": ["screening_corpus_draft.csv", "screening_overview_draft.md"]},
    {"group": "Optional single-label reports", "id": "core_domains", "script": "core_domains.py", "label": "Draft core/side secondary domains",
     "args": [], "network": False, "creates": ["core_domain_review.csv"]},
    {"group": "Optional single-label reports", "id": "core_domains_apply", "script": "core_domains.py", "label": "Apply core/side calls",
     "args": ["--apply"], "network": False, "creates": []},
    {"group": "Optional single-label reports", "id": "adjudicate", "script": "apply_adjudications.py", "label": "Apply adjudications.csv",
     "args": [], "network": False, "creates": []},
    {"group": "Optional single-label reports", "id": "audit", "script": "build_fulltext_audit.py", "label": "Build full-text audit page data",
     "args": [], "network": False, "creates": ["audit_data.json"]},
    {"group": "Optional single-label reports", "id": "synthesis", "script": "build_synthesis.py", "label": "Synthesis draft (Markdown)",
     "args": [], "network": False, "creates": ["synthesis_draft.md"]},
    {"group": "Optional single-label exports", "id": "bibtex", "script": "export_bibtex.py", "label": "BibTeX of final corpus", "args": [], "network": False, "creates": ["exports/final_corpus.bib"]},
    {"group": "Optional single-label exports", "id": "latex", "script": "export_latex_listing.py", "label": "Draft single-label LaTeX listing", "args": [], "network": False, "creates": ["exports/screening_corpus_draft.tex"]},
    {"group": "Optional single-label exports", "id": "folders", "script": "organise_folders.py", "label": "Tier x domain browsing folders", "args": [], "network": False, "creates": []},
    {"group": "6 Completeness", "id": "recall", "script": "recall_check.py", "label": "Citation-network recall", "args": [], "network": True, "creates": ["recall_check.json"]},
    {"group": "6 Completeness", "id": "completeness", "script": "completeness_check.py", "label": "OpenAlex completeness probe", "args": ["openalex"], "network": True, "creates": ["completeness_report.md"]},
]
_BY_ID = {s["id"]: s for s in STAGES}

_lock = threading.Lock()
_state: dict = {"running": False, "stage": "", "started": 0.0, "ended": 0.0, "exit_code": None, "log": deque(maxlen=400)}
_proc: subprocess.Popen | None = None


def status() -> dict:
    with _lock:
        return {"running": _state["running"], "stage": _state["stage"], "started": _state["started"],
                "ended": _state["ended"], "exit_code": _state["exit_code"], "log": list(_state["log"])}


def start(stage_id: str, extra_args: list[str], proj: Project) -> dict:
    global _proc
    stage = _BY_ID.get(stage_id)
    if not stage:
        raise ConfigError(f"unknown stage {stage_id!r}")
    with _lock:
        if _state["running"]:
            raise ConfigError(f"stage {_state['stage']} is still running")
        _state.update(running=True, stage=stage_id, started=time.time(), ended=0.0, exit_code=None)
        _state["log"].clear()
    cmd = [sys.executable, "-u", str(TOOLKIT / stage["script"]), "--project", str(proj.root), *stage["args"], *[str(a) for a in extra_args]]
    _state["log"].append("$ " + " ".join(cmd))
    env = dict(**__import__("os").environ, PYTHONIOENCODING="utf-8")
    _proc = subprocess.Popen(cmd, cwd=str(proj.root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", env=env)

    def pump():
        assert _proc is not None
        for line in _proc.stdout:  # type: ignore[union-attr]
            with _lock:
                _state["log"].append(line.rstrip("\n"))
        code = _proc.wait()
        with _lock:
            _state.update(running=False, ended=time.time(), exit_code=code)
            _state["log"].append(f"[exit {code}]")

    threading.Thread(target=pump, daemon=True).start()
    return {"stage": stage_id, "command": cmd}


def stop() -> dict:
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
        return {"stopped": True}
    return {"stopped": False}


def project_files(proj: Project) -> list[dict]:
    names = ["project.json", "corpus_deduped.csv", "title_screening.csv", "fulltext_pdf_manifest.csv",
             "fulltext_analysis.csv", "fulltext_recommendations.csv", "citation_chase_candidates.csv",
             "citation_chase_decisions.csv", "citation_chase_shortlist.csv", "supplementary_review.html",
             "corpus_assessment.csv", "corpus_assessment_backcheck.csv", "corpus_taxonomy.csv",
             "screening_corpus_draft.csv", "core_domain_review.csv", "adjudications.csv", "audit_data.json",
             "synthesis_draft.md", "screening_overview_draft.md", "recall_check.json", "completeness_report.md"]
    out = []
    for n in names:
        p = proj.root / n
        rows = None
        if p.is_file() and p.suffix == ".csv":
            try:
                with p.open(encoding="utf-8-sig", errors="replace") as f:
                    rows = max(0, sum(1 for _ in f) - 1)
            except OSError:
                rows = None
        out.append({"name": n, "exists": p.is_file(), "rows": rows,
                    "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)) if p.is_file() else ""})
    pdfs = sum(1 for _ in proj.pdf_dir.rglob("*.pdf")) if proj.pdf_dir.is_dir() else 0
    out.append({"name": "pdfs/ (files)", "exists": pdfs > 0, "rows": pdfs, "modified": ""})
    return out


def test_patterns(proj: Project, body: dict) -> dict:
    """Try patterns / rules from the (unsaved) editor against titles in the project or a pasted sample."""
    from lib import parse_export
    data = body.get("project") or proj.data
    trial = Project(root=proj.root, data=data)
    sample: list[dict] = []
    for line in (body.get("sample") or "").splitlines():
        if line.strip():
            sample.append({"title": line.strip(), "abstract": "", "year": ""})
    if not sample:
        screen = proj.root / "title_screening.csv"
        if screen.is_file():
            import csv
            with screen.open(encoding="utf-8-sig", newline="") as f:
                sample = list(csv.DictReader(f))[:2000]
        else:
            for item in trial.exports:
                if item["path"].is_file():
                    sample.extend(parse_export(item)[:1000])
    counts = {k: 0 for k in trial.patterns if k not in ("doi",)}
    decisions: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    try:
        for r in sample:
            text = f"{r.get('title', '')} {(r.get('abstract') or '')[:800]}"
            for k, pat in trial.patterns.items():
                if k in counts and pat.search(text):
                    counts[k] += 1
            d, code, _ = trial.screen(r.get("title", ""), r.get("abstract", ""), r.get("year", ""))
            decisions[d] = decisions.get(d, 0) + 1
            key = f"{d}/{code}"
            if len(examples.setdefault(key, [])) < 3:
                examples[key].append((r.get("title") or "")[:110])
    except ConfigError as exc:
        return {"error": str(exc), "sample": len(sample)}
    return {"sample": len(sample), "pattern_hits": counts, "decisions": decisions, "examples": examples}


def list_projects() -> list[dict]:
    out = []
    for p in sorted((REPO_DIR / "projects").glob("*/project.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            d = {}
        out.append({"slug": p.parent.name, "name": d.get("name", p.parent.name), "frozen": bool(d.get("frozen")),
                    "path": str(p.parent)})
    return out


def new_project(slug: str, name: str) -> dict:
    slug = re.sub(r"[^a-z0-9\-]+", "-", (slug or name or "").lower()).strip("-")
    if not slug or slug.startswith("_"):
        raise ConfigError("give the project a slug like 'urban-heat-2027'")
    dest = REPO_DIR / "projects" / slug
    if dest.exists():
        raise ConfigError(f"project {slug!r} already exists")
    shutil.copytree(TEMPLATE_DIR, dest)
    cfg = json.loads((dest / "project.json").read_text(encoding="utf-8"))
    cfg["name"], cfg["slug"] = name or slug, slug
    (dest / "project.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for sub in ("exports", "pdfs/01_not_reviewed", "pdfs/02_final_included", "fulltext_cache"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
    return {"slug": slug, "path": f"projects/{slug}",
            "hint": f"restart the server with: python toolkit.py serve {slug}"}
