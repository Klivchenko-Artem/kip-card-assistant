"""Запуск без веб-формы: python -m app.cli examples/input/testo-510.json --out examples/output"""

import argparse
import json
import sys
from pathlib import Path

from .config import ConfigError, load_settings
from .generator import generate_card
from .input_check import InputError, parse_input
from .llm import GroqClient, LlmError


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Черновик карточки товара из JSON")
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, help="папка для .json и .md")
    args = parser.parse_args()

    try:
        settings = load_settings()
        parsed = parse_input(args.input.read_bytes())
        result = generate_card(parsed, GroqClient(settings), settings.max_rewrites)
    except (InputError, LlmError, ConfigError, OSError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 1

    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        data = result.model_dump(exclude={"markdown"})
        text = json.dumps(data, ensure_ascii=False, indent=2)
        (args.out / f"{args.input.stem}.json").write_text(text + "\n", encoding="utf-8")
        (args.out / f"{args.input.stem}.md").write_text(result.markdown, encoding="utf-8")
    print(result.markdown)
    print(f"Статус: {result.status}, переписываний: {result.rewrites}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
