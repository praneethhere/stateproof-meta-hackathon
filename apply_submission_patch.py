"""Conservative submission cleanup. Run from a clean Git checkout at 0e84668.

The patch adds separate files; this script removes prebuild-only tracked Python
files and edits the README without rewriting any Git history. Refuses ambiguous
repositories or a dirty tracked working tree. Untracked notes are not deleted.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually remove legacy tracked files and edit README")
    args = ap.parse_args()
    root = Path.cwd()
    if not (root / ".git").exists() or not (root / "stateproof/crashlab_http.py").exists():
        sys.exit("STOP: Run from the existing StateProof repository root")
    head = git("rev-parse", "--short=7", "HEAD")
    if head != "0e84668":
        sys.exit(f"STOP: expected public HEAD 0e84668, found {head}; inspect latest changes first")
    if subprocess.run(["git", "diff", "--quiet"]).returncode or subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode:
        sys.exit("STOP: tracked working tree or staging area is dirty; preserve current changes before cleanup")
    for required in ("PROVENANCE.md", "POLICY_PROTOCOL.md", "stateproof/crashlab_policy.py", "contracts/policy_challenges.json", "tests/test_crashlab_policy.py"):
        if not (root / required).exists():
            sys.exit(f"STOP: missing patch file {required}")
    paths = git("ls-files", "stateproof", "tests").splitlines()
    legacy = []
    for p in paths:
        filename = Path(p).name
        if p.startswith("stateproof/") and p.endswith(".py"):
            if not filename.startswith("crashlab") and filename != "crashpilot.py":
                legacy.append(p)
        elif p.startswith("tests/") and filename.startswith("test_") and filename.endswith(".py"):
            if not filename.startswith("test_crashlab") and filename != "test_crashpilot.py":
                legacy.append(p)
    print("Legacy tracked Python files proposed for removal:")
    for p in legacy:
        print(" -", p)
    print("Legacy file count:", len(legacy))
    required_legacy = {
        "stateproof/core.py", "stateproof/__main__.py", "stateproof/experiments.py",
        "stateproof/meta_investigator.py", "stateproof/m2_cli.py",
    }
    if not required_legacy.issubset(set(legacy)) or not 20 <= len(legacy) <= 24:
        sys.exit("STOP: unexpected legacy file list. No files removed; inspect list above against the independent audit")
    readme = root / "README.md"
    original = readme.read_text(encoding="utf-8")
    replacements = [
        ("two frozen, independently authored *synthetic* workflows; compare Muse's proposed crash operation with three deterministic strategies",
         "two locally frozen *synthetic* workflows; compare Muse with a writes-first control (the keyword and seeded-random controls selected the same operations)"),
        ("| Frozen case | Muse-selected operation | Muse exposure | Each simple baseline |",
         "| Frozen synthetic case | Muse-selected operation | Muse exposure | Writes-first exposure |"),
        ("Muse exposed a duplicate effect in **2/2** frozen synthetic challenges; writes-first, keyword, and single-seed random each exposed one in **1/2**. The synthetic severity-weighted scores were **8 vs. 2**.",
         "Muse chose a duplicate-exposing operation in **2/2** deliberately constructed synthetic challenges; a writes-first control exposed one in **1/2**. Keyword and one seeded-random strategy made the same operation selections as writes-first and thus were not independent competing results."),
        ("**Local test status:** 271 tests passed on macOS on October 30, 2026. Tests do not substitute for a new live model study or establish research novelty.",
         "**Local test history:** 271 tests previously passed with the earlier StateProof Lab files present. After excluding that earlier work, the CrashLab-only test count must be rechecked from the cleaned repository (125 passed in the November 2 independent review, before the new policy tests). No test count establishes model superiority or novelty."),
        ("The initial StateProof baseline predates later CrashLab modules. The original Git history is preserved; only work genuinely completed during the hackathon window should be represented as hackathon work.",
         "The older StateProof Lab reference implementation, including an October 26 PREBUILD-labelled file, is excluded from the submission tree. Git history remains visible. See [PROVENANCE.md](PROVENANCE.md); Git commit timestamps alone do not prove authoring dates."),
    ]
    updated = original
    for old, new in replacements:
        if updated.count(old) != 1:
            sys.exit(f"STOP: README anchor count is not one: {old[:75]}...")
        updated = updated.replace(old, new, 1)
    extra = '''\n## Contract-to-policy experiment (optional new hackathon component)\n\nThe separate [policy protocol](POLICY_PROTOCOL.md) defines an explicitly bounded test in which Muse Spark 1.3 *proposes* a retry policy from the **public descriptions** of seven synthetic write operations. A deterministic readback-first client then executes 14 loopback HTTP/SQLite fault checks. The trusted adapter must verify request-key deduplication before allowing repeat writes; the model cannot authorize them by assertion. The `always_retry` control is included because it may match model outcomes when the adapter already knows the server semantics.\n\nOffline controls (no Meta API key needed):\n\n```bash\npython -m stateproof.crashlab_policy --strategy conservative --contract contracts/policy_challenges.json\npython -m stateproof.crashlab_policy --strategy always_retry --contract contracts/policy_challenges.json\npython -m stateproof.crashlab_policy --strategy oracle_reference --contract contracts/policy_challenges.json\n```\n\nOne optional, billed Meta API run **after the protocol is committed**:\n\n```bash\npython -m stateproof.crashlab_policy --strategy muse --live --accept-api-cost \\\n  --contract contracts/policy_challenges.json \\\n  --out evidence/policy_muse_original.json \\\n  --public-out docs/policy-evidence.json --html docs/policy.html\n```\n\nDo not cite a Muse policy result or claim the new public page exists until the API run succeeds, the exported files are manually reviewed, and they are pushed. The new policy study uses a deterministic actor, **not a second live Muse actor continuation**.\n'''
    if "## Contract-to-policy experiment" not in updated:
        updated += extra
    # Correct the public planner's strongest-sounding labels as well as README.
    # Both the committed HTML and its Python generator may carry these strings.
    demo_replacements = {
        "Muse · confirmed exposures": "Muse · exposing selections (2 cases)",
        "Strong keyword baseline": "Keyword heuristic (same selections)",
        "Severity-weighted exposures": "Author-assigned severity scores",
        "Equal-budget comparison": "Two-case illustrative comparison",
        "Frozen protocol SHA-256": "Locally frozen protocol SHA-256",
    }
    demo_updates = {}
    for demo_path in (root / "docs/index.html", root / "stateproof/crashlab_showcase.py"):
        if not demo_path.exists():
            sys.exit(f"STOP: expected planner asset {demo_path} missing")
        old = demo_path.read_text(encoding="utf-8")
        new = old
        for phrase, replacement in demo_replacements.items():
            n = new.count(phrase)
            if n > 1:
                sys.exit(f"STOP: ambiguous demo label {phrase} in {demo_path}")
            new = new.replace(phrase, replacement)
        demo_updates[demo_path] = new
    if updated.count("## Contract-to-policy experiment") != 1:
        sys.exit("STOP: expected exactly one new policy section")
    print("README replacements validated; prebuild cleanup is reversible via Git history")
    if not args.apply:
        print("DRY RUN ONLY. Rerun with --apply after inspection.")
        return
    subprocess.check_call(["git", "rm", "--", *legacy])
    readme.write_text(updated, encoding="utf-8")
    for demo_path, content in demo_updates.items():
        demo_path.write_text(content, encoding="utf-8")
        print("Corrected public demo labels:", demo_path.relative_to(root))
    print("Applied cleanup and README correction. Run pytest and inspect git diff before committing.")


if __name__ == "__main__":
    main()
