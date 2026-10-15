from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class ColumnEntity:
    name: str
    source_name: str
    pg_type: str
    nullable: bool = True
    is_primary_key: bool = False


@dataclass
class ForeignKeyEntity:
    column: str
    referenced_table: str
    referenced_column: str
    confidence: str = "auto"
    orphan_count: int = 0
    enabled: bool = True
    composite_columns: tuple[str, ...] = ()
    composite_references: tuple[str, ...] = ()

    @property
    def columns(self):
        return self.composite_columns or (self.column,)

    @property
    def reference_columns(self):
        return self.composite_references or (self.referenced_column,)


@dataclass
class TableEntity:
    name: str
    source_file: str
    source_sheet: str
    columns: list[ColumnEntity]
    rows: list[dict[str, Any]] = field(default_factory=list)
    foreign_keys: list[ForeignKeyEntity] = field(default_factory=list)
    header_row: int = 1

    @property
    def primary_keys(self):
        return [column for column in self.columns if column.is_primary_key]

    @property
    def primary_key(self) -> ColumnEntity | None:
        return next((column for column in self.columns if column.is_primary_key), None)


@dataclass
class WorkbookModel:
    tables: list[TableEntity] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def table_names(self) -> list[str]:
        return [table.name for table in self.tables]


Scalar = str | int | float | bool | date | datetime | None
