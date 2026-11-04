"use strict";
const el = (id) => document.getElementById(id);
const fields = ["tenant", "local_intent", "request_key", "payload", "attempt_no"];
const bookings = {
  A: ["north", "1", "k7"],
  B: ["north", "2", "k9"],
  C: ["south", "1", "k7"],
  D: ["south", "2", "k9"],
};
const modes = {
  count: "Total rows",
  identity_set: "Distinct identities",
  identity_multiset: "Identities with multiplicity",
};
const names = {
  repeat_only: "AAAA · repeat only",
  four_distinct: "ABCD · four distinct",
  mixed_count: "AABC · mixed",
  mixed_set: "AABC · mixed",
  mixed_multiset: "AABC · mixed",
};
let SQL;
let modelPlan;
function decodeTrace(trace) {
  if (!/^[ABCD]{1,4}$/.test(trace)) throw new Error("Use one to four letters from A, B, C and D.");
  const seen = {};
  return [...trace].map((a) => {
    seen[a] = (seen[a] || 0) + 1;
    return [...bookings[a], "0", seen[a]];
  });
}
function business(row) {
  return [row[0], row[1], row[3]].join(" / ");
}
function equal(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}
function accepted(expected, actual, mode) {
  if (mode === "count") return expected.length === actual.length;
  if (mode === "identity_set") return equal(expected, [...new Set(actual)].sort());
  return equal(expected, actual);
}
function observe(index, commands) {
  const db = new SQL.Database();
  try {
    db.run(
      "CREATE TABLE bookings(tenant TEXT NOT NULL, local_intent TEXT NOT NULL, request_key TEXT NOT NULL, payload TEXT NOT NULL, attempt_no INTEGER NOT NULL)",
    );
    if (index.length) db.run("CREATE UNIQUE INDEX chosen ON bookings(" + index.join(",") + ")");
    for (const cmd of commands) db.run("INSERT INTO bookings VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING", cmd);
    return db
      .exec("SELECT tenant,local_intent,request_key,payload,attempt_no FROM bookings")[0]
      .values.map(business)
      .sort();
  } finally {
    db.close();
  }
}
function list(id, values, other = [], difference = "") {
  const box = el(id);
  box.replaceChildren();
  const remaining = new Map();
  for (const value of other) remaining.set(value, (remaining.get(value) || 0) + 1);
  for (const text of values) {
    const node = document.createElement("li");
    node.textContent = text;
    const available = remaining.get(text) || 0;
    if (available > 0) remaining.set(text, available - 1);
    else if (difference) {
      node.dataset.difference = difference;
      node.setAttribute("aria-label", `${text}, ${difference}`);
    }
    box.append(node);
  }
}
function badge(id, verdict, label) {
  const tag = el(id);
  tag.className = verdict ? "pass" : "fail";
  tag.textContent = (verdict ? "PASS · " : "FAIL · ") + label;
}
function execute(event) {
  if (event) event.preventDefault();
  const trace = el("trace").value.trim().toUpperCase();
  el("trace").value = trace;
  try {
    const commands = decodeTrace(trace),
      expected = [...new Set(commands.map(business))].sort();
    const mode = el("mode").value,
      chosen = el("example").value;
    const bad = [];
    let correct = 0;
    for (let mask = 0; mask < 32; mask++) {
      const index = fields.filter((_, i) => (mask & (1 << i)) !== 0);
      const name = index.join("+") || "no_unique_index";
      const valid =
        index.includes("tenant") &&
        !index.includes("attempt_no") &&
        (index.includes("request_key") || index.includes("local_intent"));
      const rows = observe(index, commands);
      const pass = accepted(expected, rows, mode);
      if (pass === valid) correct++;
      if (pass && !valid) bad.push(name);
      if (name === chosen) {
        list("expected-list", expected, rows, "MISSING");
        list("actual-list", rows, expected, "EXTRA");
        badge("row-verdict", accepted(expected, rows, "count"), "row count");
        badge("identity-verdict", accepted(expected, rows, "identity_multiset"), "booking identities");
        const missing = expected.filter((k) => !rows.includes(k));
        const extra = rows.filter((k, i) => rows.indexOf(k) !== i);
        el("explanation").textContent =
          `${rows.length} observed for ${expected.length} expected. Missing: ${missing.join(", ") || "none"}. Duplicate copies: ${extra.join(", ") || "none"}.`;
      }
    }
    el("grade").textContent =
      `${trace} with “${modes[mode]}” classifies ${correct}/32 index designs correctly and approves ${bad.length}/26 unsafe designs.`;
    el("survivors").textContent = bad.join(", ") || "None in this family.";
  } catch (error) {
    el("grade").textContent = error.message;
    el("explanation").textContent = "No completed test.";
    el("survivors").textContent = "";
    list("expected-list", []);
    list("actual-list", []);
    for (const id of ["row-verdict", "identity-verdict"]) {
      el(id).className = "";
      el(id).textContent = "No result";
    }
  }
}
function table(id, cells) {
  const tr = document.createElement("tr");
  for (const v of cells) {
    const td = document.createElement("td");
    td.textContent = String(v);
    tr.append(td);
  }
  el(id).append(tr);
}
async function evidence(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error("Could not load " + path);
  return r.json();
}
async function loadResults() {
  const [s, b, c, m] = await Promise.all([
    evidence("intent-study-evidence.json"),
    evidence("intent-broker-evidence.json"),
    evidence("intent-semantic-controls.json"),
    evidence("intent-muse.json"),
  ]);
  for (const [key, v] of Object.entries(s.campaigns))
    table("ablation-rows", [names[key], modes[v.readout], v.false_approvals.length, v.correctly_classified]);
  el("search-note").textContent =
    `Adequate schedule/payload combinations, by number of writes: ${s.search.map((x) => `${x.writes} → ${x.combinations_classifying_all_32}/${x.schedule_payload_combinations}`).join(" · ")}. No fixed test with three or fewer writes covers this family. Four writes suffice under the specified readout and business contract.`;
  for (const eng of b.engines)
    for (const v of eng.cases)
      table("broker-rows", [
        eng.engine,
        v.mapping.replaceAll("_", " "),
        `${v.entries.length} / ${v.expected.length}`,
        v.count_pass ? "PASS" : "FAIL",
        v.identity_multiset_pass ? "PASS" : "FAIL",
      ]);
  for (const [key, label] of [
    ["recorded_muse", "Recorded Muse Spark 1.3"],
    ["frozen_nli", "Frozen DeBERTa-v3-small NLI"],
    ["nearest_seven", "Nearest labeled description"],
  ]) {
    const g = c.grades[key];
    table("semantic-rows", [label, g.matched, g.pairs_both]);
  }
  table("semantic-rows", ["Each of four previously frozen simple rules", 6, 0]);
  if (m.status === "scored") {
    modelPlan = m.proposal;
    const v = m.score;
    el("model-plan").textContent =
      `First recorded Muse proposal: ${v.schedule} with ${modes[v.readout]}. It classified ${v.correctly_classified}/${v.adapters} adapters and approved ${v.false_approvals.length} unsafe designs. The same trace with the multiset check scores ${v.same_trace_with_multiset_correct}/32. Response ${m.response_id}.`;
    el("try-muse").hidden = false;
  } else if (m.status === "unscored") {
    el("model-plan").textContent =
      `The first attempt was unscored at ${m.failure_stage}. No replacement response was selected.`;
  } else
    el("model-plan").textContent =
      "The test-design prompt is frozen. A new Muse response has not been recorded for this task.";
}
el("study-form").addEventListener("submit", execute);
el("trace").addEventListener("input", () => {
  el("grade").textContent = "Press Run to evaluate your edited sequence.";
  el("survivors").textContent = "";
});
for (const id of ["example", "mode"])
  el(id).addEventListener("change", () => {
    if (SQL) execute();
  });
el("try-muse").addEventListener("click", () => {
  if (!modelPlan || !SQL) return;
  el("trace").value = modelPlan.schedule;
  el("mode").value = modelPlan.readout;
  execute();
  el("study-form").scrollIntoView({ block: "start" });
});
initSqlJs()
  .then((engine) => {
    SQL = engine;
    el("execute").disabled = false;
    el("engine-note").textContent = "SQLite ready. A run creates 32 fresh databases.";
    execute();
  })
  .catch((e) => (el("engine-note").textContent = e.message));
loadResults().catch((e) => {
  el("model-plan").textContent =
    `${e.message}. Open the published page or serve docs over local HTTP to load the saved results.`;
});
