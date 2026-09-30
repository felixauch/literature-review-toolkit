"""Collect and verify full-text PDFs.

    python pdfs.py --project <dir> status
    python pdfs.py --project <dir> zotero          # copy matches from Zotero storage
    python pdfs.py --project <dir> oa              # Unpaywall / OpenAlex open-access  [network]
    python pdfs.py --project <dir> browser --open 10 --watch
    python pdfs.py --project <dir> browser --harvest
    python pdfs.py --project <dir> verify          # title/DOI on page 1 matches record
    python pdfs.py --project <dir> rescan          # relink files already in the folders

Every PDF is a copy named ``<record_id>__<slug>.pdf`` under
``pdfs/01_not_reviewed/`` (or ``02_final_included/`` when the record is already
a final Include). Source files are never modified. Paywalled items: use
``browser --open N`` to open the DOI pages, download by hand with your
institutional access, and let ``--watch`` file the results by reading the
first-page title.
"""
from __future__ import annotations

import csv
import re
import shutil
import sys
import time
import urllib.parse
import webbrowser
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_files import (  # noqa: E402
    find_local_pdf, pdf_name, records_needing_pdf, rescan_pdfs, upsert_manifest,
)
from lib import get_json, norm_doi, norm_title, pdf_first_page_text, read_csv  # noqa: E402
from project_config import CFG  # noqa: E402


