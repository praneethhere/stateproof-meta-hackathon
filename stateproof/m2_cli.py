"""Run: python -m stateproof.m2_cli --mode fixed --target gateway"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from .experiments import PUBLIC_CONTRACTS, fixed_baseline, random_baseline
from .meta_investigator import investigate


def main():
    p = argparse.ArgumentParser(description="Synthetic failure discovery, with independent ledger oracle")
    p.add_argument("--mode", choices=("fixed", "random", "meta"), default="fixed")
    p.add_argument("--target", choices=tuple(PUBLIC_CONTRACTS), default="gateway")
    p.add_argument("--budget", type=int, choices=(1, 2, 3, 4), default=2)
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("--out", type=Path, help="Save the receipt JSON to an explicitly chosen local path")
    args = p.parse_args()
    if args.mode == "fixed":
        receipt = fixed_baseline(args.target, args.budget)
    elif args.mode == "random":
        receipt = random_baseline(args.target, args.seed, args.budget)
    else:
        receipt = investigate(args.target, budget=args.budget)
    payload = json.dumps(receipt, indent=2, sort_keys=True)
    print(payload)
    if args.out:
        if args.out.exists():
            p.error("Will not overwrite an existing evidence receipt; use a new filename")
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"Evidence saved: {args.out}")


if __name__ == "__main__":
    main()
