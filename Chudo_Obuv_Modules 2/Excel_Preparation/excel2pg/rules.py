"""Явные правила для необычных имен, ключей и типов Excel."""

import re
from datetime import date, datetime
from decimal import Decimal
from .entities import ForeignKeyEntity
from .names import normalize_identifier


def names(value):
    return (value,) if isinstance(value, str) else tuple(value)


def column_name(table, value):
    matches = [
        c.name
        for c in table.columns
        if value in {c.name, c.source_name}
        or normalize_identifier(value) in {c.name, normalize_identifier(c.source_name)}
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Правило импорта: не найдена однозначная колонка {table.name}.{value}."
        )
    return matches[0]


def apply_table_rules(model, rules):
    for table in model.tables:
        rule = rules.get(table.name, {})
        table.name = normalize_identifier(rule.get("table", table.name), "table")
        renames = {
            column_name(table, old): normalize_identifier(new)
            for old, new in rule.get("columns", {}).items()
        }
        for c in table.columns:
            c.name = renames.get(c.name, c.name)
        if len({c.name for c in table.columns}) != len(table.columns):
            raise ValueError(
                f"Правила импорта создали повторяющиеся колонки в {table.name}."
            )
        for row in table.rows:
            values = {renames.get(k, k): v for k, v in row.items()}
            row.clear()
            row.update(values)
        if "primary_key" in rule:
            keys = [column_name(table, n) for n in names(rule["primary_key"])]
            if not keys:
                raise ValueError(f"Для {table.name} primary_key не может быть пустым.")
            seen = set()
            for row in table.rows:
                values = tuple(row.get(k) for k in keys)
                if None in values or values in seen:
                    raise ValueError(
                        f"В {table.name} первичный ключ {keys} пустой или повторяется: {values}."
                    )
                seen.add(values)
            for c in table.columns:
                c.is_primary_key = c.name in keys
            if "__row_id" not in keys:
                table.columns = [
                    c for c in table.columns if c.source_name != "(generated)"
                ]
                for row in table.rows:
                    row.pop("__row_id", None)
        for name, requested in rule.get("types", {}).items():
            actual = column_name(table, name)
            pg_type = requested.upper().strip()
            if not re.fullmatch(
                r"TEXT|BOOLEAN|SMALLINT|INTEGER|BIGINT|NUMERIC(?:\(\d{1,3}(?:,\s*\d{1,3})?\))?|REAL|DOUBLE PRECISION|DATE|TIMESTAMP(?: WITH(?:OUT)? TIME ZONE)?|UUID",
                pg_type,
            ):
                raise ValueError(
                    f"Не поддерживается тип {requested!r}; используйте тип из README."
                )
            for column in table.columns:
                if column.name == actual:
                    column.pg_type = pg_type
            for i, row in enumerate(table.rows, table.header_row + 1):
                value = row.get(actual)
                if value is None:
                    continue
                try:
                    if pg_type.startswith("NUMERIC"):
                        value = Decimal(str(value))
                        if not value.is_finite():
                            raise ValueError("не конечное число")
                    elif pg_type in {"BIGINT", "INTEGER", "SMALLINT"}:
                        number = Decimal(str(value))
                        if number != number.to_integral_value():
                            raise ValueError("дробное число")
                        value = int(number)
                    elif pg_type in {"REAL", "DOUBLE PRECISION"}:
                        value = float(value)
                    elif pg_type == "DATE" or pg_type.startswith("TIMESTAMP"):
                        from .dates import as_date

                        if pg_type == "DATE":
                            value = as_date(value)
                        elif not isinstance(value, datetime):
                            value = (
                                datetime.combine(value, datetime.min.time())
                                if isinstance(value, date)
                                else datetime.fromisoformat(
                                    str(value).replace("Z", "+00:00")
                                )
                            )
                    elif pg_type == "BOOLEAN":
                        truth = str(value).strip().casefold()
                        if truth not in {"true", "false", "1", "0", "да", "нет"}:
                            raise ValueError("ожидалось да/нет")
                        value = truth in {"true", "1", "да"}
                    elif pg_type == "TEXT":
                        value = str(value)
                    elif pg_type == "UUID":
                        import uuid

                        value = uuid.UUID(str(value))
                    row[actual] = value
                except (ValueError, TypeError, ArithmeticError) as error:
                    raise ValueError(
                        f"{table.source_file}, {table.source_sheet}, строка {i}, {actual}: {value!r} не подходит к {pg_type}."
                    ) from error
    if len(set(model.table_names())) != len(model.tables):
        raise ValueError("Правила импорта создали таблицы с одинаковыми именами.")


def apply_foreign_keys(model, rules):
    tables = {t.name: t for t in model.tables}
    for rule in rules:
        if isinstance(rule, dict):
            child, cols, parent, refs = (
                rule[k] for k in ("table", "columns", "references", "reference_columns")
            )
        else:
            child, cols, parent, refs = rule
        # Один набор правил можно использовать с неполным набором Excel.
        if child not in tables or parent not in tables:
            model.warnings.append(
                f"Явная связь {child} → {parent} пропущена: таблицы нет в выбранных файлах."
            )
            continue
        child, parent = tables[child], tables[parent]
        columns = tuple(column_name(child, n) for n in names(cols))
        parents = tuple(column_name(parent, n) for n in names(refs))
        if len(columns) != len(parents):
            raise ValueError(
                "Внешний ключ: число колонок дочерней и родительской таблицы отличается."
            )
        if parents != tuple(c.name for c in parent.primary_keys):
            raise ValueError(
                f"Родительские колонки {parent.name}{parents} должны быть первичным ключом. Задайте IMPORT_TABLE_RULES."
            )
        present = {tuple(r.get(n) for n in parents) for r in parent.rows}
        missing = {
            tuple(r.get(n) for n in columns)
            for r in child.rows
            if all(r.get(n) is not None for n in columns)
        } - present
        child.foreign_keys = [f for f in child.foreign_keys if f.columns != columns]
        child.foreign_keys.append(
            ForeignKeyEntity(
                columns[0],
                parent.name,
                parents[0],
                "explicit",
                len(missing),
                not missing,
                columns,
                parents,
            )
        )
