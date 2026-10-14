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


def load_layer(stem: str, activation_dir: str, layer: int) -> tuple[np.ndarray, np.ndarray]:
    x = np.load(Path(activation_dir) / f"{stem}.npy", mmap_mode="r")
    meta = pd.read_json(Path(activation_dir) / f"{stem}.metadata.jsonl", lines=True)
    labels = (meta["label"].to_numpy() == "harmful").astype(int)
    if len(labels) != x.shape[1]:
        raise ValueError(f"Metadata rows {len(labels)} != activation examples {x.shape[1]}")
    return np.asarray(x[layer]), labels


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Shuffled-label negative control: permute harmful/harmless labels within "
                     "the training split before estimating a difference-in-means direction, "
                     "then evaluate on a held-out target split. Repeated over many permutations "
                     "to give a null distribution for the observed (correctly labeled) transfer score."
    )
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--source-stem", required=True,
                         help="Training activation stem used to fit the direction")
    parser.add_argument("--target-stem", required=True,
                         help="Held-out activation stem (validation or test) to evaluate on")
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--num-permutations", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/tables/shuffled_label_baseline.json")
    args = parser.parse_args()

    set_seed(args.seed)
    source_x, source_labels = load_layer(args.source_stem, args.activation_dir, args.layer)
    target_x, target_labels = load_layer(args.target_stem, args.activation_dir, args.layer)
    if len(np.unique(source_labels)) < 2 or len(np.unique(target_labels)) < 2:
        raise ValueError("Need both harmful and harmless examples in source and target splits")

    rng = np.random.default_rng(args.seed)
    balanced_accuracies: list[float] = []
    aucs: list[float] = []
    for _ in range(args.num_permutations):
        shuffled = rng.permutation(source_labels)
        # A degenerate permutation (all one class) cannot define a direction; resample it.
        while len(np.unique(shuffled)) < 2:
            shuffled = rng.permutation(source_labels)
        direction = fit_direction(source_x, shuffled)
        metric = evaluate(target_x, target_labels, direction)
        balanced_accuracies.append(metric["balanced_accuracy"])
        if "roc_auc" in metric:
            aucs.append(metric["roc_auc"])

    ba_arr = np.array(balanced_accuracies)
    result = {
        "source_stem": args.source_stem,
        "target_stem": args.target_stem,
        "layer": args.layer,
        "num_permutations": args.num_permutations,
        "seed": args.seed,
        "balanced_accuracy": {
            "mean": float(ba_arr.mean()),
            "std": float(ba_arr.std()),
            "p2_5": float(np.percentile(ba_arr, 2.5)),
            "p97_5": float(np.percentile(ba_arr, 97.5)),
        },
        "note": "The correctly labeled direction's transfer score (from analyze_directions.py / "
                "compare_languages.py) should clear this distribution's upper percentile to be "
                "considered evidence of real harmfulness-related structure rather than an "
                "estimator artifact.",
    }
    if aucs:
        auc_arr = np.array(aucs)
        result["roc_auc"] = {
            "mean": float(auc_arr.mean()),
            "std": float(auc_arr.std()),
            "p2_5": float(np.percentile(auc_arr, 2.5)),
            "p97_5": float(np.percentile(auc_arr, 97.5)),
        }
    save_json(result, args.output)
    print(f"Shuffled-label baseline BA mean={result['balanced_accuracy']['mean']:.3f} "
          f"p97.5={result['balanced_accuracy']['p97_5']:.3f}")


if __name__ == "__main__":
    main()
