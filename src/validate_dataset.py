from __future__ import annotations

import argparse
from pathlib import Path

from common import load_dataset, save_json

REQUIRED = {
    "pair_id", "category", "en_prompt", "bn_prompt", "label", "split",
    "translation_status", "difficulty", "source"
}
VALID_LABELS = {"harmful", "harmless"}
VALID_SPLITS = {"train", "validation", "test"}


def validate(path: str) -> dict:
    df = load_dataset(path)
    errors: list[str] = []
    warnings: list[str] = []

    missing_columns = REQUIRED - set(df.columns)
    if missing_columns:
        errors.append(f"Missing columns: {sorted(missing_columns)}")
        return {"ok": False, "errors": errors, "warnings": warnings}

    for col in REQUIRED:
        if df[col].astype(str).str.strip().eq("").any():
            errors.append(f"Blank values found in required column: {col}")

    if not df["label"].isin(VALID_LABELS).all():
        errors.append(f"Labels must be one of {sorted(VALID_LABELS)}")
    if not df["split"].isin(VALID_SPLITS).all():
        errors.append(f"Splits must be one of {sorted(VALID_SPLITS)}")

    pair_sizes = df.groupby("pair_id").size()
    if (pair_sizes != 2).any():
        errors.append("Each pair_id must have exactly two rows: one harmful and one harmless")

    # A semantic pair must remain in exactly one split and contain both labels.
    split_counts = df.groupby("pair_id")["split"].nunique()
    if (split_counts > 1).any():
        errors.append("Some pair_id values occur across multiple splits")
    labels_per_pair = df.groupby("pair_id")["label"].nunique()
    if (labels_per_pair != 2).any():
        errors.append("Each pair_id must contain both harmful and harmless labels")

    # Each pair should have aligned bilingual fields.
    if df["en_prompt"].str.contains("REPLACE_WITH|PLACEHOLDER", case=False, regex=True).any():
        warnings.append("Placeholder prompts remain in the dataset")
    if df["bn_prompt"].str.contains("REPLACE_WITH|PLACEHOLDER", case=False, regex=True).any():
        warnings.append("Placeholder Bangla translations remain in the dataset")
    if (df.groupby("split")["label"].value_counts().groupby(level=0).size() < 2).any():
        warnings.append("At least one split does not contain both labels")
    if (df["translation_status"] != "human_verified").any():
        warnings.append("Some translations are not marked human_verified")

    summary = {
        "rows": int(len(df)),
        "pairs": int(df["pair_id"].nunique()),
        "by_split_label": {
            str(split): {str(label): int(n) for label, n in group["label"].value_counts().items()}
            for split, group in df.groupby("split")
        },
        "categories": sorted(df["category"].unique().tolist()),
        "errors": errors,
        "warnings": warnings,
        "ok": not errors,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--report", default="results/tables/dataset_validation.json")
    args = parser.parse_args()
    report = validate(args.input)
    save_json(report, args.report)
    print(f"Dataset valid: {report['ok']}")
    for message in report["errors"]:
        print(f"ERROR: {message}")
    for message in report["warnings"]:
        print(f"WARNING: {message}")
    raise SystemExit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
