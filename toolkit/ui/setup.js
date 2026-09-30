/* Project setup page: edit project.json, test vocabulary and rules, run stages. */
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let P = null;
let STAGES = [];
let hits = {};

const PATTERN_GROUPS = {
  "patterns-screen": ["population", "technology", "context", "wrong_population", "out_of_scope", "other_discipline", "market_only", "sensor_only", "review"],
  "patterns-ft": ["ft_population", "ft_decision", "ft_operation", "ft_method_only", "ft_management_variable", "ft_monitoring", "ft_out_of_scope"],
  "patterns-other": ["agent", "contribution_cue", "chase_population", "chase_technology"],
};

function toast(msg) {
  const el = $("#toast");
  if (!el) return alert(msg);
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2200);
}

/* ---------- path helpers ---------- */
function get(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function set(obj, path, value) {
  const keys = path.split(".");
  let o = obj;
  for (const k of keys.slice(0, -1)) {
    if (typeof o[k] !== "object" || o[k] == null) o[k] = {};
    o = o[k];
  }
  o[keys[keys.length - 1]] = value;
}

/* ---------- render ---------- */
function renderScalars() {
  document.querySelectorAll("[data-path]").forEach((el) => {
    const v = get(P, el.dataset.path);
    const t = el.dataset.type;
    if (t === "list") el.value = Array.isArray(v) ? v.join(", ") : v || "";
    else if (t === "lines") el.value = Array.isArray(v) ? v.join("\n") : v || "";
    else if (t === "bool") el.value = v ? "true" : "false";
    else el.value = v == null ? "" : v;
  });
}

function table(id, cols, rows, onDelete) {
  const t = $(id);
  const head = "<tr>" + cols.map((c) => `<th>${esc(c.label)}</th>`).join("") + "<th></th></tr>";
  const body = rows
    .map(
      (r, i) =>
        "<tr>" +
        cols
          .map((c) =>
            c.wide
              ? `<td><textarea data-row="${i}" data-key="${c.key}">${esc(c.key === "columns" ? Object.entries(r.columns || {}).map(([k,v])=>k+"="+(Array.isArray(v)?v.join(";"):v)).join("\n") : (r[c.key] ?? ""))}</textarea></td>`
              : `<td><input type="text" data-row="${i}" data-key="${c.key}" value="${esc(r[c.key] ?? "")}" ${c.width ? `style="width:${c.width}"` : ""}/></td>`
          )
          .join("") +
        `<td class="row-actions"><button data-del="${i}">×</button>${onDelete.move ? `<button data-up="${i}">↑</button><button data-down="${i}">↓</button>` : ""}</td></tr>`
    )
    .join("");
  t.innerHTML = head + body;
  t.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => { collect(); rows.splice(+b.dataset.del, 1); renderAll(); }));
  t.querySelectorAll("[data-up]").forEach((b) => b.addEventListener("click", () => { collect(); const i = +b.dataset.up; if (i > 0) { [rows[i - 1], rows[i]] = [rows[i], rows[i - 1]]; } renderAll(); }));
  t.querySelectorAll("[data-down]").forEach((b) => b.addEventListener("click", () => { collect(); const i = +b.dataset.down; if (i < rows.length - 1) { [rows[i + 1], rows[i]] = [rows[i], rows[i + 1]]; } renderAll(); }));
}

function readTable(id, rows, keys) {
  $(id).querySelectorAll("[data-row]").forEach((el) => {
    const r = rows[+el.dataset.row];
    if (r) {
      if (el.dataset.key === "columns") {
        const map={};for (const line of el.value.split(/\n/).filter(s=>s.trim())) { const index=line.indexOf("=");if(index<1)throw new Error("CSV column mapping needs field=Column heading, one per line.");map[line.slice(0,index).trim()]=line.slice(index+1).split(";").map(s=>s.trim()).filter(Boolean); }r.columns=map;
      } else r[el.dataset.key] = el.value;
    }
  });
  return rows.map((r) => ({...r, ...Object.fromEntries(keys.map((k) => [k, r[k] ?? ""]))}));
}

function renderPatterns() {
  P.patterns = P.patterns || {};
  for (const [gid, keys] of Object.entries(PATTERN_GROUPS)) {
    $("#" + gid).innerHTML = keys
      .map(
        (k) => `<label class="f">${esc(k)} <span class="hits" id="hit-${k}">${hits[k] != null ? `${hits[k]} hits` : ""}</span>
          <textarea data-pattern="${k}">${esc(P.patterns[k] || "")}</textarea></label>`
      )
      .join("");
  }
}

