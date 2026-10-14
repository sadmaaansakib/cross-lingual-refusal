from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from common import save_json, set_seed


def unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)


def evaluate(x: np.ndarray, labels: np.ndarray, direction: np.ndarray) -> dict:
    s = x @ direction
    pred = (s >= np.median(s)).astype(int)
    result = {"balanced_accuracy": float(balanced_accuracy_score(labels, pred))}
    if len(np.unique(labels)) == 2:
        result["roc_auc"] = float(roc_auc_score(labels, s))
    return result


def load_target(stem: str, activation_dir: str, layer: int) -> tuple[np.ndarray, np.ndarray]:
    x = np.load(Path(activation_dir) / f"{stem}.npy", mmap_mode="r")
    meta = pd.read_json(Path(activation_dir) / f"{stem}.metadata.jsonl", lines=True)
    labels = (meta["label"].to_numpy() == "harmful").astype(int)
    if len(labels) != x.shape[1]:
        raise ValueError(f"Metadata rows {len(labels)} != activation examples {x.shape[1]}")
    return np.asarray(x[layer]), labels


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Random-direction negative control: distribution of balanced accuracy / "
                     "ROC-AUC obtained from fixed-seed random unit vectors at the same layer "
                     "and hidden dimension as the estimated harmfulness direction."
    )
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--target-stem", required=True,
                         help="Activation stem to score against, e.g. Qwen2.5-7B-Instruct_en_validation")
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--num-directions", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="results/tables/random_direction_baseline.json")
    args = parser.parse_args()

    set_seed(args.seed)
    x_layer, labels = load_target(args.target_stem, args.activation_dir, args.layer)
    if len(np.unique(labels)) < 2:
        raise ValueError("Need both harmful and harmless examples in the target split")

    hidden_size = x_layer.shape[-1]
    rng = np.random.default_rng(args.seed)

    balanced_accuracies: list[float] = []
    aucs: list[float] = []
    for _ in range(args.num_directions):
        direction = unit(rng.normal(size=hidden_size))
        metric = evaluate(x_layer, labels, direction)
        balanced_accuracies.append(metric["balanced_accuracy"])
        if "roc_auc" in metric:
            aucs.append(metric["roc_auc"])

    ba_arr = np.array(balanced_accuracies)
    result = {
        "target_stem": args.target_stem,
        "layer": args.layer,
        "hidden_size": int(hidden_size),
        "num_directions": args.num_directions,
        "seed": args.seed,
        "balanced_accuracy": {
            "mean": float(ba_arr.mean()),
            "std": float(ba_arr.std()),
            "p2_5": float(np.percentile(ba_arr, 2.5)),
            "p97_5": float(np.percentile(ba_arr, 97.5)),
        },
        "note": "Compare an observed direction's balanced accuracy / AUC against this null "
                "distribution's upper percentile rather than against 0.5 alone; finite-sample "
                "median-split scoring can be biased away from chance.",
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
    print(f"Random-direction baseline BA mean={result['balanced_accuracy']['mean']:.3f} "
          f"p97.5={result['balanced_accuracy']['p97_5']:.3f}")


if __name__ == "__main__":
    main()
