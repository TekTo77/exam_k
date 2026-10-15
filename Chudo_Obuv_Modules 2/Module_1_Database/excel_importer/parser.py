from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterable

import pandas as pd

from .entities import ColumnEntity, ForeignKeyEntity, TableEntity, WorkbookModel
from .names import normalize_identifier, unique_identifiers
from .types import clean_value, infer_pg_type

EXCEL_EXTENSIONS = {".xlsx", ".xls", ".xlsb", ".xlsm", ".ods"}

COLUMN_ALIASES = {
    "users": {
        "user_id": (
            "id",
            "user_id",
            "idusers",
            "id_users",
            "код_пользователя",
            "идентификатор",
        ),
        "login": ("login", "username", "логин", "имя_пользователя"),
        "last_name": ("last_name", "lastname", "surname", "фамилия"),
        "first_name": ("first_name", "firstname", "name", "имя"),
        "middle_name": ("middle_name", "middlename", "patronymic", "отчество"),
        "role_id": ("role_id", "roleid", "id_role", "роль_id", "код_роли"),
    },
    "roles": {
        "role_id": ("id", "role_id", "код_роли", "идентификатор"),
        "role_name": ("role_name", "name", "название", "роль", "наименование"),
    },
    "products": {
        "product_id": ("id", "product_id", "код_товара", "артикул", "идентификатор"),
        "product_name": (
            "product_name",
            "name",
            "title",
            "наименование",
            "название",
            "товар",
            "модель",
        ),
        "category": ("category", "категория", "тип", "вид"),
        "subcategory": ("subcategory", "подкатегория"),
        "manufacturer": ("manufacturer", "brand", "производитель", "бренд"),
        "composition": ("composition", "состав", "материал"),
        "description": ("description", "описание", "характеристика"),
        "price": ("price", "цена", "стоимость"),
    },
    "sizes": {
        "size_id": ("id", "size_id", "код_размера", "идентификатор"),
        "size_value": ("size_value", "size", "размер", "размер_обуви"),
    },
    "stock_items": {
        "stock_item_id": ("id", "stock_item_id", "код"),
        "product_id": ("product_id", "id_product", "товар_id", "код_товара", "артикул"),
        "size_id": ("size_id", "id_size", "размер_id", "код_размера"),
        "quantity_available": (
            "quantity_available",
            "quantity",
            "количество",
            "остаток",
            "остатки",
            "количество_на_складе",
        ),
    },
}


def _read_sheets(source, header_row):
    if isinstance(source, (str, Path)):
        data = source
    else:
        data = BytesIO(source.read())
    if isinstance(header_row, dict):
        with pd.ExcelFile(data, engine="calamine") as book:
            return {
                sheet: book.parse(
                    sheet,
                    header=_header_number(header_row.get(sheet, 1)) - 1,
                    dtype=object,
                    keep_default_na=False,
                )
                for sheet in book.sheet_names
            }
    return pd.read_excel(
        data,
        sheet_name=None,
        engine="calamine",
        header=_header_number(header_row) - 1,
        dtype=object,
        keep_default_na=False,
    )


def _header_number(value):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("Строка заголовков должна быть целым числом от 1.")
    return value


