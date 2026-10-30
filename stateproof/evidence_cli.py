"""Offline reference baseline / optional one-case Meta test, no secrets in artifacts."""
import argparse
import json
from pathlib import Path
from .evidence_game import baseline_report, cohort
from .evidence_meta import run_muse


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["offline", "meta"], default="offline")
    p.add_argument("--case-index", type=int, default=0)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    if args.mode == "offline":
        result = baseline_report()
    else:
        cases = cohort()
        if not 0 <= args.case_index < len(cases):
            p.error(f"--case-index must be 0..{len(cases)-1}")
        id_, case = cases[args.case_index]
        result = run_muse(case, id_)
    data = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        if args.out.exists():
            p.error("refusing to overwrite receipt")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(data + "\n")
        print(f"Wrote {args.out}")
    else:
        print(data)

if __name__ == "__main__":
    main()
