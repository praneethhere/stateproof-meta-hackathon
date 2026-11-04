#!/usr/bin/env python3
"""Safely add a judge-facing walkthrough without modifying existing experiment output."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent
original = root / 'docs/index.html'
source = root / 'docs/experience.html'
readme = root / 'README.md'
assert original.is_file() and source.is_file() and readme.is_file(), 'Run inside the repo after unpacking the ZIP'
assert (root/'docs/recovery.html').is_file() and (root/'docs/audit.html').is_file(), 'Expected live demo pages missing'
assert (root/'docs/policy.html').is_file(), 'Expected policy demo missing'
html = original.read_text()
assert '<body' in html.lower(), 'Unexpected index.html structure; refused to edit'
assert 'experience.html' not in html, 'Experience link already added to homepage'
link = ('<div style="margin:12px auto 18px;max-width:880px;padding:14px 18px;'
        'border:1px solid #39d5ac;border-radius:12px;background:#082b29;'
        'color:#e9fff7;text-align:center;font:600 16px system-ui,sans-serif;">'
        '🏁 New: <a href="./experience.html" style="color:#8fffea;">'
        'Start with the judge-facing guided demonstration →</a></div>')
idx = html.lower().index('>',html.lower().index('<body')) + 1
new_html = html[:idx] + '\n' + link + '\n' + html[idx:]
original.write_text(new_html)
text = readme.read_text()
marker='# StateProof CrashLab'
assert marker in text, 'Unexpected README heading; refused to edit'
link_md=('\n**Start here — guided judge demo:** '
         '[Observe the Muse failure, guarded continuation, and contract audit]'
         '(https://praneethhere.github.io/stateproof-meta-hackathon/experience.html). '
         'This is an interactive playback of recorded and deterministic local experiments, not a hosted model endpoint.\n')
if 'guided judge demo' not in text:
    text=text.replace(marker,marker+'\n'+link_md,1)
    readme.write_text(text)
print('Installed docs/experience.html')
print('Added a judge-demo link to docs/index.html and README.md')
print('Existing pages, receipts, protocols, and source code were not replaced')
