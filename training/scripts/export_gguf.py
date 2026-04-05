#!/usr/bin/env python3
"""
Eksport modelu HuggingFace → GGUF → rejestracja w Ollama.

Wymaga: llama.cpp (zainstalowane osobno lub z obrazu)

Użycie:
    python export_gguf.py --model /app/output/finetuned/merged --name moj-model
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

MODELFILE_TEMPLATE = """FROM {gguf_path}

SYSTEM \"\"\"
Jesteś lokalnym asystentem AI wytrenowanym na własnych danych.
Odpowiadaj precyzyjnie, zwięźle i pomocnie.
\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER stop \"### Instruction:\"
PARAMETER stop \"### Response:\"
"""


def check_command(cmd: str) -> bool:
    try:
        subprocess.run([cmd, "--help"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def main():
    parser = argparse.ArgumentParser(description="Eksport modelu do GGUF i rejestracja w Ollama")
    parser.add_argument("--model", required=True, help="Katalog z modelem HuggingFace (merged)")
    parser.add_argument("--name",  required=True, help="Nazwa modelu w Ollama (np. moj-model)")
    parser.add_argument("--quant", default="q4_k_m", help="Kwantyzacja: q4_k_m, q5_k_m, q8_0, f16")
    parser.add_argument("--llama-cpp", default="convert_hf_to_gguf.py",
                        help="Ścieżka do skryptu llama.cpp convert_hf_to_gguf.py")
    parser.add_argument("--output-dir", default="/app/output/gguf", help="Katalog wyjściowy GGUF")
    args = parser.parse_args()

    model_path = Path(args.model)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not model_path.exists():
        print(f"BŁĄD: Katalog modelu nie istnieje: {model_path}", file=sys.stderr)
        sys.exit(1)

    gguf_fp16 = output_dir / f"{args.name}-f16.gguf"
    gguf_quant = output_dir / f"{args.name}-{args.quant}.gguf"

    # ── 1. Konwersja HF → GGUF (f16) ─────────────────────────────────────────
    print(f"[1/3] Konwertuję {model_path} → {gguf_fp16}")
    cmd_convert = [
        sys.executable, args.llama_cpp,
        str(model_path),
        "--outfile", str(gguf_fp16),
        "--outtype", "f16",
    ]
    result = subprocess.run(cmd_convert)
    if result.returncode != 0:
        print("\nKonwersja nie powiodła się. Upewnij się, że llama.cpp jest zainstalowane.")
        print("Instalacja: git clone https://github.com/ggerganov/llama.cpp && cd llama.cpp && pip install -r requirements.txt")
        sys.exit(1)

    # ── 2. Kwantyzacja ────────────────────────────────────────────────────────
    print(f"[2/3] Kwantyzuję → {args.quant} → {gguf_quant}")
    if check_command("llama-quantize"):
        result = subprocess.run(["llama-quantize", str(gguf_fp16), str(gguf_quant), args.quant.upper()])
    else:
        print(f"  llama-quantize niedostępne, używam f16: {gguf_fp16}")
        gguf_quant = gguf_fp16

    # ── 3. Modelfile + rejestracja w Ollama ───────────────────────────────────
    print(f"[3/3] Rejestruję model '{args.name}' w Ollama")
    modelfile_content = MODELFILE_TEMPLATE.format(gguf_path=str(gguf_quant))
    modelfile_path = output_dir / f"{args.name}.Modelfile"
    modelfile_path.write_text(modelfile_content)

    if check_command("ollama"):
        result = subprocess.run(["ollama", "create", args.name, "-f", str(modelfile_path)])
        if result.returncode == 0:
            print(f"\nGotowe! Model '{args.name}' dostępny w Ollama.")
            print(f"  Uruchom: ollama run {args.name}")
        else:
            print(f"\nOllama zwróciła błąd. Spróbuj ręcznie:")
            print(f"  ollama create {args.name} -f {modelfile_path}")
    else:
        print(f"\nOllama niedostępna. Zarejestruj ręcznie:")
        print(f"  ollama create {args.name} -f {modelfile_path}")

    print(f"\nPliki wyjściowe:")
    print(f"  GGUF:      {gguf_quant}")
    print(f"  Modelfile: {modelfile_path}")


if __name__ == "__main__":
    main()