function renderAll() {
  P.exports = P.exports || [];
  P.abstract_supplements = P.abstract_supplements || [];
  P.screening_rules = P.screening_rules || [];
  P.taxonomy = P.taxonomy || {};
  P.taxonomy.domains = P.taxonomy.domains || [];
  P.taxonomy.tiers = P.taxonomy.tiers || [];
  renderScalars();
  table("#exports", [{ key: "file", label: "file (relative to project)" }, { key: "source", label: "source label", width: "8rem" }, { key: "format", label: "format", width: "7rem" }, {key: "columns", label: "CSV columns: field=heading (optional)", wide: true}], P.exports, {});
  table("#supplements", [{ key: "file", label: "file" }, { key: "format", label: "format", width: "7rem" }], P.abstract_supplements, {});
  renderPatterns();
  table("#rules", [{ key: "if", label: "if (condition)", wide: true }, { key: "decision", label: "decision", width: "6rem" }, { key: "code", label: "code", width: "9rem" }, { key: "reason", label: "reason", wide: true }], P.screening_rules, { move: true });
  table("#domains", [{ key: "name", label: "name" }, { key: "pattern", label: "pattern (title+abstract)", wide: true }, { key: "folder", label: "folder", width: "7rem" }, { key: "decision_phrases", label: "decision phrases (core/side test)", wide: true }, { key: "audit_pattern", label: "audit pattern (optional)", wide: true }], P.taxonomy.domains, { move: true });
  table("#tiers", [{ key: "name", label: "name", width: "6rem" }, { key: "pattern", label: "pattern", wide: true }, { key: "label", label: "long label" }, { key: "folder", label: "folder", width: "7rem" }, { key: "audit_pattern", label: "audit pattern (optional)", wide: true }], P.taxonomy.tiers, { move: true });
}

/* ---------- collect ---------- */
function collect() {
  document.querySelectorAll("[data-path]").forEach((el) => {
    const t = el.dataset.type;
    let v = el.value;
    if (t === "list") v = v.split(",").map((s) => s.trim()).filter(Boolean);
    else if (t === "lines") v = v.split("\n").map((s) => s.trim()).filter(Boolean);
    else if (t === "bool") v = v === "true";
    else if (el.type === "number") v = v === "" ? 0 : Number(v);
    set(P, el.dataset.path, v);
  });
  document.querySelectorAll("[data-pattern]").forEach((el) => { P.patterns[el.dataset.pattern] = el.value; });
  P.exports = readTable("#exports", P.exports, ["file", "source", "format"]);
  P.abstract_supplements = readTable("#supplements", P.abstract_supplements, ["file", "format"]);
  P.screening_rules = readTable("#rules", P.screening_rules, ["if", "decision", "code", "reason"]);
  P.taxonomy.domains = readTable("#domains", P.taxonomy.domains, ["name", "pattern", "folder", "decision_phrases", "audit_pattern"]);
  P.taxonomy.tiers = readTable("#tiers", P.taxonomy.tiers, ["name", "pattern", "label", "folder", "audit_pattern"]);
  ["root", "root_display", "domain_names", "tier_names", "default_domain", "default_tier"].forEach((k) => delete P[k]);
  return P;
}

