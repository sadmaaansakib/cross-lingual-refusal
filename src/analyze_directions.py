from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from common import load_config, load_dataset, save_json, set_seed


def unit(v: np.ndarray) -> np.ndarray:
    return v / (np.linalg.norm(v) + 1e-12)


def fit_direction(x: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return unit(x[labels == 1].mean(axis=0) - x[labels == 0].mean(axis=0))


def scores(x: np.ndarray, direction: np.ndarray) -> np.ndarray:
    return x @ direction


def evaluate(x: np.ndarray, labels: np.ndarray, direction: np.ndarray) -> dict:
    s = scores(x, direction)
    pred = (s >= np.median(s)).astype(int)
    result = {"balanced_accuracy": float(balanced_accuracy_score(labels, pred))}
    if len(np.unique(labels)) == 2:
        result["roc_auc"] = float(roc_auc_score(labels, s))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--dataset", default="data/processed/prompts.csv")
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--activation-stem", required=True, help="Stem without .npy, e.g. Qwen2.5-7B-Instruct_en_train")
    parser.add_argument("--output", default="results/tables/directions.json")
    args = parser.parse_args()
    cfg = load_config(args.config)
    set_seed(int(cfg["project"]["seed"]))

    x = np.load(Path(args.activation_dir) / f"{args.activation_stem}.npy", mmap_mode="r")
    meta_path = Path(args.activation_dir) / f"{args.activation_stem}.metadata.jsonl"
    meta = pd.read_json(meta_path, lines=True)
    labels = (meta["label"].to_numpy() == "harmful").astype(int)
    if len(labels) != x.shape[1]:
        raise ValueError(f"Metadata rows {len(labels)} != activation examples {x.shape[1]}")
    if len(np.unique(labels)) < 2:
        raise ValueError("Need both harmful and harmless examples")

    rows = []
    directions = {}
    for layer in range(x.shape[0]):
        direction = fit_direction(np.asarray(x[layer]), labels)
        metric = evaluate(np.asarray(x[layer]), labels, direction)
        rows.append({"layer": layer, **metric, "direction_norm": float(np.linalg.norm(direction))})
        directions[str(layer)] = direction.tolist()

    result = {
        "activation_stem": args.activation_stem,
        "shape": list(x.shape),
        "metrics_by_layer": rows,
        "directions_by_layer": directions,
        "selection_note": "This script provides descriptive train-split scores. Select layers using a held-out validation split before final test evaluation.",
    }
    save_json(result, args.output)
    best = max(rows, key=lambda r: r["balanced_accuracy"])
    print(f"Best descriptive layer: {best['layer']} BA={best['balanced_accuracy']:.3f}")


if __name__ == "__main__":
    main()
