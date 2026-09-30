/* Full-text corpus audit UI */
const $ = (sel) => document.querySelector(sel);

const SERIOUS_FLAG =
  /^(tier_mismatch|domain_mismatch|coupling_violation|weak_operational|unreadable)/;

const state = {
  data: null,
  decisions: {}, // record_id -> row
  flag: "mismatches",
  review: "undecided",
  tier: "all",
  domain: "all",
  flagtype: "all",
  query: "",
  sort: "flags",
  toastTimer: null,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function linkLabel(link) {
  return (
    {
      operational: "Executive (operational)",
      explicit: "Advisory (explicit)",
      implicit: "Informational (implicit)",
      none: "No clear link",
    }[link] || link
  );
}

function toast(message) {
  let el = $("#audit-toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "audit-toast";
    el.className = "audit-toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}

function hasSeriousMismatch(r) {
  return (r.flags || []).some((f) => SERIOUS_FLAG.test(f));
}

function decisionFor(recordId) {
  return (state.decisions[recordId] || {}).decision || "";
}

function filtered() {
  const q = state.query.trim().toLowerCase();
  let rows = state.data.records.slice();

  rows = rows.filter((r) => {
    const decision = decisionFor(r.record_id);
    if (state.flag === "flagged" && !r.flags.length) return false;
    if (state.flag === "mismatches" && !hasSeriousMismatch(r)) return false;
    if (state.flag === "clean" && r.flags.length) return false;
    if (state.flag === "cited" && !r.cited_in_manuscript) return false;
    if (state.flag === "uncited" && r.cited_in_manuscript) return false;

    if (state.review === "undecided" && decision) return false;
    if (state.review === "change" && decision !== "change") return false;
    if (state.review === "keep" && decision !== "keep") return false;
    if (state.review === "decided" && !decision) return false;

    if (state.tier !== "all" && r.tier !== state.tier) return false;
    if (state.domain !== "all" && r.primary_domain !== state.domain) return false;
    if (state.flagtype !== "all") {
      const hit = r.flags.some((f) => f.split(":")[0] === state.flagtype);
      if (!hit) return false;
    }
    if (!q) return true;
    const blob = [
      r.record_id,
      r.title,
      r.authors,
      r.summary,
      ...(r.quotes || []).map((x) => x.quote),
      ...(r.flags || []),
      ...(r.manuscript_citations || []).map((c) => c.context),
    ]
      .join(" ")
      .toLowerCase();
    return blob.includes(q);
  });

  rows.sort((a, b) => {
    if (state.sort === "flags") {
      return b.flag_count - a.flag_count || a.record_id.localeCompare(b.record_id);
    }
    if (state.sort === "cited") {
      return (
        Number(b.cited_in_manuscript) - Number(a.cited_in_manuscript) ||
        a.record_id.localeCompare(b.record_id)
      );
    }
    if (state.sort === "domain") {
      return (
        (a.primary_domain || "").localeCompare(b.primary_domain || "") ||
        a.record_id.localeCompare(b.record_id)
      );
    }
    if (state.sort === "tier") {
      return (a.tier || "").localeCompare(b.tier || "") || a.record_id.localeCompare(b.record_id);
    }
    return a.record_id.localeCompare(b.record_id);
  });
  return rows;
}

function decisionStats() {
  const mismatches = state.data.records.filter(hasSeriousMismatch);
  let change = 0;
  let keep = 0;
  let undecided = 0;
  for (const r of mismatches) {
    const d = decisionFor(r.record_id);
    if (d === "change") change += 1;
    else if (d === "keep") keep += 1;
    else undecided += 1;
  }
  return { total: mismatches.length, change, keep, undecided };
}

function renderOverview() {
  const m = state.data.meta;
  const ds = decisionStats();
  $("#overview").innerHTML = `
    <div class="audit-chip"><b>${m.corpus_size}</b><span>PDFs read</span></div>
    <div class="audit-chip"><b>${ds.total}</b><span>mismatches</span></div>
    <div class="audit-chip"><b>${ds.undecided}</b><span>undecided</span></div>
    <div class="audit-chip"><b>${ds.change}</b><span>flagged to change</span></div>
    <div class="audit-chip"><b>${ds.keep}</b><span>kept as charted</span></div>
    <div class="audit-chip"><b>${m.cited_in_manuscript}</b><span>cited in manuscript</span></div>
  `;
  $("#stat-total").textContent = m.corpus_size;
  $("#stat-flags").textContent = ds.total;
  $("#stat-cited").textContent = m.cited_in_manuscript;
  $("#stat-ok").textContent = ds.keep;
  $("#lead").textContent = `Generated ${m.generated_at}. ${m.note}`;
  $("#meta-note").textContent = m.refresh_pdfs
    ? "Text source: fresh PDF extract for every paper."
    : "Text source: full PDF extract cache (page-separated).";
}

function fillDomains() {
  const tiers=[...new Set(state.data.records.map(r=>r.tier).filter(Boolean))].sort();
  $("#filter-tier").innerHTML='<option value="all">All tiers</option>'+tiers.map(t=>`<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join('');
  $("#filter-tier").value=state.tier;

  const select = $("#filter-domain");
  const domains = [
    ...new Set(state.data.records.map((r) => r.primary_domain).filter(Boolean)),
  ].sort();
  select.innerHTML =
    `<option value="all">All domains</option>` +
    domains.map((d) => `<option value="${escapeHtml(d)}">${escapeHtml(d)}</option>`).join("");
  select.value = state.domain;
}

function fillFlagTypes() {
  const select = $("#filter-flagtype");
  const types = Object.keys(state.data.meta.flag_counts || {}).sort();
  select.innerHTML =
    `<option value="all">Any flag type</option>` +
    types
      .map(
        (t) =>
          `<option value="${escapeHtml(t)}">${escapeHtml(t)} (${state.data.meta.flag_counts[t]})</option>`
      )
      .join("");
  select.value = state.flagtype;
}

function decisionBadge(decision) {
  if (decision === "change") {
    return `<span class="badge decision-change">change charting</span>`;
  }
  if (decision === "keep") {
    return `<span class="badge decision-keep">keep as charted</span>`;
  }
  return `<span class="badge decision-open">undecided</span>`;
}

function actionBar(r) {
  if (!hasSeriousMismatch(r)) return "";
  const decision = decisionFor(r.record_id);
  return `
    <div class="audit-actions" data-actions="${escapeHtml(r.record_id)}">
      <div class="audit-section-label">Mismatch review</div>
      <p class="suggest">
        Confirm → mark for charting change · Discard → keep current labels.
      </p>
      <div class="action-btns">
        <button type="button" class="btn-change ${decision === "change" ? "active" : ""}" data-audit-decide="change" data-rid="${escapeHtml(r.record_id)}">
          Confirm mismatch · change
        </button>
        <button type="button" class="btn-keep ${decision === "keep" ? "active" : ""}" data-audit-decide="keep" data-rid="${escapeHtml(r.record_id)}">
          Discard · keep as charted
        </button>
        ${
          decision
            ? `<button type="button" class="secondary btn-clear" data-audit-decide="" data-rid="${escapeHtml(r.record_id)}">Clear</button>`
            : ""
        }
      </div>
    </div>
  `;
}

function cardHtml(r) {
  const decision = decisionFor(r.record_id);
  const quotes = (r.quotes || [])
    .map(
      (q) => `
      <div class="quote-block">
        <span class="qlabel">${escapeHtml(q.label)}</span>
        <blockquote>“${escapeHtml(q.quote)}”</blockquote>
        <span class="pg">p. ${q.page}${q.match ? ` · matched “${escapeHtml(q.match)}”` : ""}</span>
      </div>`
    )
    .join("");

  const cites = (r.manuscript_citations || [])
    .map(
      (c) => `
      <div class="cite-block">
        <div><code>${escapeHtml(c.cite_key)}</code> · ${escapeHtml(c.chapter)}</div>
        <div>${escapeHtml(c.context)}</div>
      </div>`
    )
    .join("");

  const flags =
    r.flags && r.flags.length
      ? `<ul class="flag-list">${r.flags.map((f) => `<li>${escapeHtml(f)}</li>`).join("")}</ul>`
      : `<p class="suggest">No automatic flags.</p>`;

  const suggestBits = [];
  if (r.suggested_tier && r.suggested_tier !== r.tier) {
    suggestBits.push(`text leans tier <b>${escapeHtml(r.suggested_tier)}</b>`);
  }
  if (r.suggested_domain && r.suggested_domain !== r.primary_domain) {
    suggestBits.push(`text leans domain <b>${escapeHtml(r.suggested_domain)}</b>`);
  }
  if (r.suggested_link && r.suggested_link !== r.decision_link) {
    suggestBits.push(`text leans link <b>${escapeHtml(linkLabel(r.suggested_link))}</b>`);
  }

  return `
    <article class="audit-card ${r.flags.length ? "flagged" : ""} ${decision ? `decided-${decision}` : ""}" id="${escapeHtml(r.record_id)}">
      <div class="audit-card-head">
        <span class="rid">${escapeHtml(r.record_id)}</span>
        <h3>${escapeHtml(r.title)}</h3>
      </div>
      <p class="audit-meta">${escapeHtml(r.authors)} (${escapeHtml(r.year)}) · ${escapeHtml(r.pages_extracted)} pages · ${escapeHtml(r.text_source)}</p>
      <div class="badge-row">
        <span class="badge tier-${escapeHtml(r.tier)}">${escapeHtml(r.tier)}</span>
        <span class="badge">${escapeHtml(r.primary_domain || "—")}</span>
        <span class="badge">${escapeHtml(linkLabel(r.decision_link))}</span>
        ${
          r.flags.length
            ? `<span class="badge flag">${r.flags.length} flag${r.flags.length > 1 ? "s" : ""}</span>`
            : `<span class="badge ok">clean</span>`
        }
        ${r.cited_in_manuscript ? `<span class="badge cite">cited in manuscript ×${r.manuscript_citations.length}</span>` : ""}
        ${hasSeriousMismatch(r) ? decisionBadge(decision) : ""}
      </div>
      ${r.summary ? `<p class="audit-summary">${escapeHtml(r.summary)}${r.summary.length >= 400 ? "…" : ""}</p>` : ""}
      ${
        r.sections && r.sections.length
          ? `<p class="sections-inline"><b>Front sections:</b> ${escapeHtml(r.sections.join(" · "))}</p>`
          : ""
      }
      <div class="audit-section-label">Evidence quotes (from full text)</div>
      ${quotes || `<p class="suggest">No automatic quote extracted.</p>`}
      <div class="audit-section-label">Flags &amp; cross-checks</div>
      ${flags}
      ${suggestBits.length ? `<p class="suggest">Auto cross-check: ${suggestBits.join("; ")}.</p>` : ""}
      ${actionBar(r)}
      ${
        cites
          ? `<div class="audit-section-label">Manuscript citations</div>${cites}`
          : `<div class="audit-section-label">Manuscript citations</div><p class="suggest">Not cited in the manuscript (by DOI match; pass --bib and --tex-dir to build_fulltext_audit.py).</p>`
      }
    </article>
  `;
}

function render() {
  const rows = filtered();
  const ds = decisionStats();
  $("#count").textContent = `Showing ${rows.length} of ${state.data.records.length} · mismatches ${ds.undecided} undecided / ${ds.change} change / ${ds.keep} keep`;
  $("#list").innerHTML =
    rows.map(cardHtml).join("") || `<p class="suggest">No papers match these filters.</p>`;
  renderOverview();
}

async function saveDecision(recordId, decision) {
  const record = state.data.records.find((r) => r.record_id === recordId);
  if (!record) return;
  const payload = {
    record_id: recordId,
    decision,
    charted_tier: record.tier,
    charted_domain: record.primary_domain,
    charted_link: record.decision_link,
    suggested_tier: record.suggested_tier,
    suggested_domain: record.suggested_domain,
    suggested_link: record.suggested_link,
    flags: (record.flags || []).join("; "),
  };
  try {
    const res = await fetch("/api/save-audit-decision", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    if (decision) {
      state.decisions[recordId] = data.row;
    } else {
      delete state.decisions[recordId];
    }
    toast(
      decision === "change"
        ? `${recordId}: flagged to change`
        : decision === "keep"
          ? `${recordId}: keep as charted`
          : `${recordId}: decision cleared`
    );
    render();
  } catch (error) {
    console.error(error);
    toast("Could not save decision — is serve.py running?");
  }
}

function exportFlagged() {
  const rows = state.data.records.filter((r) => r.flags.length);
  const header = [
    "record_id",
    "review_decision",
    "tier",
    "primary_domain",
    "decision_link",
    "suggested_tier",
    "suggested_domain",
    "suggested_link",
    "flags",
    "title",
  ];
  const lines = [header.join(",")];
  for (const r of rows) {
    const vals = [
      r.record_id,
      decisionFor(r.record_id),
      r.tier,
      r.primary_domain,
      r.decision_link,
      r.suggested_tier,
      r.suggested_domain,
      r.suggested_link,
      r.flags.join("; "),
      r.title,
    ].map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`);
    lines.push(vals.join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "fulltext_audit_flags_export.csv";
  a.click();
}

async function boot() {
  const [auditRes, decRes] = await Promise.all([
    fetch("audit_data.json?v=" + Date.now()),
    fetch("/api/audit-decisions"),
  ]);
  if (!auditRes.ok) {
    $("#lead").textContent =
      "audit_data.json missing. Run: python build_fulltext_audit.py";
    return;
  }
  state.data = await auditRes.json();
  if (decRes.ok) {
    const payload = await decRes.json();
    state.decisions = payload.decisions || {};
  }
  renderOverview();
  fillDomains();
  fillFlagTypes();
  render();
}

$("#filter-flag").addEventListener("change", (e) => {
  state.flag = e.target.value;
  render();
});
$("#filter-review").addEventListener("change", (e) => {
  state.review = e.target.value;
  render();
});
$("#filter-tier").addEventListener("change", (e) => {
  state.tier = e.target.value;
  render();
});
$("#filter-domain").addEventListener("change", (e) => {
  state.domain = e.target.value;
  render();
});
$("#filter-flagtype").addEventListener("change", (e) => {
  state.flagtype = e.target.value;
  render();
});
$("#search").addEventListener("input", (e) => {
  state.query = e.target.value;
  render();
});
$("#sort").addEventListener("change", (e) => {
  state.sort = e.target.value;
  render();
});
$("#btn-export").addEventListener("click", exportFlagged);

$("#list").addEventListener("click", (e) => {
  const btn = e.target.closest("[data-audit-decide]");
  if (!btn) return;
  const rid = btn.getAttribute("data-rid");
  const decision = btn.getAttribute("data-audit-decide") || "";
  saveDecision(rid, decision);
});

boot();
