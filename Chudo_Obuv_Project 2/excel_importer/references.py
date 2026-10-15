"""Связь по тексту, если в Excel нет ID."""

from collections import defaultdict
import unicodedata

from .entities import ColumnEntity
from .names import normalize_identifier


def text_key(values):
    return " ".join(unicodedata.normalize("NFKC", str(v or "")) for v in values).split()


def match_key(values):
    return " ".join(text_key(values)).casefold()


def _fields(table, groups):
    names = {
        normalize_identifier(alias): column.name
        for column in table.columns
        for alias in (column.name, column.source_name)
    }
    result = [
        next(
            (
                names[normalize_identifier(a)]
                for a in group
                if normalize_identifier(a) in names
            ),
            None,
        )
        for group in groups
    ]
    return result if all(result) else None


def prepare_references(model, rules=()):
    """Заполняем ID при единственном совпадении. Готовые ID не заменяем."""
    tables = {table.name: table for table in model.tables}
    for rule in rules:
        parent, child = tables.get(rule["parent_table"]), tables.get(
            rule["child_table"]
        )
        if parent is None or child is None or parent.primary_key is None:
            continue
        if len(parent.primary_keys) != 1:
            model.warnings.append(
                f"{child.name}: поиск ID по тексту пропущен — у {parent.name} составной ключ."
            )
            continue
        parent_fields = _fields(parent, rule["parent_fields"])
        child_fields = _fields(child, rule["child_fields"])
        if parent_fields is None or child_fields is None:
            continue
        existing = _fields(child, (rule.get("existing_columns", (rule["column"],)),))
        column = existing[0] if existing else rule["column"]
        if existing is None:
            child.columns.append(
                ColumnEntity(column, "(resolved reference)", parent.primary_key.pg_type)
            )
        candidates = defaultdict(list)
        for row in parent.rows:
            key = match_key(row.get(field) for field in parent_fields)
            if key:
                candidates[key].append(row[parent.primary_key.name])
        unresolved = 0
        for row in child.rows:
            if row.get(column) is not None:
                continue
            matches = candidates[match_key(row.get(field) for field in child_fields)]
            row[column] = matches[0] if len(matches) == 1 else None
            unresolved += len(matches) != 1
        if unresolved:
            model.warnings.append(
                f"{child.name}.{column}: не удалось однозначно связать {unresolved} строк. "
                "Укажите идентификаторы вручную; такие заказы не видны покупателю."
            )
    return model
