#!/usr/bin/env bash
# Run from the repository root after pushing the frozen inputs to origin/main.
set -eu
if [[ "${1-}" != '--live' || "${2-}" != '--accept-api-cost' || $# -ne 2 ]]; then
  echo 'Usage: bash run_muse_pairs.sh --live --accept-api-cost' >&2
  exit 2
fi
failed=0
for fixture in a b; do
  if [[ -f "docs/contrast-${fixture}-evidence.json" && -f "docs/contrast-${fixture}.html" ]]; then
    echo "Using the saved response for fixture ${fixture}."
  elif ! python -m stateproof.crashlab_contrastive_runner --fixture "$fixture" --live --accept-api-cost; then
    failed=1
  fi
done
[[ $failed -eq 0 ]] || { echo 'Both receipts are needed for the combined score. Preserve any failed attempt.' >&2; exit 1; }
if [[ ! -f docs/contrast-evidence.json ]]; then
  python -m stateproof.crashlab_contrastive_summary
fi
python prepare_contrast_nav.py
