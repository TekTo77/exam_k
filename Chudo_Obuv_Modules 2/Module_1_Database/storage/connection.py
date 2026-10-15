"""Подключение берём только из postgres_connection.json."""

import json
from pathlib import Path
from config import PROJECT_DIR


def config_path():
    # В модульной версии общий файл лежит на уровень выше.
    local = PROJECT_DIR / "postgres_connection.json"
    shared = PROJECT_DIR.parent / "postgres_connection.json"
    return local if local.is_file() or not shared.is_file() else shared


def read_connection_settings(path=None):
    path = Path(path) if path is not None else config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"Проверь файл подключения: {path}") from error
    if not isinstance(data, dict):
        raise ValueError("В файле подключения должен быть JSON-объект.")
    for key in ("host", "port", "database", "user", "schema"):
        if not isinstance(data.get(key), (str, int)) or not str(data[key]).strip():
            raise ValueError(f"Заполни {key} в файле {path.name}.")
    try:
        port = int(str(data["port"]).strip())
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError as error:
        raise ValueError("Порт должен быть числом от 1 до 65535.") from error
    if not isinstance(data.get("password", ""), str):
        raise ValueError("Пароль должен быть строкой в кавычках.")
    tables = data.get("active_tables")
    if tables is not None and (
        not isinstance(tables, list) or not all(isinstance(v, str) for v in tables)
    ):
        raise ValueError("active_tables: null или список названий таблиц.")
    return {**data, "port": str(port)}


def read_connection_config(path=None):
    from psycopg.conninfo import make_conninfo

    data = read_connection_settings(path)
    return {
        "dsn": make_conninfo(
            host=str(data["host"]).strip(),
            port=data["port"],
            dbname=str(data["database"]).strip(),
            user=str(data["user"]).strip(),
            password=data.get("password", ""),
        ),
        "schema": str(data["schema"]).strip(),
        "active_tables": data.get("active_tables"),
    }
