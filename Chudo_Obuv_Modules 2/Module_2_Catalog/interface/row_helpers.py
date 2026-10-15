def row_value(row, key: str, default=""):
    try:
        return row[key]
    except (KeyError, IndexError):
        return default
