"""Safely link an existing, verified post-hoc audit after review; idempotent."""
from pathlib import Path
import json
from stateproof.crashlab import digest

home = Path('docs/index.html')
page = Path('docs/audit.html')
evidence = Path('docs/audit-evidence.json')
assert all(x.is_file() for x in (home, page, evidence)), 'Missing expected deployed files'
record = json.loads(evidence.read_text(encoding='utf8'))
assert record['evidence_type'] == 'RECORDED_MUSE_POLICY_PLUS_DETERMINISTIC_SYNTHETIC_DRIFT_AUDIT'
assert record['score']['critical_mismatches'] == 1
assert record['score']['duplicates_after_boundary'] == 0
assert record['separate_live_guard_episode']['evidence_type'] == 'SEPARATE_SAVED_LIVE_MUSE_EPISODE_NOT_M7_CONTINUATION'
assert record['receipt_sha256'] == digest({k:v for k,v in record.items() if k!='receipt_sha256'})
assert record['receipt_sha256'] in page.read_text(encoding='utf8'), 'HTML/evidence mismatch'
text = home.read_text(encoding='utf8')
marker = '<!-- CRASHLAB_POLICY_NAV_V1 -->'
assert text.count(marker) == 1, 'Unexpected home page layout; refuse to modify'
link = '''<!-- CRASHLAB_AUDIT_NAV_V1 -->
<div role="navigation" aria-label="Recorded Muse and executable contract audit" style="margin:0 0 18px;padding:13px 17px;border:1px solid #379783;border-radius:12px;background:#122c31;color:#ebfff9;font-size:14px;line-height:1.55">
<strong>New judge walkthrough:</strong> <a href="./audit.html" style="color:#91ffe5;font-weight:800">Muse policy, synthetic contract drift, and a separately recorded live guard continuation</a>.
<span style="color:#c2d3d3">A deliberately changed local service exposes a false document guarantee; the external boundary refuses unsafe reissue. No provider incident or new model run is claimed for the drift audit.</span>
</div>
'''
if '<!-- CRASHLAB_AUDIT_NAV_V1 -->' not in text:
    home.write_text(text.replace(marker,link+'\n'+marker,1),encoding='utf8')
    print('Homepage now links to contract audit')
else:
    print('Homepage already links to contract audit')
readme=Path('README.md')
assert readme.is_file()
s=readme.read_text(encoding='utf8')
line='- **[Recorded Muse + synthetic contract-drift audit](https://praneethhere.github.io/stateproof-meta-hackathon/audit.html)** — deliberate local sandbox implementation mismatch; actual HTTP/SQLite probe; separate saved live Muse guard continuation. This is a post-hoc demonstration, not a provider incident.\n'
head='## Interactive demonstrations\n'
assert s.count(head)==1
if line not in s:
    readme.write_text(s.replace(head,head+line,1),encoding='utf8')
    print('README now links to the audit')
else:
    print('README already links to the audit')

# The earlier M8B counterfactual STILL has no Muse continuation. Add a separate
# dated observation rather than silently relabeling that replay as a model run.
updated=readme.read_text(encoding='utf8')
note=("\n**Separate November 4 live Muse guard episode:** In a newly recorded "
      "agent run, Muse requested two writes under lost-acknowledgment and stale-read faults; "
      "the hard-stop boundary denied the second HTTP write. Muse continued and reported "
      "`DONE` after observing one ledger effect, matching the independent SQLite oracle "
      "(one episode). This is **not** the continuation of the original M7 failure "
      "or the no-model M8B counterfactual. The separately verified, sanitized tool "
      "sequence appears in the [contract-drift audit](https://praneethhere.github.io/stateproof-meta-hackathon/audit.html).\n")
anchor='The hard-stop guard also blocks a legitimate retry after a *pre-commit timeout*'
assert updated.count(anchor)==1, 'Unexpected README guard section; do not edit'
if note.strip() not in updated:
    updated=updated.replace(anchor,note+'\n'+anchor,1)
    readme.write_text(updated,encoding='utf8')
    print('README distinguishes separate Nov 4 live Muse continuation from M8B replay')
