from __future__ import annotations

import csv
from pathlib import Path

path = Path("data/processed/prompts.csv")
with path.open("r", encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
fields = list(rows[0])

pair_ids = sorted({r["pair_id"] for r in rows})
# Preserve the first 60 existing pairs' split assignments, then make the final
# 65 pairs deterministic: 15 train, 15 validation, 35 test would not be balanced.
# Instead assign all pairs by stable order for a clean 75/25/25 split.
for idx, pair_id in enumerate(pair_ids):
    split = "train" if idx < 75 else "validation" if idx < 100 else "test"
    for row in rows:
        if row["pair_id"] == pair_id:
            row["split"] = split

with path.open("w", encoding="utf-8", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
print(f"Rebalanced {len(pair_ids)} pairs / {len(rows)} rows")
