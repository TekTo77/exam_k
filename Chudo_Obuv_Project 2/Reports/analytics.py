"""Шесть расчётов из модуля 5. Исходные CSV не меняются."""

from pathlib import Path
import pandas as pd
import config

ALIASES = {
    "sessions": {
        "id": ("session_id",),
        "user": ("user_id",),
        "started": (
            "session_start",
            "session_start_time",
            "start_time",
            "started_at",
            "session_date",
        ),
        "device": ("device_type",),
        "source": ("traffic_source",),
    },
    "orders": {
        "id": ("order_id",),
        "user": ("user_id",),
        "session": ("session_id",),
        "created": ("order_date", "order_time", "order_datetime", "created_at"),
        "status": ("status", "order_status"),
        "discount": ("discount_percent",),
    },
    "items": {
        "order": ("order_id",),
        "model": ("model_id", "shoe_model_id", "product_id"),
        "quantity": ("quantity",),
        "price": ("unit_price", "price"),
        "amount": ("line_total", "item_total", "total_price", "subtotal"),
        "discount": ("discount_percent",),
    },
    "models": {
        "id": ("model_id", "shoe_model_id", "product_id"),
        "category": ("category",),
    },
}
OPTIONAL = {
    ("orders", "discount"),
    ("items", "discount"),
    ("items", "amount"),
    ("items", "price"),
}


def load_csv(folder):
    frames = {}
    for name, filename in config.FILES.items():
        path = Path(folder) / filename
        if not path.is_file():
            raise ValueError(
                f"Нет файла {filename}. Положите четыре CSV в выбранную папку."
            )
        try:
            frame = pd.read_csv(
                path,
                sep=None,
                engine="python",
                encoding="utf-8-sig",
                dtype=str,
                keep_default_na=False,
            )
        except UnicodeDecodeError:
            frame = pd.read_csv(
                path,
                sep=None,
                engine="python",
                encoding="cp1251",
                dtype=str,
                keep_default_na=False,
            )
        frames[name] = frame
    return frames


def mapped(frame, domain):
    frame = frame.copy()
    frame.columns = [str(c).strip() for c in frame.columns]
    if len(set(frame.columns)) != len(frame.columns):
        raise ValueError(f"{domain}: повторяющиеся заголовки.")
    selected = {}
    for field, aliases in ALIASES[domain].items():
        requested = config.COLUMNS.get(domain, {}).get(field)
        choices = (
            [requested] if requested else [c for c in aliases if c in frame.columns]
        )
        if requested and requested not in frame.columns:
            raise ValueError(f"{domain}: нет колонки {requested}.")
        if len(choices) > 1:
            raise ValueError(
                f"{domain}.{field}: подходят {choices}. Выберите колонку через COLUMNS в config.py."
            )
        if not choices:
            if (domain, field) in OPTIONAL:
                continue
            raise ValueError(
                f"{domain}: не найдена колонка {field}; настройте COLUMNS в config.py."
            )
        selected[field] = frame[choices[0]]
    result = pd.DataFrame(selected)
    for column in ("id", "user", "session", "order", "model"):
        if column in result:
            result[column] = result[column].astype(str).str.strip()
            if result[column].eq("").any():
                raise ValueError(f"{domain}.{column}: пустой идентификатор.")
    return result


def numbers(series, label):
    result = pd.to_numeric(series, errors="coerce")
    if (
        result.isna().any()
        or not result.map(lambda n: float("-inf") < n < float("inf")).all()
    ):
        raise ValueError(f"{label}: ожидаются конечные числа с точкой.")
    return result


def winner(series):
    if series.empty:
        return None
    best = series.max()
    # При равенстве показываем все ответы, а не выбираем случайный.
    return ", ".join(sorted(str(k) for k in series.index[series.eq(best)]))


