"""Показывает источник данных и настройки. Пароль не выводится."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.repository import Database


def main():
    db = Database()
    try:
        info = db.fetch_one(
            "SELECT current_database() AS db, current_schema() AS schema"
        )
        print(f"PostgreSQL: база {info['db']}, схема {info['schema']}")
        print(
            f"Варианты: {db.variants_enabled}; остатки: {db.stock_mode}; заказы: {db.orders_enabled}"
        )
        print(
            "Текущий импорт:",
            (
                ", ".join(db.active_tables)
                if db.active_tables is not None
                else "вся выбранная схема"
            ),
        )
        for domain in db.TABLE_ALIASES:
            table = db._domain_table(domain)
            print(
                f"{domain}: {table or 'не используется'}"
                + (f" ({db._table_row_count(table)} строк)" if table else "")
            )
            if table:
                print(
                    "  "
                    + ", ".join(
                        f"{field}={column}"
                        for field, column in db.domain_columns[domain].items()
                        if column
                    )
                )
        if db._domain_table("products"):
            print("Поля из справочников:", db._build_lookup_paths())
        for warning in db.mapping_warnings:
            print("Предупреждение:", warning)
    finally:
        db.close()


if __name__ == "__main__":
    main()
