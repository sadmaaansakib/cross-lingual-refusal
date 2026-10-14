from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from common import save_json, set_seed


def unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)


def fit_direction(x: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return unit(x[labels == 1].mean(axis=0) - x[labels == 0].mean(axis=0))


def evaluate(x: np.ndarray, labels: np.ndarray, direction: np.ndarray) -> dict:
    s = x @ direction
    pred = (s >= np.median(s)).astype(int)
    result = {"balanced_accuracy": float(balanced_accuracy_score(labels, pred))}
    if len(np.unique(labels)) == 2:
        result["roc_auc"] = float(roc_auc_score(labels, s))
    return result


def load(stem: str, activation_dir: str) -> tuple[np.ndarray, np.ndarray]:
    x = np.load(Path(activation_dir) / f"{stem}.npy", mmap_mode="r")
    meta = pd.read_json(Path(activation_dir) / f"{stem}.metadata.jsonl", lines=True)
    labels = (meta["label"].to_numpy() == "harmful").astype(int)
    if len(labels) != x.shape[1]:
        raise ValueError(f"Metadata rows {len(labels)} != activation examples {x.shape[1]}")
    return x, labels


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Layer-mismatch negative control. Fits a direction at --layer on the "
                     "training split, then applies it to the target split's activations at "
                     "--mismatch-layer (a different, non-corresponding layer) instead of the "
                     "matched layer. Reports both the matched-layer and mismatched-layer scores "
                     "so you can confirm transfer performance is layer-specific rather than an "
                     "artifact that would appear at any layer."
    )
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--source-stem", required=True, help="Training activation stem to fit the direction on")
    parser.add_argument("--target-stem", required=True, help="Held-out activation stem to evaluate on")
    parser.add_argument("--layer", type=int, required=True, help="Layer used to fit the direction (matched layer)")
    parser.add_argument("--mismatch-layer", type=int, required=True,
                         help="Different layer to apply the same direction to, as a negative control")
    parser.add_argument("--output", default="results/tables/layer_mismatch_baseline.json")
    args = parser.parse_args()

    if args.mismatch_layer == args.layer:
        raise ValueError("--mismatch-layer must differ from --layer to serve as a negative control")

    set_seed(42)
    source_x, source_labels = load(args.source_stem, args.activation_dir)
    target_x, target_labels = load(args.target_stem, args.activation_dir)
    if len(np.unique(source_labels)) < 2 or len(np.unique(target_labels)) < 2:
        raise ValueError("Need both harmful and harmless examples in source and target splits")

    direction = fit_direction(np.asarray(source_x[args.layer]), source_labels)

    matched_score = evaluate(np.asarray(target_x[args.layer]), target_labels, direction)
    mismatched_score = evaluate(np.asarray(target_x[args.mismatch_layer]), target_labels, direction)

    result = {
        "source_stem": args.source_stem,
        "target_stem": args.target_stem,
        "fit_layer": args.layer,
        "mismatch_layer": args.mismatch_layer,
        "matched_layer_score": matched_score,
        "mismatched_layer_score": mismatched_score,
        "note": "matched_layer_score should clearly exceed mismatched_layer_score. If they are "
                "similar, apparent transfer may not be tied to a layer-specific representation.",
    }
    save_json(result, args.output)
    print(f"Matched BA={matched_score['balanced_accuracy']:.3f} "
          f"Mismatched BA={mismatched_score['balanced_accuracy']:.3f}")


if __name__ == "__main__":
    main()