def target_folder(record: dict) -> Path:
    folder = CFG.pdf_included if record.get("final") == "Include" else CFG.pdf_pending
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def title_similarity(a: str, b: str) -> float:
    na, nb = norm_title(a), norm_title(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 0.98
    return SequenceMatcher(None, na, nb).ratio()


def match_text_to_records(text: str, records: list[dict]) -> tuple[dict | None, float, float]:
    """Best record for a PDF's first-page text (by DOI, then title similarity)."""
    low = text.lower()
    for r in records:
        d = norm_doi(r.get("doi") or "")
        if d and d in low:
            return r, 1.0, 0.0
    scored = []
    for r in records:
        nt = norm_title(r.get("title") or "")
        if len(nt) < 20:
            continue
        hay = norm_title(text[:3000])
        score = 0.99 if nt in hay else SequenceMatcher(None, nt, hay[: len(nt) + 40]).ratio()
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return None, 0.0, 0.0
    best, runner = scored[0], (scored[1] if len(scored) > 1 else (0.0, None))
    return best[1], best[0], runner[0]


def file_pdf(src: Path, record: dict, source_label: str, score: float, runner: float, move: bool) -> Path:
    dest = target_folder(record) / pdf_name(record["record_id"], record.get("title") or "")
    if move:
        shutil.move(str(src), str(dest))
    else:
        shutil.copy2(src, dest)
    status = "final_included" if record.get("final") == "Include" else "not_reviewed"
    upsert_manifest(record["record_id"], record.get("title") or "", dest, source_label, status,
                    f"{score:.2f}", f"{runner:.2f}")
    return dest


# --------------------------------------------------------------------------
def cmd_status() -> None:
    missing = records_needing_pdf()
    print(f"{len(missing)} kept records still need a PDF")
    for r in missing[:30]:
        print(f"  {r['record_id']}  {r['year']}  {r['title'][:80]}")
    if len(missing) > 30:
        print("  ...")


def cmd_zotero() -> None:
    storage = CFG.zotero_storage
    if not storage or not storage.is_dir():
        sys.exit("paths.zotero_storage is not set or does not exist")
    missing = records_needing_pdf()
    pdfs = list(storage.rglob("*.pdf"))
    print(f"{len(pdfs)} PDFs in Zotero storage; {len(missing)} records need one")
    copied = 0
    for pdf in pdfs:
        stem_title = re.sub(r"^.*? - \d{4} - ", "", pdf.stem)  # Zotero "Author - Year - Title" pattern
        best, score = None, 0.0
        for r in missing:
            s = title_similarity(stem_title, r["title"])
            if s > score:
                best, score = r, s
        if best is None or score < 0.85:
            continue
        if find_local_pdf(best["record_id"]):
            continue
        # confirm with first page when the filename match is not exact
        if score < 0.97:
            text = pdf_first_page_text(pdf)
            rec2, s2, _ = match_text_to_records(text, [best]) if text else (None, 0.0, 0.0)
            if rec2 is None or s2 < 0.8:
                continue
        file_pdf(pdf, best, str(pdf), score, 0.0, move=False)
        copied += 1
        print(f"  {best['record_id']} <- {pdf.name}")
    rescan_pdfs()
    print(f"copied {copied} PDFs from Zotero")


def unpaywall_pdf_url(doi: str) -> str:
    try:
        data = get_json(f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email={CFG.contact_email}", CFG.user_agent)
    except Exception:  # noqa: BLE001
        return ""
    loc = data.get("best_oa_location") or {}
    return loc.get("url_for_pdf") or ""


def openalex_pdf_url(doi: str) -> str:
    try:
        data = get_json("https://api.openalex.org/works/https://doi.org/" + urllib.parse.quote(doi, safe="/.")
                        + f"?mailto={CFG.contact_email}", CFG.user_agent)
    except Exception:  # noqa: BLE001
        return ""
    loc = data.get("best_oa_location") or {}
    return loc.get("pdf_url") or ""


def download(url: str, dest: Path) -> bool:
    try:
        import requests
    except ImportError:
        sys.exit("requests is required for downloads: pip install requests")
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,*/*"}, timeout=40)
    except Exception:  # noqa: BLE001
        return False
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return False
    dest.write_bytes(r.content)
    return True


def cmd_oa() -> None:
    missing = records_needing_pdf()
    log_path = CFG.file("pdf_download_log.csv")
    log = read_csv(log_path)
    got = 0
    for r in missing:
        doi = norm_doi(r.get("doi") or "")
        tried = []
        urls = [u for u in (r.get("fulltext_oa_url"),) if u and u.lower().endswith(".pdf")]
        if doi:
            urls += [unpaywall_pdf_url(doi), openalex_pdf_url(doi)]
        ok = False
        for url in [u for u in urls if u]:
            tried.append(url)
            tmp = CFG.pdf_pending / f"_tmp_{r['record_id']}.pdf"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            if download(url, tmp):
                file_pdf(tmp, r, url, 1.0, 0.0, move=True)
                ok = True
                got += 1
                break
            tmp.unlink(missing_ok=True)
        log.append({"record_id": r["record_id"], "doi": doi, "result": "ok" if ok else "none",
                    "tried": " | ".join(tried), "when": time.strftime("%Y-%m-%d %H:%M")})
        print(f"  {r['record_id']}: {'ok' if ok else 'no OA copy'}")
        time.sleep(0.3)
    with log_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["record_id", "doi", "result", "tried", "when"])
        w.writeheader()
        w.writerows(log)
    rescan_pdfs()
    print(f"downloaded {got} of {len(missing)}")


def harvest(records: list[dict], move: bool = False) -> int:
    filed = 0
    for folder in CFG.download_dirs:
        if not folder.is_dir():
            continue
        for pdf in sorted(folder.glob("*.pdf"), key=lambda p: p.stat().st_mtime):
            if time.time() - pdf.stat().st_mtime < 3:
                continue  # still being written
            text = pdf_first_page_text(pdf)
            if not text:
                continue
            rec, score, runner = match_text_to_records(text, records)
            if rec is None or score < 0.8 or (score < 0.95 and runner > score - 0.05):
                continue
            dest = file_pdf(pdf, rec, f"browser:{pdf.name}", score, runner, move=move)
            print(f"  filed {pdf.name} -> {dest.name} (score {score:.2f})")
            filed += 1
            records[:] = [r for r in records if r["record_id"] != rec["record_id"]]
    return filed


def cmd_browser(args: list[str]) -> None:
    missing = records_needing_pdf()
    if "--open" in args:
        n = int(args[args.index("--open") + 1])
        for r in missing[:n]:
            doi = norm_doi(r.get("doi") or "")
            url = f"https://doi.org/{doi}" if doi else "https://scholar.google.com/scholar?q=" + urllib.parse.quote(r["title"])
            webbrowser.open(url)
            time.sleep(0.6)
        print(f"opened {min(n, len(missing))} pages; download each PDF, --watch files them")
    if "--harvest" in args:
        n = harvest(missing)
        rescan_pdfs()
        print(f"filed {n}")
    if "--watch" in args:
        print("watching", ", ".join(str(p) for p in CFG.download_dirs), "(Ctrl+C to stop)")
        try:
            while True:
                if harvest(missing):
                    rescan_pdfs()
                    print(f"  {len(missing)} still missing")
                time.sleep(3)
        except KeyboardInterrupt:
            print("stopped")


def cmd_verify() -> None:
    screen = {r["record_id"]: r for r in read_csv(CFG.file("title_screening.csv"))}
    problems = 0
    for folder in (CFG.pdf_pending, CFG.pdf_included):
        for pdf in sorted(folder.glob("*__*.pdf")):
            rid = pdf.name.split("__", 1)[0]
            rec = screen.get(rid)
            if not rec:
                print(f"  {pdf.name}: no such record")
                problems += 1
                continue
            text = pdf_first_page_text(pdf)
            doi = norm_doi(rec.get("doi") or "")
            ok_doi = bool(doi) and doi in text.lower()
            ok_title = title_similarity(text[:1500], rec["title"]) > 0.6 or norm_title(rec["title"])[:40] in norm_title(text)
            if not (ok_doi or ok_title):
                print(f"  {pdf.name}: first page does not match title/DOI")
                problems += 1
    print(f"verify: {problems} problems")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd != "status":
        CFG.guard_writable()
    CFG.ensure_dirs()
    if cmd == "status":
        cmd_status()
    elif cmd == "zotero":
        cmd_zotero()
    elif cmd == "oa":
        cmd_oa()
    elif cmd == "browser":
        cmd_browser(args[1:])
    elif cmd == "verify":
        cmd_verify()
    elif cmd == "rescan":
        print(rescan_pdfs())
    else:
        sys.exit(f"unknown command {cmd!r}\n{__doc__}")


if __name__ == "__main__":
    main()
