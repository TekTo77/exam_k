"""Правила чтения Excel и создания ключей."""
from pathlib import Path
from design import APP_TITLE, COLORS

PROJECT_DIR = Path(__file__).resolve().parent

IMPORT_REFERENCE_RULES = (
    {
        "parent_table": "users",
        "child_table": "orders",
        "column": "user_id",
        "parent_fields": (
            ("last_name", "фамилия"),
            ("first_name", "имя"),
            ("middle_name", "отчетсво", "отчество"),
        ),
        "child_fields": (("client_name", "фио", "фио_клиента", "покупатель"),),
        "existing_columns": (
            "user_id",
            "id_user",
            "idusers",
            "клиент_id",
            "пользователь_id",
        ),
    },
)

DATE_INPUT_FORMATS = ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S")

IMPORT_TABLE_RULES = {}

IMPORT_FOREIGN_KEYS = ()

IMPORT_AUTO_FOREIGN_KEYS = True

IMPORT_HEADER_ROWS = {}
