"""Only run AFTER a real exported docs/policy.html exists and was reviewed."""
from pathlib import Path
import hashlib
import json
from stateproof.crashlab import digest

home = Path('docs/index.html')
policy = Path('docs/policy.html')
receipt = Path("docs/policy-evidence.json")
protocol = Path("POLICY_PROTOCOL.md")
assert home.exists() and policy.exists() and receipt.exists() and protocol.exists(), "Missing live public evidence or protocol"
record = json.loads(receipt.read_text(encoding="utf-8"))
assert record.get("strategy") == "muse" and record.get("meta", {}).get("response_id"), "No completed real Muse policy response"
assert record.get("evidence_type") == "LIVE_META_MODEL_API_RESULT", "Wrong evidence type"
assert record.get("receipt_sha256") == digest({k:v for k,v in record.items() if k != "receipt_sha256"}), "Receipt digest mismatch"
assert record.get("protocol_sha256") == hashlib.sha256(protocol.read_bytes()).hexdigest(), "Protocol was modified after the run"
assert record.get("git_commit_at_run"), "Missing original Git commit"
page = policy.read_text(encoding="utf-8")
assert "RECORDED META MODEL API RESPONSE" in page and record["receipt_sha256"] in page, "HTML does not match saved Muse receipt"
s = home.read_text(encoding='utf-8')
marker = '<!-- CRASHLAB_RECOVERY_NAV_V1 -->'
assert s.count(marker) == 1, 'Unexpected homepage layout: do not edit'
insert = '''<!-- CRASHLAB_POLICY_NAV_V1 -->
<div role="navigation" aria-label="Contract-to-policy evaluation" style="margin:0 0 18px;padding:12px 16px;border:1px solid #345d7d;border-radius:12px;background:#102236;color:#e5f4ff;font-size:14px;line-height:1.55">
<strong>New experiment:</strong> <a href="./policy.html" style="color:#8bd2ff;font-weight:800">Muse-generated retry policy versus synthetic HTTP controls</a>.
<span style="color:#adbad0">Model authors the policy; deterministic tools enforce and test it.</span>
</div>
'''
if '<!-- CRASHLAB_POLICY_NAV_V1 -->' not in s:
    s = s.replace(marker, insert + '\n' + marker, 1)
    home.write_text(s, encoding='utf-8')
    print('Policy navigation added to docs/index.html')
else:
    print('Policy navigation already present')

readme = Path("README.md")
assert readme.exists(), "README.md missing"
text = readme.read_text(encoding="utf-8")
line = "- **[Recorded Muse contract-to-retry-policy evaluation](https://praneethhere.github.io/stateproof-meta-hackathon/policy.html)** — one model-authored policy evaluated by a deterministic client on isolated HTTP + SQLite; trusted adapter verifies retry authorization.\n"
if line not in text:
    heading = "## Interactive demonstrations\n"
    assert text.count(heading) == 1, "Unexpected README; no modification"
    text = text.replace(heading, heading + line, 1)
    readme.write_text(text, encoding="utf-8")
    print("README links to the newly generated policy page")
