"""Second-opinion classifier for undecided records.

    python backcheck_classifier.py --project <dir> [--all]

Trains TF-IDF + a linear SVM (scikit-learn) on the reviewer's own completed
Include/Exclude decisions and writes suggestions for the remaining undecided
rows (draft Maybe by default; every undecided row with ``--all``) into the
``backcheck_*`` columns of title_screening.csv. Human decisions are never
touched. Needs at least 30 decided rows per class.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import read_csv_with_fields, write_csv  # noqa: E402
from project_config import CFG  # noqa: E402

FIELDS = [
    "backcheck_decision", "backcheck_confidence", "backcheck_score", "backcheck_reason",
    "backcheck_exclusion_code", "backcheck_nearest_include", "backcheck_nearest_exclude",
    "backcheck_batch",
]


def text(row: dict) -> str:
    title = row.get("title") or ""
    return f"{title} {title} {row.get('abstract') or ''}"


def main() -> None:
    CFG.guard_writable()
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        from sklearn.svm import LinearSVC
    except ImportError:
        sys.exit("scikit-learn and numpy are required: pip install scikit-learn numpy")

    path = CFG.file("title_screening.csv")
    fields, rows = read_csv_with_fields(path)
    for f in FIELDS:
        if f not in fields:
            fields.append(f)
    train = [r for r in rows if (r.get("human_decision") or "") in ("Include", "Exclude")]
    counts = Counter(r["human_decision"] for r in train)
    if counts.get("Include", 0) < 30 or counts.get("Exclude", 0) < 30:
        sys.exit(f"not enough decided rows to learn from: {dict(counts)} (need >= 30 each)")
    all_rows = "--all" in sys.argv
    targets = [r for r in rows if not (r.get("human_decision") or "").strip()
               and (all_rows or r.get("suggested_decision") == "Maybe")]
    if not targets:
        print("nothing to classify")
        return

    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words="english")
    X = vec.fit_transform([text(r) for r in train])
    y = np.array([1 if r["human_decision"] == "Include" else 0 for r in train])
    clf = LinearSVC(C=0.5, class_weight="balanced").fit(X, y)
    Xt = vec.transform([text(r) for r in targets])
    scores = clf.decision_function(Xt)
    sims = cosine_similarity(Xt, X)
    inc_idx = [i for i, r in enumerate(train) if r["human_decision"] == "Include"]
    exc_idx = [i for i, r in enumerate(train) if r["human_decision"] == "Exclude"]
    batch = f"svm_{time.strftime('%Y%m%d')}"

    out = Counter()
    for r, s, sim in zip(targets, scores, sims):
        ni = max(inc_idx, key=lambda i: sim[i])
        ne = max(exc_idx, key=lambda i: sim[i])
        if abs(s) < 0.25:
            decision, conf = "Maybe", "low"
        else:
            decision = "Include" if s > 0 else "Exclude"
            conf = "high" if abs(s) > 0.8 else "medium"
        r["backcheck_decision"] = decision
        r["backcheck_confidence"] = conf
        r["backcheck_score"] = f"{s:.3f}"
        r["backcheck_nearest_include"] = f"{train[ni]['record_id']} ({sim[ni]:.2f})"
        r["backcheck_nearest_exclude"] = f"{train[ne]['record_id']} ({sim[ne]:.2f})"
        r["backcheck_exclusion_code"] = train[ne].get("exclusion_code") or "" if decision == "Exclude" else ""
        r["backcheck_reason"] = (
            f"Linear SVM on {len(train)} decided records; margin {s:+.2f}. "
            f"Closest Include {train[ni]['record_id']}, closest Exclude {train[ne]['record_id']}."
        )
        r["backcheck_batch"] = batch
        out[decision] += 1
    write_csv(path, rows, fields)
    print(f"classified {len(targets)} rows: {dict(out)} (batch {batch})")


if __name__ == "__main__":
    main()
