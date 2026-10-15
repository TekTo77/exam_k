from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import psycopg
from psycopg import sql

from .entities import TableEntity, WorkbookModel
from .constraint_names import _constraint_name


@dataclass
class ImportResult:
    tables_created: int
    rows_inserted: int
    foreign_keys_added: int
    warnings: list[str]


def _qualified(schema: str, name: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(schema), sql.Identifier(name))


def _create_table_statement(
    schema: str, table: TableEntity, if_not_exists: bool = False
) -> sql.Composed:
    definitions = []
    for column in table.columns:
        definition = sql.SQL("{} {}{}").format(
            sql.Identifier(column.name),
            sql.SQL(column.pg_type),
            sql.SQL(
                " NOT NULL" if not column.nullable or column.is_primary_key else ""
            ),
        )
        definitions.append(definition)
    primary_key = table.primary_key
    if primary_key:
        definitions.append(
            sql.SQL("PRIMARY KEY ({})").format(
                sql.SQL(", ").join(sql.Identifier(c.name) for c in table.primary_keys)
            )
        )
    prefix = (
        sql.SQL("CREATE TABLE IF NOT EXISTS ")
        if if_not_exists
        else sql.SQL("CREATE TABLE ")
    )
    return sql.SQL("{}{} ({})").format(
        prefix, _qualified(schema, table.name), sql.SQL(", ").join(definitions)
    )


def _add_column_statement(
    schema: str, table_name: str, column_name: str, pg_type: str
) -> sql.Composed:
    """Добавляем новый столбец Excel при дописывании."""
    return sql.SQL("ALTER TABLE IF EXISTS {} ADD COLUMN IF NOT EXISTS {} {}").format(
        _qualified(schema, table_name),
        sql.Identifier(column_name),
        sql.SQL(pg_type),
    )


def _quote(value: str) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def create_schema_sql(
    model: WorkbookModel, schema: str = "public", replace: bool = True
) -> str:
    """SQL структуры для просмотра и сохранения."""
    lines = [f"CREATE SCHEMA IF NOT EXISTS {_quote(schema)};"]
    for table in model.tables:
        if replace:
            lines.append(
                f"DROP TABLE IF EXISTS {_quote(schema)}.{_quote(table.name)} CASCADE;"
            )
        column_lines = []
        for column in table.columns:
            nullable = (
                " NOT NULL" if not column.nullable or column.is_primary_key else ""
            )
            column_lines.append(f"  {_quote(column.name)} {column.pg_type}{nullable}")
        if table.primary_key:
            column_lines.append(
                f"  PRIMARY KEY ({', '.join(_quote(c.name) for c in table.primary_keys)})"
            )
        columns_str = ",\n".join(column_lines)
        lines.append(
            f"CREATE TABLE {_quote(schema)}.{_quote(table.name)} (\n{columns_str}\n);"
        )
    for table in model.tables:
        for fk in table.foreign_keys:
            if fk.enabled:
                lines.append(
                    f"ALTER TABLE {_quote(schema)}.{_quote(table.name)} ADD CONSTRAINT {_quote(_constraint_name(table, fk))} "
                    f"FOREIGN KEY ({', '.join(_quote(c) for c in fk.columns)}) REFERENCES {_quote(schema)}.{_quote(fk.referenced_table)} ({', '.join(_quote(c) for c in fk.reference_columns)});"
                )
    return "\n\n".join(lines) + "\n"


def import_model(
    model: WorkbookModel,
    conninfo: str,
    schema: str = "public",
    replace: bool = True,
    add_foreign_keys: bool = True,
) -> ImportResult:
    if not model.tables:
        raise ValueError("Нет таблиц для импорта. Проверьте файлы и строку заголовков.")
    warnings = list(model.warnings)
    inserted = 0
    fks_added = 0
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema))
            )
            if replace:
                for table in model.tables:
                    cursor.execute(
                        sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                            _qualified(schema, table.name)
                        )
                    )
            for table in model.tables:
                cursor.execute(
                    _create_table_statement(schema, table, if_not_exists=not replace)
                )
                # Новые колонки создаём до записи строк.
                for column in table.columns:
                    cursor.execute(
                        _add_column_statement(
                            schema, table.name, column.name, column.pg_type
                        )
                    )
            for table in model.tables:
                if not table.rows:
                    continue
                if (
                    not replace
                    and table.primary_key
                    and table.primary_key.source_name == "(generated)"
                ):
                    cursor.execute(
                        sql.SQL("SELECT EXISTS(SELECT 1 FROM {})").format(
                            _qualified(schema, table.name)
                        )
                    )
                    if cursor.fetchone()[0]:
                        raise ValueError(
                            f"Дописать {table.name} со служебным __row_id небезопасно для ссылок. Выберите замену таблиц или задайте настоящий первичный ключ в IMPORT_TABLE_RULES."
                        )
                names = [column.name for column in table.columns]
                statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                    _qualified(schema, table.name),
                    sql.SQL(", ").join(map(sql.Identifier, names)),
                    sql.SQL(", ").join(sql.Placeholder() for _ in names),
                )
                cursor.executemany(
                    statement, ([row.get(name) for name in names] for row in table.rows)
                )
                inserted += len(table.rows)
            if add_foreign_keys:
                for table in model.tables:
                    for fk in table.foreign_keys:
                        if not fk.enabled:
                            if fk.orphan_count:
                                warnings.append(
                                    f"Связь {table.name}.{fk.column} пропущена: {fk.orphan_count} значений нет в {fk.referenced_table}."
                                )
                            continue
                        constraint = _constraint_name(table, fk)
                        cursor.execute("SAVEPOINT excel2pg_fk")
                        try:
                            cursor.execute(
                                sql.SQL(
                                    "ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {} ({})"
                                ).format(
                                    _qualified(schema, table.name),
                                    sql.Identifier(constraint),
                                    sql.SQL(", ").join(map(sql.Identifier, fk.columns)),
                                    _qualified(schema, fk.referenced_table),
                                    sql.SQL(", ").join(
                                        map(sql.Identifier, fk.reference_columns)
                                    ),
                                )
                            )
                            fks_added += 1
                        except psycopg.Error as exc:
                            warnings.append(
                                f"Не добавлена связь {table.name}.{fk.column}: {exc}"
                            )
                            cursor.execute("ROLLBACK TO SAVEPOINT excel2pg_fk")
                        finally:
                            cursor.execute("RELEASE SAVEPOINT excel2pg_fk")
    return ImportResult(len(model.tables), inserted, fks_added, warnings)
