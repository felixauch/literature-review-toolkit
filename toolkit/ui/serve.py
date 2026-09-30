"""Local review interface server (project-aware).

    python serve.py --project <dir> [--port 8765]

Serves the interface files from this folder and the project's data
(data.json, audit_data.json, synthesis_draft.md, supplementary_review.html,
pdfs/) from the project folder. Writes human decisions back into the
project's CSVs. Also hosts the setup page (setup.html) that edits
project.json and runs stage scripts.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

UI = Path(__file__).resolve().parent
sys.path.insert(0, str(UI.parent))
sys.path.insert(0, str(UI))
from project_config import CFG, ConfigError, TEMPLATE_DIR, REPO_DIR, load_project, validate  # noqa: E402
from corpus_files import (  # noqa: E402
    apply_fulltext_decisions, organise_local_pdf, records_needing_pdf, rescan_pdfs, update_manifest_status,
)
import runner  # noqa: E402

ROOT = CFG.root
CSV_PATH = ROOT / "title_screening.csv"
FULLTEXT_PATH = ROOT / "fulltext_recommendations.csv"
CHASE_PATH = ROOT / "citation_chase_decisions.csv"
DRAFT_CORPUS_PATH = ROOT / "screening_corpus_draft.csv"
ASSESSMENT_PATH = ROOT / "corpus_assessment.csv"
BACKCHECK_PATH = ROOT / "corpus_assessment_backcheck.csv"
TAXONOMY_PATH = ROOT / "corpus_taxonomy.csv"
PDF_MANIFEST_PATH = ROOT / "fulltext_pdf_manifest.csv"
AUDIT_DECISIONS_PATH = ROOT / "fulltext_audit_decisions.csv"
CORPUS = ROOT
FULLTEXT_CORPUS = CFG.pdf_dir
PENDING_PDFS = CFG.pdf_pending
INCLUDED_PDFS = CFG.pdf_included
PORT = 8765
UA = CFG.user_agent
UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
PROJECT_FILES = {"/data.json", "/audit_data.json", "/synthesis_draft.md", "/supplementary_review.html",
                 "/screening_overview_draft.md", "/merge_summary.md", "/core_domain_review.md"}

_MDPI_URL = re.compile(
    r"(?:https?://)?(?:www\.)?mdpi\.com/(\d{4}-\d{4})/(\d+)/(\d+)/(\d+)",
    re.I,
)
_SCIENCEDIRECT_PII = re.compile(
    r"(?:https?://)?(?:www\.)?sciencedirect\.com/science/article/pii/(S\d+)",
    re.I,
)
_IEEE_DOC = re.compile(r"ieee\.org/document/(\d+)", re.I)
_EMBEDDED_URL = re.compile(
    r"(?:url=|q=)(https?%3A%2F%2F[^&\"']+|https?://[^&\"'\s]+)",
    re.I,
)

_LOOKUP_CACHE: dict | None = None


def parse_doi_input(raw: str) -> str:
    text = (raw or "").strip()
    match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", text, re.I)
    if not match:
        return ""
    return normalize_doi(match.group(0))


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip().lower().rstrip(".,;)")
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)


def normalize_title(title: str) -> str:
    title = (title or "").lower()
    title = re.sub(r"[^a-z0-9]+", "", title)
    return title


def looks_like_url(raw: str) -> bool:
    return bool(re.match(r"https?://", (raw or "").strip(), re.I))


def normalize_url_key(url: str) -> str:
    text = (url or "").strip().lower()
    text = re.sub(r"^https?://(?:www\.)?", "", text)
    text = text.split("#")[0].split("?")[0].rstrip("/")
    text = re.sub(r"/pdf$", "", text)
    return text


def ieee_document_id(url: str) -> str:
    text = url or ""
    match = _IEEE_DOC.search(text)
    if match:
        return match.group(1)
    parsed = urlparse(text)
    if "ieee.org" not in parsed.netloc.lower():
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if parts:
        tail = parts[-1].split(".")[0]
        if tail.isdigit():
            return tail
    arnumber = re.search(r"arnumber=(\d+)", text, re.I)
    return arnumber.group(1) if arnumber else ""


def register_url_key(store: dict[str, str], url: str, doi: str) -> None:
    doi = normalize_doi(doi)
    if not doi:
        return
    key = normalize_url_key(url)
    if key:
        store[key] = doi
    doc_id = ieee_document_id(url)
    if doc_id:
        store[f"ieee.org/document/{doc_id}"] = doi


def crossref_works(params: dict) -> list[dict]:
    query = dict(params)
    query.setdefault("rows", 5)
    api = "https://api.crossref.org/works?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(api, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return data.get("message", {}).get("items") or []
    except Exception:  # noqa: BLE001
        return []


def doi_from_mdpi_url(url: str) -> str:
    match = _MDPI_URL.search(url)
    if not match:
        return ""
    issn, volume, issue, article = match.groups()
    items = crossref_works({"query": article, "filter": f"issn:{issn}", "rows": 5})
    for item in items:
        doi = normalize_doi(item.get("DOI") or "")
        if not doi:
            continue
        item_volume = str(item.get("volume") or "")
        item_issue = str(item.get("issue") or "")
        if item_volume and item_volume != volume:
            continue
        if item_issue and item_issue != issue:
            continue
        for link in item.get("link") or []:
            link_url = (link.get("URL") or "").lower()
            if article in link_url or f"/{volume}/{issue}/" in link_url:
                return doi
    if len(items) == 1:
        return normalize_doi(items[0].get("DOI") or "")
    return ""


def doi_from_sciencedirect_url(url: str) -> str:
    match = _SCIENCEDIRECT_PII.search(url)
    if not match:
        return ""
    pii = match.group(1)
    items = crossref_works({"query": pii, "filter": "member:78", "rows": 3})
    if len(items) == 1:
        return normalize_doi(items[0].get("DOI") or "")
    for item in items:
        for link in item.get("link") or []:
            if pii.lower() in (link.get("URL") or "").lower():
                return normalize_doi(item.get("DOI") or "")
    return ""


def doi_from_publisher_patterns(url: str) -> str:
    doi = parse_doi_input(url)
    if doi:
        return doi
    for resolver in (doi_from_mdpi_url, doi_from_sciencedirect_url):
        doi = resolver(url)
        if doi:
            return doi
    return ""


def unwrap_scholar_urls(url: str) -> list[str]:
    """Google Scholar often wraps the real publisher URL in query params."""
    seen: set[str] = set()
    out: list[str] = []

    def add(candidate: str) -> None:
        candidate = (candidate or "").strip()
        if not candidate or candidate in seen:
            return
        seen.add(candidate)
        out.append(candidate)

    add(url)
    for match in _EMBEDDED_URL.finditer(url):
        decoded = unquote(match.group(1))
        if decoded.startswith("http"):
            add(decoded)

    parsed = urlparse(url)
    if "scholar.google" not in parsed.netloc:
        return out

    qs = parse_qs(parsed.query)
    for key in ("url", "q", "u"):
        for val in qs.get(key, []):
            if val.startswith("http"):
                add(val)
            else:
                decoded = unquote(val)
                if decoded.startswith("http"):
                    add(decoded)
    return out


def candidate_urls(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    if looks_like_url(text):
        seen: set[str] = set()
        out: list[str] = []
        for url in unwrap_scholar_urls(text):
            if url not in seen:
                seen.add(url)
                out.append(url)
        return out
    return [text]


def doi_from_html(html: str) -> str:
    patterns = [
        r'<meta[^>]+name=["\']citation_doi["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']citation_doi["\']',
        r'<meta[^>]+name=["\']DC\.Identifier["\'][^>]+content=["\']doi:([^"\']+)["\']',
        r'<meta[^>]+name=["\']doi["\'][^>]+content=["\']([^"\']+)["\']',
        r'https?://(?:dx\.)?doi\.org/(10\.\d{4,9}/[^\s"\'<>]+)',
        r'"doi"\s*:\s*"(10\.\d{4,9}/[^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            doi = normalize_doi(match.group(1))
            if doi:
                return doi
    return ""


def fetch_html(url: str, timeout: int = 20) -> tuple[str, str]:
    last_error: Exception | None = None
    for attempt, user_agent in enumerate((UA, UA_BROWSER)):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                final_url = resp.geturl()
                body = resp.read(600_000).decode("utf-8", errors="ignore")
                return final_url, body
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt == 0:
                time.sleep(0.4)
            else:
                time.sleep(0.8)
    raise last_error  # type: ignore[misc]


def resolve_input_to_doi(raw: str, url_by_key: dict[str, str] | None = None) -> tuple[str, str, str]:
    """Return (doi, resolved_url, resolve_note)."""
    text = (raw or "").strip()
    if not text:
        return "", "", "Empty input"

    doi = parse_doi_input(text)
    if doi:
        return doi, text, "DOI parsed from input"

    if not looks_like_url(text):
        return "", text, "Paste a DOI (10.xxxx/…) or a full http(s) link."

    url_index = url_by_key or {}
    errors: list[str] = []
    for candidate in candidate_urls(text):
        key = normalize_url_key(candidate)
        cached = url_index.get(key, "")
        if not cached:
            doc_id = ieee_document_id(candidate)
            if doc_id:
                cached = url_index.get(f"ieee.org/document/{doc_id}", "")
        if cached:
            host = urlparse(candidate).netloc or "saved project link"
            return cached, candidate, f"Matched known project URL ({host})"

        doi = doi_from_publisher_patterns(candidate)
        if doi:
            host = urlparse(candidate).netloc or "publisher link"
            return doi, candidate, f"DOI resolved via Crossref ({host})"

        try:
            final_url, html = fetch_html(candidate)
            doi = parse_doi_input(final_url) or doi_from_html(html) or doi_from_publisher_patterns(final_url)
            if doi:
                host = urlparse(final_url).netloc or "publisher page"
                return doi, final_url, f"DOI resolved from {host}"
            errors.append(f"{urlparse(candidate).netloc}: no DOI in page")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{urlparse(candidate).netloc}: {exc}")

    if "scholar.google" in text and not any(
        "scholar.google" not in urlparse(u).netloc for u in candidate_urls(text)
    ):
        hint = (
            "This Scholar link does not contain a publisher URL. Right-click the paper "
            "title in Scholar → Copy link address, and paste that link here."
        )
    elif ieee_document_id(text):
        hint = (
            "IEEE blocks automated DOI lookup. Copy the DOI from the IEEE page "
            "(or paste a Springer/MDPI/Elsevier link from Scholar instead)."
        )
    elif "scholar.google" in text:
        hint = (
            "Could not resolve a DOI from the publisher link embedded in this Scholar URL."
        )
    else:
        hint = "Could not resolve a DOI from this link."
    if errors:
        hint += " (" + "; ".join(errors[:2]) + ")"
    return "", text, hint


def load_lookup_cache() -> dict:
    global _LOOKUP_CACHE
    if _LOOKUP_CACHE is not None:
        return _LOOKUP_CACHE

    title_by_doi: dict[str, dict] = {}
    title_by_norm: dict[str, dict] = {}
    if CSV_PATH.exists():
        for row in csv.DictReader(CSV_PATH.open(encoding="utf-8")):
            doi = normalize_doi(row.get("doi") or "")
            if doi:
                title_by_doi[doi] = row
            norm = normalize_title(row.get("title") or "")
            if norm:
                title_by_norm[norm] = row

    fulltext_by_id: dict[str, dict] = {}
    fulltext_by_doi: dict[str, dict] = {}
    url_by_key: dict[str, str] = {}
    if FULLTEXT_PATH.exists():
        for row in csv.DictReader(FULLTEXT_PATH.open(encoding="utf-8")):
            fulltext_by_id[row["record_id"]] = row

    assess_by_id: dict[str, dict] = {}
    if ASSESSMENT_PATH.exists():
        for row in csv.DictReader(ASSESSMENT_PATH.open(encoding="utf-8")):
            assess_by_id[row["record_id"]] = row

    chase_by_doi: dict[str, dict] = {}
    if CHASE_PATH.exists():
        for row in csv.DictReader(CHASE_PATH.open(encoding="utf-8")):
            doi = normalize_doi(row.get("doi") or "")
            if doi:
                chase_by_doi[doi] = row

    final_by_doi: dict[str, dict] = {}
    if DRAFT_CORPUS_PATH.exists():
        for row in csv.DictReader(DRAFT_CORPUS_PATH.open(encoding="utf-8")):
            doi = normalize_doi(row.get("doi") or "")
            if doi:
                final_by_doi[doi] = row

    for doi, title_row in title_by_doi.items():
        rid = title_row.get("record_id") or ""
        if rid in fulltext_by_id:
            fulltext_by_doi[doi] = fulltext_by_id[rid]
            ft_row = fulltext_by_id[rid]
            for field in ("fulltext_url", "fulltext_oa_url"):
                register_url_key(url_by_key, ft_row.get(field) or "", doi)

    _LOOKUP_CACHE = {
        "title_by_doi": title_by_doi,
        "title_by_norm": title_by_norm,
        "url_by_key": url_by_key,
        "fulltext_by_id": fulltext_by_id,
        "fulltext_by_doi": fulltext_by_doi,
        "assess_by_id": assess_by_id,
        "chase_by_doi": chase_by_doi,
        "final_by_doi": final_by_doi,
    }
    return _LOOKUP_CACHE


def invalidate_lookup_cache() -> None:
    global _LOOKUP_CACHE
    _LOOKUP_CACHE = None


def corpus_status(
    record_id: str,
    title_row: dict | None,
    fulltext_row: dict | None,
    chase_row: dict | None,
    final_row: dict | None,
) -> tuple[str, str]:
    """Return (status_code, human label)."""
    if final_row or (fulltext_row or {}).get("fulltext_final_decision") == "Include":
        return "in_final_corpus", "In final corpus"
    if (fulltext_row or {}).get("fulltext_final_decision") == "Exclude":
        reason = (fulltext_row or {}).get("fulltext_reason") or (
            fulltext_row or {}
        ).get("fulltext_final_notes") or "Excluded at full-text screening"
        return "excluded_fulltext", reason
    if chase_row and (chase_row.get("decision") or "").strip() == "Exclude":
        return "excluded_citation_chase", chase_row.get("reason") or "Excluded (citation chase)"
    if title_row and (title_row.get("human_decision") or "").strip() == "Exclude":
        code = title_row.get("exclusion_code") or title_row.get("backcheck_exclusion_code") or ""
        reason = title_row.get("screen_reason") or title_row.get("backcheck_reason") or ""
        detail = code or reason or "Excluded at title/abstract screening"
        return "excluded_title", detail
    if chase_row and (chase_row.get("decision") or "").strip() == "Include":
        return "chase_include_not_final", "Citation-chase Include but not in final corpus"
    if title_row and (title_row.get("human_decision") or "").strip() == "Include":
        return "screened_include_not_final", "Retained for full-text but not in final corpus"
    if title_row:
        dec = (title_row.get("human_decision") or title_row.get("suggested_decision") or "").strip()
        if dec:
            return "screened_other", f"Screened ({dec})"
        return "in_search_not_screened", "In database search, not yet decided"
    if chase_row:
        return "citation_chase_only", "Citation-chase candidate only (not in database export)"
    return "not_found", "Not found in this project's search records"


def lookup_doi(raw: str) -> dict:
    cache = load_lookup_cache()
    parsed, resolved_url, resolve_note = resolve_input_to_doi(
        raw, cache.get("url_by_key") or {}
    )
    base = {
        "input": (raw or "").strip(),
        "resolved_url": resolved_url,
        "resolve_note": resolve_note,
    }
    if not parsed:
        return {
            **base,
            "ok": True,
            "found": False,
            "parsed_doi": "",
            "status": "invalid",
            "status_label": "Could not resolve DOI",
            "message": resolve_note,
        }

    title_row = cache["title_by_doi"].get(parsed)
    chase_row = cache["chase_by_doi"].get(parsed)
    final_row = cache["final_by_doi"].get(parsed)
    record_id = ""
    if title_row:
        record_id = title_row.get("record_id") or ""
    elif chase_row:
        record_id = chase_row.get("record_id") or ""
    elif final_row:
        record_id = final_row.get("record_id") or ""

    fulltext_row = cache["fulltext_by_doi"].get(parsed)
    assess_row = cache["assess_by_id"].get(record_id) if record_id and title_row else None

    if not title_row and not chase_row and not final_row:
        return {
            **base,
            "ok": True,
            "found": False,
            "parsed_doi": parsed,
            "status": "not_found",
            "status_label": "Not in project",
            "message": "DOI resolved, but no record in the database search, citation chase, or final corpus.",
        }

    status, status_detail = corpus_status(
        record_id, title_row, fulltext_row, chase_row, final_row
    )

    row = title_row or chase_row or final_row or {}
    return {
        **base,
        "ok": True,
        "found": True,
        "parsed_doi": parsed,
        "status": status,
        "status_label": {
            "in_final_corpus": "In final corpus",
            "excluded_fulltext": "Excluded (full text)",
            "excluded_citation_chase": "Excluded (citation chase)",
            "excluded_title": "Excluded (title/abstract)",
            "chase_include_not_final": "Citation chase — not final",
            "screened_include_not_final": "Screened Include — not final",
            "screened_other": "Screened",
            "in_search_not_screened": "In search — undecided",
            "citation_chase_only": "Citation chase only",
        }.get(status, status),
        "status_detail": status_detail,
        "record_id": record_id,
        "title": row.get("title") or "",
        "authors": row.get("authors") or "",
        "year": row.get("year") or "",
        "journal": row.get("journal") or "",
        "search_arm": "citation_chasing"
        if (record_id or "").startswith(CFG.supplementary_prefix)
        else ("database" if title_row else "unknown"),
        "human_decision": (title_row or {}).get("human_decision") or "",
        "exclusion_code": (title_row or {}).get("exclusion_code")
        or (title_row or {}).get("backcheck_exclusion_code")
        or "",
        "fulltext_final_decision": (fulltext_row or {}).get("fulltext_final_decision") or "",
        "fulltext_reason": (fulltext_row or {}).get("fulltext_reason") or "",
        "fulltext_local_pdf": (fulltext_row or {}).get("fulltext_local_pdf") or "",
        "citation_chase_decision": (chase_row or {}).get("decision") or "",
        "citation_chase_reason": (chase_row or {}).get("reason") or "",
        "assess_tier": (assess_row or {}).get("assess_tier") or "",
        "assess_primary_domain": (assess_row or {}).get("assess_primary_domain") or "",
        "assess_decision_link": (assess_row or {}).get("assess_decision_link") or "",
        "sources": (title_row or {}).get("sources") or "citation_chasing"
        if chase_row
        else "",
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI), **kwargs)

    # ---- helpers ----------------------------------------------------------
    def _json(self, payload, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _error(self, exc: Exception, status: int = 500) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(str(exc).encode("utf-8"))

    def _send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(404, f"{path.name} not found in project; run the stage that creates it")
            return
        ctype = self.guess_type(str(path))
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    # ---- GET --------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if path in PROJECT_FILES:
            return self._send_file(ROOT / path.lstrip("/"))
        if path.startswith("/pdfs/"):
            target = (ROOT / unquote(path.lstrip("/"))).resolve()
            if CFG.pdf_dir.resolve() not in target.parents:
                return self.send_error(403)
            return self._send_file(target)
        try:
            if path == "/api/audit-decisions":
                return self._json({"ok": True, "decisions": load_audit_decisions()})
            if path == "/api/lookup-doi":
                query = parse_qs(parsed.query)
                raw = (query.get("q") or query.get("doi") or [""])[0]
                return self._json(lookup_doi(raw))
            if path == "/api/project":
                return self._json({"ok": True, "project": CFG.public(), "problems": validate(CFG),
                                   "stages": runner.STAGES, "files": runner.project_files(CFG)})
            if path == "/api/run-status":
                return self._json({"ok": True, **runner.status()})
            if path == "/api/projects":
                return self._json({"ok": True, "projects": runner.list_projects()})
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        super().do_GET()

    # ---- POST -------------------------------------------------------------
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/rescan-pdfs":
                info = rescan_pdfs()
                info["missing"] = len(records_needing_pdf())
                self._rebuild()
                return self._json({"ok": True, **info})
            if path == "/api/save-audit-decision":
                return self._json({"ok": True, **apply_audit_decision(self._body())})
            if path in ("/api/save", "/api/save-fulltext", "/api/save-assessment"):
                CFG.guard_writable()
                payload = self._body()
                decisions = {d["record_id"]: d for d in payload.get("decisions", [])}
                updated = (apply_fulltext_decisions(decisions) if path == "/api/save-fulltext"
                           else apply_assessment_decisions(decisions) if path == "/api/save-assessment"
                           else apply_decisions(decisions))
                self._rebuild()
                return self._json({"ok": True, "updated": updated})
            if path == "/api/project":
                CFG.guard_writable()
                payload = self._body()
                CFG.data.clear()
                CFG.data.update(payload.get("project") or payload)
                CFG.save()
                invalidate_lookup_cache()
                return self._json({"ok": True, "problems": validate(CFG)})
            if path == "/api/test-patterns":
                return self._json({"ok": True, **runner.test_patterns(CFG, self._body())})
            if path == "/api/run":
                body = self._body()
                return self._json({"ok": True, **runner.start(body.get("stage", ""), body.get("args") or [], CFG)})
            if path == "/api/run-stop":
                return self._json({"ok": True, **runner.stop()})
            if path == "/api/new-project":
                body = self._body()
                return self._json({"ok": True, **runner.new_project(body.get("slug", ""), body.get("name", ""))})
            if path == "/api/rebuild-data":
                self._rebuild()
                return self._json({"ok": True})
        except ConfigError as exc:
            return self._error(exc, 409)
        except Exception as exc:  # noqa: BLE001
            return self._error(exc)
        self.send_error(404)

    def _rebuild(self) -> None:
        from build_data import main as rebuild

        rebuild()
        invalidate_lookup_cache()

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def load_audit_decisions() -> dict:
    """Return {record_id: decision_row} from the audit decision log."""
    if not AUDIT_DECISIONS_PATH.exists():
        return {}
    rows = list(csv.DictReader(AUDIT_DECISIONS_PATH.open(encoding="utf-8")))
    return {row["record_id"]: row for row in rows if row.get("record_id")}


def apply_audit_decision(payload: dict) -> dict:
    """Persist confirm-change or discard-keep for an audit mismatch.

    decision values:
      change — accept mismatch; charting should be updated
      keep   — discard mismatch; keep current charting
      ""     — clear decision
    """
    record_id = (payload.get("record_id") or "").strip()
    decision = (payload.get("decision") or "").strip().lower()
    if not record_id:
        raise ValueError("record_id required")
    if decision not in {"change", "keep", ""}:
        raise ValueError("decision must be 'change', 'keep', or empty to clear")

    fields = [
        "record_id",
        "decision",
        "note",
        "charted_tier",
        "charted_domain",
        "charted_link",
        "suggested_tier",
        "suggested_domain",
        "suggested_link",
        "flags",
        "updated_at",
    ]
    existing = load_audit_decisions()
    if decision == "":
        existing.pop(record_id, None)
    else:
        existing[record_id] = {
            "record_id": record_id,
            "decision": decision,
            "note": (payload.get("note") or "").strip(),
            "charted_tier": payload.get("charted_tier") or "",
            "charted_domain": payload.get("charted_domain") or "",
            "charted_link": payload.get("charted_link") or "",
            "suggested_tier": payload.get("suggested_tier") or "",
            "suggested_domain": payload.get("suggested_domain") or "",
            "suggested_link": payload.get("suggested_link") or "",
            "flags": payload.get("flags") or "",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    with AUDIT_DECISIONS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(existing.values())

    return {
        "record_id": record_id,
        "decision": decision,
        "total_decisions": len(existing),
        "row": existing.get(record_id),
    }


def apply_decisions(decisions: dict) -> int:
    rows = list(csv.DictReader(CSV_PATH.open(encoding="utf-8")))
    if not rows:
        return 0
    fields = list(rows[0].keys())
    updated = 0
    for row in rows:
        d = decisions.get(row["record_id"])
        if not d:
            continue
        row["human_decision"] = d.get("human_decision") or ""
        row["exclusion_code"] = d.get("exclusion_code") or row.get("exclusion_code") or ""
        row["human_notes"] = d.get("human_notes") or ""
        updated += 1
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # also sync pass_A if present
    pass_a = ROOT / "pass_A_decisions.csv"
    if pass_a.exists():
        pa = list(csv.DictReader(pass_a.open(encoding="utf-8")))
        if pa:
            pfields = list(pa[0].keys())
            for row in pa:
                d = decisions.get(row["record_id"])
                if not d:
                    continue
                row["human_decision"] = d.get("human_decision") or ""
                row["exclusion_code"] = d.get("exclusion_code") or ""
                row["human_notes"] = d.get("human_notes") or ""
            with pass_a.open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=pfields, extrasaction="ignore")
                w.writeheader()
                w.writerows(pa)
    return updated


def contribution_type(tier: str) -> str:
    return CFG.tier_label(tier)


def apply_assessment_decisions(decisions: dict) -> int:
    """Persist reviewer edits to corpus categorisation fields."""
    if not ASSESSMENT_PATH.exists():
        raise FileNotFoundError("Run assess_corpus.py or reassess_final_corpus.py first.")
    rows = list(csv.DictReader(ASSESSMENT_PATH.open(encoding="utf-8")))
    if not rows:
        return 0
    fields = list(rows[0].keys())
    for field in ("assess_reasoning", "assess_reasoning_user"):
        if field not in fields:
            fields.append(field)
    updated = 0
    for row in rows:
        patch = decisions.get(row["record_id"])
        if not patch:
            continue
        tier = patch.get("assess_tier") or row.get("assess_tier") or CFG.default_tier
        primary = patch.get("assess_primary_domain") or row.get("assess_primary_domain") or ""
        secondary_raw = patch.get("assess_secondary_domains")
        if secondary_raw is None:
            secondary = row.get("assess_secondary_domains") or ""
        elif isinstance(secondary_raw, list):
            secondary = "; ".join(item for item in secondary_raw if item and item != primary)
        else:
            secondary = str(secondary_raw)
        secondary_list = [
            item.strip()
            for item in secondary.split(";")
            if item.strip() and item.strip() != primary
        ]
        secondary = "; ".join(secondary_list)
        domains = [primary] + secondary_list if primary else secondary_list
        row["assess_tier"] = tier
        row["assess_primary_domain"] = primary
        row["assess_secondary_domains"] = secondary
        row["assess_domains"] = "; ".join(domains)
        row["assess_contribution_type"] = contribution_type(tier)
        if patch.get("assess_decision_link"):
            link = patch["assess_decision_link"]
            # Coupling rule: only tiers listed in taxonomy.operational_tiers may execute an operation.
            if link == "operational" and CFG.operational_tiers and tier not in CFG.operational_tiers:
                raise ValueError(
                    f"{row['record_id']}: operational link requires one of {CFG.operational_tiers}."
                )
            row["assess_decision_link"] = link
        user_note = (patch.get("assess_reasoning_user") or "").strip()
        if user_note:
            row["assess_reasoning_user"] = user_note
            base = (row.get("assess_reasoning") or "").strip()
            marker = "Reviewer note:"
            if marker in base:
                base = base.split(marker, 1)[0].strip()
            row["assess_reasoning"] = f"{base} Reviewer note: {user_note}".strip()
        updated += 1
    with ASSESSMENT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    back_rows = {row["record_id"]: row for row in rows}
    if BACKCHECK_PATH.exists():
        back_existing = list(csv.DictReader(BACKCHECK_PATH.open(encoding="utf-8")))
        back_fields = list(back_existing[0].keys()) if back_existing else [
            "record_id",
            "assess_domains",
            "assess_tier",
            "assess_decision_link",
            "assess_relevance",
            "assess_band",
            "backcheck_exclude",
            "backcheck_exclude_reason",
        ]
    else:
        back_existing = []
        back_fields = [
            "record_id",
            "assess_domains",
            "assess_tier",
            "assess_decision_link",
            "assess_relevance",
            "assess_band",
            "backcheck_exclude",
            "backcheck_exclude_reason",
        ]
    back_by_id = {row["record_id"]: row for row in back_existing}
    for rid, assess in back_rows.items():
        target = back_by_id.get(rid, {"record_id": rid})
        target["assess_domains"] = assess["assess_domains"]
        target["assess_tier"] = assess["assess_tier"]
        target["assess_decision_link"] = assess.get("assess_decision_link") or ""
        target["assess_relevance"] = assess.get("assess_relevance") or ""
        target["assess_band"] = assess.get("assess_band") or ""
        target.setdefault("backcheck_exclude", "")
        target.setdefault("backcheck_exclude_reason", "")
        back_by_id[rid] = target
    with BACKCHECK_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=back_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(back_by_id.values())

    tax_rows = {row["record_id"]: row for row in csv.DictReader(TAXONOMY_PATH.open(encoding="utf-8"))} if TAXONOMY_PATH.exists() else {}
    tax_fields = ["record_id", "assess_primary_domain", "assess_secondary_domains"]
    for rid, assess in back_rows.items():
        tax_rows[rid] = {
            "record_id": rid,
            "assess_primary_domain": assess["assess_primary_domain"],
            "assess_secondary_domains": assess["assess_secondary_domains"],
        }
    with TAXONOMY_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tax_fields)
        writer.writeheader()
        writer.writerows(tax_rows.values())
    return updated


def main() -> None:
    global PORT
    if "--port" in sys.argv:
        PORT = int(sys.argv[sys.argv.index("--port") + 1])
    from build_data import main as rebuild

    if CSV_PATH.exists():
        rebuild()
    else:
        print("No title_screening.csv yet; open /setup.html to configure the project and run the first stage.")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Project: {CFG.name} ({CFG.root})", flush=True)
    print(f"Review UI:  http://127.0.0.1:{PORT}/", flush=True)
    print(f"Setup page: http://127.0.0.1:{PORT}/setup.html", flush=True)
    print("Ctrl+C to stop.", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
