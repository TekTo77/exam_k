"""Названия файлов и полей можно поменять под свои CSV."""

FILES = {
    "sessions": "Sessions_analytics.csv",
    "orders": "Orders_analytics.csv",
    "items": "Order_items_analytics.csv",
    "models": "Shoe_models_analytics.csv",
}
# Укажи свои имена, если автоматический выбор не подходит.
# Например: {"sessions": {"started": "date_start"}}
COLUMNS = {}
START_DATE = "2026-01-01"
END_DATE = "2026-04-01"  # Правая граница не включается.
COMPLETED_STATUSES = ("completed", "завершён", "завершен")
# auto: позиции, если скидка в items; иначе количество суммируется по заказу.
CORRELATION_LEVEL = "auto"  # "auto", "items", "orders"
