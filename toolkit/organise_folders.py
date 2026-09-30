"""Copy included PDFs into tier x core-domain browsing folders.

    python organise_folders.py --project <dir>

Creates ``browse/<tier folder>/<domain folder>/<ID>_<Author>_<Year>.pdf``
for every final Include; multi-core papers are copied into every listed core
domain. Files are copies; the canonical PDFs stay in pdfs/02_final_included/.
Writes browse/FOLDER_MANIFEST.txt.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_files import find_local_pdf  # noqa: E402
from lib import read_csv, short_author  # noqa: E402
from project_config import CFG  # noqa: E402


def main() -> None:
    CFG.guard_writable()
    rows = read_csv(CFG.file("screening_corpus_draft.csv"))
    if not rows:
        sys.exit("screening_corpus_draft.csv missing; run build_overview.py")
    folders = CFG.domain_folder
    copied, missing, lines = 0, [], []
    for r in rows:
        tier_dir = CFG.browse_dir / CFG.tier_folder(r.get("report_tier") or "")
        rel = (r.get("fulltext_local_pdf") or "").replace("\\", "/")
        src = CFG.root / rel if rel else None
        if not src or not src.is_file():
            src = find_local_pdf(r["record_id"])
        if not src:
            missing.append(r["record_id"])
            continue
        cores = [c.strip() for c in (r.get("report_core_domains") or r.get("report_primary_domain") or "").split(";") if c.strip()]
        name = f"{r['record_id']}_{short_author(r.get('authors') or '')}_{(r.get('year') or 'nd').strip()}.pdf"
        for core in cores:
            dest = tier_dir / folders.get(core, "other") / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            lines.append(str(dest.relative_to(CFG.browse_dir)).replace("\\", "/"))
            copied += 1
    CFG.browse_dir.mkdir(parents=True, exist_ok=True)
    (CFG.browse_dir / "FOLDER_MANIFEST.txt").write_text("\n".join(sorted(lines)) + "\n", encoding="utf-8")
    print(f"copied {copied} files ({len(rows)} papers); missing PDFs: {len(missing)} {missing[:10]}")


if __name__ == "__main__":
    main()