def calculate(frames):
    s, o, i, m = [
        mapped(frames[k], k) for k in ("sessions", "orders", "items", "models")
    ]
    for domain, frame in (("sessions", s), ("orders", o), ("models", m)):
        if frame["id"].duplicated().any():
            raise ValueError(f"{domain}: идентификатор должен быть уникальным.")
    start = pd.Timestamp(config.START_DATE, tz="UTC")
    end = pd.Timestamp(config.END_DATE, tz="UTC")
    if start >= end:
        raise ValueError("Начальная дата должна быть раньше конечной.")
    s["started"] = pd.to_datetime(
        s["started"], utc=True, errors="raise", format="mixed"
    )
    o["created"] = pd.to_datetime(
        o["created"], utc=True, errors="raise", format="mixed"
    )
    if s["started"].isna().any() or o["created"].isna().any():
        raise ValueError("В сессии или заказе не указана дата.")
    s = s[s["started"].ge(start) & s["started"].lt(end)].copy()
    statuses = {x.casefold() for x in config.COMPLETED_STATUSES}
    o = o[
        o["created"].ge(start)
        & o["created"].lt(end)
        & o["status"].str.strip().str.casefold().isin(statuses)
    ].copy()
    i = i[i["order"].isin(o["id"])].copy()
    if not set(o["id"]) <= set(i["order"]):
        raise ValueError("У завершённого заказа нет позиций в файле items.")
    i["quantity"] = numbers(i["quantity"], "items.quantity")
    if (i["quantity"].le(0) | i["quantity"].mod(1).ne(0)).any():
        raise ValueError("items.quantity: количество должно быть положительным целым.")
    buyers = o.merge(
        s[["id", "user", "device"]],
        left_on="session",
        right_on="id",
        suffixes=("", "_session"),
        validate="many_to_one",
        how="left",
    )
    if buyers["id_session"].isna().any():
        raise ValueError("У завершённого заказа нет сессии в выбранном периоде.")
    if buyers["user"].ne(buyers["user_session"]).any():
        raise ValueError("Пользователь заказа не совпадает с пользователем его сессии.")
    visitors = s.groupby("device")["user"].nunique()
    conversion = (
        buyers.groupby("device")["user"].nunique().reindex(visitors.index, fill_value=0)
        / visitors
    )
    first = s.sort_values(["started", "id"]).drop_duplicates("user")
    first_order = o.groupby("user")["created"].min()
    elapsed = first_order - first.set_index("user")["started"]
    elapsed = (
        elapsed[
            elapsed.ge(pd.Timedelta(0)) & elapsed.le(pd.Timedelta(days=7))
        ].dt.total_seconds()
        / 60
    )
    january = first[first["started"].dt.month.eq(1)].copy()
    february_users = set(s.loc[s["started"].dt.month.eq(2), "user"])
    january["returned"] = january["user"].isin(february_users)
    retention = january.groupby("source")["returned"].mean()
    if "amount" in i:
        i["cost"] = numbers(i["amount"], "items.amount")
    elif "price" in i:
        i["cost"] = numbers(i["price"], "items.price") * i["quantity"]
    else:
        raise ValueError(
            "Для стоимости позиций нужна колонка price или amount (см. config.py)."
        )
    if i["cost"].lt(0).any():
        raise ValueError("Стоимость позиции не может быть отрицательной.")
    totals = i.groupby("order")["cost"].sum().reindex(o["id"], fill_value=0)
    q1, q3 = totals.quantile(0.25), totals.quantile(0.75)
    spread = q3 - q1
    remaining = totals.between(q1 - 1.5 * spread, q3 + 1.5 * spread).sum()
    level = config.CORRELATION_LEVEL
    if level not in {"auto", "items", "orders"}:
        raise ValueError("CORRELATION_LEVEL должен быть auto, items или orders.")
    if level == "items" or (level == "auto" and "discount" in i):
        if "discount" not in i:
            raise ValueError("Для корреляции по позициям нужна скидка в items.")
        pairs = pd.DataFrame(
            {
                "discount": numbers(i["discount"], "items.discount"),
                "quantity": i["quantity"],
            }
        )
    else:
        if "discount" not in o:
            raise ValueError(
                "Не найдена discount_percent. Настройте COLUMNS и CORRELATION_LEVEL."
            )
        quantities = i.groupby("order")["quantity"].sum()
        pairs = pd.DataFrame(
            {
                "discount": numbers(o.set_index("id")["discount"], "orders.discount"),
                "quantity": quantities,
            }
        ).dropna()
    correlation = (
        pairs["discount"].corr(pairs["quantity"])
        if len(pairs) >= 2 and pairs.nunique().min() > 1
        else None
    )
    grouped = i.merge(
        m, left_on="model", right_on="id", validate="many_to_one", how="left"
    )
    if (
        grouped["category"].isna().any()
        or grouped["category"].astype(str).str.strip().eq("").any()
    ):
        raise ValueError("У позиции нет модели или категории в справочнике.")
    sales = grouped.groupby("category")["quantity"].sum()
    return {
        "5.1": winner(conversion),
        "5.2": float(elapsed.median()) if not elapsed.empty else None,
        "5.3": winner(retention),
        "5.4": int(remaining),
        "5.5": (
            float(correlation)
            if correlation is not None and pd.notna(correlation)
            else None
        ),
        "5.6": winner(sales),
    }
