'use strict';
const lab = window.CRASHLAB;
const byId = id => document.getElementById(id);
const presets = {
  attempt: lab.defaultCase.index_sql,
  request: 'CREATE UNIQUE INDEX retry_key ON reservations(request_key)',
  lookup: 'CREATE INDEX retry_key ON reservations(request_key)'
};
const indexPattern = new RegExp(lab.indexPattern, 'i');
let engine;
let lastRun;
let sqliteVersion;

function makeDatabase(indexSql) {
  const db = new engine.Database();
  try {
    db.run(lab.table);
    db.run(indexSql);
    return db;
  } catch (error) {
    db.close();
    throw error;
  }
}

function write(db, config, attempt) {
  db.run(lab.insert, [lab.intent, config.key === 'forward' ? lab.key : null, attempt]);
}

function ledger(db) {
  const result = db.exec(lab.read);
  return result.length ? result[0].values : [];
}

function probe(config) {
  const test = makeDatabase(config.index_sql);
  try {
    write(test, config, 1);
    write(test, config, 2);
    return ledger(test).length;
  } finally {
    test.close();
  }
}

function execute(config, verify) {
  const probeRows = verify ? probe(config) : null;
  const allowRetry = config.policy === 'retry_same_key' && (!verify || probeRows === 1);
  const db = makeDatabase(config.index_sql);
  try {
    if (config.fault === 'after') write(db, config, 1);
    if (allowRetry) write(db, config, 2);
    const rows = ledger(db);
    return {probeRows, allowRetry, rows, count: rows.length};
  } finally {
    db.close();
  }
}

function describe(lane, result, verified) {
  const n = result.count;
  lane.dataset.state = n === 1 ? 'good' : n === 0 ? 'empty' : 'bad';
  lane.querySelector('[data-count]').textContent = String(n);
  lane.querySelector('[data-verdict]').textContent = n === 1 ? 'One booking held' : n === 0 ? 'Booking incomplete' : 'Duplicate booking holds';
  const decision = result.allowRetry ? 'The client retried.' : 'The client held the retry.';
  lane.querySelector('[data-explain]').textContent = verified
    ? `The separate probe produced ${result.probeRows} ${result.probeRows === 1 ? 'row' : 'rows'}. ${decision}`
    : `The stored Muse policy permits a same-key retry. ${decision}`;
  const logs = lane.querySelector('[data-rows]');
  logs.replaceChildren();
  for (const [id, intent, key, attempt] of result.rows) {
    const row = document.createElement('div');
    row.textContent = `#${id} · ${intent} · ${key ?? 'NULL'} · try ${attempt}`;
    logs.append(row);
  }
  if (!n) logs.textContent = 'SELECT returned no rows.';
}

function invalidate() {
  lastRun = null;
  byId('test-file').disabled = true;
  byId('receipt-file').disabled = true;
  byId('error').hidden = true;
  for (const lane of document.querySelectorAll('.lane')) {
    delete lane.dataset.state;
    lane.querySelector('[data-count]').textContent = '—';
    lane.querySelector('[data-verdict]').textContent = 'Ready to execute';
    lane.querySelector('[data-explain]').textContent = 'Run this configuration to inspect the committed rows.';
    lane.querySelector('[data-rows]').replaceChildren();
  }
  byId('summary').textContent = 'Configuration changed. Run the test to measure both paths.';
}

function run(event) {
  if (event) event.preventDefault();
  invalidate();
  const config = {index_sql:byId('ddl').value.trim(), fault:byId('fault').value, key:byId('key').value, policy:lab.policy.action};
  try {
    if (config.index_sql.length > 300 || !/^[\x09\x0a\x0d\x20-\x7e]+$/.test(config.index_sql) || !indexPattern.test(config.index_sql)) {
      throw new Error('Use one CREATE [UNIQUE] INDEX on reservations with request_key, attempt_no or intent_id.');
    }
    const policy = execute(config, false);
    const verified = execute(config, true);
    lastRun = {schema:'stateproof-browser-sqlite-run-v1', recorded_at:new Date().toISOString(), sqlite:sqliteVersion,
      source_model:lab.meta.model, source_response:lab.meta.response_id, source_receipt_sha256:lab.receipt,
      inference:'previously recorded policy; zero browser model calls', fault_injection:'simulated application acknowledgement',
      config, sql:{create:lab.table, insert:lab.insert, oracle:lab.read}, intent:lab.intent, policy, verified};
    describe(byId('policy-lane'), policy, false);
    describe(byId('verified-lane'), verified, true);
    byId('test-file').disabled = false;
    byId('receipt-file').disabled = false;
    const outcome = config.fault === 'after' ? 'The first write committed.' : 'The first write never committed.';
    byId('summary').textContent = `${outcome} The caller saw a missing reply in both paths. A fresh SELECT found ${policy.count} ${policy.count === 1 ? 'row' : 'rows'} under the policy and ${verified.count} with the probe.`;
  } catch (error) {
    byId('error').textContent = error.message;
    byId('error').hidden = false;
    byId('summary').textContent = 'No completed run. Correct the configuration and try again.';
  }
}

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

