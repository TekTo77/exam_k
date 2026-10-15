"""Импорт Excel в PostgreSQL."""

from .entities import WorkbookModel
from .parser import parse_excel_files

__all__ = ["WorkbookModel", "parse_excel_files"]
