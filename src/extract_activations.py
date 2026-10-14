from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from common import file_sha256, load_config, load_dataset, resolve_dtype, save_json, set_seed


def format_text(tokenizer, prompt: str) -> str:
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        tokenize=False,
        add_generation_prompt=True,
    )


def get_last_nonpad(hidden: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    last = attention_mask.sum(dim=1).long() - 1
    batch_idx = torch.arange(hidden.shape[0], device=hidden.device)
    return hidden[batch_idx, last]


def extract(args: argparse.Namespace) -> None:
    cfg = load_config(args.config)
    seed = int(cfg["project"]["seed"])
    set_seed(seed)
    dataset = load_dataset(args.dataset or cfg["paths"]["dataset"])
    dataset = dataset[dataset["split"] == args.split].reset_index(drop=True)
    if dataset.empty:
        raise ValueError(f"No rows found for split={args.split}")

    model_id = args.model_id or cfg["model"]["model_id"]
    dtype = resolve_dtype(cfg["model"].get("torch_dtype", "float32"))
    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        revision=cfg["model"].get("revision", "main"),
        trust_remote_code=bool(cfg["model"].get("trust_remote_code", False)),
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=cfg["model"].get("revision", "main"),
        torch_dtype=dtype,
        device_map=cfg["model"].get("device_map", "auto"),
        trust_remote_code=bool(cfg["model"].get("trust_remote_code", False)),
    )
    model.eval()

    batch_size = args.batch_size or int(cfg["extraction"]["batch_size"])
    max_length = int(cfg["extraction"]["max_length"])
    layer_batches: list[torch.Tensor] = []
    metadata: list[dict] = []

    for start in range(0, len(dataset), batch_size):
        batch_df = dataset.iloc[start:start + batch_size]
        texts = [format_text(tokenizer, p) for p in batch_df[args.language + "_prompt"]]
        tokens = tokenizer(
            texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=max_length,
        ).to(model.device)
        with torch.inference_mode():
            result = model(**tokens, output_hidden_states=True, use_cache=False)

        # [layers, batch, hidden]. Exclude embeddings by default for comparable transformer-layer analysis.
        hidden_states = result.hidden_states
        if not bool(cfg["extraction"].get("include_embedding_layer", False)):
            hidden_states = hidden_states[1:]
        selected = torch.stack([
            get_last_nonpad(hidden.float(), tokens["attention_mask"])
            for hidden in hidden_states
        ])
        layer_batches.append(selected.cpu())
        for _, row in batch_df.iterrows():
            metadata.append({
                "pair_id": row["pair_id"],
                "category": row["category"],
                "label": row["label"],
                "split": row["split"],
                "language": args.language,
                "prompt": row[args.language + "_prompt"],
            })

    activations = torch.cat(layer_batches, dim=1).numpy().astype(np.float32)
    out_dir = Path(args.output_dir or cfg["paths"]["activation_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{Path(model_id).name.replace('/', '_')}_{args.language}_{args.split}"
    np.save(out_dir / f"{stem}.npy", activations)
    pd.DataFrame(metadata).to_json(out_dir / f"{stem}.metadata.jsonl", orient="records", lines=True, force_ascii=False)
    save_json({
        "model_id": model_id,
        "language": args.language,
        "split": args.split,
        "rows": len(metadata),
        "shape": list(activations.shape),
        "dtype": str(activations.dtype),
        "pooling": "last_nonpad",
        "dataset_path": str(args.dataset or cfg["paths"]["dataset"]),
        "dataset_sha256": file_sha256(args.dataset or cfg["paths"]["dataset"]),
        "seed": seed,
        "hidden_size": int(activations.shape[-1]),
        "num_layers": int(activations.shape[0]),
    }, out_dir / f"{stem}.manifest.json")
    print(f"Saved activations: {out_dir / (stem + '.npy')} shape={activations.shape}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--dataset")
    parser.add_argument("--model-id")
    parser.add_argument("--language", choices=["en", "bn"], required=True)
    parser.add_argument("--split", choices=["train", "validation", "test"], default="train")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    extract(args)


if __name__ == "__main__":
    main()
