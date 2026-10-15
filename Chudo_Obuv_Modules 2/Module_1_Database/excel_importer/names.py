from __future__ import annotations

import re
import unicodedata


def normalize_identifier(value: object, fallback: str = "column") -> str:
    """Приводим имя к формату для таблиц и колонок."""
    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w]+", "_", text, flags=re.UNICODE).strip("_")
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"_{text}"
    return text.encode("utf-8")[:60].decode("utf-8", errors="ignore")


def unique_identifiers(values: list[object], fallback: str) -> list[str]:
    result: list[str] = []
    used: set[str] = set()
    for index, value in enumerate(values, 1):
        base = normalize_identifier(value, f"{fallback}_{index}")
        candidate = base
        suffix = 2
        while candidate in used:
            candidate = (
                f"{base.encode('utf-8')[:52].decode('utf-8', errors='ignore')}_{suffix}"
            )
            suffix += 1
        used.add(candidate)
        result.append(candidate)
    return result
