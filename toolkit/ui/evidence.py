"""Short evidence quotes from title/abstract for the screening cards.

Chooses which project patterns to quote from the draft decision and its
exclusion code, then returns the sentence around the first match, tagged
with its source ("Title: …" / "Abstract: …").
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

UI = Path(__file__).resolve().parent
sys.path.insert(0, str(UI.parent))
from lib import sentence_around  # noqa: E402
from project_config import CFG  # noqa: E402


def _first_quote(text: str, keys: list[str], source: str) -> str | None:
    for key in keys:
        m = CFG.rx(key).search(text or "")
        if m:
            q = sentence_around(text, m.start(), m.end())
            if q:
                return f'{source}: “{q}”'
    return None


def evidence_quote(title: str, abstract: str, suggested: str, exclusion_code: str, screen_reason: str) -> str:
    title, abstract = title or "", abstract or ""
    reason, code = (screen_reason or "").lower(), (exclusion_code or "").lower()
    if suggested == "Exclude" or code in ("wrong_population", "wrong_crop", "out_of_scope"):
        keys = ["wrong_population", "out_of_scope", "other_discipline", "market_only", "not_english"]
    elif suggested == "Include":
        keys = ["population", "technology", "context"]
    elif "review" in reason or "review" in code:
        keys = ["review"]
    elif "no_decision" in code or "sensing" in reason or "sensor" in reason:
        keys = ["sensor_only", "population"]
    elif "needs_abstract" in code or "abstract" in reason:
        keys = ["population", "technology", "sensor_only"]
    else:
        keys = ["population", "technology", "wrong_population", "out_of_scope"]

    prefer_title = "title" in reason or not abstract
    order = [("Title", title), ("Abstract", abstract)] if prefer_title else [("Abstract", abstract), ("Title", title)]
    quotes: list[str] = []
    for source, text in order:
        q = _first_quote(text, keys, source)
        if not q:
            continue
        quotes.append(q)
        if suggested == "Include" and source == "Title":
            for key in keys:
                m = CFG.rx(key).search(title)
                if m:
                    tagged = f'Title: “{sentence_around(title, m.start(), m.end(), max_len=120)}”'
                    if tagged not in quotes:
                        quotes.append(tagged)
                if len(quotes) >= 2:
                    break
        break
    if not quotes:
        t = re.sub(r"\s+", " ", title).strip()
        if len(t) > 180:
            t = t[:177] + "…"
        return f'Title: “{t}”' if t else ""
    return " · ".join(quotes[:2])
