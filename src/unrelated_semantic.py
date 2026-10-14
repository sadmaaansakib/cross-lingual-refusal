from __future__ import annotations

import argparse
import json
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


def load_layer(stem: str, activation_dir: str, layer: int) -> tuple[np.ndarray, pd.DataFrame]:
    x = np.load(Path(activation_dir) / f"{stem}.npy", mmap_mode="r")
    meta = pd.read_json(Path(activation_dir) / f"{stem}.metadata.jsonl", lines=True)
    if len(meta) != x.shape[1]:
        raise ValueError(f"Metadata rows {len(meta)} != activation examples {x.shape[1]}")
    return np.asarray(x[layer]), meta


def load_harm_direction(path: str, layer: int) -> np.ndarray:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return np.asarray(payload["directions_by_layer"][str(layer)], dtype=np.float64)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unrelated-semantic negative control. Fits a direction contrasting two "
                     "HARMLESS categories (e.g. science vs daily_life) at the same layer/pooling, "
                     "then scores it on a held-out target split's harmful-vs-harmless labels. "
                     "A specific, safety-related direction should outperform this baseline; if "
                     "this benign contrast transfers just as well, the earlier transfer result "
                     "likely reflects generic semantic structure rather than harmfulness."
    )
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--source-stem", required=True, help="Training activation stem to fit the contrast on")
    parser.add_argument("--category-a", required=True, help="First harmless category, e.g. science")
    parser.add_argument("--category-b", required=True, help="Second harmless category, e.g. daily_life")
    parser.add_argument("--target-stem", required=True, help="Held-out stem to evaluate transfer on")
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--harm-direction-json", default=None,
                         help="Optional analyze_directions.py output to report cosine similarity against")
    parser.add_argument("--output", default="results/tables/unrelated_semantic_baseline.json")
    args = parser.parse_args()

    set_seed(42)
    source_x, source_meta = load_layer(args.source_stem, args.activation_dir, args.layer)
    mask = (source_meta["label"] == "harmless") & (source_meta["category"].isin([args.category_a, args.category_b]))
    if mask.sum() < 4:
        raise ValueError(
            f"Fewer than 4 harmless examples found for categories "
            f"{args.category_a!r}/{args.category_b!r} in {args.source_stem}"
        )
    subset_x = source_x[mask.to_numpy()]
    subset_labels = (source_meta.loc[mask, "category"] == args.category_b).to_numpy().astype(int)
    if len(np.unique(subset_labels)) < 2:
        raise ValueError("Need examples from both categories to fit a contrast direction")
    direction = fit_direction(subset_x, subset_labels)

    target_x, target_meta = load_layer(args.target_stem, args.activation_dir, args.layer)
    target_labels = (target_meta["label"].to_numpy() == "harmful").astype(int)
    transfer = evaluate(target_x, target_labels, direction)

    result = {
        "source_stem": args.source_stem,
        "category_a": args.category_a,
        "category_b": args.category_b,
        "target_stem": args.target_stem,
        "layer": args.layer,
        "unrelated_direction_transfer_to_harmfulness": transfer,
        "note": "Compare this transfer score against the real harmfulness direction's transfer "
                "score on the same target split. It should be noticeably lower if the effect is "
                "specific to harmfulness rather than generic semantic separation.",
    }
    if args.harm_direction_json:
        harm_direction = unit(load_harm_direction(args.harm_direction_json, args.layer))
        result["cosine_with_harm_direction"] = float(np.dot(direction, harm_direction))

    save_json(result, args.output)
    print(f"Unrelated-semantic baseline transfer BA={transfer['balanced_accuracy']:.3f}")


if __name__ == "__main__":
    main()
