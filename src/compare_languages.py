from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, roc_auc_score

from common import load_dataset, save_json


def unit(v):
    return v / (np.linalg.norm(v) + 1e-12)


def fit_direction(x, labels):
    return unit(x[labels == 1].mean(axis=0) - x[labels == 0].mean(axis=0))


def score(direction, x, labels):
    values = x @ direction
    predicted = (values >= np.median(values)).astype(int)
    result = {"balanced_accuracy": float(balanced_accuracy_score(labels, predicted))}
    if len(np.unique(labels)) == 2:
        result["roc_auc"] = float(roc_auc_score(labels, values))
    return result


def load(stem, directory, dataset):
    x = np.load(Path(directory) / f"{stem}.npy", mmap_mode="r")
    meta = pd.read_json(Path(directory) / f"{stem}.metadata.jsonl", lines=True)
    labels = (meta["label"].to_numpy() == "harmful").astype(int)
    return x, labels, meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--source-en", required=True, help="English train activation stem")
    parser.add_argument("--source-bn", required=True, help="Bangla train activation stem")
    parser.add_argument("--target-en", required=True, help="English validation/test activation stem")
    parser.add_argument("--target-bn", required=True, help="Bangla validation/test activation stem")
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--output", default="results/tables/cross_language_comparison.json")
    args = parser.parse_args()

    xe, ye, _ = load(args.source_en, args.activation_dir, None)
    xb, yb, _ = load(args.source_bn, args.activation_dir, None)
    te, tye, _ = load(args.target_en, args.activation_dir, None)
    tb, tyb, _ = load(args.target_bn, args.activation_dir, None)
    de = fit_direction(np.asarray(xe[args.layer]), ye)
    db = fit_direction(np.asarray(xb[args.layer]), yb)

    result = {
        "layer": args.layer,
        "cosine_english_bangla": float(np.dot(de, db)),
        "english_direction_on_english": score(de, np.asarray(te[args.layer]), tye),
        "english_direction_on_bangla": score(de, np.asarray(tb[args.layer]), tyb),
        "bangla_direction_on_bangla": score(db, np.asarray(tb[args.layer]), tyb),
        "bangla_direction_on_english": score(db, np.asarray(te[args.layer]), tye),
        "note": "Use validation for layer selection and test only after freezing the selection rule.",
    }
    save_json(result, args.output)
    print(result)


if __name__ == "__main__":
    main()
