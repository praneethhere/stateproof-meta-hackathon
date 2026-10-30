"""Produce a verifiable M2.4 JSON receipt and optional offline HTML demo."""
import argparse
import json
from pathlib import Path
from .m24_runner import run_index
from .m24_report import render_html


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["offline", "meta"], default="offline")
    p.add_argument("--case-index", type=int, default=2)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--html", type=Path)
    args = p.parse_args()
    outputs = [args.out] + ([args.html] if args.html else [])
    if len(set(outputs)) != len(outputs) or any(x.exists() for x in outputs):
        p.error("Output files must be different and must not already exist")
    r = run_index(args.case_index, mode=args.mode)
    for path, content in ((args.out, json.dumps(r, indent=2, sort_keys=True) + "\n"),
                          *(([(args.html, render_html(r))] if args.html else []))):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf8")
        print("Wrote", path)
    print("Gate:", r["gate_supported_status"], "Final:", r["claimed_status"],
          "Cost:", r["cost"], "Mode:", r["mode"])


if __name__ == "__main__":
    main()
