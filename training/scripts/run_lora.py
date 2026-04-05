#!/usr/bin/env python3
"""
Fine-tuning LoRA / QLoRA lokalnego modelu.

Użycie:
    python run_lora.py --dataset /app/output/dataset.jsonl --model qwen3:4b

Wyjście:
    /app/output/<output_name>/  – wagi LoRA + scalone wagi modelu

Następnie eksportuj do GGUF:
    python export_gguf.py --model /app/output/<output_name>
"""

import argparse
import json
import os
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, TaskType
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from trl import SFTTrainer

# ─── Mapowanie krótkich nazw Ollama → HuggingFace ────────────────────────────
MODEL_MAP = {
    "qwen3:4b":          "Qwen/Qwen2.5-3B-Instruct",
    "qwen3:8b":          "Qwen/Qwen2.5-7B-Instruct",
    "qwen2.5:7b":        "Qwen/Qwen2.5-7B-Instruct",
    "qwen2.5-coder:7b":  "Qwen/Qwen2.5-Coder-7B-Instruct",
    "llama3.2:3b":       "meta-llama/Llama-3.2-3B-Instruct",
    "mistral:7b":        "mistralai/Mistral-7B-Instruct-v0.3",
    "phi3:mini":         "microsoft/Phi-3-mini-4k-instruct",
}

ALPACA_TEMPLATE = (
    "### Instruction:\n{instruction}\n\n"
    "### Input:\n{input}\n\n"
    "### Response:\n{output}"
)


def load_jsonl(path: str) -> Dataset:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"Załadowano {len(records)} przykładów z {path}")
    return Dataset.from_list(records)


def format_prompt(example: dict) -> dict:
    text = ALPACA_TEMPLATE.format(
        instruction=example.get("instruction", ""),
        input=example.get("input", ""),
        output=example.get("output", ""),
    )
    return {"text": text}


def main():
    parser = argparse.ArgumentParser(description="Fine-tuning LoRA lokalnego modelu")
    parser.add_argument("--dataset",     required=True,  help="Ścieżka do pliku JSONL z danymi")
    parser.add_argument("--model",       default="qwen3:4b", help="Nazwa modelu (Ollama lub HuggingFace ID)")
    parser.add_argument("--output",      default="/app/output/finetuned", help="Katalog wyjściowy")
    parser.add_argument("--epochs",      type=int,   default=3)
    parser.add_argument("--batch",       type=int,   default=4)
    parser.add_argument("--lr",          type=float, default=2e-4)
    parser.add_argument("--rank",        type=int,   default=16, help="Rząd macierzy LoRA")
    parser.add_argument("--max-length",  type=int,   default=2048)
    parser.add_argument("--load-in-4bit", action="store_true", default=True, help="QLoRA – 4-bit quantization")
    args = parser.parse_args()

    hf_model = MODEL_MAP.get(args.model, args.model)
    print(f"Model: {args.model} → {hf_model}")
    print(f"Dataset: {args.dataset}")
    print(f"Output: {args.output}")
    print(f"GPU: {torch.cuda.is_available()} | CUDA: {torch.version.cuda}")

    # ── Wczytaj dane ─────────────────────────────────────────────────────────
    dataset = load_jsonl(args.dataset).map(format_prompt)

    # ── Tokenizer ─────────────────────────────────────────────────────────────
    tokenizer = AutoTokenizer.from_pretrained(hf_model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # ── Model (opcjonalnie 4-bit QLoRA) ───────────────────────────────────────
    model_kwargs = {"trust_remote_code": True}
    if args.load_in_4bit and torch.cuda.is_available():
        from transformers import BitsAndBytesConfig
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.bfloat16,
        )
        model_kwargs["torch_dtype"] = torch.bfloat16
    else:
        model_kwargs["torch_dtype"] = torch.float32

    model = AutoModelForCausalLM.from_pretrained(hf_model, **model_kwargs)

    # ── LoRA config ──────────────────────────────────────────────────────────
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.rank,
        lora_alpha=args.rank * 2,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    # ── Training arguments ────────────────────────────────────────────────────
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        learning_rate=args.lr,
        fp16=torch.cuda.is_available(),
        logging_steps=10,
        save_strategy="epoch",
        optim="paged_adamw_8bit" if torch.cuda.is_available() else "adamw_torch",
        report_to="none",
    )

    # ── Trainer ───────────────────────────────────────────────────────────────
    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_length,
        tokenizer=tokenizer,
    )

    print("\nRozpoczynam trening...")
    trainer.train()

    # ── Zapisz adapter + scal z base modelem ─────────────────────────────────
    adapter_dir = output_dir / "adapter"
    trainer.save_model(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"\nAdapter LoRA zapisany: {adapter_dir}")

    # Scal wagi (merge)
    merged_dir = output_dir / "merged"
    print("Scalanie wag LoRA z base modelem...")
    from peft import PeftModel
    base_model = AutoModelForCausalLM.from_pretrained(hf_model, torch_dtype=torch.float16, trust_remote_code=True)
    merged = PeftModel.from_pretrained(base_model, str(adapter_dir))
    merged = merged.merge_and_unload()
    merged.save_pretrained(str(merged_dir))
    tokenizer.save_pretrained(str(merged_dir))
    print(f"Model scalony zapisany: {merged_dir}")
    print(f"\nNastępny krok: python export_gguf.py --model {merged_dir} --name moj-model")


if __name__ == "__main__":
    main()
