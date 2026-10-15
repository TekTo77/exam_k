from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def infer_pg_type(series: pd.Series) -> str:
    non_null = series.dropna()
    if non_null.empty:
        return "TEXT"
    dtype = series.dtype
    if pd.api.types.is_bool_dtype(dtype):
        return "BOOLEAN"
    if pd.api.types.is_datetime64_any_dtype(dtype):
        return "TIMESTAMP"
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE PRECISION"
    if pd.api.types.is_numeric_dtype(dtype):
        return "DOUBLE PRECISION"
    sample = non_null.head(200)
    if all(isinstance(value, bool) for value in non_null):
        return "BOOLEAN"
    if all(
        isinstance(value, int) and not isinstance(value, bool) for value in non_null
    ):
        return "BIGINT"
    if all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in non_null
    ):
        return "DOUBLE PRECISION"
    if all(isinstance(value, (datetime, date, pd.Timestamp)) for value in sample):
        return "TIMESTAMP"
    return "TEXT"


def clean_value(value: Any) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    return value
