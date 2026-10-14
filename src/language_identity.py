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
        description="Language-identity negative control. Fits a direction that separates "
                     "English from Bangla activations for the same split, ignoring the "
                     "harmfulness label entirely, then (a) confirms it trivially separates "
                     "language and (b) reports its cosine similarity against the real "
                     "harmfulness directions so you can tell whether apparent EN-BN alignment "
                     "is actually driven by script/language rather than safety structure."
    )
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--en-stem", required=True, help="English activation stem, e.g. ..._en_train")
    parser.add_argument("--bn-stem", required=True, help="Bangla activation stem for the same split")
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--harm-direction-en-json", default=None,
                         help="Optional analyze_directions.py output for the English harmfulness direction")
    parser.add_argument("--harm-direction-bn-json", default=None,
                         help="Optional analyze_directions.py output for the Bangla harmfulness direction")
    parser.add_argument("--output", default="results/tables/language_identity_baseline.json")
    args = parser.parse_args()

    set_seed(42)
    en_x, en_meta = load_layer(args.en_stem, args.activation_dir, args.layer)
    bn_x, bn_meta = load_layer(args.bn_stem, args.activation_dir, args.layer)

    combined_x = np.concatenate([en_x, bn_x], axis=0)
    language_labels = np.concatenate([np.zeros(len(en_x), dtype=int), np.ones(len(bn_x), dtype=int)])
    direction = fit_direction(combined_x, language_labels)
    self_check = evaluate(combined_x, language_labels, direction)

    result = {
        "en_stem": args.en_stem,
        "bn_stem": args.bn_stem,
        "layer": args.layer,
        "language_direction_self_separation": self_check,
        "note": "self_separation should be near-perfect (it is fit and evaluated on the same "
                "language-labeled data); that is expected and not evidence of anything about "
                "harmfulness. The cosine values below are the actual diagnostic.",
    }

    if args.harm_direction_en_json:
        en_harm = unit(load_harm_direction(args.harm_direction_en_json, args.layer))
        result["cosine_with_english_harm_direction"] = float(np.dot(direction, en_harm))
    if args.harm_direction_bn_json:
        bn_harm = unit(load_harm_direction(args.harm_direction_bn_json, args.layer))
        result["cosine_with_bangla_harm_direction"] = float(np.dot(direction, bn_harm))

    save_json(result, args.output)
    print(f"Language-identity direction self-separation BA="
          f"{self_check['balanced_accuracy']:.3f}. See output for cosine diagnostics.")


if __name__ == "__main__":
    main()
