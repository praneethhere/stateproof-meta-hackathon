# Run the six-pair Muse experiment

Push the commit that contains the two fixtures, pair manifest, code, addendum and protocol to `origin/main` before either model call. The runner checks those files against Git. Trials use the two predeclared batches, high reasoning effort, and no automatic model retries. The two model responses are the independent calls. All twelve items and all six paired outcomes appear in the summary.

With the project virtual environment active and `MODEL_API_KEY` set locally, run the following from the repository root. These are billed Meta API calls.

```bash
bash run_muse_pairs.sh --live --accept-api-cost
```

The runner records a per-fixture attempt before contacting Meta and reuses finished receipts. If a model request fails, preserve `evidence/contrast_api_errors.jsonl` and the `.attempt` file. A service retry must be explicitly documented, including the original failure. Keep a copy of the first marker before any disclosed retry. Never repeat a successful call for a different score. Both successful source receipts are necessary for a combined score. Keep the raw `evidence/` directory private.

After inspecting the generated pages and receipts, publish only the named results. A script exit of zero means local synthesis succeeded. It does not publish the results.

```bash
git add docs/contrast{,-a,-b}.html docs/contrast{,-a,-b}-evidence.json docs/index.html README.md
git diff --cached --check && git commit -m "Publish both Muse runs and all six paired grades" && git push origin main
```

The seven-item exploratory negation control matched 7/7 on the examples that motivated it. On the six new hand-authored pairs the four controls each match 6/12 individual cases and 0/6 complete pairs. Those numbers are deterministic control results. The Muse score requires the actual Meta responses. Report the first attempts, the finished pair score and all errors. Do not project these results onto production reliability.
