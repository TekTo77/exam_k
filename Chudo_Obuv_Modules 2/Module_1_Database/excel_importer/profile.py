"""Правила из подготовленных Excel."""
import json
from pathlib import Path

def read_import_profile(path, files=()):
    """Читаем JSON, а не исполняем чужой Python-файл."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != "excelprep-import" or data.get("version") != 1:
        raise ValueError("Нужен import_profile.json из редактора Excel.")
    if not isinstance(data.get("files"), list) or not all(
        isinstance(n, str) for n in data["files"]
    ):
        raise ValueError("В профиле нет списка Excel-файлов.")
    if not isinstance(data.get("table_rules"), dict) or not isinstance(
        data.get("foreign_keys"), list
    ):
        raise ValueError("В профиле неверные правила таблиц или связей.")
    if not {Path(f).name for f in files} <= set(data["files"]):
        raise ValueError("Эти Excel-файлы не входят в выбранный профиль.")
    return {**data, "auto_foreign_keys": False, "reference_rules": []}
