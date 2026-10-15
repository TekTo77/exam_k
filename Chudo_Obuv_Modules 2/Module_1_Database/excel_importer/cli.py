from __future__ import annotations

import argparse
from pathlib import Path

from .parser import EXCEL_EXTENSIONS, parse_excel_files
from .postgres import create_schema_sql, import_model


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт Excel в PostgreSQL")
    parser.add_argument("files", nargs="+", help="Файлы Excel или папки с файлами")
    parser.add_argument("--header-row", type=int, default=1)
    parser.add_argument(
        "--append", action="store_true", help="Добавить строки без пересоздания таблиц"
    )
    parser.add_argument("--sql-out", type=Path, help="Сохранить SQL структуры")
    parser.add_argument("--profile", type=Path, help="import_profile.json из редактора")
    args = parser.parse_args()
    paths: list[Path] = []
    for item in args.files:
        path = Path(item)
        if path.is_dir():
            paths.extend(
                sorted(
                    p for p in path.iterdir() if p.suffix.lower() in EXCEL_EXTENSIONS
                )
            )
        else:
            paths.append(path)
    from config import (
        IMPORT_REFERENCE_RULES,
        IMPORT_TABLE_RULES,
        IMPORT_FOREIGN_KEYS,
        IMPORT_AUTO_FOREIGN_KEYS,
        IMPORT_HEADER_ROWS,
    )

    from .profile import read_import_profile

    profile = args.profile
    parents = {p.resolve().parent for p in paths}
    if profile is None and len(parents) == 1:
        candidate = next(iter(parents)) / "import_profile.json"
        if candidate.is_file():
            profile = candidate
    rules = read_import_profile(profile, paths) if profile else None
    model = parse_excel_files(
        paths,
        header_row=1 if rules else args.header_row,
        reference_rules=() if rules else IMPORT_REFERENCE_RULES,
        table_rules=rules["table_rules"] if rules else IMPORT_TABLE_RULES,
        foreign_keys=rules["foreign_keys"] if rules else IMPORT_FOREIGN_KEYS,
        auto_foreign_keys=False if rules else IMPORT_AUTO_FOREIGN_KEYS,
        header_rows={} if rules else IMPORT_HEADER_ROWS,
    )
    from storage.connection import read_connection_config

    settings = read_connection_config()
    if args.sql_out:
        args.sql_out.write_text(
            create_schema_sql(model, settings["schema"], not args.append),
            encoding="utf-8",
        )
    result = import_model(
        model, settings["dsn"], settings["schema"], replace=not args.append
    )
    print(
        f"Готово: таблиц {result.tables_created}, строк {result.rows_inserted}, внешних ключей {result.foreign_keys_added}"
    )
    for warning in result.warnings:
        print(f"Предупреждение: {warning}")


if __name__ == "__main__":
    main()
