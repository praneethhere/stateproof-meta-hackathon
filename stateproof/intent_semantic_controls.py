"""Retrospective, isolated-description controls for the frozen six-pair study."""

from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re

from stateproof.crashlab import digest
from stateproof.intent_study import ROOT

MODEL = "cross-encoder/nli-deberta-v3-small"
REVISION = "fa2804872c3b4bd748f38c0185cc85775361e735"
HYPOTHESES = (
    "Repeating this write with the same identifier is guaranteed not to create or charge for the business effect a second time.",
    "Repeating this write with the same identifier may create or charge for the business effect a second time.",
)


def operations(path):
    data = json.loads(path.read_text())
    return [
        (
            row["id"],
            row["description"],
            data["private_simulator"][row["id"]]["dedupe"] == "request_key",
        )
        for row in data["public"]["operations"]
        if row["method"] != "GET"
    ]


def grams(text):
    counts = Counter()
    for word in re.findall(r"\w+|[^\w\s]", text.casefold()):
        padded = " " + word + " "
        for width in (3, 4, 5):
            counts.update(padded[i : i + width] for i in range(len(padded) - width + 1))
    return counts


def nearest_descriptions(training, descriptions):
    frequencies = Counter()
    for _, text, _ in training:
        frequencies.update(grams(text).keys())
    weights = {
        g: math.log((1 + len(training)) / (1 + count)) + 1
        for g, count in frequencies.items()
    }

    def vector(text):
        features = {g: k * weights[g] for g, k in grams(text).items() if g in weights}
        norm = math.sqrt(sum(value * value for value in features.values())) or 1
        return {g: v / norm for g, v in features.items()}

    candidates = [(op, vector(text), safe) for op, text, safe in training]
    decisions = []
    for text in descriptions:
        query = vector(text)
        ranked = sorted(
            (
                (-sum(w * other.get(g, 0) for g, w in query.items()), op, safe)
                for op, other, safe in candidates
            )
        )
        negative_score, op, safe = ranked[0]
        decisions.append({"retry": safe, "neighbor_id": op, "cosine": -negative_score})
    return decisions


def nli_descriptions(model_dir, descriptions):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    pin = json.loads((ROOT / "research/nli-files.json").read_text())
    hashes = {}
    for name in (
        "model.safetensors",
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "added_tokens.json",
        "spm.model",
    ):
        with (model_dir / name).open("rb") as handle:
            hashes[name] = hashlib.file_digest(handle, "sha256").hexdigest()
    if pin["model"] != MODEL or pin["revision"] != REVISION or hashes != pin["sha256"]:
        raise ValueError("Local checkpoint differs from the pinned upstream files")
    import torch
    import transformers
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    tokenizer = AutoTokenizer.from_pretrained(
        model_dir, local_files_only=True, trust_remote_code=False
    )
    model = (
        AutoModelForSequenceClassification.from_pretrained(
            model_dir,
            local_files_only=True,
            use_safetensors=True,
            trust_remote_code=False,
        )
        .cpu()
        .eval()
    )
    labels = {name.casefold(): int(i) for i, name in model.config.id2label.items()}
    if "entailment" not in labels:
        raise ValueError("Checkpoint does not declare the entailment class")
    decisions = []
    for description in descriptions:
        batch = tokenizer(
            [description] * 2, list(HYPOTHESES), padding=True, return_tensors="pt"
        )
        with torch.inference_mode():
            logits = model(**batch).logits.tolist()
        yes, no = (row[labels["entailment"]] for row in logits)
        decisions.append(
            {
                "retry": yes > no,
                "entailment_retry": yes,
                "entailment_verify": no,
                "logits": logits,
            }
        )
    return decisions, {
        "checkpoint": MODEL,
        "revision": REVISION,
        "weights_and_tokenizer_sha256": hashes,
        "hypotheses": HYPOTHESES,
        "labels": labels,
        "transformers": transformers.__version__,
        "torch": torch.__version__,
    }


def evaluate(model_dir):
    paths = [ROOT / "contracts" / f"contrastive_semantics_{name}.json" for name in "ab"]
    training_path = ROOT / "contracts/policy_challenges.json"
    training = operations(training_path)
    items = [row for path in paths for row in operations(path)]
    descriptions = [text for _, text, _ in items]
    refs = {op: safe for op, _, safe in items}
    pairing = json.loads((ROOT / "contracts/contrastive_pair_map.json").read_text())[
        "pairs"
    ]
    nearest = nearest_descriptions(training, descriptions)
    nli, meta = nli_descriptions(model_dir, descriptions)
    published = json.loads((ROOT / "docs/contrast-evidence.json").read_text())
    if published["receipt_sha256"] != digest(
        {k: v for k, v in published.items() if k != "receipt_sha256"}
    ):
        raise ValueError(
            "The published original experiment receipt does not match its checksum"
        )
    mrows = {
        r["operation_id"]: r["muse_action"] == "retry_same_key"
        for r in published["operations"]
    }
    grades = {}
    for name, predictions in [
        ("recorded_muse", [{"retry": mrows[op]} for op, _, _ in items]),
        ("nearest_seven", nearest),
        ("frozen_nli", nli),
    ]:
        rows = {
            op: {
                **prediction,
                "reference_retry": refs[op],
                "correct": prediction["retry"] == refs[op],
            }
            for (op, _, _), prediction in zip(items, predictions)
        }
        correct_pairs = [
            p["name"]
            for p in pairing
            if rows[p["safe_id"]]["correct"] and rows[p["unsafe_id"]]["correct"]
        ]
        grades[name] = {
            "matched": sum(x["correct"] for x in rows.values()),
            "operations": len(rows),
            "pairs_both": len(correct_pairs),
            "pairs": len(pairing),
            "correct_pairs": correct_pairs,
            "rows": rows,
        }
    report = {
        "schema": "stateproof-retrospective-semantic-controls-v1",
        "original_summary_sha256": published["receipt_sha256"],
        "protocol_sha256": hashlib.sha256(
            (ROOT / "INTENT_STUDY_PROTOCOL.md").read_bytes()
        ).hexdigest(),
        "input_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [training_path, *paths]
        },
        "nli": meta,
        "grades": grades,
        "scope": "Retrospective on 12 author-written items. NLI and nearest neighbor see one item at a time. Muse saw six per call, produced evidence quotes, and had the paired clauses in context.",
    }
    report["sha256"] = digest(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model-dir",
        required=True,
        type=Path,
        help="Local safetensors snapshot of the declared Hugging Face revision",
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Use a new output path")
    result = evaluate(args.model_dir)
    with args.out.open("x", encoding="utf8") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
    print({k: (v["matched"], v["pairs_both"]) for k, v in result["grades"].items()})


if __name__ == "__main__":
    main()
