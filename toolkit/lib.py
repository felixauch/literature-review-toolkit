"""Shared helpers for the review toolkit stage scripts."""
from __future__ import annotations

import csv
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

PAGE_SEP = "\f"

# Windows consoles default to a legacy code page; titles contain accents.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

_ACCENT_MAP = str.maketrans({
    "á": "a", "à": "a", "â": "a", "ã": "a", "ä": "a", "é": "e", "è": "e", "ê": "e",
    "ë": "e", "í": "i", "ì": "i", "î": "i", "ï": "i", "ó": "o", "ò": "o", "ô": "o",
    "õ": "o", "ö": "o", "ú": "u", "ù": "u", "û": "u", "ü": "u", "ç": "c", "ñ": "n",
    "ł": "l", "ß": "ss",
})


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
def norm_doi(doi: str) -> str:
    d = (doi or "").strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    d = d.replace("\\_", "_").replace("\\", "")
    return d.rstrip(".,;)")


def norm_title(t: str) -> str:
    t = (t or "").lower().translate(_ACCENT_MAP)
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    t = re.split(r"[;\[]", t, maxsplit=1)[0]
    return re.sub(r"[^a-z0-9]", "", t)


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\x00", "")).strip()


def short_author(authors: str) -> str:
    first = (authors or "Unknown").replace(";", " and ").split(" and ")[0].strip()
    if "," in first:
        last = first.split(",", 1)[0].strip()
    else:
        last = first.split()[-1] if first.split() else "Unknown"
    last = re.sub(r"[^A-Za-z0-9\-]", "", last)
    return last or "Unknown"


def slugify(text: str, limit: int = 60) -> str:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-")
    return t[:limit].rstrip("-") or "untitled"


def tex_escape(text: str) -> str:
    if not text:
        return ""
    text = (
        text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2010", "-")
        .replace("\u2011", "-").replace("\u2018", "'").replace("\u2019", "'")
        .replace("\u201c", "''").replace("\u201d", "''").replace("\u00a0", " ")
        .replace("\u2026", "...")
    )
    text = text.replace("\\", "\\textbackslash{}")
    for a, b in {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
                 "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}.items():
        text = text.replace(a, b)
    text = re.sub(r"</?scp>", "", text, flags=re.I)
    return re.sub(r"<[^>]+>", "", text)


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------
def read_csv(path: Path) -> list[dict]:
    if not Path(path).exists():
        return []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_csv_with_fields(path: Path) -> tuple[list[str], list[dict]]:
    if not Path(path).exists():
        return [], []
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fields is None:
        fields = []
        for row in rows:
            for key in row:
                if key not in fields:
                    fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def index_by(rows: list[dict], key: str = "record_id") -> dict[str, dict]:
    return {r[key]: r for r in rows if r.get(key)}


def backup(path: Path, tag: str = "bak") -> Path | None:
    path = Path(path)
    if not path.exists():
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = path.with_name(f"{path.stem}.{tag}_{stamp}{path.suffix}")
    dest.write_bytes(path.read_bytes())
    return dest


# --------------------------------------------------------------------------
# Text evidence
# --------------------------------------------------------------------------
def sentence_for(pattern: re.Pattern, pages: list[str]) -> tuple[str, int] | None:
    """Return a bounded sentence-like excerpt and its one-based page number."""
    for page_no, text in enumerate(pages, start=1):
        m = pattern.search(text)
        if not m:
            continue
        start = max(text.rfind(".", 0, m.start()) + 1, text.rfind("\n", 0, m.start()) + 1)
        ends = [p for p in (text.find(".", m.end()), text.find("\n", m.end())) if p >= 0]
        end = min(ends) if ends else min(len(text), m.end() + 220)
        excerpt = compact(text[start:end]).strip(" \"'“”")
        if excerpt:
            return excerpt[:350] + ("…" if len(excerpt) > 350 else ""), page_no
    return None


def evidence_for(pages: list[str], patterns: list[re.Pattern], limit: int = 2) -> tuple[str, str]:
    excerpts: list[str] = []
    labels: list[str] = []
    for pat in patterns:
        res = sentence_for(pat, pages)
        if not res:
            continue
        excerpt, page_no = res
        labelled = f"p. {page_no}: {excerpt}"
        if labelled not in excerpts:
            excerpts.append(labelled)
            labels.append(str(page_no))
        if len(excerpts) >= limit:
            break
    return " | ".join(excerpts), ", ".join(labels)


def sentence_around(text: str, start: int, end: int, max_len: int = 220) -> str:
    if not text:
        return ""
    left = start
    while left > 0 and text[left - 1] not in ".!?;\n":
        left -= 1
        if start - left > 160:
            break
    right = end
    while right < len(text) and text[right] not in ".!?;\n":
        right += 1
        if right - end > 160:
            break
    snippet = text[left:right].strip(" \t\r\n\"'“”‘’")
    if len(snippet) > max_len:
        pad = max_len // 2
        mid = (start + end) // 2
        a, b = max(0, mid - pad), min(len(text), mid + pad)
        snippet = text[a:b].strip()
        if a > 0:
            snippet = "…" + snippet
        if b < len(text):
            snippet += "…"
    return re.sub(r"\s+", " ", snippet)


# --------------------------------------------------------------------------
# PDF text
# --------------------------------------------------------------------------
def read_cached_pages(cache_dir: Path, record_id: str) -> list[str]:
    cache = Path(cache_dir) / f"{record_id}.txt"
    if cache.exists() and cache.stat().st_size > 0:
        return [p for p in cache.read_text(encoding="utf-8").split(PAGE_SEP) if p.strip()]
    return []


def extract_pages(cache_dir: Path, record_id: str, pdf_path: Path) -> tuple[list[str], int, str]:
    """Extract page text with pypdf, caching so rule tweaks do not re-extract."""
    cache_dir = Path(cache_dir)
    cache = cache_dir / f"{record_id}.txt"
    if cache.exists() and cache.stat().st_size > 0:
        pages = cache.read_text(encoding="utf-8").split(PAGE_SEP)
        return pages, len(pages), ""
    try:
        from pypdf import PdfReader  # noqa: WPS433
    except ImportError:
        return [], 0, "pypdf not installed"
    try:
        reader = PdfReader(str(pdf_path), strict=False)
        pages = [compact(p.extract_text() or "") for p in reader.pages]
    except Exception as exc:  # noqa: BLE001
        return [], 0, f"{type(exc).__name__}: {exc}"[:500]
    if any(pages):
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(PAGE_SEP.join(pages), encoding="utf-8")
    return pages, len(pages), ""


def pdf_first_page_text(pdf_path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path), strict=False)
        return compact(reader.pages[0].extract_text() or "") if reader.pages else ""
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------
# HTTP (Crossref / OpenAlex / Unpaywall)
# --------------------------------------------------------------------------
def get_json(url: str, user_agent: str, timeout: int = 20, retries: int = 2):
    last: Exception | None = None
    for _ in range(retries):
        try:
            headers = {"User-Agent": user_agent}
            parsed = urllib.parse.urlparse(url)
            key = os.environ.get("OPENALEX_API_KEY", "")
            if parsed.scheme == "https" and parsed.hostname == "api.openalex.org" and key:
                headers["Authorization"] = "Bearer " + key
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.0)
    raise last  # type: ignore[misc]


