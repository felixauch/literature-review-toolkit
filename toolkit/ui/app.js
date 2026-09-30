/* Title screening UI */
const state = {
  records: [],
  codes: [],
  index: 0,
  filterPass: "A1_clear",
  filterStatus: "undecided",
  query: "",
  view: "screen",
  reportDomain: "all",
  reportTier: "all",
  reportRecommendation: "all",
  reportEvidence: "all",
  reportQuery: "",
  corpusPdfFilter: "all",
  corpusDomain: "all",
  corpusQuery: "",
  assessBand: "all",
  assessLink: "all",
  assessDomain: "all",
  assessTier: "all",
  assessCandidates: false,
  assessSort: "relevance-desc",
  assessQuery: "",
  supplementaryDomain: "all",
  supplementaryTier: "all",
  supplementaryLink: "all",
  supplementaryDecision: "queue",
  supplementarySort: "decision",
  supplementaryQuery: "",
  supplementaryDismissed: new Set(),
  categorizationDomain: "all",
  categorizationTier: "all",
  categorizationLink: "all",
  categorizationQueue: "queue",
  categorizationSort: "record",
  categorizationQuery: "",
  categorizationDismissed: new Set(),
  doiCheckQuery: "",
};

const SUPP_DISMISSED_KEY = "rt_supplementary_dismissed_v1";
const CAT_DISMISSED_KEY = "rt_categorization_dismissed_v1";
const DOI_HISTORY_KEY = "rt_doi_check_history_v1";

let DOMAIN_OPTIONS = [];
let TIER_OPTIONS = [];
let OPERATIONAL_TIERS = [];
let DEFAULT_TIER = "";
let TIER_LABELS = {};
let PROJECT_SLUG = "project";
function tierHeaderCells() { return TIER_OPTIONS.map((t) => `<th>${escapeHtml(t)}</th>`).join(""); }
function tierCountSpans(countFn) {
  const cls = ["high", "medium", "low", "high", "medium", "low"];
  return TIER_OPTIONS.map((t, i) => `<span class="band-count ${cls[i % cls.length]}"><strong>${countFn(t)}</strong> ${escapeHtml(t)}</span>`).join("\n        ");
}
function applyTaxonomy(meta) {
  const tax = meta.taxonomy || {};
  DOMAIN_OPTIONS = tax.domains || [];
  TIER_OPTIONS = tax.tiers || [];
  OPERATIONAL_TIERS = tax.operational_tiers || [];
  DEFAULT_TIER = tax.default_tier || (TIER_OPTIONS[TIER_OPTIONS.length - 1] || "");
  TIER_LABELS = tax.tier_labels || {};
  PROJECT_SLUG = meta.project_slug || "project";
  if (meta.project_name) document.title = `${meta.ui_title || "Screening"} — ${meta.project_name}`;
  for (const id of ["supplementary-tier", "categorization-tier"]) {
    const sel = document.getElementById(id);
    if (sel && sel.options.length <= 1) {
      for (const tier of TIER_OPTIONS) { const o = document.createElement("option"); o.value = tier; o.textContent = tier; sel.appendChild(o); }
    }
  }
  const h1 = document.querySelector("aside h1");
  if (h1 && meta.ui_title) h1.textContent = meta.ui_title;
  const sub = document.querySelector("aside .sub");
  if (sub && meta.ui_subtitle) sub.innerHTML = `${escapeHtml(meta.ui_subtitle)}<br />Project: <b>${escapeHtml(meta.project_name || "")}</b>${meta.frozen ? " (frozen, read-only)" : ""}`;
}