byId('schema').addEventListener('change', () => {
  const value = byId('schema').value;
  if (value !== 'custom') byId('ddl').value = presets[value];
  else byId('ddl').focus();
  invalidate();
});
byId('ddl').addEventListener('input', () => { byId('schema').value = 'custom'; invalidate(); });
byId('fault').addEventListener('change', invalidate);
byId('key').addEventListener('change', invalidate);
byId('settings').addEventListener('submit', run);
byId('repair').addEventListener('click', () => {
  byId('ddl').value = presets.request;
  byId('schema').value = 'request';
  run();
});
byId('test-file').addEventListener('click', () => {
  if (!lastRun) return;
  const assignment = `CASE = json.loads(${JSON.stringify(JSON.stringify(lastRun.config))})  # EXPORTED_CASE`;
  const source = lab.template.replace(lab.templateLine, () => assignment);
  download('test_stateproof_retry.py', source, 'text/x-python');
});
byId('receipt-file').addEventListener('click', () => {
  if (lastRun) download('stateproof_retry_run.json', JSON.stringify(lastRun, null, 2) + '\n', 'application/json');
});
byId('ddl').value = presets.attempt;
byId('quote').textContent = `“${lab.policy.quote}”`;
if (lab.pairResult) {
  const pairs = lab.pairResult;
  byId('pair-result').hidden = false;
  byId('pair-short').hidden = false;
  byId('pair-short').textContent = `Muse: ${pairs.pairs_both_correct}/${pairs.pairs} complete pairs ↘`;
  const controlScores = Object.values(pairs.controls);
  const controls = new Set(controlScores).size === 1 ? `Each of four simple controls got ${controlScores[0]}/${pairs.pairs} complete pairs.` : 'Individual control scores appear in the full report.';
  byId('pair-score').textContent = `Muse got ${pairs.pairs_both_correct}/${pairs.pairs} complete pairs and ${pairs.policy_correct}/${pairs.operations} individual decisions on twelve author-written contracts. ${controls}`;
  for (const example of pairs.example) {
    const div = document.createElement('div');
    const quote = document.createElement('blockquote'); quote.textContent = `“${example.muse_quote}”`;
    const action = document.createElement('strong'); action.textContent = example.muse_action === 'retry_same_key' ? 'Muse allows the same-key retry' : 'Muse calls for verification';
    div.append(quote, action); byId('pair-examples').append(div);
  }
}
for (const observed of lab.redis.cases) byId('redis-case').add(new Option(observed.title, observed.id));
function showRedis() {
  const observed = lab.redis.cases.find(c => c.id === byId('redis-case').value);
  byId('redis-count').textContent = String(observed.entry_count);
  byId('redis-commands').textContent = [observed.first_command,observed.retry_command].map((c,i) => `${i === 0 ? 'FIRST' : 'RETRY'}  ${c.join(' ')}`).join('\n');
  byId('redis-ledger').textContent = `Redis ${lab.redis.version} · observed XRANGE IDs: ${observed.entries.map(x => x.stream_id).join(', ')}`;
}
byId('redis-case').value = 'explicit';
byId('redis-case').addEventListener('change', showRedis);
showRedis();
(async () => {
  try {
    engine = await initSqlJs();
    const db = new engine.Database();
    try { sqliteVersion = db.exec('SELECT sqlite_version()')[0].values[0][0]; } finally { db.close(); }
    byId('ready').textContent = `SQLite ${sqliteVersion} ready · no account or API key`;
    byId('run').disabled = false;
    byId('repair').disabled = false;
  } catch (error) {
    byId('ready').textContent = 'SQLite could not start. Open this page in a browser with WebAssembly enabled.';
    byId('error').textContent = error.message;
    byId('error').hidden = false;
  }
})();