def _table_name(file_name: str, sheet_name: str, used: set[str]) -> str:
    normalized_sheet = normalize_identifier(sheet_name, "sheet")
    # Для Sheet1/Лист1 берём имя файла.
    generic_sheet = normalized_sheet in {
        "sheet",
        "sheet1",
        "sheet2",
        "лист",
        "лист1",
        "лист2",
    }
    base = normalize_identifier(
        Path(file_name).stem if generic_sheet else sheet_name, "sheet"
    )
    for suffix in ("_import", "_data", "_file"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    aliases = {
        "product": "products",
        "products": "products",
        "size": "sizes",
        "sizes": "sizes",
        "stock": "stock_items",
        "stock_item": "stock_items",
        "stock_items": "stock_items",
        "user": "users",
        "users": "users",
        "role": "roles",
        "roles": "roles",
        "order": "orders",
        "orders": "orders",
        "order_item": "order_items",
        "order_items": "order_items",
        "пользователь": "users",
        "пользователи": "users",
        "роль": "roles",
        "роли": "roles",
        "товар": "products",
        "товары": "products",
        "продукт": "products",
        "продукты": "products",
        "обувь": "products",
        "размер": "sizes",
        "размеры": "sizes",
        "остаток": "stock_items",
        "остатки": "stock_items",
        "склад": "stock_items",
        "заказ": "orders",
        "заказы": "orders",
        "состав_заказа": "order_items",
        "позиции_заказа": "order_items",
    }
    base = aliases.get(base, base)
    if base in used:
        base = normalize_identifier(f"{Path(file_name).stem}_{sheet_name}", "table")
    candidate = base
    n = 2
    while candidate in used:
        candidate = f"{base.encode('utf-8')[:52].decode('utf-8', errors='ignore')}_{n}"
        n += 1
    used.add(candidate)
    return candidate


def _canonical_column_name(table_name: str, column_name: str) -> str:
    normalized = column_name.lower()
    for canonical, aliases in COLUMN_ALIASES.get(table_name, {}).items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return column_name


def _is_key_candidate(column: ColumnEntity, series: pd.Series, table_name: str) -> bool:
    normalized = column.name.lower()
    if series.isna().any() or not series.is_unique:
        return False
    if normalized in {"id", "code", "key"} or normalized in {
        f"id_{_singular(table_name)}",
        f"{_singular(table_name)}_code",
        f"{_singular(table_name)}_key",
    }:
        return True
    if normalized.endswith("_id"):
        prefix = normalized.removesuffix("_id")
        table_base = _singular(table_name)
        return prefix == table_name or prefix == table_base
    return False


def _make_table(
    file_name: str, sheet_name: str, frame: pd.DataFrame, name: str, header_row: int
) -> TableEntity:
    # Текстовые коды 001 и слова NA/NULL не превращаем в числа или пустоту.
    mapper = getattr(frame, "map", None)
    if mapper is None:
        mapper = frame.applymap
    frame = mapper(lambda v: None if isinstance(v, str) and v == "" else v)
    frame = frame.dropna(axis=0, how="all")
    # Пустые именованные поля сохраняем: они могут понадобиться следующему импорту.
    frame = frame.loc[
        :,
        [
            not (str(column).startswith("Unnamed:") and frame[column].isna().all())
            for column in frame.columns
        ],
    ]
    if not len(frame.columns):
        return TableEntity(name, file_name, sheet_name, [], [], header_row=header_row)
    frame = frame.copy()
    source_columns = list(frame.columns)
    normalized_columns = unique_identifiers(source_columns, "column")
    canonical_columns: list[str] = []
    used_columns: set[str] = set()
    for column_name in normalized_columns:
        base = _canonical_column_name(name, column_name)
        candidate = base
        suffix = 2
        while candidate in used_columns:
            candidate = (
                f"{base.encode('utf-8')[:52].decode('utf-8', errors='ignore')}_{suffix}"
            )
            suffix += 1
        used_columns.add(candidate)
        canonical_columns.append(candidate)
    frame.columns = canonical_columns
    columns: list[ColumnEntity] = []
    for source_name, column_name in zip(source_columns, frame.columns):
        column = ColumnEntity(
            name=column_name,
            source_name=str(source_name),
            pg_type=infer_pg_type(frame[column_name]),
            # Разрешаем пустые значения при следующих загрузках.
            nullable=True,
        )
        if not any(c.is_primary_key for c in columns) and _is_key_candidate(
            column, frame[column_name], name
        ):
            column.is_primary_key = True
        columns.append(column)
    if not any(column.is_primary_key for column in columns):
        columns.insert(
            0, ColumnEntity("__row_id", "(generated)", "BIGINT", False, True)
        )
        frame.insert(0, "__row_id", range(1, len(frame) + 1))
    rows = [
        {column: clean_value(value) for column, value in row.items()}
        for row in frame.to_dict(orient="records")
    ]
    return TableEntity(name, file_name, sheet_name, columns, rows, [], header_row)


def _singular(value: str) -> str:
    if value.endswith("ies"):
        return value[:-3] + "y"
    return value[:-1] if value.endswith("s") else value


def _foreign_prefix(column_name: str) -> str | None:
    """Ищем возможного родителя по имени ID-колонки."""
    name = column_name.lower()
    if name.endswith("_id"):
        return name[:-3]
    if name.startswith("id_"):
        return name[3:]
    # После нормализации userID становится userid.
    if name.endswith("id") and len(name) > 2:
        return name[:-2].rstrip("_")
    return None


def _guess_foreign_keys(model: WorkbookModel) -> None:
    by_key: dict[str, list[tuple[TableEntity, ColumnEntity]]] = defaultdict(list)

    for table in model.tables:
        for column in table.columns:
            if (
                len(table.primary_keys) == 1
                and column.is_primary_key
                and column.name != "__row_id"
            ):
                by_key[column.name].append((table, column))

    for table in model.tables:
        for column in table.columns:
            # Служебный номер строки не используем для связей.
            if column.name == "__row_id":
                continue

            prefix = _foreign_prefix(column.name)
            if not prefix:
                continue

            candidates: list[tuple[TableEntity, ColumnEntity]] = []

            for parent in model.tables:
                if parent is table:
                    continue

                parent_key = parent.primary_key
                if (
                    len(parent.primary_keys) != 1
                    or parent_key is None
                    or parent_key.name == "__row_id"
                ):
                    continue

                table_match = _singular(parent.name) == _singular(prefix)
                key_match = parent_key.name == column.name or parent_key.name == "id"

                if table_match and key_match:
                    candidates.append((parent, parent_key))

            if not candidates:
                candidates = [
                    (parent, key)
                    for parent, key in by_key.get(column.name, [])
                    if parent is not table
                ]

            if len(candidates) != 1:
                continue

            parent, parent_key = candidates[0]

            child_values = {
                row.get(column.name)
                for row in table.rows
                if row.get(column.name) is not None
            }

            parent_values = {
                row.get(parent_key.name)
                for row in parent.rows
                if row.get(parent_key.name) is not None
            }

            orphan_count = len(child_values - parent_values)

            table.foreign_keys.append(
                ForeignKeyEntity(
                    column.name,
                    parent.name,
                    parent_key.name,
                    "auto",
                    orphan_count,
                    orphan_count == 0,
                )
            )


def parse_excel_files(
    files: Iterable[str | Path | BinaryIO],
    header_row: int = 1,
    include_empty_sheets: bool = False,
    reference_rules=(),
    table_rules=None,
    foreign_keys=(),
    auto_foreign_keys=True,
    header_rows=None,
) -> WorkbookModel:
    _header_number(header_row)
    model = WorkbookModel()
    used_names: set[str] = set()
    for source in files:
        file_name = getattr(source, "name", None) or Path(source).name
        suffix = Path(file_name).suffix.lower()
        if suffix not in EXCEL_EXTENSIONS:
            model.warnings.append(f"Пропущен неподдерживаемый файл: {file_name}")
            continue
        try:
            file_header = (header_rows or {}).get(Path(file_name).name, header_row)
            sheets = _read_sheets(source, file_header)
        except Exception as exc:
            model.warnings.append(f"Не удалось прочитать {file_name}: {exc}")
            continue
        for sheet_name, frame in sheets.items():
            table = _make_table(
                file_name,
                str(sheet_name),
                frame,
                _table_name(file_name, str(sheet_name), used_names),
                (
                    file_header.get(str(sheet_name), 1)
                    if isinstance(file_header, dict)
                    else file_header
                ),
            )
            if (table_rules or {}).get(table.name, {}).get("skip"):
                model.warnings.append(f"Лист пропущен по правилу: {table.name}")
                continue
            if table.columns and (table.rows or include_empty_sheets):
                model.tables.append(table)
            else:
                model.warnings.append(
                    f"Пустой лист пропущен: {file_name} / {sheet_name}"
                )
    from .references import prepare_references

    from .rules import apply_table_rules, apply_foreign_keys

    apply_table_rules(model, table_rules or {})
    prepare_references(model, reference_rules)
    if auto_foreign_keys:
        _guess_foreign_keys(model)
    apply_foreign_keys(model, foreign_keys)
    return model
