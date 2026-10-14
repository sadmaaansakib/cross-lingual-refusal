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


def load_layer(stem: str, activation_dir: str, layer: int) -> tuple[np.ndarray, pd.DataFrame]:
    x = np.load(Path(activation_dir) / f"{stem}.npy", mmap_mode="r")
    meta = pd.read_json(Path(activation_dir) / f"{stem}.metadata.jsonl", lines=True)
    if len(meta) != x.shape[1]:
        raise ValueError(f"Metadata rows {len(meta)} != activation examples {x.shape[1]}")
    return np.asarray(x[layer]), meta


def build_topic_subspace(x: np.ndarray, categories: np.ndarray, num_components: int) -> np.ndarray:
    """
    Fits a topic-identity subspace using between-class scatter across harmless
    categories only (i.e. categories that carry no label information in this
    dataset). Returns an orthonormal basis (num_components, hidden) spanning
    the directions that best separate topic, independent of the harmful vs.
    harmless split.
    """
    unique_cats = sorted(set(categories.tolist()))
    if len(unique_cats) < 2:
        raise ValueError("Need at least 2 distinct categories to build a topic subspace")
    centroids = np.stack([x[categories == c].mean(axis=0) for c in unique_cats])
    grand_mean = centroids.mean(axis=0)
    centered = centroids - grand_mean
    # SVD of the between-category centroid matrix gives the directions along
    # which topic identity varies most; this is a between-class-scatter PCA.
    _, s, vt = np.linalg.svd(centered, full_matrices=False)
    num_components = min(num_components, vt.shape[0])
    return vt[:num_components]


def project_out(x: np.ndarray, basis: np.ndarray) -> np.ndarray:
    """Removes the component of each row of x lying in the subspace spanned by basis (rows orthonormal)."""
    coeffs = x @ basis.T
    return x - coeffs @ basis


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Topic-projection residualization. In this dataset, category and label "
                     "are perfectly confounded (every category is 100%% one label), so a "
                     "harmful/harmless direction cannot be distinguished from a topic-identity "
                     "direction by classification alone. This script fits a topic-identity "
                     "subspace from the HARMLESS categories (which vary in topic without "
                     "varying in label), projects that subspace out of the activations, and "
                     "re-measures harmful/harmless separability in the residual space. If "
                     "separability collapses, the original signal was substantially topical; "
                     "if it survives, some harm-specific structure exists beyond topic."
    )
    parser.add_argument("--activation-dir", default="activations")
    parser.add_argument("--stem", required=True, help="Activation stem to analyze, e.g. Qwen2.5-7B-Instruct_en_train")
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--num-topic-components", type=int, default=5,
                         help="Number of leading topic-subspace dimensions to remove (<= number of harmless categories - 1)")
    parser.add_argument("--output", default="results/tables/topic_residualized.json")
    args = parser.parse_args()

    set_seed(42)
    x_layer, meta = load_layer(args.stem, args.activation_dir, args.layer)
    labels = (meta["label"].to_numpy() == "harmful").astype(int)
    categories = meta["category"].to_numpy()

    if len(np.unique(labels)) < 2:
        raise ValueError("Need both harmful and harmless examples in this stem")

    harmless_mask = labels == 0
    harmless_x = x_layer[harmless_mask]
    harmless_categories = categories[harmless_mask]
    if len(set(harmless_categories.tolist())) < 2:
        raise ValueError("Need at least 2 distinct harmless categories to define a topic subspace")

    topic_basis = build_topic_subspace(harmless_x, harmless_categories, args.num_topic_components)

    original = evaluate(x_layer, labels, fit_direction(x_layer, labels))

    residual_x = project_out(x_layer, topic_basis)
    residual_direction = fit_direction(residual_x, labels)
    residualized = evaluate(residual_x, labels, residual_direction)

    result = {
        "stem": args.stem,
        "layer": args.layer,
        "num_topic_components_removed": topic_basis.shape[0],
        "harmless_categories_used": sorted(set(harmless_categories.tolist())),
        "original_balanced_accuracy": original,
        "topic_residualized_balanced_accuracy": residualized,
        "balanced_accuracy_retained_fraction": (
            None if original["balanced_accuracy"] <= 0.5 else
            float((residualized["balanced_accuracy"] - 0.5) / (original["balanced_accuracy"] - 0.5))
        ),
        "note": "balanced_accuracy_retained_fraction near 1.0 means separability survives "
                "topic removal (evidence of harm-specific structure); near 0.0 means the "
                "original signal was almost entirely explained by topic identity. Because "
                "the topic subspace is fit only from harmless-category variation, this is a "
                "conservative test -- it can only remove topic structure that is visible "
                "without using label information at all.",
    }
    save_json(result, args.output)
    print(f"Original BA={original['balanced_accuracy']:.3f} -> "
          f"Residualized BA={residualized['balanced_accuracy']:.3f} "
          f"(retained fraction={result['balanced_accuracy_retained_fraction']})")


if __name__ == "__main__":
    main()
