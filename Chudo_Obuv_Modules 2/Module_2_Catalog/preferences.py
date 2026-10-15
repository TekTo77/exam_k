"""Папка фото и сопоставления. Подключение хранится отдельно."""

import json
from pathlib import Path

from config import PROJECT_DIR
from design import DEFAULT_IMAGES_FOLDER

SETTINGS_PATH = PROJECT_DIR / "settings.json"


def read_settings():
    if not SETTINGS_PATH.exists():
        return {}
    data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("settings.json должен содержать объект JSON.")
    return data


def write_settings(data):
    temporary = SETTINGS_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(SETTINGS_PATH)


def images_directory(settings):
    folder = Path(settings.get("images_folder") or DEFAULT_IMAGES_FOLDER).expanduser()
    return folder if folder.is_absolute() else PROJECT_DIR / folder
