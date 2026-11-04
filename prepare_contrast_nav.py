"""Only link prospectively saved evidence once both runs passed source validation."""
from pathlib import Path
import json
from stateproof.crashlab import digest
page=Path('docs/contrast.html')
summary=Path('docs/contrast-evidence.json')
home=Path('docs/index.html')
readme=Path('README.md')
assert all(p.is_file() for p in (page,summary,home,readme))
r=json.loads(summary.read_text(encoding='utf8'))
assert r['evidence_type']=='TWO_RECORDED_META_RESPONSES_PLUS_DETERMINISTIC_SYNTHETIC_SCORING'
assert r['score']['operations']==12 and r['score']['scenarios']==24
assert r['receipt_sha256']==digest({k:v for k,v in r.items() if k!='receipt_sha256'})
assert r['receipt_sha256'] in page.read_text(encoding='utf8')
s=home.read_text(encoding='utf8')
marker='<!-- CRASHLAB_POLICY_NAV_V1 -->'
assert s.count(marker)==1,'Unexpected homepage layout'
link='''<!-- CRASHLAB_CONTRAST_NAV_V1 -->
<div role="navigation" aria-label="Prospective Muse semantic challenge" style="margin:0 0 18px;padding:12px 16px;border:1px solid #7464a2;border-radius:12px;background:#1d203c;color:#f3eaff;font-size:14px;line-height:1.55">
<strong>Muse contrastive experiment:</strong> <a href="./contrast.html" style="color:#cfc3ff;font-weight:800">Six matched pairs testing retry-policy interpretation</a>.
<span>Two recorded Muse calls; all classifications and simple baselines shown. Small author-built synthetic challenge, not a population benchmark.</span></div>
'''
if '<!-- CRASHLAB_CONTRAST_NAV_V1 -->' not in s:
    home.write_text(s.replace(marker,link+'\n'+marker,1),encoding='utf8')
s=readme.read_text(encoding='utf8')
head='## Interactive demonstrations\n'
assert s.count(head)==1
bullet='- **[Two recorded Muse contrastive policy challenges](https://praneethhere.github.io/stateproof-meta-hackathon/contrast.html)** — six hand-authored minimal semantic pairs in two frozen batches; report model policy grades against transparent weak controls and verified HTTP/SQLite tests.\n'
if bullet not in s:readme.write_text(s.replace(head,head+bullet,1),encoding='utf8')
if Path('stateproof/build_retry_lab.py').is_file():
    from stateproof.build_retry_lab import javascript
    Path('docs/retry-lab-data.js').write_text(javascript(), encoding='utf8')
print('Verified contrastive summary linked to homepage and README')