/* ---------- server ---------- */
async function api(path, body) {
  const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function showProblems(problems) {
  const el = $("#problems");
  if (!problems || !problems.length) {
    el.className = "problems ok";
    el.textContent = "project.json is complete: exports present, patterns compile, rules parse.";
  } else {
    el.className = "problems";
    el.innerHTML = "<b>Check:</b><ul>" + problems.map((p) => `<li>${esc(p)}</li>`).join("") + "</ul>";
  }
}

function renderFiles(files) {
  $("#files").innerHTML = files
    .map((f) => `<div class="${f.exists ? "" : "no"}"><span>${esc(f.name)}</span><span>${f.exists ? (f.rows != null ? f.rows + " rows" : "✓") + (f.modified ? " · " + esc(f.modified) : "") : "—"}</span></div>`)
    .join("");
}

function renderStages() {
  const groups = {};
  for (const s of STAGES) (groups[s.group] = groups[s.group] || []).push(s);
  $("#stages").innerHTML = Object.entries(groups)
    .map(
      ([g, list]) => `<div class="stage-group"><h3>${esc(g)}</h3><div class="btns">${list
        .map((s) => `<button data-stage="${s.id}" class="${s.network ? "net" : ""}" title="${esc(s.script + " " + s.args.join(" "))}">${esc(s.label)}</button>`)
        .join("")}</div></div>`
    )
    .join("");
  $("#stages").querySelectorAll("[data-stage]").forEach((b) =>
    b.addEventListener("click", async () => {
      const s = STAGES.find((x) => x.id === b.dataset.stage);
      if (s.network && !confirm(`"${s.label}" calls external services (Crossref/OpenAlex/Unpaywall). Continue?`)) return;
      if (s.id === "merge_screen" && !confirm("Merge exports and draft screening. Refuses to overwrite existing human decisions. Continue?")) return;
      try {
        await api("/api/run", { stage: s.id });
        pollLog(true);
      } catch (e) { toast(String(e.message || e)); }
    })
  );
}

let polling = null;
async function pollLog(force) {
  try {
    const st = await api("/api/run-status");
    $("#run-state").textContent = st.running ? `running: ${st.stage}` : st.stage ? `${st.stage} finished (exit ${st.exit_code})` : "idle";
    const pre = $("#log");
    pre.textContent = (st.log || []).join("\n");
    pre.scrollTop = pre.scrollHeight;
    if (st.running || force) {
      clearTimeout(polling);
      polling = setTimeout(() => pollLog(false), st.running ? 1200 : 0);
      if (!st.running && force) { const d = await api("/api/project"); renderFiles(d.files); showProblems(d.problems); }
    }
  } catch (e) { $("#run-state").textContent = "server?"; }
}

async function load() {
  const d = await api("/api/project");
  P = d.project;
  STAGES = d.stages;
  $("#proj-name").textContent = P.name || P.slug;
  $("#proj-root").textContent = P.root_display || P.root || "";
  $("#proj-frozen").innerHTML = P.frozen ? '<span class="badge-frozen">frozen</span>' : "";
  renderAll();
  showProblems(d.problems);
  renderFiles(d.files);
  renderStages();
  pollLog(false);
  try {
    const pr = await api("/api/projects");
    $("#projects").innerHTML = "Projects in this toolkit: " + pr.projects.map((p) => `<code>${esc(p.slug)}</code>${p.frozen ? " (frozen)" : ""}`).join(", ") + ". Start another with <code>python toolkit.py serve &lt;slug&gt;</code>.";
  } catch (e) { /* ignore */ }
}

/* ---------- actions ---------- */
$("#btn-save").addEventListener("click", async () => {
  try {
    const r = await api("/api/project", { project: collect() });
    showProblems(r.problems);
    toast("Saved project.json");
  } catch (e) { toast("Save failed: " + (e.message || e)); }
});
$("#btn-test").addEventListener("click", async () => {
  try {
    const r = await api("/api/test-patterns", { project: collect(), sample: $("#sample").value });
    if (r.error) { $("#test-out").innerHTML = `<div class="problems">${esc(r.error)}</div>`; return; }
    hits = r.pattern_hits || {};
    for (const [k, v] of Object.entries(hits)) { const el = $("#hit-" + k); if (el) el.textContent = `${v} hits`; }
    const ex = Object.entries(r.examples || {}).map(([k, arr]) => `<li><b>${esc(k)}</b>: ${arr.map(esc).join(" · ")}</li>`).join("");
    $("#test-out").innerHTML = `<div class="problems ok">Tested ${r.sample} records → ${Object.entries(r.decisions || {}).map(([k, v]) => `${k} ${v}`).join(", ")}</div><ul class="examples">${ex}</ul>`;
  } catch (e) { toast("Test failed: " + (e.message || e)); }
});
$("#btn-stop").addEventListener("click", () => api("/api/run-stop", {}).then(() => pollLog(true)).catch((e) => toast(String(e))));
$("#btn-rebuild").addEventListener("click", () => api("/api/rebuild-data", {}).then(() => toast("data.json rebuilt")).catch((e) => toast(String(e.message || e))));
$("#add-export").addEventListener("click", () => { collect(); P.exports.push({ file: "exports/", source: "", format: "bibtex" }); renderAll(); });
$("#add-supplement").addEventListener("click", () => { collect(); P.abstract_supplements.push({ file: "exports/", format: "bibtex" }); renderAll(); });
$("#add-rule").addEventListener("click", () => { collect(); P.screening_rules.push({ if: "", decision: "Maybe", code: "", reason: "" }); renderAll(); });
$("#add-domain").addEventListener("click", () => { collect(); P.taxonomy.domains.push({ name: "", pattern: "", folder: "", decision_phrases: "", audit_pattern: "" }); renderAll(); });
$("#add-tier").addEventListener("click", () => { collect(); P.taxonomy.tiers.push({ name: "", pattern: "", label: "", folder: "", audit_pattern: "" }); renderAll(); });
$("#btn-new").addEventListener("click", async () => {
  try {
    const r = await api("/api/new-project", { slug: $("#new-slug").value, name: $("#new-name").value });
    $("#new-out").textContent = `Created ${r.path}. ${r.hint}`;
  } catch (e) { $("#new-out").textContent = String(e.message || e); }
});

load()
  .then(() => {
    // ?section=<element id> scrolls to a section (used for deep links and documentation screenshots)
    const q = new URLSearchParams(location.search);
    const sec = q.get("section");
    const el = sec && document.getElementById(sec);
    if (el) el.scrollIntoView({ block: "start" });
    // ?only=blk-<name> shows a single section (documentation screenshots)
    const only = q.get("only");
    if (only && document.getElementById(only)) {
      document.querySelectorAll("section.blk").forEach((b) => { if (b.id !== only) b.style.display = "none"; });
    }
  })
  .catch((e) => { $("#problems").textContent = "Could not load project: " + (e.message || e); });