function loadSupplementaryDismissed() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(SUPP_DISMISSED_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveSupplementaryDismissed() {
  sessionStorage.setItem(
    SUPP_DISMISSED_KEY,
    JSON.stringify([...state.supplementaryDismissed])
  );
}

function dismissSupplementaryRecord(recordId) {
  state.supplementaryDismissed.add(recordId);
  saveSupplementaryDismissed();
}

function resetSupplementaryQueue() {
  state.supplementaryDismissed.clear();
  saveSupplementaryDismissed();
}

function loadCategorizationDismissed() {
  try {
    return new Set(JSON.parse(sessionStorage.getItem(CAT_DISMISSED_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveCategorizationDismissed() {
  sessionStorage.setItem(
    CAT_DISMISSED_KEY,
    JSON.stringify([...state.categorizationDismissed])
  );
}

function resetCategorizationQueue() {
  state.categorizationDismissed.clear();
  saveCategorizationDismissed();
}

const $ = (sel) => document.querySelector(sel);

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 1600);
}

function storageKey() {
  return `${PROJECT_SLUG}_title_screening_v3`;
}

function loadLocal() {
  try {
    return JSON.parse(localStorage.getItem(storageKey()) || "{}");
  } catch {
    return {};
  }
}

function saveLocal() {
  const map = {};
  for (const r of state.records) {
    if (r.human_decision || r.human_notes || r.exclusion_code) {
      map[r.record_id] = {
        human_decision: r.human_decision,
        human_notes: r.human_notes,
        exclusion_code: r.exclusion_code,
      };
    }
  }
  localStorage.setItem(storageKey(), JSON.stringify(map));
}

function syncPass(r) {
  // Human Maybe always lives in C (abstract / revisit queue)
  if (r.human_decision === "Maybe") {
    r.pass = "C_maybe";
  } else if (!r.human_decision && r.backcheck_batch) {
    r.pass =
      {
        Include: "D1_backcheck_include",
        Exclude: "D2_backcheck_exclude",
        Maybe: "D3_backcheck_uncertain",
      }[r.backcheck_decision] || "D3_backcheck_uncertain";
  } else {
    r.pass = r.ai_pass || r.pass;
  }
}

function applyLocal(records) {
  const map = loadLocal();
  for (const r of records) {
    if (!r.ai_pass) r.ai_pass = r.pass;
    const saved = map[r.record_id];
    if (!saved) {
      syncPass(r);
      continue;
    }
    if (saved.human_decision) r.human_decision = saved.human_decision;
    if (saved.human_notes != null) r.human_notes = saved.human_notes;
    if (saved.exclusion_code != null) r.exclusion_code = saved.exclusion_code;
    syncPass(r);
  }
}

function filtered() {
  const q = state.query.trim().toLowerCase();
  return state.records.filter((r) => {
    if (state.filterPass !== "all" && r.pass !== state.filterPass) return false;
    const decided = Boolean(r.human_decision);
    if (state.filterStatus === "undecided" && decided) return false;
    if (state.filterStatus === "decided" && !decided) return false;
    if (state.filterStatus === "Include" && r.human_decision !== "Include")
      return false;
    if (state.filterStatus === "Maybe" && r.human_decision !== "Maybe")
      return false;
    if (state.filterStatus === "Exclude" && r.human_decision !== "Exclude")
      return false;
    if (!q) return true;
    return (
      r.title.toLowerCase().includes(q) ||
      r.record_id.toLowerCase().includes(q) ||
      (r.authors || "").toLowerCase().includes(q)
    );
  });
}

function counts() {
  const total = state.records.length;
  let decided = 0;
  let include = 0;
  let maybe = 0;
  let exclude = 0;
  for (const r of state.records) {
    if (!r.human_decision) continue;
    decided += 1;
    if (r.human_decision === "Include") include += 1;
    else if (r.human_decision === "Maybe") maybe += 1;
    else if (r.human_decision === "Exclude") exclude += 1;
  }
  return { total, decided, include, maybe, exclude, left: total - decided };
}

function updateSidebar() {
  const c = counts();
  $("#stat-total").textContent = c.total;
  $("#stat-left").textContent = c.left;
  $("#stat-include").textContent = c.include;
  $("#stat-maybe").textContent = c.maybe;
  $("#stat-exclude").textContent = c.exclude;
  $("#stat-decided").textContent = c.decided;
  const pct = c.total ? Math.round((c.decided / c.total) * 100) : 0;
  $("#progress-bar").style.width = `${pct}%`;
  $("#progress-label").textContent = `${pct}% decided`;
}

function currentList() {
  return filtered();
}

function currentRecord() {
  const list = currentList();
  if (!list.length) return null;
  if (state.index >= list.length) state.index = list.length - 1;
  if (state.index < 0) state.index = 0;
  return list[state.index];
}

function render() {
  updateSidebar();
  $("#screen-view").hidden = state.view !== "screen";
  $("#report-view").hidden = state.view !== "report";
  $("#corpus-view").hidden = state.view !== "corpus";
  $("#assess-view").hidden = state.view !== "assess";
  $("#supplementary-view").hidden = state.view !== "supplementary";
  $("#categorization-view").hidden = state.view !== "categorization";
  $("#doi-check-view").hidden = state.view !== "doi-check";
  $("#mode-report").classList.toggle("active", state.view === "report");
  $("#mode-corpus").classList.toggle("active", state.view === "corpus");
  $("#mode-assess").classList.toggle("active", state.view === "assess");
  $("#mode-supplementary").classList.toggle("active", state.view === "supplementary");
  $("#mode-categorization").classList.toggle("active", state.view === "categorization");
  $("#mode-doi-check").classList.toggle("active", state.view === "doi-check");
  if (state.view === "doi-check") {
    renderDoiCheck();
    return;
  }
  if (state.view === "categorization") {
    renderCategorization();
    return;
  }
  if (state.view === "supplementary") {
    renderSupplementary();
    return;
  }
  if (state.view === "assess") {
    renderAssess();
    return;
  }
  if (state.view === "report") {
    renderReport();
    return;
  }
  if (state.view === "corpus") {
    renderCorpus();
    return;
  }
  renderReviewList();
  const review = isReviewMode();
  $("#mode-screen").classList.toggle("active", !review && state.filterStatus === "undecided");
  $("#mode-review").classList.toggle(
    "active",
    review || state.filterStatus === "decided"
  );
  const list = currentList();
  const r = currentRecord();
  $("#queue-meta").textContent = list.length
    ? `${state.index + 1} / ${list.length} in current filter${review ? " · review mode (redecide OK)" : ""}`
    : "No records in this filter";

  if (!r) {
    $("#card").innerHTML = `<div class="empty">No records match this filter.<br/>Try <b>Review decided</b>, or Status → Decided only / All statuses.</div>`;
    return;
  }

  const isBackcheck = Boolean(r.backcheck_batch && r.backcheck_decision);
  const sug = (isBackcheck ? r.backcheck_decision : r.suggested_decision) || "";
  const sugClass = sug.toLowerCase();
  const humClass = (r.human_decision || "").toLowerCase();
  const reason = (isBackcheck ? r.backcheck_reason : r.screen_reason) || "—";
  const quote = r.evidence_quote || "";
  const suggestedCode = isBackcheck
    ? r.backcheck_exclusion_code
    : r.exclusion_code;
  const codeHint = suggestedCode
    ? `Code: ${suggestedCode}`
    : sug === "Exclude"
      ? "Code: wrong_crop / sensor_only (edit below if needed)"
      : "";
  const recommendationLabel = isBackcheck
    ? "Personalised backcheck"
    : "Script recommendation";
  const similarityContext = isBackcheck
    ? `<div class="ai-banner-reason">
         <strong>Closest reviewed Include:</strong> ${escapeHtml(r.backcheck_nearest_include || "—")}<br>
         <strong>Closest reviewed Exclude:</strong> ${escapeHtml(r.backcheck_nearest_exclude || "—")}
       </div>`
    : "";
  const keyFor = { Include: "1", Maybe: "2", Exclude: "3" };

  function decisionButton(label) {
    const isAi = sug === label;
    const isYou = r.human_decision === label;
    const classes = [
      isYou ? "active" : "",
      isAi ? "ai-pick" : "",
    ]
      .filter(Boolean)
      .join(" ");
    return `
      <button data-d="${label}" class="${classes}">
        <span class="btn-top">
          <span class="btn-label">${label}</span>
          <span class="btn-key">${keyFor[label]}</span>
          ${isAi ? `<span class="ai-tag">${isBackcheck ? "backcheck pick" : "Script suggestion"}</span>` : ""}
        </span>
        ${
          isAi
            ? `<span class="btn-reason">${escapeHtml(reason)}</span>
               ${quote ? `<span class="btn-quote">${escapeHtml(quote)}</span>` : ""}
               ${codeHint ? `<span class="btn-code">${escapeHtml(codeHint)}</span>` : ""}`
            : `<span class="btn-reason muted">Not the script suggestion</span>`
        }
      </button>`;
  }

  const abs = r.has_abstract
    ? `<div class="abstract"><strong>Abstract</strong><br>${escapeHtml(r.abstract || "(empty)")}</div>`
    : `<div class="reason"><em>No abstract in export — decide from title, or leave Maybe for abstract screening.</em></div>`;

  $("#card").innerHTML = `
    <div class="badges">
      <span class="badge">${escapeHtml(r.record_id)}</span>
      <span class="badge">${escapeHtml(r.pass)}</span>
      <span class="badge ${sugClass}">${isBackcheck ? "Backcheck" : "Script"} → ${escapeHtml(sug)}</span>
      ${isBackcheck ? `<span class="badge">${escapeHtml(r.backcheck_confidence || "low")} confidence</span>` : ""}
      ${
        r.human_decision
          ? `<span class="badge ${humClass}">You: ${escapeHtml(r.human_decision)}</span>`
          : `<span class="badge">undecided</span>`
      }
      ${r.has_abstract ? `<span class="badge">has abstract</span>` : ""}
    </div>
    <h2>${escapeHtml(r.title)}</h2>
    <div class="authors">${escapeHtml(r.authors || "—")} · ${escapeHtml(r.year || "?")} · ${escapeHtml(r.sources || "")}</div>

    <div class="ai-banner ${sugClass}">
      <div class="ai-banner-label">${recommendationLabel}</div>
      <div class="ai-banner-decision">${escapeHtml(sug)}</div>
      <div class="ai-banner-reason">${escapeHtml(reason)}</div>
      ${similarityContext}
      ${
        quote
          ? `<blockquote class="ai-banner-quote">${escapeHtml(quote)}</blockquote>`
          : ""
      }
      ${
        suggestedCode
          ? `<div class="ai-banner-code">Suggested code: <strong>${escapeHtml(suggestedCode)}</strong></div>`
          : ""
      }
    </div>

    <div class="decision-row">
      ${decisionButton("Include")}
      ${decisionButton("Maybe")}
      ${decisionButton("Exclude")}
    </div>
    <div class="extras">
      <div>
        <label for="code">Exclusion code</label>
        <select id="code">
          <option value="">—</option>
          ${state.codes
            .map(
              (c) =>
                `<option value="${c}" ${r.exclusion_code === c ? "selected" : ""}>${c}</option>`
            )
            .join("")}
        </select>
      </div>
      <div>
        <label for="notes">Notes</label>
        <textarea id="notes" placeholder="Optional short note">${escapeHtml(r.human_notes || "")}</textarea>
      </div>
    </div>
    <details class="more-details">
      <summary>Abstract &amp; metadata</summary>
      <div class="meta-grid" style="margin-top:0.75rem">
        <div><small>Journal</small>${escapeHtml(r.journal || "—")}</div>
        <div><small>DOI</small>${
          r.doi
            ? `<a href="https://doi.org/${encodeURIComponent(r.doi)}" target="_blank" rel="noopener">${escapeHtml(r.doi)}</a>`
            : "—"
        }</div>
      </div>
      ${abs}
    </details>
    <div class="card-actions">
      ${
        r.human_decision
          ? `<button type="button" id="btn-clear" class="linkish">Clear decision (back to undecided)</button>`
          : ""
      }
    </div>
    <div class="help">
      ${
        review
          ? "<b>Review mode:</b> change Include/Maybe/Exclude anytime · <b>J</b>/<b>K</b> browse · <b>S</b> save"
          : "Press the same number as the <b>script suggestion</b> to accept fast · <b>J</b>/<b>K</b> next/prev · <b>S</b> save · use <b>Review decided</b> to recheck"
      }
    </div>
  `;

  $("#card").querySelectorAll(".decision-row button").forEach((btn) => {
    btn.addEventListener("click", () => decide(btn.dataset.d));
  });
  const clearBtn = $("#btn-clear");
  if (clearBtn) clearBtn.addEventListener("click", clearDecision);
  $("#code").addEventListener("change", (e) => {
    r.exclusion_code = e.target.value;
    saveLocal();
  });
  $("#notes").addEventListener("input", (e) => {
    r.human_notes = e.target.value;
    saveLocal();
  });
}

function escapeHtml(s) {
  return String(s)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function isReviewMode() {
  return state.filterStatus !== "undecided";
}

function decide(decision) {
  const r = currentRecord();
  if (!r) return;
  const id = r.record_id;
  const wasReview = isReviewMode();
  if (!r.ai_pass) r.ai_pass = r.pass;
  r.human_decision = decision;
  if (decision === "Exclude") {
    r.exclusion_code =
      r.backcheck_exclusion_code || r.exclusion_code || guessCode(r);
  }
  syncPass(r);
  saveLocal();

  const list = currentList();
  if (wasReview) {
    // Stay in review queue: prefer same record, else next/prev still in filter
    let idx = list.findIndex((x) => x.record_id === id);
    if (idx < 0) {
      // record left this filter (e.g. Exclude → Include while viewing Excludes)
      idx = Math.min(state.index, Math.max(0, list.length - 1));
    }
    state.index = idx;
  } else {
    // The decided record leaves an "Undecided only" queue. The next record
    // shifts into the same index, so keep that position instead of skipping it.
    state.index = Math.min(state.index, Math.max(0, list.length - 1));
  }
  render();
}

function clearDecision() {
  const r = currentRecord();
  if (!r) return;
  if (!r.ai_pass) r.ai_pass = r.pass;
  r.human_decision = "";
  syncPass(r);
  saveLocal();
  toast(`Cleared ${r.record_id} → undecided`);
  const list = currentList();
  if (!list.length) {
    state.index = 0;
  } else if (state.index >= list.length) {
    state.index = list.length - 1;
  }
  render();
}

function setMode(mode) {
  state.view = "screen";
  if (mode === "review") {
    state.filterStatus = "decided";
    state.filterPass = "all";
  } else {
    state.filterStatus = "undecided";
  }
  $("#filter-status").value = state.filterStatus;
  $("#filter-pass").value = state.filterPass;
  $("#mode-screen").classList.toggle("active", mode === "screen");
  $("#mode-review").classList.toggle("active", mode === "review");
  state.index = 0;
  render();
}

function includedRecords() {
  return state.records.filter((r) => r.human_decision === "Include");
}

function domainsForRecord(r) {
  return r.report_domains?.length
    ? r.report_domains
    : [r.report_domain || "Uncategorised"];
}

function recommendationForRecord(r) {
  return r.fulltext_recommendation || "Needs verification";
}

function finalDecisionForRecord(r) {
  return r.fulltext_final_decision || "";
}

function fillReportSelect(el, values, selected, label) {
  el.innerHTML = [
    `<option value="all">All ${label}</option>`,
    ...values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`),
  ].join("");
  el.value = selected;
}

function renderReport() {
  const records = includedRecords();
  const domains = [...new Set(records.flatMap(domainsForRecord))].sort();
  const tiers = TIER_OPTIONS;
  const recommendations = ["Retain", "Needs verification", "Exclude"];
  const evidence = [...new Set(records.map((r) => r.fulltext_evidence_status || "Metadata / abstract only"))].sort();
  fillReportSelect($("#report-domain"), domains, state.reportDomain, "domains");
  fillReportSelect($("#report-tier"), tiers, state.reportTier, "technology tiers");
  fillReportSelect($("#report-recommendation"), recommendations, state.reportRecommendation, "recommendations");
  fillReportSelect($("#report-evidence"), evidence, state.reportEvidence, "evidence types");

  const matrix = domains
    .map((domain) => {
      const cells = tiers
        .map(
          (tier) =>
            `<td>${records.filter((r) => domainsForRecord(r).includes(domain) && (r.report_tier || DEFAULT_TIER) === tier).length}</td>`
        )
        .join("");
      return `<tr><th>${escapeHtml(domain)}</th>${cells}</tr>`;
    })
    .join("");
  const recommendationCounts = recommendations
    .map((recommendation) => `<span class="recommendation-count ${recommendation.toLowerCase().replaceAll(" ", "-")}"><strong>${records.filter((r) => recommendationForRecord(r) === recommendation).length}</strong> ${escapeHtml(recommendation)}</span>`)
    .join("");
  const oaLinks = records.filter((r) => r.fulltext_oa_url).length;
  const reviewed = records.filter((r) => r.fulltext_reviewed === "yes").length;
  const finalIncludes = records.filter((r) => finalDecisionForRecord(r) === "Include").length;
  const finalExcludes = records.filter((r) => finalDecisionForRecord(r) === "Exclude").length;
  $("#report-summary").innerHTML = `
    <div class="report-total"><strong>${records.length}</strong><span>retained for full-text screening</span></div>
    <div class="matrix-wrap">
      <div class="recommendation-summary">${recommendationCounts}<span class="evidence-count">${oaLinks} OA links found · ${reviewed} local PDF reviewed · final: ${finalIncludes} Include, ${finalExcludes} Exclude</span></div>
      <div class="matrix-note">Domain counts overlap because papers may carry multiple tags.</div>
      <table class="matrix">
        <thead><tr><th>Draft application domain</th>${tierHeaderCells()}</tr></thead>
        <tbody>${matrix}</tbody>
      </table>
    </div>`;

  const q = state.reportQuery.trim().toLowerCase();
  const shown = records.filter((r) => {
    if (state.reportDomain !== "all" && !domainsForRecord(r).includes(state.reportDomain)) return false;
    if (state.reportTier !== "all" && r.report_tier !== state.reportTier) return false;
    if (state.reportRecommendation !== "all" && recommendationForRecord(r) !== state.reportRecommendation) return false;
    if (state.reportEvidence !== "all" && (r.fulltext_evidence_status || "Metadata / abstract only") !== state.reportEvidence) return false;
    return !q || [r.title, r.authors, r.doi, r.journal, r.record_id]
      .some((value) => String(value || "").toLowerCase().includes(q));
  });
  $("#report-count").textContent = `${shown.length} of ${records.length} retained papers shown`;
  $("#report-list").innerHTML = shown
    .map((r) => {
      const recommendation = recommendationForRecord(r);
      const recommendationClass = recommendation.toLowerCase().replaceAll(" ", "-");
      const finalDecision = finalDecisionForRecord(r);
      const doi = r.doi
        ? `<a href="https://doi.org/${encodeURIComponent(r.doi)}" target="_blank" rel="noreferrer">DOI</a>`
        : "—";
      const oa = r.fulltext_oa_url
        ? `<a href="${escapeHtml(r.fulltext_oa_url)}" target="_blank" rel="noreferrer">OA full text</a>`
        : doi;
      const analysisDetail = r.fulltext_analysis_status
        ? `<details class="fulltext-analysis">
            <summary>Automated full-text analysis · ${escapeHtml(r.fulltext_analysis_status)}</summary>
            <p>${escapeHtml(r.fulltext_analysis_evidence || r.fulltext_analysis_error || "No extractable evidence quote was found.")}</p>
            ${r.fulltext_analysis_pages ? `<small>Evidence pages: ${escapeHtml(r.fulltext_analysis_pages)}</small>` : ""}
          </details>`
        : "";
      const finalControls = `
        <div class="final-decision-row">
          <span class="final-label">${finalDecision ? `Final: ${escapeHtml(finalDecision)}` : "Set final full-text decision:"}</span>
          <button type="button" class="final-decision include ${finalDecision === "Include" ? "active" : ""}" data-final-id="${escapeHtml(r.record_id)}" data-final-decision="Include">Include</button>
          <button type="button" class="final-decision exclude ${finalDecision === "Exclude" ? "active" : ""}" data-final-id="${escapeHtml(r.record_id)}" data-final-decision="Exclude">Exclude</button>
        </div>`;
      return `<tr>
        <td><button type="button" class="record-link" data-report-id="${escapeHtml(r.record_id)}">${escapeHtml(r.record_id)}</button></td>
        <td><span class="tag-list">${domainsForRecord(r).map((domain) => `<span class="tag domain">${escapeHtml(domain)}</span>`).join("")}</span></td>
        <td><span class="tag tier">${escapeHtml(r.report_tier || DEFAULT_TIER)}</span></td>
        <td><span class="recommendation ${recommendationClass}">${escapeHtml(recommendation)}</span><br><span class="recommendation-reason">${escapeHtml(r.fulltext_reason || "—")}</span>${analysisDetail}${finalControls}</td>
        <td><strong>${escapeHtml(r.title)}</strong><br><span class="report-authors">${escapeHtml(r.authors || "—")} · ${escapeHtml(r.year || "?")}</span></td>
        <td>${escapeHtml(r.fulltext_evidence_status || "Metadata / abstract only")}<br><span class="recommendation-reason">${escapeHtml(r.fulltext_access_note || "")}</span><br>${oa}</td>
      </tr>`;
    })
    .join("");
  $("#report-list").querySelectorAll("[data-report-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = "screen";
      jumpToId(button.dataset.reportId);
    });
  });
  $("#report-list").querySelectorAll("[data-final-id]").forEach((button) => {
    button.addEventListener("click", () =>
      setFulltextFinalDecision(button.dataset.finalId, button.dataset.finalDecision)
    );
  });
}

async function setFulltextFinalDecision(recordId, decision) {
  const record = state.records.find((r) => r.record_id === recordId);
  if (!record) return;
  if (decision === "Exclude" && state.view !== "supplementary") {
    const message = record.fulltext_local_pdf
      ? `Exclude ${recordId} from the final corpus? Its copied project PDF copy will be deleted. The source file is kept.`
      : `Exclude ${recordId} from the final corpus?`;
    if (!window.confirm(message)) return;
  }
  const previous = record.fulltext_final_decision || "";
  const previousPdf = record.fulltext_local_pdf || "";
  record.fulltext_final_decision = decision;
  if (decision === "Exclude") record.fulltext_local_pdf = "";
  if (state.view === "supplementary") dismissSupplementaryRecord(recordId);
  render();
  try {
    const res = await fetch("/api/save-fulltext", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decisions: [{
          record_id: recordId,
          fulltext_final_decision: decision,
          fulltext_final_notes: record.fulltext_final_notes || "",
        }],
      }),
    });
    if (!res.ok) throw new Error(await res.text());
    toast(`${recordId}: ${decision} · ${supplementaryQueueRemaining()} left`);
  } catch (error) {
    record.fulltext_final_decision = previous;
    record.fulltext_local_pdf = previousPdf;
    if (state.view === "supplementary") {
      state.supplementaryDismissed.delete(recordId);
      saveSupplementaryDismissed();
    }
    render();
    toast("Final decision was not saved");
    console.error(error);
  }
}

/* ---------- Final corpus view ---------- */

function finalCorpusRecords() {
  return state.records.filter((r) => r.fulltext_final_decision === "Include");
}

function suggestedPdfName(r) {
  const slug = (r.title || "paper")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return `${r.record_id}__${slug}.pdf`;
}

function renderCorpus() {
  const records = finalCorpusRecords();
  const withPdf = records.filter((r) => r.fulltext_local_pdf);
  const missingPdf = records.filter((r) => !r.fulltext_local_pdf);

  const domains = [...new Set(records.flatMap(domainsForRecord))].sort();
  fillReportSelect($("#corpus-domain"), domains, state.corpusDomain, "domains");

  $("#corpus-summary").innerHTML = `
    <div class="report-total"><strong>${records.length}</strong><span>papers included after full-text screening</span></div>
    <div class="matrix-wrap">
      <div class="recommendation-summary">
        <span class="recommendation-count retain"><strong>${withPdf.length}</strong> PDF in corpus</span>
        <span class="recommendation-count needs-verification"><strong>${missingPdf.length}</strong> PDF still needed</span>
      </div>
      <div class="matrix-note">
        Missing PDFs: download the paper (DOI / OA link in the table), save it
        with the suggested filename into
        <code>pdfs/02_final_included</code>, then click
        <b>Rescan PDF folder</b>.
      </div>
    </div>`;

  const q = state.corpusQuery.trim().toLowerCase();
  const shown = records.filter((r) => {
    const has = Boolean(r.fulltext_local_pdf);
    if (state.corpusPdfFilter === "has" && !has) return false;
    if (state.corpusPdfFilter === "missing" && has) return false;
    if (state.corpusDomain !== "all" && !domainsForRecord(r).includes(state.corpusDomain)) return false;
    return !q || [r.title, r.authors, r.doi, r.journal, r.record_id]
      .some((value) => String(value || "").toLowerCase().includes(q));
  });
  $("#corpus-count").textContent = `${shown.length} of ${records.length} included papers shown`;

  $("#corpus-list").innerHTML = shown
    .map((r) => {
      const has = Boolean(r.fulltext_local_pdf);
      const doi = r.doi
        ? `<a href="https://doi.org/${encodeURIComponent(r.doi)}" target="_blank" rel="noreferrer">DOI</a>`
        : "";
      const oa = r.fulltext_oa_url
        ? `<a href="${escapeHtml(r.fulltext_oa_url)}" target="_blank" rel="noreferrer">OA full text</a>`
        : "";
      const links = [doi, oa].filter(Boolean).join(" · ") || "—";
      const pdfCell = has
        ? `<span class="pdf-badge has">PDF in corpus</span>
           <div class="pdf-file">${escapeHtml((r.fulltext_local_pdf || "").split("/").pop())}</div>`
        : `<span class="pdf-badge missing">PDF needed</span>
           <div class="pdf-file">Save as:
             <code>${escapeHtml(suggestedPdfName(r))}</code>
             <button type="button" class="copy-name" data-copy-name="${escapeHtml(suggestedPdfName(r))}">Copy</button>
           </div>
           <div class="pdf-links">${links}</div>`;
      return `<tr class="${has ? "" : "corpus-missing-row"}">
        <td><button type="button" class="record-link" data-report-id="${escapeHtml(r.record_id)}">${escapeHtml(r.record_id)}</button></td>
        <td><strong>${escapeHtml(r.title)}</strong><br>
          <span class="report-authors">${escapeHtml(r.authors || "—")} · ${escapeHtml(r.year || "?")} · ${escapeHtml(r.journal || "")}</span></td>
        <td><span class="tag-list">${domainsForRecord(r).map((domain) => `<span class="tag domain">${escapeHtml(domain)}</span>`).join("")}</span>
          <span class="tag tier">${escapeHtml(r.report_tier || DEFAULT_TIER)}</span></td>
        <td>${pdfCell}</td>
        <td><button type="button" class="final-decision exclude" data-corpus-exclude="${escapeHtml(r.record_id)}">Exclude</button></td>
      </tr>`;
    })
    .join("");

  $("#corpus-list").querySelectorAll("[data-report-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = "screen";
      jumpToId(button.dataset.reportId);
    });
  });
  $("#corpus-list").querySelectorAll("[data-corpus-exclude]").forEach((button) => {
    button.addEventListener("click", () =>
      setFulltextFinalDecision(button.dataset.corpusExclude, "Exclude")
    );
  });
  $("#corpus-list").querySelectorAll("[data-copy-name]").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(button.dataset.copyName);
        toast("Filename copied");
      } catch {
        toast("Copy failed — select the name manually");
      }
    });
  });
}

async function rescanCorpusPdfs() {
  const btn = $("#btn-corpus-rescan");
  btn.disabled = true;
  btn.textContent = "Rescanning…";
  try {
    const res = await fetch("/api/rescan-pdfs", { method: "POST" });
    if (!res.ok) throw new Error(await res.text());
    const info = await res.json();
    await reloadData();
    toast(`Rescan: ${info.linked} PDF(s) newly linked · ${info.missing} still missing`);
  } catch (error) {
    toast("Rescan failed — is serve.py running?");
    console.error(error);
  } finally {
    btn.disabled = false;
    btn.textContent = "Rescan PDF folder";
  }
}

async function reloadData() {
  const res = await fetch(`data.json?t=${Date.now()}`);
  const data = await res.json();
  state.records = data.records;
  state.codes = data.meta.exclusion_codes;
  applyTaxonomy(data.meta);
  applyLocal(state.records);
  render();
}

function exportCorpusCsv() {
  const headers = ["record_id", "title", "authors", "year", "journal", "doi", "report_domains", "report_tier", "classification_status", "pdf_status", "fulltext_local_pdf", "fulltext_oa_url"];
  const lines = [headers.join(",")];
  for (const r of finalCorpusRecords()) {
    lines.push(headers.map((header) => {
      const value = header === "classification_status"
        ? "unconfirmed"
        : header === "report_domains"
        ? domainsForRecord(r).join("; ")
        : header === "pdf_status"
          ? (r.fulltext_local_pdf ? "in_corpus" : "missing")
          : (r[header] ?? "");
      return csvEscape(value);
    }).join(","));
  }
  downloadText("screening_corpus_draft.csv", lines.join("\n"));
  toast(`Exported ${lines.length - 1} screened papers; classifications remain unconfirmed here`);
}

/* ---------- Assessment & synthesis view ---------- */

function assessRecords() {
  return state.records.filter(
    (r) => r.fulltext_final_decision === "Include" && r.assess_band
  );
}

function assessDomainsForRecord(r) {
  return r.assess_domains?.length ? r.assess_domains : domainsForRecord(r);
}

function assessPrimaryDomainForRecord(r) {
  return r.assess_primary_domain || assessDomainsForRecord(r)[0] || "Unassigned";
}

const LINK_LABEL = {
  explicit: "Advisory",
  operational: "Executive",
  implicit: "Informational",
  none: "No clear link",
};

function renderAssess() {
  const records = assessRecords();
  const domains = [...new Set(records.flatMap(assessDomainsForRecord))].sort();
  const primaryDomains = [...new Set(records.map(assessPrimaryDomainForRecord))].sort();
  const tiers = TIER_OPTIONS;
  fillReportSelect($("#assess-domain"), domains, state.assessDomain, "domains");
  fillReportSelect($("#assess-tier"), tiers, state.assessTier, "tiers");

  const bandCount = (b) => records.filter((r) => r.assess_band === b).length;
  const linkCount = (l) => records.filter((r) => r.assess_decision_link === l).length;
  const candidates = records.filter((r) => r.assess_exclude_candidate === "yes");

  const matrix = primaryDomains
    .map((domain) => {
      const cells = tiers
        .map(
          (tier) =>
            `<td>${records.filter((r) => assessPrimaryDomainForRecord(r) === domain && (r.assess_tier || DEFAULT_TIER) === tier).length}</td>`
        )
        .join("");
      return `<tr><th>${escapeHtml(domain)}</th>${cells}</tr>`;
    })
    .join("");

  $("#assess-summary").innerHTML = `
    <div class="report-total"><strong>${records.length}</strong><span>assessed included papers</span></div>
    <div class="matrix-wrap">
      <div class="recommendation-summary">
        <span class="band-count high"><strong>${bandCount("High")}</strong> High</span>
        <span class="band-count medium"><strong>${bandCount("Medium")}</strong> Medium</span>
        <span class="band-count low"><strong>${bandCount("Low")}</strong> Low</span>
        <span class="evidence-count">${linkCount("explicit")} explicit · ${linkCount("operational")} operational · ${linkCount("implicit")} implicit · ${linkCount("none")} none · <b>${candidates.length}</b> exclude-candidate${candidates.length === 1 ? "" : "s"}</span>
      </div>
      <div class="matrix-note">The headline matrix uses one primary domain per paper, so its cells sum to the corpus total. Additional validated domains remain visible on each record as coverage tags. Relevance is retained as an internal prioritisation heuristic.</div>
      <table class="matrix">
        <thead><tr><th>Primary management domain</th>${tierHeaderCells()}</tr></thead>
        <tbody>${matrix}</tbody>
      </table>
    </div>`;

  const q = state.assessQuery.trim().toLowerCase();
  let shown = records.filter((r) => {
    if (state.assessBand !== "all" && r.assess_band !== state.assessBand) return false;
    if (state.assessLink !== "all" && r.assess_decision_link !== state.assessLink) return false;
    if (state.assessDomain !== "all" && !assessDomainsForRecord(r).includes(state.assessDomain)) return false;
    if (state.assessTier !== "all" && (r.assess_tier || DEFAULT_TIER) !== state.assessTier) return false;
    if (state.assessCandidates && r.assess_exclude_candidate !== "yes") return false;
    return !q || [r.title, r.authors, r.doi, r.journal, r.record_id]
      .some((value) => String(value || "").toLowerCase().includes(q));
  });
  const relOf = (r) => parseInt(r.assess_relevance || "0", 10);
  if (state.assessSort === "relevance-desc") shown.sort((a, b) => relOf(b) - relOf(a));
  else if (state.assessSort === "relevance-asc") shown.sort((a, b) => relOf(a) - relOf(b));
  else shown.sort((a, b) => a.record_id.localeCompare(b.record_id));

  $("#assess-count").textContent = `${shown.length} of ${records.length} assessed papers shown`;

  $("#assess-list").innerHTML = shown
    .map((r) => {
      const score = relOf(r);
      const band = (r.assess_band || "").toLowerCase();
      const link = r.assess_decision_link || "none";
      const candidate = r.assess_exclude_candidate === "yes";
      const evidence = r.assess_evidence
        ? `<details class="fulltext-analysis"><summary>Evidence excerpt${r.assess_evidence_pages ? ` · p. ${escapeHtml(r.assess_evidence_pages)}` : ""}</summary><p>${escapeHtml(r.assess_evidence)}</p></details>`
        : "";
      const flag = candidate
        ? `<div class="exclude-flag">⚠ Suggest excluding: ${escapeHtml(r.assess_exclude_reason || "low decision relevance")}</div>`
        : "";
      return `<tr class="${candidate ? "assess-candidate-row" : ""}">
        <td><button type="button" class="record-link" data-report-id="${escapeHtml(r.record_id)}">${escapeHtml(r.record_id)}</button></td>
        <td class="relevance-cell">
          <div class="relevance-bar ${band}"><i style="width:${score}%"></i></div>
          <span class="relevance-num ${band}">${score} · ${escapeHtml(r.assess_band || "")}</span>
        </td>
        <td><span class="tag-list"><span class="tag domain"><strong>Primary:</strong> ${escapeHtml(assessPrimaryDomainForRecord(r))}</span>${(r.assess_secondary_domains || []).map((d) => `<span class="tag domain">${escapeHtml(d)}</span>`).join("")}</span>
          <span class="tag tier">${escapeHtml(r.assess_tier || DEFAULT_TIER)}</span></td>
        <td><span class="link-badge ${link}">${escapeHtml(LINK_LABEL[link] || link)}</span></td>
        <td><span class="contrib-type">${escapeHtml(r.assess_contribution_type || "")}</span>
          <div class="use-note">${escapeHtml(r.assess_use || "—")}</div>
          ${evidence}${flag}
          <div class="assess-paper"><strong>${escapeHtml(r.title)}</strong><br><span class="report-authors">${escapeHtml(r.authors || "—")} · ${escapeHtml(r.year || "?")}</span></div></td>
        <td><button type="button" class="final-decision exclude" data-assess-exclude="${escapeHtml(r.record_id)}">Exclude</button></td>
      </tr>`;
    })
    .join("");

  $("#assess-list").querySelectorAll("[data-report-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = "screen";
      jumpToId(button.dataset.reportId);
    });
  });
  $("#assess-list").querySelectorAll("[data-assess-exclude]").forEach((button) => {
    button.addEventListener("click", () =>
      setFulltextFinalDecision(button.dataset.assessExclude, "Exclude")
    );
  });
}

/* ---------- Supplementary (citation-chase) summaries ---------- */

function supplementaryRecords() {
  return state.records.filter((r) => r.search_arm === "citation_chasing");
}

function supplementaryIncludedRecords() {
  return supplementaryRecords().filter((r) => r.fulltext_final_decision === "Include");
}

function supplementaryQueueRemaining() {
  return supplementaryRecords().filter(
    (r) => !state.supplementaryDismissed.has(r.record_id)
  ).length;
}

function finalDecisionLabel(r) {
  return r.fulltext_final_decision || "Pending";
}

function renderSupplementary() {
  const pool = supplementaryRecords();
  const included = supplementaryIncludedRecords();
  const primaryDomains = [
    ...new Set(pool.map(assessPrimaryDomainForRecord)),
  ].sort();
  fillReportSelect(
    $("#supplementary-domain"),
    primaryDomains,
    state.supplementaryDomain,
    "primary domains"
  );

  const tierCount = (records, t) =>
    records.filter((r) => (r.assess_tier || DEFAULT_TIER) === t).length;
  const linkCount = (records, l) =>
    records.filter((r) => r.assess_decision_link === l).length;
  const decisionCount = (decision) =>
    pool.filter((r) => (r.fulltext_final_decision || "") === decision).length;
  const pendingCount = pool.filter((r) => !r.fulltext_final_decision).length;
  const queueRemaining = supplementaryQueueRemaining();

  const matrix = primaryDomains
    .map((domain) => {
      const cells = TIER_OPTIONS
        .map(
          (tier) =>
            `<td>${included.filter((r) => assessPrimaryDomainForRecord(r) === domain && (r.assess_tier || DEFAULT_TIER) === tier).length}</td>`
        )
        .join("");
      return `<tr><th>${escapeHtml(domain)}</th>${cells}</tr>`;
    })
    .join("");

  $("#supplementary-summary").innerHTML = `
    <div class="report-total"><strong>${queueRemaining}</strong><span>remaining in review queue</span></div>
    <div class="matrix-wrap">
      <div class="recommendation-summary">
        <span class="recommendation-count retain"><strong>${decisionCount("Include")}</strong> Include</span>
        <span class="recommendation-count exclude"><strong>${decisionCount("Exclude")}</strong> Exclude</span>
        ${pendingCount ? `<span class="recommendation-count needs-verification"><strong>${pendingCount}</strong> pending</span>` : ""}
        <span class="evidence-count">Current corpus preview: ${included.length} supplementary includes</span>
      </div>
      <div class="matrix-note">Set <b>Include</b> or <b>Exclude</b> on each card below. The matrix preview counts only current Includes. Database-arm papers (${state.records.filter((r) => r.search_arm === "database" && r.fulltext_final_decision === "Include").length} includes) are unchanged here.</div>
      <table class="matrix">
        <thead><tr><th>Primary domain (includes only)</th>${tierHeaderCells()}</tr></thead>
        <tbody>${matrix}</tbody>
      </table>
      <div class="recommendation-summary" style="margin-top:0.65rem">
        ${tierCountSpans((t) => tierCount(included, t))}
        <span class="evidence-count">${linkCount(included, "explicit")} advisory · ${linkCount(included, "operational")} executive · ${linkCount(included, "implicit")} informational</span>
      </div>
    </div>`;

  const q = state.supplementaryQuery.trim().toLowerCase();
  let shown = pool.filter((r) => {
    if (
      state.supplementaryDecision === "queue" &&
      state.supplementaryDismissed.has(r.record_id)
    ) {
      return false;
    }
    const finalDecision = r.fulltext_final_decision || "";
    if (state.supplementaryDecision === "Include" && finalDecision !== "Include") {
      return false;
    }
    if (state.supplementaryDecision === "Exclude" && finalDecision !== "Exclude") {
      return false;
    }
    if (state.supplementaryDecision === "pending" && finalDecision) {
      return false;
    }
    if (
      state.supplementaryDomain !== "all" &&
      assessPrimaryDomainForRecord(r) !== state.supplementaryDomain
    ) {
      return false;
    }
    if (
      state.supplementaryTier !== "all" &&
      (r.assess_tier || DEFAULT_TIER) !== state.supplementaryTier
    ) {
      return false;
    }
    if (
      state.supplementaryLink !== "all" &&
      r.assess_decision_link !== state.supplementaryLink
    ) {
      return false;
    }
    return (
      !q ||
      [
        r.title,
        r.authors,
        r.doi,
        r.record_id,
        r.research_summary,
        r.results_summary,
      ].some((value) => String(value || "").toLowerCase().includes(q))
    );
  });

  const relOf = (r) => parseInt(r.assess_relevance || "0", 10);
  if (state.supplementarySort === "relevance-desc") {
    shown.sort((a, b) => relOf(b) - relOf(a));
  } else if (state.supplementarySort === "domain") {
    shown.sort((a, b) =>
      assessPrimaryDomainForRecord(a).localeCompare(
        assessPrimaryDomainForRecord(b)
      )
    );
  } else if (state.supplementarySort === "decision") {
    const rank = (r) => {
      if (!r.fulltext_final_decision) return 0;
      if (r.fulltext_final_decision === "Exclude") return 1;
      return 2;
    };
    shown.sort((a, b) => rank(a) - rank(b) || a.record_id.localeCompare(b.record_id));
  } else {
    shown.sort((a, b) => a.record_id.localeCompare(b.record_id));
  }

  const hiddenCount = state.supplementaryDismissed.size;
  $("#supplementary-count").textContent =
    state.supplementaryDecision === "queue"
      ? `${shown.length} shown · ${queueRemaining} remaining in queue · ${decisionCount("Include")} Include · ${decisionCount("Exclude")} Exclude`
      : `${shown.length} of ${pool.length} supplementary papers shown · ${decisionCount("Include")} Include · ${decisionCount("Exclude")} Exclude${hiddenCount ? ` · ${hiddenCount} hidden in queue` : ""}`;

  $("#supplementary-list").innerHTML = shown.length
    ? shown
    .map((r) => {
      const link = r.assess_decision_link || "none";
      const score = relOf(r);
      const band = (r.assess_band || "").toLowerCase();
      const finalDecision = r.fulltext_final_decision || "";
      const decisionClass =
        finalDecision === "Include"
          ? "is-included"
          : finalDecision === "Exclude"
            ? "is-excluded"
            : "is-pending";
      const doi = r.doi
        ? `<a href="https://doi.org/${encodeURIComponent(r.doi)}" target="_blank" rel="noreferrer">DOI</a>`
        : "";
      const pdf = r.fulltext_local_pdf
        ? `<span class="pdf-badge has">PDF in corpus</span>`
        : `<span class="pdf-badge missing">PDF missing</span>`;
      const evidence = r.assess_evidence
        ? `<details class="fulltext-analysis"><summary>Supporting excerpt${r.assess_evidence_pages ? ` · p. ${escapeHtml(r.assess_evidence_pages)}` : ""}</summary><p>${escapeHtml(r.assess_evidence)}</p></details>`
        : "";
      const secondary = (r.assess_secondary_domains || [])
        .map((d) => `<span class="tag domain">${escapeHtml(d)}</span>`)
        .join("");
      return `<article class="supplementary-card ${decisionClass}">
        <header class="supplementary-card-head">
          <div>
            <button type="button" class="record-link" data-report-id="${escapeHtml(r.record_id)}">${escapeHtml(r.record_id)}</button>
            <span class="supplementary-year">${escapeHtml(r.year || "?")}</span>
            ${pdf}
            <span class="final-decision-badge ${finalDecision ? finalDecision.toLowerCase() : "pending"}">${escapeHtml(finalDecisionLabel(r))}</span>
          </div>
          <div class="supplementary-badges">
            <span class="tag domain"><strong>Primary:</strong> ${escapeHtml(assessPrimaryDomainForRecord(r))}</span>
            ${secondary}
            <span class="tag tier">${escapeHtml(r.assess_tier || DEFAULT_TIER)}</span>
            <span class="link-badge ${link}">${escapeHtml(LINK_LABEL[link] || link)}</span>
            <span class="relevance-num ${band}">${score} · ${escapeHtml(r.assess_band || "")}</span>
          </div>
        </header>
        <h3 class="supplementary-title">${escapeHtml(r.title)}</h3>
        <p class="report-authors">${escapeHtml(r.authors || "—")}${r.journal ? ` · ${escapeHtml(r.journal)}` : ""}${doi ? ` · ${doi}` : ""}</p>
        <div class="supplementary-section">
          <h4>What is researched</h4>
          <p>${escapeHtml(r.research_summary || (r.abstract || "").slice(0, 320) || "—")}</p>
        </div>
        <div class="supplementary-section">
          <h4>Key results</h4>
          <p class="results-note">${escapeHtml(r.results_summary || r.assess_use || "—")}</p>
          ${evidence}
        </div>
        <div class="supplementary-section">
          <h4>Categorisation</h4>
          <dl class="supplementary-meta">
            <div><dt>Contribution type</dt><dd>${escapeHtml(r.assess_contribution_type || "—")}</dd></div>
            <div><dt>Technology tier</dt><dd>${escapeHtml(r.assess_tier || DEFAULT_TIER)}</dd></div>
            <div><dt>Primary domain</dt><dd>${escapeHtml(assessPrimaryDomainForRecord(r))}</dd></div>
            <div><dt>Decision link</dt><dd>${escapeHtml(LINK_LABEL[link] || link)}</dd></div>
            <div><dt>Relevance</dt><dd>${score} (${escapeHtml(r.assess_band || "—")})</dd></div>
          </dl>
        </div>
        <div class="supplementary-actions">
          <span class="final-label">${finalDecision ? `Final: ${escapeHtml(finalDecision)}` : "Set final decision:"}</span>
          <button type="button" class="final-decision include ${finalDecision === "Include" ? "active" : ""}" data-supplementary-id="${escapeHtml(r.record_id)}" data-final-decision="Include">Include in corpus</button>
          <button type="button" class="final-decision exclude ${finalDecision === "Exclude" ? "active" : ""}" data-supplementary-id="${escapeHtml(r.record_id)}" data-final-decision="Exclude">Exclude from corpus</button>
        </div>
      </article>`;
    })
    .join("")
    : `<p class="matrix-note">Review queue complete. Use <b>Reset queue</b> to review again, or switch the filter to <b>All decisions</b>.</p>`;

  $("#supplementary-list")
    .querySelectorAll("[data-report-id]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        state.view = "screen";
        jumpToId(button.dataset.reportId);
      });
    });
  $("#supplementary-list")
    .querySelectorAll("[data-supplementary-id]")
    .forEach((button) => {
      button.addEventListener("click", () =>
        setFulltextFinalDecision(
          button.dataset.supplementaryId,
          button.dataset.finalDecision
        )
      );
    });
}

function exportSupplementaryCsv() {
  const headers = [
    "record_id",
    "fulltext_final_decision",
    "title",
    "authors",
    "year",
    "doi",
    "research_summary",
    "results_summary",
    "assess_primary_domain",
    "assess_secondary_domains",
    "assess_tier",
    "assess_decision_link",
    "assess_contribution_type",
    "assess_relevance",
    "assess_band",
  ];
  const lines = [headers.join(",")];
  for (const r of supplementaryRecords()) {
    lines.push(
      headers
        .map((header) => {
          const value =
            header === "assess_secondary_domains"
              ? (r.assess_secondary_domains || []).join("; ")
              : r[header] ?? "";
          return csvEscape(value);
        })
        .join(",")
    );
  }
  downloadText("supplementary_papers_summary.csv", lines.join("\n"));
  toast(`Exported ${lines.length - 1} supplementary summaries`);
}

/* ---------- Final corpus categorization review ---------- */

function categorizationRecords() {
  return state.records.filter(
    (r) => r.fulltext_final_decision === "Include" && r.assess_band
  );
}

function categorizationQueueRemaining() {
  return categorizationRecords().filter(
    (r) => !state.categorizationDismissed.has(r.record_id)
  ).length;
}

// Coupling rule: only a physical Agent can execute a field operation, so
// "Executive (operational)" is offered for Agent tier only.
function allowedLinksFor(tier) {
  return OPERATIONAL_TIERS.includes(tier)
    ? ["operational", "explicit", "implicit"]
    : ["explicit", "implicit", "none"];
}

function linkOptionsHtml(tier, current) {
  const allowed = allowedLinksFor(tier);
  const effective = allowed.includes(current) ? current : allowed[allowed.length - 1];
  return allowed
    .map(
      (value) =>
        `<option value="${value}" ${effective === value ? "selected" : ""}>${escapeHtml(LINK_LABEL[value] || value)}</option>`
    )
    .join("");
}

function secondaryDomainCheckboxes(r, primary) {
  return DOMAIN_OPTIONS.filter((d) => d !== primary)
    .map(
      (domain) =>
        `<label class="domain-check"><input type="checkbox" data-cat-secondary="${escapeHtml(r.record_id)}" value="${escapeHtml(domain)}" ${(r.assess_secondary_domains || []).includes(domain) ? "checked" : ""} /> ${escapeHtml(domain)}</label>`
    )
    .join("");
}

function readCategorizationForm(recordId) {
  const card = $(`#categorization-list [data-cat-card="${recordId}"]`);
  if (!card) return null;
  const primary = card.querySelector("[data-cat-primary]")?.value || "";
  const tier = card.querySelector("[data-cat-tier]")?.value || DEFAULT_TIER;
  const link = card.querySelector("[data-cat-link]")?.value || "";
  const note = card.querySelector("[data-cat-note]")?.value?.trim() || "";
  const secondary = [...card.querySelectorAll("[data-cat-secondary]:checked")].map(
    (el) => el.value
  );
  return {
    assess_primary_domain: primary,
    assess_secondary_domains: secondary.filter((d) => d !== primary),
    assess_tier: tier,
    assess_decision_link: link,
    assess_reasoning_user: note,
  };
}

async function saveCategorization(recordId, dismissAfter = true) {
  const record = state.records.find((r) => r.record_id === recordId);
  const patch = readCategorizationForm(recordId);
  if (!record || !patch) return;
  if (!allowedLinksFor(patch.assess_tier).includes(patch.assess_decision_link)) {
    toast(
      patch.assess_decision_link === "operational"
        ? "Executive mode requires Agent tier — pick Agent or change the mode."
        : "This mode is not valid for the selected tier."
    );
    return;
  }
  const previous = {
    assess_tier: record.assess_tier,
    assess_primary_domain: record.assess_primary_domain,
    assess_secondary_domains: [...(record.assess_secondary_domains || [])],
    assess_decision_link: record.assess_decision_link,
    assess_domains: [...(record.assess_domains || [])],
    assess_reasoning: record.assess_reasoning,
  };
  record.assess_tier = patch.assess_tier;
  record.assess_primary_domain = patch.assess_primary_domain;
  record.assess_secondary_domains = patch.assess_secondary_domains;
  record.assess_decision_link = patch.assess_decision_link;
  record.assess_domains = [
    patch.assess_primary_domain,
    ...patch.assess_secondary_domains,
  ].filter(Boolean);
  record.assess_contribution_type = TIER_LABELS[patch.assess_tier] || patch.assess_tier;
  if (dismissAfter && state.view === "categorization") {
    state.categorizationDismissed.add(recordId);
    saveCategorizationDismissed();
  }
  render();
  try {
    const res = await fetch("/api/save-assessment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions: [{ record_id: recordId, ...patch }] }),
    });
    if (!res.ok) throw new Error(await res.text());
    toast(
      `${recordId} saved · ${categorizationQueueRemaining()} left in queue`
    );
  } catch (error) {
    Object.assign(record, previous);
    state.categorizationDismissed.delete(recordId);
    saveCategorizationDismissed();
    render();
    toast("Categorization was not saved");
    console.error(error);
  }
}

function renderCategorization() {
  const pool = categorizationRecords();
  const primaryDomains = [...new Set(pool.map(assessPrimaryDomainForRecord))].sort();
  fillReportSelect(
    $("#categorization-domain"),
    primaryDomains,
    state.categorizationDomain,
    "primary domains"
  );

  const tierCount = (tier) =>
    pool.filter((r) => (r.assess_tier || DEFAULT_TIER) === tier).length;
  const queueRemaining = categorizationQueueRemaining();

  const matrix = primaryDomains
    .map((domain) => {
      const cells = TIER_OPTIONS.map(
        (tier) =>
          `<td>${pool.filter((r) => assessPrimaryDomainForRecord(r) === domain && (r.assess_tier || DEFAULT_TIER) === tier).length}</td>`
      ).join("");
      return `<tr><th>${escapeHtml(domain)}</th>${cells}</tr>`;
    })
    .join("");

  $("#categorization-summary").innerHTML = `
    <div class="report-total"><strong>${pool.length}</strong><span>papers in final corpus</span></div>
    <div class="matrix-wrap">
      <div class="recommendation-summary">
        ${tierCountSpans((t) => tierCount(t))}
        <span class="evidence-count">${queueRemaining} remaining in review queue</span>
      </div>
      <table class="matrix">
        <thead><tr><th>Primary domain</th>${tierHeaderCells()}</tr></thead>
        <tbody>${matrix}</tbody>
      </table>
    </div>`;

  const q = state.categorizationQuery.trim().toLowerCase();
  let shown = pool.filter((r) => {
    if (
      state.categorizationQueue === "queue" &&
      state.categorizationDismissed.has(r.record_id)
    ) {
      return false;
    }
    if (
      state.categorizationDomain !== "all" &&
      assessPrimaryDomainForRecord(r) !== state.categorizationDomain
    ) {
      return false;
    }
    if (
      state.categorizationTier !== "all" &&
      (r.assess_tier || DEFAULT_TIER) !== state.categorizationTier
    ) {
      return false;
    }
    if (
      state.categorizationLink !== "all" &&
      r.assess_decision_link !== state.categorizationLink
    ) {
      return false;
    }
    return (
      !q ||
      [
        r.title,
        r.authors,
        r.doi,
        r.record_id,
        r.assess_reasoning,
        assessPrimaryDomainForRecord(r),
      ].some((value) => String(value || "").toLowerCase().includes(q))
    );
  });

  const relOf = (r) => parseInt(r.assess_relevance || "0", 10);
  if (state.categorizationSort === "relevance-desc") {
    shown.sort((a, b) => relOf(b) - relOf(a));
  } else if (state.categorizationSort === "tier") {
    shown.sort(
      (a, b) =>
        TIER_OPTIONS.indexOf(a.assess_tier || DEFAULT_TIER) -
          TIER_OPTIONS.indexOf(b.assess_tier || DEFAULT_TIER) ||
        a.record_id.localeCompare(b.record_id)
    );
  } else if (state.categorizationSort === "domain") {
    shown.sort((a, b) =>
      assessPrimaryDomainForRecord(a).localeCompare(
        assessPrimaryDomainForRecord(b)
      )
    );
  } else {
    shown.sort((a, b) => a.record_id.localeCompare(b.record_id));
  }

  $("#categorization-count").textContent =
    state.categorizationQueue === "queue"
      ? `${shown.length} shown · ${queueRemaining} remaining in queue`
      : `${shown.length} of ${pool.length} papers shown`;

  $("#categorization-list").innerHTML = shown.length
    ? shown
        .map((r) => {
          const link = r.assess_decision_link || "none";
          const primary = assessPrimaryDomainForRecord(r);
          const tierOptions = TIER_OPTIONS.map(
            (tier) =>
              `<option value="${tier}" ${(r.assess_tier || DEFAULT_TIER) === tier ? "selected" : ""}>${tier}</option>`
          ).join("");
          const primaryOptions = DOMAIN_OPTIONS.map(
            (domain) =>
              `<option value="${escapeHtml(domain)}" ${primary === domain ? "selected" : ""}>${escapeHtml(domain)}</option>`
          ).join("");
          const linkOptions = linkOptionsHtml(r.assess_tier || DEFAULT_TIER, link);
          const reasoning = r.assess_reasoning || "No automated reasoning recorded.";
          return `<article class="categorization-card" data-cat-card="${escapeHtml(r.record_id)}">
        <header class="supplementary-card-head">
          <div>
            <button type="button" class="record-link" data-report-id="${escapeHtml(r.record_id)}">${escapeHtml(r.record_id)}</button>
            <span class="supplementary-year">${escapeHtml(r.year || "?")}</span>
            <span class="relevance-num ${(r.assess_band || "").toLowerCase()}">${relOf(r)} · ${escapeHtml(r.assess_band || "")}</span>
          </div>
          <div class="supplementary-badges">
            <span class="tag tier">${escapeHtml(r.assess_tier || DEFAULT_TIER)}</span>
            <span class="tag domain">${escapeHtml(primary)}</span>
            <span class="link-badge ${link}">${escapeHtml(LINK_LABEL[link] || link)}</span>
          </div>
        </header>
        <h3 class="supplementary-title">${escapeHtml(r.title)}</h3>
        <p class="report-authors">${escapeHtml(r.authors || "—")}</p>
        <div class="categorization-reasoning">
          <h4>Categorization reasoning</h4>
          <p>${escapeHtml(reasoning)}</p>
        </div>
        <div class="categorization-form">
          <label>Technology tier
            <select data-cat-tier="${escapeHtml(r.record_id)}">${tierOptions}</select>
          </label>
          <label>Primary domain
            <select data-cat-primary="${escapeHtml(r.record_id)}">${primaryOptions}</select>
          </label>
          <label>Decision-integration mode
            <select data-cat-link="${escapeHtml(r.record_id)}">${linkOptions}</select>
            <span class="field-hint">Executive is only available for Agent tier — software cannot act on the crop.</span>
          </label>
          <div class="categorization-secondary">
            <span class="field-label">Secondary domains</span>
            <div class="domain-check-grid">${secondaryDomainCheckboxes(r, primary)}</div>
          </div>
          <label class="categorization-note">Reviewer note (optional)
            <textarea data-cat-note="${escapeHtml(r.record_id)}" rows="2" placeholder="Why you changed tier or domain…"></textarea>
          </label>
          <button type="button" class="final-decision include" data-cat-save="${escapeHtml(r.record_id)}">Save categorization</button>
        </div>
      </article>`;
        })
        .join("")
    : `<p class="matrix-note">Review queue complete. Use <b>Reset queue</b> to review again, or switch to <b>All papers</b>.</p>`;

  $("#categorization-list")
    .querySelectorAll("[data-report-id]")
    .forEach((button) => {
      button.addEventListener("click", () => {
        state.view = "screen";
        jumpToId(button.dataset.reportId);
      });
    });
  $("#categorization-list")
    .querySelectorAll("[data-cat-primary]")
    .forEach((select) => {
      select.addEventListener("change", () => {
        const rid = select.dataset.catPrimary;
        const card = $(`#categorization-list [data-cat-card="${rid}"]`);
        const grid = card?.querySelector(".domain-check-grid");
        const record = state.records.find((r) => r.record_id === rid);
        if (grid && record) {
          grid.innerHTML = secondaryDomainCheckboxes(record, select.value);
        }
      });
    });
  $("#categorization-list")
    .querySelectorAll("[data-cat-tier]")
    .forEach((select) => {
      select.addEventListener("change", () => {
        const rid = select.dataset.catTier;
        const card = $(`#categorization-list [data-cat-card="${rid}"]`);
        const linkSelect = card?.querySelector("[data-cat-link]");
        if (linkSelect) {
          linkSelect.innerHTML = linkOptionsHtml(select.value, linkSelect.value);
        }
      });
    });
  $("#categorization-list")
    .querySelectorAll("[data-cat-save]")
    .forEach((button) => {
      button.addEventListener("click", () =>
        saveCategorization(button.dataset.catSave, true)
      );
    });
}

function loadDoiHistory() {
  try {
    return JSON.parse(sessionStorage.getItem(DOI_HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveDoiHistory(items) {
  sessionStorage.setItem(DOI_HISTORY_KEY, JSON.stringify(items.slice(0, 20)));
}

function pushDoiHistory(entry) {
  const items = loadDoiHistory().filter((item) => item.parsed_doi !== entry.parsed_doi);
  items.unshift(entry);
  saveDoiHistory(items);
}

function doiStatusClass(status) {
  if (status === "in_final_corpus") return "is-included";
  if (status === "not_found" || status === "invalid") return "is-unknown";
  if (String(status || "").startsWith("excluded")) return "is-excluded";
  return "is-pending";
}

function renderDoiResultCard(data) {
  const cls = doiStatusClass(data.status);
  const doiUrl = data.parsed_doi ? `https://doi.org/${data.parsed_doi}` : "";
  const resolveBlock =
    data.resolve_note && data.status !== "invalid"
      ? `<p class="doi-check-resolve">${escapeHtml(data.resolve_note)}</p>`
      : data.resolve_note
        ? `<p class="doi-check-resolve">${escapeHtml(data.resolve_note)}</p>`
        : "";
  const resolvedLink =
    data.resolved_url && data.resolved_url !== data.input
      ? `<p class="doi-check-meta">Resolved from <a href="${escapeHtml(data.resolved_url)}" target="_blank" rel="noopener">${escapeHtml(data.resolved_url)}</a></p>`
      : "";
  if (!data.found) {
    return `<div class="doi-check-card ${cls}">
      <div class="doi-check-status">${escapeHtml(data.status_label || "Not found")}</div>
      <p>${escapeHtml(data.message || "No match in this project.")}</p>
      ${resolveBlock}
      ${data.parsed_doi ? `<p class="doi-check-meta">Resolved DOI: <a href="${doiUrl}" target="_blank" rel="noopener">${escapeHtml(data.parsed_doi)}</a></p>` : ""}
      ${resolvedLink}
    </div>`;
  }

  const pdf = data.fulltext_local_pdf
    ? `<a href="/${escapeHtml(data.fulltext_local_pdf)}" target="_blank" rel="noopener">Open project PDF</a>`
    : "";
  const metaRows = [
    data.record_id && `<tr><th>Record</th><td><code>${escapeHtml(data.record_id)}</code></td></tr>`,
    data.search_arm && `<tr><th>Search arm</th><td>${escapeHtml(data.search_arm)}</td></tr>`,
    data.human_decision && `<tr><th>Title/abstract</th><td>${escapeHtml(data.human_decision)}${data.exclusion_code ? ` · ${escapeHtml(data.exclusion_code)}` : ""}</td></tr>`,
    data.citation_chase_decision && `<tr><th>Citation chase</th><td>${escapeHtml(data.citation_chase_decision)}</td></tr>`,
    data.fulltext_final_decision && `<tr><th>Full text</th><td>${escapeHtml(data.fulltext_final_decision)}</td></tr>`,
    data.assess_tier && `<tr><th>Charting</th><td>${escapeHtml(data.assess_tier)} · ${escapeHtml(data.assess_primary_domain || "—")} · ${escapeHtml(data.assess_decision_link || "—")}</td></tr>`,
  ].filter(Boolean);

  return `<div class="doi-check-card ${cls}">
    <div class="doi-check-card-head">
      <div class="doi-check-status">${escapeHtml(data.status_label)}</div>
      <div class="doi-check-detail">${escapeHtml(data.status_detail || "")}</div>
    </div>
    <h3>${escapeHtml(data.title)}</h3>
    <p class="doi-check-authors">${escapeHtml(data.authors)} · ${escapeHtml(data.year)}${data.journal ? ` · ${escapeHtml(data.journal)}` : ""}</p>
    <p class="doi-check-meta"><a href="${doiUrl}" target="_blank" rel="noopener">${escapeHtml(data.parsed_doi)}</a>${pdf ? ` · ${pdf}` : ""}</p>
    ${resolveBlock}
    ${resolvedLink}
    ${data.fulltext_reason ? `<p class="doi-check-reason">${escapeHtml(data.fulltext_reason)}</p>` : ""}
    ${data.citation_chase_reason && !data.fulltext_reason ? `<p class="doi-check-reason">${escapeHtml(data.citation_chase_reason)}</p>` : ""}
    ${metaRows.length ? `<table class="doi-check-table"><tbody>${metaRows.join("")}</tbody></table>` : ""}
  </div>`;
}

function renderDoiHistory() {
  const items = loadDoiHistory();
  const wrap = $("#doi-check-history-wrap");
  const list = $("#doi-check-history");
  if (!items.length) {
    wrap.hidden = true;
    return;
  }
  wrap.hidden = false;
  list.innerHTML = items
    .map(
      (item) => `<button type="button" class="doi-history-item ${doiStatusClass(item.status)}" data-query="${escapeHtml(item.query)}">
        <span class="doi-history-status">${escapeHtml(item.status_label || item.status)}</span>
        <span class="doi-history-title">${escapeHtml(item.title || item.parsed_doi || item.query)}</span>
      </button>`
    )
    .join("");
  list.querySelectorAll(".doi-history-item").forEach((btn) => {
    btn.addEventListener("click", () => {
      $("#doi-check-input").value = btn.dataset.query;
      runDoiLookup(btn.dataset.query);
    });
  });
}

function renderDoiCheck() {
  renderDoiHistory();
}

async function runDoiLookup(raw) {
  const query = (raw || "").trim();
  if (!query) {
    toast("Paste a DOI or link first");
    return;
  }
  const resultEl = $("#doi-check-result");
  resultEl.innerHTML = `<div class="doi-check-card is-pending"><p>Resolving link and checking corpus…</p></div>`;
  try {
    const res = await fetch(`/api/lookup-doi?q=${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    resultEl.innerHTML = renderDoiResultCard(data);
    pushDoiHistory({
      query,
      parsed_doi: data.parsed_doi,
      status: data.status,
      status_label: data.status_label,
      title: data.title,
    });
    renderDoiHistory();
  } catch (err) {
    resultEl.innerHTML = `<div class="doi-check-card is-unknown"><p>Lookup failed. Is <code>serve.py</code> running?</p><p>${escapeHtml(String(err))}</p></div>`;
    console.error(err);
  }
}

function exportCategorizationCsv() {
  const headers = [
    "record_id",
    "title",
    "assess_tier",
    "assess_primary_domain",
    "assess_secondary_domains",
    "assess_decision_link",
    "assess_relevance",
    "assess_band",
    "assess_reasoning",
  ];
  const lines = [headers.join(",")];
  for (const r of categorizationRecords()) {
    lines.push(
      headers
        .map((header) => {
          const value =
            header === "assess_secondary_domains"
              ? (r.assess_secondary_domains || []).join("; ")
              : r[header] ?? "";
          return csvEscape(value);
        })
        .join(",")
    );
  }
  downloadText("final_corpus_categorization.csv", lines.join("\n"));
  toast(`Exported ${lines.length - 1} categorization rows`);
}

function exportAssessCsv() {
  const headers = ["record_id", "assess_relevance", "assess_band", "assess_decision_link", "assess_tier", "assess_primary_domain", "assess_secondary_domains", "assess_domains", "assess_contribution_type", "assess_exclude_candidate", "assess_exclude_reason", "assess_use", "title", "authors", "year", "doi"];
  const lines = [headers.join(",")];
  for (const r of assessRecords()) {
    lines.push(headers.map((header) => {
      const value = ["assess_domains", "assess_secondary_domains"].includes(header)
        ? (r[header] || []).join("; ")
        : (r[header] ?? "");
      return csvEscape(value);
    }).join(","));
  }
  downloadText("corpus_assessment.csv", lines.join("\n"));
  toast(`Exported ${lines.length - 1} assessed papers`);
}

function exportReportCsv() {
  const headers = ["record_id", "report_domains", "report_tier", "fulltext_recommendation", "fulltext_confidence", "fulltext_evidence_status", "fulltext_reason", "fulltext_oa_url", "fulltext_local_pdf", "fulltext_final_decision", "fulltext_final_notes", "title", "authors", "year", "journal", "doi", "abstract"];
  const lines = [headers.join(",")];
  for (const r of includedRecords()) {
    lines.push(headers.map((header) => {
      const value = header === "classification_status"
        ? "unconfirmed"
        : header === "report_domains"
        ? domainsForRecord(r).join("; ")
        : header === "fulltext_recommendation"
          ? recommendationForRecord(r)
          : (r[header] ?? "");
      return csvEscape(value);
    }).join(","));
  }
  downloadText("included_papers_categorised_report.csv", lines.join("\n"));
  toast(`Exported ${lines.length - 1} categorised retained papers`);
}

function jumpToId(recordId) {
  // Show all passes + all statuses so the record is visible, then focus it
  state.filterPass = "all";
  state.filterStatus = "all";
  $("#filter-pass").value = "all";
  $("#filter-status").value = "all";
  $("#mode-screen").classList.remove("active");
  $("#mode-review").classList.add("active");
  const list = currentList();
  const idx = list.findIndex((r) => r.record_id === recordId);
  state.index = idx >= 0 ? idx : 0;
  render();
}

function renderReviewList() {
  const el = $("#review-list");
  if (!el) return;
  const decided = state.records.filter((r) => r.human_decision);
  const passFiltered =
    state.filterPass === "all"
      ? decided
      : decided.filter((r) => r.pass === state.filterPass);

  // In undecided mode, still show recent decided for quick jump (current pass)
  const items =
    state.filterStatus === "undecided"
      ? decided.filter(
          (r) => state.filterPass === "all" || r.pass === state.filterPass
        )
      : filtered().filter((r) => r.human_decision);

  const show = (state.filterStatus === "undecided" ? passFiltered : items).slice(
    0,
    200
  );

  if (!show.length) {
    el.innerHTML = `<div class="empty-list">No decided records yet.</div>`;
    return;
  }

  const current = currentRecord();
  el.innerHTML = show
    .map((r) => {
      const cur = current && current.record_id === r.record_id ? "current" : "";
      const short = (r.title || "").slice(0, 42);
      return `<button type="button" data-id="${escapeHtml(r.record_id)}" class="${cur}">
        <span class="rid">${escapeHtml(r.record_id)}</span>
        <span class="dtag">${escapeHtml(r.human_decision)}</span><br/>
        ${escapeHtml(short)}${(r.title || "").length > 42 ? "…" : ""}
      </button>`;
    })
    .join("");

  el.querySelectorAll("button[data-id]").forEach((btn) => {
    btn.addEventListener("click", () => jumpToId(btn.dataset.id));
  });
}

function guessCode(r) {
  return r.exclusion_code || (r.screen_reason.includes("Genomics") ? "sensor_only" : "wrong_crop");
}

function move(delta) {
  const list = currentList();
  if (!list.length) return;
  state.index = Math.max(0, Math.min(list.length - 1, state.index + delta));
  render();
}

function exportCsv() {
  const headers = [
    "record_id",
    "human_decision",
    "exclusion_code",
    "human_notes",
    "suggested_decision",
    "pass",
    "year",
    "title",
    "doi",
  ];
  const lines = [headers.join(",")];
  for (const r of state.records) {
    if (!r.human_decision) continue;
    const vals = headers.map((h) => csvEscape(r[h] ?? ""));
    lines.push(vals.join(","));
  }
  downloadText("title_screening_human_decisions.csv", lines.join("\n"));
  toast(`Exported ${lines.length - 1} decisions`);
}

function csvEscape(v) {
  const s = String(v).replaceAll('"', '""');
  return `"${s}"`;
}

function downloadText(name, text) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

async function saveToServer() {
  const decisions = state.records
    .filter((r) => r.human_decision)
    .map((r) => ({
      record_id: r.record_id,
      human_decision: r.human_decision,
      exclusion_code: r.exclusion_code,
      human_notes: r.human_notes,
    }));
  try {
    const res = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    toast(`Saved ${data.updated} decisions to title_screening.csv`);
  } catch (err) {
    toast("Save failed — use Export CSV, or start serve.py");
    console.error(err);
  }
}

function bind() {
  $("#mode-screen").addEventListener("click", () => setMode("screen"));
  $("#mode-review").addEventListener("click", () => setMode("review"));
  $("#mode-report").addEventListener("click", () => {
    state.view = "report";
    render();
  });
  $("#mode-corpus").addEventListener("click", () => {
    state.view = "corpus";
    render();
  });
  $("#mode-assess").addEventListener("click", () => {
    state.view = "assess";
    render();
  });
  $("#mode-supplementary").addEventListener("click", () => {
    state.view = "supplementary";
    render();
  });
  $("#mode-categorization").addEventListener("click", () => {
    state.view = "categorization";
    render();
  });
  $("#mode-doi-check").addEventListener("click", () => {
    state.view = "doi-check";
    render();
  });
  $("#btn-doi-check").addEventListener("click", () => {
    runDoiLookup($("#doi-check-input").value);
  });
  $("#doi-check-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      runDoiLookup(e.target.value);
    }
  });
  $("#supplementary-domain").addEventListener("change", (e) => {
    state.supplementaryDomain = e.target.value;
    renderSupplementary();
  });
  $("#supplementary-tier").addEventListener("change", (e) => {
    state.supplementaryTier = e.target.value;
    renderSupplementary();
  });
  $("#supplementary-link").addEventListener("change", (e) => {
    state.supplementaryLink = e.target.value;
    renderSupplementary();
  });
  $("#supplementary-decision").addEventListener("change", (e) => {
    state.supplementaryDecision = e.target.value;
    renderSupplementary();
  });
  $("#btn-supplementary-reset-queue").addEventListener("click", () => {
    resetSupplementaryQueue();
    state.supplementaryDecision = "queue";
    $("#supplementary-decision").value = "queue";
    renderSupplementary();
    toast("Review queue reset — all 101 papers visible again");
  });
  $("#supplementary-sort").addEventListener("change", (e) => {
    state.supplementarySort = e.target.value;
    renderSupplementary();
  });
  $("#supplementary-search").addEventListener("input", (e) => {
    state.supplementaryQuery = e.target.value;
    renderSupplementary();
  });
  $("#btn-supplementary-export").addEventListener("click", exportSupplementaryCsv);
  $("#categorization-domain").addEventListener("change", (e) => {
    state.categorizationDomain = e.target.value;
    renderCategorization();
  });
  $("#categorization-tier").addEventListener("change", (e) => {
    state.categorizationTier = e.target.value;
    renderCategorization();
  });
  $("#categorization-link").addEventListener("change", (e) => {
    state.categorizationLink = e.target.value;
    renderCategorization();
  });
  $("#categorization-queue").addEventListener("change", (e) => {
    state.categorizationQueue = e.target.value;
    renderCategorization();
  });
  $("#categorization-sort").addEventListener("change", (e) => {
    state.categorizationSort = e.target.value;
    renderCategorization();
  });
  $("#categorization-search").addEventListener("input", (e) => {
    state.categorizationQuery = e.target.value;
    renderCategorization();
  });
  $("#btn-categorization-reset-queue").addEventListener("click", () => {
    resetCategorizationQueue();
    state.categorizationQueue = "queue";
    $("#categorization-queue").value = "queue";
    renderCategorization();
    toast("Categorization queue reset");
  });
  $("#btn-categorization-export").addEventListener("click", exportCategorizationCsv);
  $("#assess-band").addEventListener("change", (e) => {
    state.assessBand = e.target.value;
    renderAssess();
  });
  $("#assess-link").addEventListener("change", (e) => {
    state.assessLink = e.target.value;
    renderAssess();
  });
  $("#assess-domain").addEventListener("change", (e) => {
    state.assessDomain = e.target.value;
    renderAssess();
  });
  $("#assess-tier").addEventListener("change", (e) => {
    state.assessTier = e.target.value;
    renderAssess();
  });
  $("#assess-candidates").addEventListener("change", (e) => {
    state.assessCandidates = e.target.checked;
    renderAssess();
  });
  $("#assess-sort").addEventListener("change", (e) => {
    state.assessSort = e.target.value;
    renderAssess();
  });
  $("#assess-search").addEventListener("input", (e) => {
    state.assessQuery = e.target.value;
    renderAssess();
  });
  $("#btn-assess-export").addEventListener("click", exportAssessCsv);
  $("#btn-assess-synthesis").addEventListener("click", () => {
    window.open("synthesis_draft.md", "_blank");
  });
  $("#corpus-pdf-filter").addEventListener("change", (e) => {
    state.corpusPdfFilter = e.target.value;
    renderCorpus();
  });
  $("#corpus-domain").addEventListener("change", (e) => {
    state.corpusDomain = e.target.value;
    renderCorpus();
  });
  $("#corpus-search").addEventListener("input", (e) => {
    state.corpusQuery = e.target.value;
    renderCorpus();
  });
  $("#btn-corpus-rescan").addEventListener("click", rescanCorpusPdfs);
  $("#btn-corpus-export").addEventListener("click", exportCorpusCsv);
  $("#report-domain").addEventListener("change", (e) => {
    state.reportDomain = e.target.value;
    renderReport();
  });
  $("#report-tier").addEventListener("change", (e) => {
    state.reportTier = e.target.value;
    renderReport();
  });
  $("#report-recommendation").addEventListener("change", (e) => {
    state.reportRecommendation = e.target.value;
    renderReport();
  });
  $("#report-evidence").addEventListener("change", (e) => {
    state.reportEvidence = e.target.value;
    renderReport();
  });
  $("#report-search").addEventListener("input", (e) => {
    state.reportQuery = e.target.value;
    renderReport();
  });
  $("#btn-report-export").addEventListener("click", exportReportCsv);
  $("#filter-pass").addEventListener("change", (e) => {
    state.filterPass = e.target.value;
    state.index = 0;
    render();
  });
  $("#filter-status").addEventListener("change", (e) => {
    state.filterStatus = e.target.value;
    state.index = 0;
    render();
  });
  $("#search").addEventListener("input", (e) => {
    state.query = e.target.value;
    state.index = 0;
    render();
  });
  $("#btn-prev").addEventListener("click", () => move(-1));
  $("#btn-next").addEventListener("click", () => move(1));
  $("#btn-export").addEventListener("click", exportCsv);
  $("#btn-save").addEventListener("click", saveToServer);
  // Click stats to review that bucket
  $("#stat-decided").parentElement.style.cursor = "pointer";
  $("#stat-include").parentElement.style.cursor = "pointer";
  $("#stat-maybe").parentElement.style.cursor = "pointer";
  $("#stat-exclude").parentElement.style.cursor = "pointer";
  $("#stat-decided").parentElement.title = "Review all decided";
  $("#stat-include").parentElement.title = "Review your Includes";
  $("#stat-maybe").parentElement.title = "Review your Maybes";
  $("#stat-exclude").parentElement.title = "Review your Excludes";
  $("#stat-decided").parentElement.addEventListener("click", () => {
    state.filterPass = "all";
    state.filterStatus = "decided";
    $("#filter-pass").value = "all";
    $("#filter-status").value = "decided";
    state.index = 0;
    render();
  });
  $("#stat-include").parentElement.addEventListener("click", () => {
    state.filterPass = "all";
    state.filterStatus = "Include";
    $("#filter-pass").value = "all";
    $("#filter-status").value = "Include";
    state.index = 0;
    render();
  });
  $("#stat-maybe").parentElement.addEventListener("click", () => {
    state.filterPass = "all";
    state.filterStatus = "Maybe";
    $("#filter-pass").value = "all";
    $("#filter-status").value = "Maybe";
    state.index = 0;
    render();
  });
  $("#stat-exclude").parentElement.addEventListener("click", () => {
    state.filterPass = "all";
    state.filterStatus = "Exclude";
    $("#filter-pass").value = "all";
    $("#filter-status").value = "Exclude";
    state.index = 0;
    render();
  });

  document.addEventListener("keydown", (e) => {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(e.target.tagName)) return;
    if (state.view !== "screen" && e.key !== "s" && e.key !== "S") return;
    if (e.key === "1") decide("Include");
    else if (e.key === "2") decide("Maybe");
    else if (e.key === "3") decide("Exclude");
    else if (e.key === "j" || e.key === "ArrowRight") move(1);
    else if (e.key === "k" || e.key === "ArrowLeft") move(-1);
    else if (e.key === "s" || e.key === "S") saveToServer();
    else if (e.key === "r" || e.key === "R") setMode("review");
    else if (e.key === "u" || e.key === "U") setMode("screen");
  });
}

async function init() {
  state.supplementaryDismissed = loadSupplementaryDismissed();
  state.categorizationDismissed = loadCategorizationDismissed();
  bind();
  await reloadData();
  $("#filter-pass").value = state.filterPass;
  $("#supplementary-decision").value = state.supplementaryDecision;
  $("#categorization-queue").value = state.categorizationQueue;
  render();
  applyDeepLink();
}

// Deep links: index.html#view=corpus | assess | report | supplementary | categorization | doi-check
// and, for the screening view, &pass=<queue>&status=<undecided|all|decided|Include|Maybe|Exclude>.
function applyDeepLink() {
  const h = new URLSearchParams(location.hash.replace(/^#/, ""));
  const pass = h.get("pass");
  const status = h.get("status");
  if (pass && [...$("#filter-pass").options].some((o) => o.value === pass)) {
    $("#filter-pass").value = pass;
    $("#filter-pass").dispatchEvent(new Event("change"));
  }
  if (status && [...$("#filter-status").options].some((o) => o.value === status)) {
    $("#filter-status").value = status;
    $("#filter-status").dispatchEvent(new Event("change"));
  }
  const view = h.get("view");
  const btn = view && document.getElementById(`mode-${view}`);
  if (btn) btn.click();
}

init();
