"""Запуск: python main.py /путь/к/папке/с/CSV."""

import argparse
import json
from pathlib import Path
from analytics import calculate, load_csv


def main():
    parser = argparse.ArgumentParser(description="Чудо Обувь — модуль 5, аналитика")
    parser.add_argument(
        "folder", nargs="?", default="data", help="Папка с четырьмя CSV из приложения 4"
    )
    parser.add_argument("--save", type=Path, help="Сохранить ответы в JSON")
    args = parser.parse_args()
    try:
        answers = calculate(load_csv(args.folder))
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Проверьте данные: {error}\n")
    for key, value in answers.items():
        if value is None:
            text = "Недостаточно данных для расчёта"
        elif key == "5.5":
            text = f"{value:.3f}"
        else:
            text = str(value)
        print(f"{key}: {text}")
    if args.save:
        args.save.write_text(
            json.dumps(answers, ensure_ascii=False, indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
