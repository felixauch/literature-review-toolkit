"""Project configuration for the review toolkit.

One ``project.json`` per review holds everything that is topic-specific:
exports, vocabulary (regex patterns), screening rules, taxonomy, paths and
contact details. Every stage script and the interface read it through this
module, so the Python code itself never contains topic vocabulary.

Resolution order for the active project:

1. ``--project <dir>`` on the command line (removed from ``sys.argv``);
2. the ``REVIEW_PROJECT`` environment variable;
3. a ``project.json`` in the current working directory.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOOLKIT_DIR = Path(__file__).resolve().parent
REPO_DIR = TOOLKIT_DIR.parent
TEMPLATE_DIR = REPO_DIR / "projects" / "_template"

# Patterns every project has even when the config does not name them.
BUILTIN_PATTERNS = {
    "not_english": r"[^\x00-\x7F]{3,}",
    "doi": r"10\.\d{4,9}/[^\s\"'<>()\[\]]+",
}

PATTERN_KEYS = [
    # title/abstract screening
    "population", "technology", "context", "wrong_population", "out_of_scope",
    "other_discipline", "market_only", "sensor_only", "review",
    # full text
    "ft_population", "ft_decision", "ft_operation", "ft_method_only",
    "ft_management_variable", "ft_monitoring", "ft_out_of_scope",
    # charting / chasing
    "agent", "contribution_cue", "chase_population", "chase_technology",
]

_NEVER = re.compile(r"(?!x)x")  # matches nothing


class ConfigError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Rule DSL
# --------------------------------------------------------------------------
class _Parser:
    """Tiny boolean expression parser for screening rules.

    Grammar::

        expr := and ('|' and)*
        and  := not ('&' not)*
        not  := '!' not | atom
        atom := '(' expr ')' | IDENT
        IDENT := field ':' pattern_key | flag

    ``field`` is ``title``, ``abstract`` or ``text`` (title + abstract head);
    flags are ``title_only``, ``has_abstract``, ``year_before_min``,
    ``no_year``.
    """

    TOKEN = re.compile(r"\s*(\(|\)|&|\||!|[A-Za-z_][A-Za-z0-9_:\-]*)")

    def __init__(self, text: str):
        self.tokens = [m.group(1) for m in self.TOKEN.finditer(text)]
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        tok = self.peek()
        if tok is None:
            raise ConfigError("unexpected end of rule expression")
        self.pos += 1
        return tok

    def parse(self):
        node = self.expr()
        if self.peek() is not None:
            raise ConfigError(f"unexpected token {self.peek()!r} in rule")
        return node

    def expr(self):
        node = self.and_()
        while self.peek() == "|":
            self.take()
            node = ("or", node, self.and_())
        return node

    def and_(self):
        node = self.not_()
        while self.peek() == "&":
            self.take()
            node = ("and", node, self.not_())
        return node

    def not_(self):
        if self.peek() == "!":
            self.take()
            return ("not", self.not_())
        return self.atom()

    def atom(self):
        tok = self.take()
        if tok == "(":
            node = self.expr()
            if self.take() != ")":
                raise ConfigError("missing ')' in rule")
            return node
        if tok in ("&", "|", ")", "!"):
            raise ConfigError(f"unexpected {tok!r} in rule")
        if ":" in tok:
            fld, key = tok.split(":", 1)
            if fld not in ("title", "abstract", "text"):
                raise ConfigError(f"unknown field {fld!r} in rule")
            return ("match", fld, key)
        if tok in ("title_only", "has_abstract", "year_before_min", "no_year", "always"):
            return ("flag", tok)
        raise ConfigError(f"unknown token {tok!r} in rule")


def _eval(node, ctx: dict[str, Any], patterns: dict[str, re.Pattern]) -> bool:
    kind = node[0]
    if kind == "or":
        return _eval(node[1], ctx, patterns) or _eval(node[2], ctx, patterns)
    if kind == "and":
        return _eval(node[1], ctx, patterns) and _eval(node[2], ctx, patterns)
    if kind == "not":
        return not _eval(node[1], ctx, patterns)
    if kind == "flag":
        return bool(ctx.get(node[1], False))
    if kind == "match":
        pat = patterns.get(node[2])
        if pat is None:
            raise ConfigError(f"rule refers to unknown pattern {node[2]!r}")
        return bool(pat.search(ctx[node[1]] or ""))
    raise ConfigError(f"bad node {node!r}")


@dataclass
class Rule:
    condition: str
    decision: str
    code: str = ""
    reason: str = ""
    evidence: list[str] = field(default_factory=list)
    _ast: Any = None

    def compile(self) -> "Rule":
        self._ast = _Parser(self.condition or "always").parse()
        return self


# --------------------------------------------------------------------------
# Config object
# --------------------------------------------------------------------------
@dataclass
class Project:
    root: Path
    data: dict

    # ---- identity -------------------------------------------------------
    @property
    def name(self) -> str:
        return self.data.get("name") or self.root.name

    @property
    def slug(self) -> str:
        return self.data.get("slug") or self.root.name

    @property
    def frozen(self) -> bool:
        return bool(self.data.get("frozen"))

    @property
    def population_label(self) -> str:
        return self.data.get("population_label") or "study setting"

    @property
    def record_prefix(self) -> str:
        return self.data.get("record_prefix") or "R"

    @property
    def supplementary_prefix(self) -> str:
        return self.data.get("supplementary_prefix") or "S"

    @property
    def contact_email(self) -> str:
        return self.data.get("contact_email") or "reviewer@example.org"

    @property
    def user_agent(self) -> str:
        return f"review-toolkit/{self.slug} (mailto:{self.contact_email})"

    # ---- limits ---------------------------------------------------------
    @property
    def min_year(self) -> int:
        return int((self.data.get("limits") or {}).get("min_year") or 0)

    @property
    def languages(self) -> list[str]:
        return list((self.data.get("limits") or {}).get("languages") or ["en"])

    # ---- files and folders ---------------------------------------------
    @property
    def pdf_dir(self) -> Path:
        return self.root / "pdfs"

    @property
    def pdf_pending(self) -> Path:
        return self.pdf_dir / "01_not_reviewed"

    @property
    def pdf_included(self) -> Path:
        return self.pdf_dir / "02_final_included"

    @property
    def cache_dir(self) -> Path:
        return self.root / "fulltext_cache"

    @property
    def browse_dir(self) -> Path:
        return self.root / "browse"

    @property
    def ui_data(self) -> Path:
        return self.root / "data.json"

    def file(self, name: str) -> Path:
        return self.root / name

    @property
    def zotero_storage(self) -> Path | None:
        raw = (self.data.get("paths") or {}).get("zotero_storage") or ""
        return Path(os.path.expanduser(raw)) if raw else None

    @property
    def download_dirs(self) -> list[Path]:
        raw = (self.data.get("paths") or {}).get("download_dirs") or ["~/Downloads"]
        return [Path(os.path.expanduser(p)) for p in raw]

    @property
    def exports(self) -> list[dict]:
        out = []
        for item in self.data.get("exports") or []:
            path = self.root / item["file"]
            out.append({**item, "path": path})
        return out

    @property
    def abstract_supplements(self) -> list[dict]:
        out = []
        for item in self.data.get("abstract_supplements") or []:
            out.append({**item, "path": self.root / item["file"]})
        return out

    # ---- vocabulary -----------------------------------------------------
    @property
    def patterns(self) -> dict[str, re.Pattern]:
        if not hasattr(self, "_patterns"):
            compiled: dict[str, re.Pattern] = {}
            raw = dict(BUILTIN_PATTERNS)
            raw.update(self.data.get("patterns") or {})
            for key, value in raw.items():
                if not value:
                    compiled[key] = _NEVER
                    continue
                try:
                    compiled[key] = re.compile(value, re.I)
                except re.error as exc:
                    raise ConfigError(f"pattern {key!r} does not compile: {exc}") from exc
            self._patterns = compiled
        return self._patterns

    def rx(self, key: str) -> re.Pattern:
        pat = self.patterns.get(key)
        if pat is None:
            return _NEVER
        return pat

    # ---- screening rules -----------------------------------------------
    @property
    def screening_rules(self) -> list[Rule]:
        if not hasattr(self, "_rules"):
            rules = []
            for item in self.data.get("screening_rules") or []:
                rules.append(
                    Rule(
                        condition=item.get("if", "always"),
                        decision=item["decision"],
                        code=item.get("code", ""),
                        reason=item.get("reason", ""),
                        evidence=list(item.get("evidence") or []),
                    ).compile()
                )
            if not rules or rules[-1].condition != "always":
                rules.append(Rule("always", "Maybe", "needs_abstract", "No rule matched").compile())
            self._rules = rules
        return self._rules

    def screen(self, title: str, abstract: str, year: str) -> tuple[str, str, str]:
        """Apply the ordered rules; return (decision, code, reason)."""
        abstract = (abstract or "").strip()
        yr = None
        try:
            yr = int(re.search(r"\d{4}", year or "").group(0))
        except Exception:  # noqa: BLE001
            yr = None
        ctx = {
            "title": title or "",
            "abstract": abstract,
            "text": f"{title} {abstract[:800]}",
            "title_only": not abstract,
            "has_abstract": bool(abstract),
            "year_before_min": bool(yr and self.min_year and yr < self.min_year),
            "no_year": yr is None,
            "always": True,
        }
        for rule in self.screening_rules:
            if _eval(rule._ast, ctx, self.patterns):
                reason = rule.reason.format(year=year or "?", min_year=self.min_year)
                return rule.decision, rule.code, reason
        return "Maybe", "needs_abstract", "No rule matched"

    # ---- taxonomy -------------------------------------------------------
    @property
    def taxonomy(self) -> dict:
        return self.data.get("taxonomy") or {}

    @property
    def domains(self) -> list[dict]:
        return list(self.taxonomy.get("domains") or [])

    @property
    def domain_names(self) -> list[str]:
        return [d["name"] for d in self.domains]

    @property
    def default_domain(self) -> str:
        return self.taxonomy.get("default_domain") or "Other"

    @property
    def domain_folder(self) -> dict[str, str]:
        out = {}
        for d in self.domains:
            out[d["name"]] = d.get("folder") or re.sub(r"[^a-z0-9]+", "_", d["name"].lower()).strip("_")
        out.setdefault(self.default_domain, re.sub(r"[^a-z0-9]+", "_", self.default_domain.lower()).strip("_"))
        return out

    @property
    def tiers(self) -> list[dict]:
        return list(self.taxonomy.get("tiers") or [])

    @property
    def tier_names(self) -> list[str]:
        return [t["name"] for t in self.tiers]

    @property
    def default_tier(self) -> str:
        return self.taxonomy.get("default_tier") or (self.tier_names[-1] if self.tier_names else "Other")

    @property
    def operational_tiers(self) -> list[str]:
        return list(self.taxonomy.get("operational_tiers") or [])

    @property
    def saturated_domains(self) -> list[str]:
        return list(self.taxonomy.get("saturated_domains") or [])

    @property
    def link_labels(self) -> dict[str, str]:
        return dict(self.taxonomy.get("link_labels") or {
            "implicit": "informational", "explicit": "advisory", "operational": "executive"})

    def tier_label(self, tier: str) -> str:
        for t in self.tiers:
            if t["name"] == tier:
                return t.get("label") or t["name"]
        return tier or self.default_tier

    def tier_folder(self, tier: str) -> str:
        for i, t in enumerate(self.tiers, start=1):
            if t["name"] == tier:
                return t.get("folder") or f"{i:02d}_{re.sub(r'[^A-Za-z0-9]+', '', tier)}"
        return "00_other"

    def categorise(self, title: str, abstract: str) -> tuple[list[str], str]:
        """Draft domain tags and a tier from title + abstract (regex)."""
        text = f"{title} {abstract}"
        domains = [d["name"] for d in self.domains if d.get("pattern") and re.search(d["pattern"], text, re.I)]
        if not domains:
            domains = [self.default_domain]
        tier = self.default_tier
        for t in self.tiers:
            if t.get("pattern") and re.search(t["pattern"], text, re.I):
                tier = t["name"]
                break
        return domains, tier

    # ---- misc -----------------------------------------------------------
    @property
    def exclusion_codes(self) -> list[str]:
        return list(self.data.get("exclusion_codes") or [])

    @property
    def contested_ids(self) -> set[str]:
        return set(self.data.get("contested_ids") or [])

    @property
    def completeness_queries(self) -> list[str]:
        return list(self.data.get("completeness_queries") or [])

    @property
    def ui(self) -> dict:
        return self.data.get("ui") or {}

    # ---- persistence ----------------------------------------------------
    def save(self) -> None:
        (self.root / "project.json").write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        for attr in ("_patterns", "_rules"):
            if hasattr(self, attr):
                delattr(self, attr)

    def ensure_dirs(self) -> None:
        for p in (self.root / "exports", self.pdf_pending, self.pdf_included, self.cache_dir):
            p.mkdir(parents=True, exist_ok=True)

    def guard_writable(self) -> None:
        if self.frozen:
            raise ConfigError(
                f"Project {self.slug!r} is frozen (project.json: frozen=true); "
                "refusing to write. Copy it to a new project to work on it."
            )

    def public(self) -> dict:
        """JSON-safe view for the interface."""
        try:
            display = self.root.resolve().relative_to(REPO_DIR.resolve()).as_posix()
        except ValueError:
            display = self.root.as_posix()
        return {
            **self.data,
            "root": str(self.root),
            "root_display": display,
            "domain_names": self.domain_names,
            "tier_names": self.tier_names,
            "default_domain": self.default_domain,
            "default_tier": self.default_tier,
        }


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------
def _pop_cli_project() -> str | None:
    argv = sys.argv
    for i, arg in enumerate(argv):
        if arg == "--project" and i + 1 < len(argv):
            value = argv[i + 1]
            del argv[i : i + 2]
            return value
        if arg.startswith("--project="):
            del argv[i]
            return arg.split("=", 1)[1]
    return None


# Remove --project from argv as soon as this module is imported, so scripts
# that parse their own arguments never see it.
_CLI_PROJECT = _pop_cli_project()


def find_project_dir(explicit: str | Path | None = None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    if _CLI_PROJECT:
        candidates.append(Path(_CLI_PROJECT))
    env = os.environ.get("REVIEW_PROJECT")
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd())
    for cand in candidates:
        cand = cand.expanduser()
        if (cand / "project.json").is_file():
            return cand.resolve()
        # allow a project slug relative to the repo's projects folder
        alt = REPO_DIR / "projects" / str(cand)
        if (alt / "project.json").is_file():
            return alt.resolve()
    raise ConfigError(
        "No project found. Pass --project <dir>, set REVIEW_PROJECT, or run "
        "from a folder containing project.json."
    )


def load_project(explicit: str | Path | None = None) -> Project:
    root = find_project_dir(explicit)
    try:
        data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{root / 'project.json'} is not valid JSON: {exc}") from exc
    proj = Project(root=root, data=data)
    proj.patterns  # compile early so errors surface at start-up
    proj.screening_rules
    return proj


def validate(proj: Project) -> list[str]:
    """Return human-readable problems (empty list = fine)."""
    problems: list[str] = []
    if not proj.data.get("name"):
        problems.append("name is empty")
    if not proj.exports:
        problems.append("no exports listed")
    for item in proj.exports:
        if not item["path"].is_file():
            problems.append(f"export file missing: {item['file']}")
        if item.get("format") not in ("bibtex", "ieee_csv", "csv"):
            problems.append(f"export {item['file']}: unknown format {item.get('format')!r}")
    for key in ("population", "technology"):
        if proj.rx(key) is _NEVER:
            problems.append(f"pattern {key!r} is empty; screening rules will not fire")
    try:
        proj.screening_rules
    except ConfigError as exc:
        problems.append(str(exc))
    return problems


# Lazily created singleton for scripts: ``from project_config import CFG``.
class _Lazy:
    _proj: Project | None = None

    def __getattr__(self, item):
        if self._proj is None:
            object.__setattr__(self, "_proj", load_project())
        return getattr(self._proj, item)


CFG = _Lazy()