def openalex_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words: dict[int, str] = {}
    for w, positions in inv.items():
        for p in positions:
            words[p] = w
    return " ".join(words[i] for i in sorted(words))


def openalex_work_by_doi(doi: str, user_agent: str) -> dict | None:
    if not doi:
        return None
    url = "https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="/.")
    try:
        return get_json(url, user_agent)
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------
# Bibliographic export parsing
# --------------------------------------------------------------------------
def parse_bibtex(path: Path, source_label: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    entries: list[dict] = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,]+)\s*,(.*?)\n\}", text, re.DOTALL | re.IGNORECASE):
        body = m.group(3)

        def field(name: str) -> str:
            # braces balanced one level deep ({Sentinel-2} inside a title is fine)
            mm = re.search(rf"\b{name}\s*=\s*\{{((?:[^{{}}]|\{{[^{{}}]*\}})*)\}}", body, re.DOTALL | re.IGNORECASE)
            if not mm:
                mm = re.search(rf"\b{name}\s*=\s*\"([^\"]*)\"", body, re.DOTALL | re.IGNORECASE)
            return re.sub(r"\s+", " ", mm.group(1).strip()) if mm else ""

        title = field("title")
        if not title:
            continue
        entries.append({
            "source_db": source_label,
            "source_file": Path(path).name,
            "title": title.strip("{}"),
            "authors": field("author"),
            "year": field("year"),
            "doi": norm_doi(field("doi")),
            "journal": field("journal") or field("booktitle"),
            "abstract": field("abstract"),
            "type": m.group(1),
            "bibkey": m.group(2).strip(),
        })
    return entries


IEEE_COLUMNS = {
    "title": ["Document Title", "Title"],
    "authors": ["Authors", "Author"],
    "year": ["Publication Year", "Year"],
    "doi": ["DOI"],
    "journal": ["Publication Title", "Source", "Journal"],
    "abstract": ["Abstract"],
    "type": ["Document Identifier", "Type"],
}


def parse_csv_export(path: Path, source_label: str, columns: dict | None = None) -> list[dict]:
    """Parse an IEEE-style CSV export (or any CSV with a column map)."""
    cols = {**IEEE_COLUMNS, **(columns or {})}
    entries: list[dict] = []
    with Path(path).open(encoding="utf-8-sig", errors="replace", newline="") as f:
        for row in csv.DictReader(f):
            def pick(key: str) -> str:
                for name in cols.get(key, []):
                    if name in row and (row.get(name) or "").strip():
                        return row[name].strip()
                return ""
            title = pick("title")
            if not title:
                continue
            entries.append({
                "source_db": source_label,
                "source_file": Path(path).name,
                "title": title,
                "authors": pick("authors"),
                "year": pick("year"),
                "doi": norm_doi(pick("doi")),
                "journal": pick("journal"),
                "abstract": pick("abstract"),
                "type": pick("type"),
                "bibkey": "",
            })
    return entries


def parse_export(item: dict) -> list[dict]:
    fmt = item.get("format", "bibtex")
    if fmt == "bibtex":
        return parse_bibtex(item["path"], item.get("source", "db"))
    if fmt in ("ieee_csv", "csv"):
        return parse_csv_export(item["path"], item.get("source", "db"), item.get("columns"))
    raise ValueError(f"unknown export format {fmt!r} for {item.get('file')}")
