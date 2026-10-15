from __future__ import annotations

import json
import hashlib
import os
import re
from typing import Any

from config import PROJECT_DIR, DATABASE_MAPPINGS, EXTRA_PRODUCT_FIELDS
from preferences import read_settings
from storage.identifiers import normalize_identifier
from storage.order_operations import OrdersMixin
from storage.schema_adapter import AdaptationMixin
import config as project_config

try:
    import psycopg
except ImportError:
    psycopg = None



def _quote_identifier(value: str) -> str:
    """Имя таблицы или колонки в кавычках SQL."""
    return '"' + str(value).replace('"', '""') + '"'


def _extra_product_aliases(core):
    aliases = {}
    for field, spec in EXTRA_PRODUCT_FIELDS.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", field) or field in set(core) | {
            "total_quantity",
            "price_text",
            "unit",
            "variant",
        }:
            raise ValueError(f"Недопустимое/занятое имя EXTRA_PRODUCT_FIELDS: {field}")
        values = spec.get("aliases", (field,))
        if isinstance(values, str) or not all(isinstance(v, str) for v in values):
            raise ValueError(
                f"aliases для {field} должен быть списком или кортежем строк."
            )
        aliases[field] = (field, *values)
    return aliases


class Row(dict):
    """Строка БД: доступ по имени или номеру колонки."""

    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, statement: str, params: tuple[Any, ...] = ()):
        self.cursor.execute(statement.replace("?", "%s"), params)
        return self

    def executemany(self, statement: str, params):
        self.cursor.executemany(statement.replace("?", "%s"), params)
        return self

    def fetchone(self):
        row = self.cursor.fetchone()
        if row is None:
            return None
        return Row(dict(zip([item.name for item in self.cursor.description], row)))

    def fetchall(self):
        if not self.cursor.description:
            return []
        names = [item.name for item in self.cursor.description]
        return [Row(dict(zip(names, row))) for row in self.cursor.fetchall()]


class PostgresConnection:
    def __init__(self, dsn: str, schema: str):
        if psycopg is None:
            raise RuntimeError(
                "Установи зависимости командой: pip install -r requirements.txt"
            )
        self.raw = psycopg.connect(
            dsn,
            **(
                {"connect_timeout": 5}
                if "connect_timeout" not in psycopg.conninfo.conninfo_to_dict(dsn)
                else {}
            ),
        )
        self.schema = schema
        if not schema or "\x00" in schema:
            self.raw.close()
            raise ValueError("Некорректное имя схемы PostgreSQL.")
        # Читаем только выбранную схему; не подхватываем старые public-таблицы.
        self.raw.execute(
            psycopg.sql.SQL("SET search_path TO {}").format(
                psycopg.sql.Identifier(schema)
            )
        )
        self.raw.commit()

    def execute(self, statement: str, params: tuple[Any, ...] = ()):
        return PostgresCursor(self.raw.cursor()).execute(statement, params)

    def executemany(self, statement: str, params):
        return PostgresCursor(self.raw.cursor()).executemany(statement, params)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        return False


def _read_postgres_config():
    from storage.connection import read_connection_config
    return read_connection_config()


class Database(AdaptationMixin, OrdersMixin):
    """Подключение и чтение данных PostgreSQL."""

    TABLE_ALIASES = {
        "roles": ("roles", "role", "роли", "роль"),
        "users": ("users", "user", "пользователи", "пользователь", "клиенты"),
        "products": (
            "products",
            "product",
            "товары",
            "товар",
            "продукты",
            "обувь",
            "каталог",
        ),
        "sizes": ("sizes", "size", "размеры", "размер"),
        "stock_items": ("stock_items", "stock", "остатки", "склад", "остаток"),
        "orders": ("orders", "order", "заказы", "заказ"),
        "order_items": ("order_items", "order_item", "состав_заказа", "позиции_заказа"),
    }

    COLUMN_ALIASES = {
        "users": {
            "user_id": (
                "user_id",
                "idusers",
                "id_users",
                "id",
                "__row_id",
                "код_пользователя",
                "идентификатор",
            ),
            "login": ("login", "username", "user_name", "логин", "имя_пользователя"),
            "last_name": ("last_name", "lastname", "surname", "фамилия"),
            "first_name": ("first_name", "firstname", "name", "имя"),
            "middle_name": (
                "отчетсво",
                "middle_name",
                "middlename",
                "patronymic",
                "отчество",
            ),
            "role_id": ("role_id", "roleid", "id_role", "роль_id", "код_роли"),
            "role_name": ("role_name", "роль", "role"),
        },
        "roles": {
            "role_id": ("role_id", "id", "__row_id", "код_роли", "идентификатор"),
            "role_name": ("role_name", "name", "название", "роль", "наименование"),
        },
        "products": {
            "product_id": (
                "product_id",
                "id",
                "__row_id",
                "код_товара",
                "артикул",
                "идентификатор",
            ),
            "product_name": (
                "product_name",
                "name",
                "title",
                "наименование_товара",
                "наименование",
                "название",
                "товар",
                "модель",
            ),
            "category": ("category", "категория", "тип", "вид"),
            "subcategory": ("subcategory", "подкатегория"),
            "manufacturer": (
                "производство",
                "manufacturer",
                "brand",
                "производитель",
                "бренд",
            ),
            "composition": ("composition", "состав", "материал"),
            "description": ("description", "описание", "характеристика"),
            "price": ("price", "цена", "стоимость"),
            "quantity_available": (
                "quantity_available",
                "quantity",
                "stock",
                "остаток",
                "количество",
            ),
            "image_path": (
                "image_path",
                "image_file",
                "image_filename",
                "photo_filename",
                "изображение",
                "фото",
                "картинка",
                "image",
                "photo",
                "picture",
                "filename",
            ),
        },
        "sizes": {
            "size_id": ("size_id", "id", "__row_id", "код_размера", "идентификатор"),
            "size_value": ("size_value", "size", "размер", "размер_обуви"),
        },
        "stock_items": {
            "stock_item_id": ("stock_item_id", "id", "__row_id", "код"),
            "product_id": (
                "product_id",
                "id_product",
                "товар_id",
                "код_товара",
                "артикул",
            ),
            "size_id": ("size_id", "id_size", "размер_id", "код_размера"),
            "quantity_available": (
                "quantity_available",
                "quantity",
                "количество_доступное_для_заказа",
                "количество",
                "остаток",
                "остатки",
                "количество_на_складе",
            ),
            "product_name": ("product_name", "наименование_товара", "товар", "name"),
            "manufacturer": ("производство", "manufacturer", "производитель", "brand"),
            "size_value": ("size_value", "size", "размер"),
        },
        "orders": {
            "order_id": ("order_id", "номер_заказа", "код_заказа", "id", "__row_id"),
            "order_date": ("order_date", "date", "дата", "дата_заказа"),
            "user_id": (
                "user_id",
                "id_user",
                "idusers",
                "id_users",
                "пользователь_id",
                "клиент_id",
            ),
            "client_name": ("client_name", "фио", "фио_клиента", "покупатель"),
            "product_id": ("product_id", "id_product", "товар_id", "код_товара"),
            "product_name": ("product_name", "наименование_товара", "товар", "name"),
            "manufacturer": ("производство", "manufacturer", "производитель", "brand"),
            "size_id": ("size_id", "id_size", "размер_id"),
            "size_value": ("size_value", "size", "размер"),
            "category": ("category", "категория"),
            "quantity": ("quantity", "количество"),
            "unit_price": ("unit_price", "цена_за_единицу", "price", "цена"),
        },
        "order_items": {
            "order_item_id": ("order_item_id", "id", "__row_id"),
            "order_id": ("order_id", "id_order", "заказ_id", "номер_заказа"),
            "product_id": ("product_id", "id_product", "товар_id", "код_товара"),
            "size_id": ("size_id", "id_size", "размер_id", "код_размера"),
            "quantity": ("quantity", "количество"),
            "unit_price": (
                "unit_price",
                "цена_за_единицу",
                "price",
                "цена",
                "стоимость",
            ),
            "product_name": ("product_name", "наименование_товара", "товар", "name"),
            "manufacturer": ("производство", "manufacturer", "производитель", "brand"),
            "size_value": ("size_value", "size", "размер"),
        },
    }
    COLUMN_ALIASES["products"].update(
        _extra_product_aliases(COLUMN_ALIASES["products"])
    )

    def __init__(self, connection_config=None):
        config = (
            connection_config
            if connection_config is not None
            else _read_postgres_config()
        )
        if not config:
            raise RuntimeError("Не найдены настройки подключения к PostgreSQL.")
        self.backend = "postgres"
        self.connection = PostgresConnection(config["dsn"], config["schema"])
        self.mapping_key = hashlib.sha256(
            (config["dsn"] + "|" + config["schema"]).encode()
        ).hexdigest()[:20]
        self.active_tables = config.get("active_tables")
        try:
            if project_config.CREATE_COMPATIBILITY_TABLES:
                self._ensure_postgres_schema()
            self._refresh_domain_mapping()
        except Exception:
            self.connection.close()
            raise

    def close(self) -> None:
        self.connection.close()

    def _ensure_postgres_schema(self) -> None:
        """Создаём пустые стандартные таблицы, если их нет."""
        # Импортированные таблицы не пересоздаём.
        statements = [
            """CREATE TABLE IF NOT EXISTS roles (
                role_id BIGSERIAL PRIMARY KEY, role_name TEXT NOT NULL UNIQUE
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                user_id BIGSERIAL PRIMARY KEY, last_name TEXT NOT NULL,
                first_name TEXT NOT NULL, middle_name TEXT NOT NULL DEFAULT '',
                login TEXT NOT NULL UNIQUE, role_id BIGINT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS products (
                product_id BIGSERIAL PRIMARY KEY, category TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '', product_name TEXT NOT NULL,
                manufacturer TEXT NOT NULL DEFAULT '', composition TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                price NUMERIC NOT NULL DEFAULT 0 CHECK (price >= 0)
            )""",
            """CREATE TABLE IF NOT EXISTS sizes (
                size_id BIGSERIAL PRIMARY KEY, size_value INTEGER NOT NULL UNIQUE
            )""",
            """CREATE TABLE IF NOT EXISTS stock_items (
                stock_item_id BIGSERIAL PRIMARY KEY, product_id BIGINT NOT NULL,
                size_id BIGINT NOT NULL, quantity_available INTEGER NOT NULL DEFAULT 0,
                UNIQUE(product_id, size_id)
            )""",
            """CREATE TABLE IF NOT EXISTS orders (
                order_id BIGSERIAL PRIMARY KEY, order_date DATE NOT NULL, user_id BIGINT NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS order_items (
                order_item_id BIGSERIAL PRIMARY KEY, order_id BIGINT NOT NULL,
                product_id BIGINT NOT NULL, size_id BIGINT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0), unit_price NUMERIC NOT NULL CHECK (unit_price >= 0),
                UNIQUE(order_id, product_id, size_id)
            )""",
        ]
        with self.connection:
            for statement in statements:
                self._safe_schema_execute(statement)

    def _safe_schema_execute(self, statement: str) -> bool:
        """При ошибке откатываем только эту подготовку схемы."""
        try:
            self.connection.raw.execute("SAVEPOINT chudo_schema_step")
            self.connection.raw.execute(statement)
            self.connection.raw.execute("RELEASE SAVEPOINT chudo_schema_step")
            return True
        except Exception:
            try:
                self.connection.raw.execute("ROLLBACK TO SAVEPOINT chudo_schema_step")
                self.connection.raw.execute("RELEASE SAVEPOINT chudo_schema_step")
            except Exception:
                self.connection.raw.rollback()
            return False

    def _safe_fetch_one(
        self, statement: str, params: tuple[Any, ...] = (), default=None, strict=False
    ):
        """Читаем строку; при ошибке восстанавливаем транзакцию."""
        try:
            self.connection.raw.execute("SAVEPOINT chudo_read_step")
            row = self.connection.execute(statement, params).fetchone()
            self.connection.raw.execute("RELEASE SAVEPOINT chudo_read_step")
            return row
        except Exception:
            try:
                self.connection.raw.execute("ROLLBACK TO SAVEPOINT chudo_read_step")
                self.connection.raw.execute("RELEASE SAVEPOINT chudo_read_step")
            except Exception:
                self.connection.raw.rollback()
            if strict:
                raise
            return default

    def _safe_fetch_all(
        self, statement: str, params: tuple[Any, ...] = (), default=None, strict=False
    ):
        """Читаем строки с обработкой ошибок необязательных таблиц."""
        try:
            self.connection.raw.execute("SAVEPOINT chudo_read_step")
            rows = self.connection.execute(statement, params).fetchall()
            self.connection.raw.execute("RELEASE SAVEPOINT chudo_read_step")
            return rows
        except Exception:
            try:
                self.connection.raw.execute("ROLLBACK TO SAVEPOINT chudo_read_step")
                self.connection.raw.execute("RELEASE SAVEPOINT chudo_read_step")
            except Exception:
                self.connection.raw.rollback()
            if strict:
                raise
            return [] if default is None else default

    def _table_columns(self, table: str) -> set[str]:
        rows = self._safe_fetch_all(
            """SELECT column_name FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name=?""",
            (table,),
        )
        return {str(row[0]) for row in rows}

    def _refresh_domain_mapping(self) -> None:
        """Находим таблицы и колонки по данным и настройкам."""
        rows = self._safe_fetch_all("""SELECT table_name FROM information_schema.tables
            WHERE table_schema=current_schema() AND table_type='BASE TABLE'""")
        available = [str(row[0]) for row in rows]
        if getattr(self, "active_tables", None) is not None:
            available = [name for name in available if name in self.active_tables]
        self._order_cache = None
        self.domain_tables: dict[str, str] = {}
        self.domain_columns: dict[str, dict[str, str | None]] = {}
        for canonical, aliases in self.TABLE_ALIASES.items():
            lowered = {normalize_identifier(name): name for name in available}
            candidates = [lowered[name] for name in aliases if name in lowered]
            if not candidates:
                continue
            # Предпочитаем заполненную таблицу.
            candidates.sort(key=lambda name: self._table_row_count(name), reverse=True)
            table = candidates[0]
            self.domain_tables[canonical] = table
            columns = self._table_columns(table)
            self.domain_columns[canonical] = self.suggest_columns(canonical, columns)
        self.available_tables = sorted(available)
        self.mapping_warnings = []
        self._disabled_product_fields = set()
        configured = {
            **read_settings().get("mappings", {}).get(self.mapping_key, {}),
            **DATABASE_MAPPINGS,
        }
        for canonical, mapping in configured.items():
            if canonical not in self.TABLE_ALIASES:
                continue
            if mapping is None or mapping.get("table") is None:
                self.domain_tables.pop(canonical, None)
                self.domain_columns.pop(canonical, None)
                continue
            table = mapping.get("table")
            if table not in available:
                self.mapping_warnings.append(
                    f"Таблица {table} больше не найдена: используется автоопределение."
                )
                continue
            columns = self._table_columns(table)
            column_map = self.suggest_columns(canonical, columns)
            for field, column in mapping.get("columns", {}).items():
                if field not in self.COLUMN_ALIASES.get(canonical, {}):
                    self.mapping_warnings.append(
                        f"Неизвестное поле настройки {canonical}.{field}."
                    )
                    continue
                if canonical == "products" and column is None:
                    self._disabled_product_fields.add(field)
                if column is None or column in columns:
                    column_map[field] = column
                else:
                    self.mapping_warnings.append(
                        f"Колонка {table}.{column} больше не найдена: используется автоопределение."
                    )
            self.domain_tables[canonical] = table
            self.domain_columns[canonical] = column_map
        self._configure_features()
        if not all(
            self._domain_column("products", f)
            for f in ("product_id", "product_name", "price")
        ):
            self.mapping_warnings.append(
                "Для каталога сопоставьте products: product_id, product_name и price в config.py или окне «Настройка данных»."
            )
        if self.orders_enabled:
            self._ensure_order_money_column()
            self._ensure_order_user_link()

    def suggest_columns(self, canonical, columns):
        # Проверяем варианты названий по порядку.
        normalized = {
            normalize_identifier(column): column for column in sorted(columns)
        }
        result = {}
        for field, aliases in self.COLUMN_ALIASES.get(canonical, {}).items():
            result[field] = next(
                (
                    normalized[normalize_identifier(a)]
                    for a in aliases
                    if normalize_identifier(a) in normalized
                ),
                None,
            )
            if result[field] is None and not field.endswith("_id"):
                matches = [
                    column
                    for column in sorted(columns)
                    if not normalize_identifier(column).endswith("_id")
                    and any(
                        len(a) > 3 and a in normalize_identifier(column)
                        for a in aliases
                    )
                ]
                if len(matches) == 1:
                    result[field] = matches[0]
        return result

    def _table_row_count(self, table: str) -> int:
        result = self._safe_fetch_one(
            f"SELECT COUNT(*) FROM {_quote_identifier(table)}", default=None
        )
        try:
            return int(result[0]) if result else 0
        except (TypeError, ValueError, IndexError):
            return 0

    def _domain_table(self, canonical: str) -> str | None:
        return getattr(self, "domain_tables", {}).get(canonical)

    def _domain_column(self, canonical: str, field: str) -> str | None:
        return getattr(self, "domain_columns", {}).get(canonical, {}).get(field)

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()):
        return self.connection.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()):
        return self.connection.execute(sql, params).fetchall()

    def find_user_by_login(self, login: str):
        table = self._domain_table("users")
        column = self._domain_column("users", "login")
        if not table or not column:
            return None
        rows = self._safe_fetch_all(
            f"SELECT * FROM {_quote_identifier(table)} WHERE lower({_quote_identifier(column)}::text)=lower(?)",
            (login.strip(),),
            strict=True,
        )
        if len(rows) > 1:
            raise ValueError(
                "Этот логин встречается у нескольких пользователей. Сделайте логины уникальными."
            )
        if not rows:
            return None
        source = rows[0]
        row = Row(source)
        row["role_name"] = self._role_for_user(source)
        for target in ("user_id", "last_name", "first_name", "middle_name"):
            column = self._domain_column("users", target)
            row[target] = (
                source.get(column) if column else (None if target == "user_id" else "")
            )
        return row

    def categories(self) -> list[str]:
        return sorted(
            {str(row["category"]) for row in self.products() if row.get("category")}
        )

    def products(
        self,
        search: str = "",
        category: str = "Все категории",
        sort: str = "По возрастанию цены",
    ):
        table = self._domain_table("products")
        product_id = self._domain_column("products", "product_id")
        product_name = self._domain_column("products", "product_name")
        category_column = self._domain_column("products", "category")
        price = self._domain_column("products", "price")
        if not table or not product_id or not product_name or not price:
            return []
        description = self._domain_column("products", "description")
        manufacturer = self._domain_column("products", "manufacturer")
        subcategory = self._domain_column("products", "subcategory")
        stock_table = self._domain_table("stock_items")
        stock_quantity = self._domain_column("stock_items", "quantity_available")
        relationship = self._stock_join()
        mode = getattr(self, "stock_mode", "none")
        if mode == "separate" and stock_table and stock_quantity and relationship:
            stock_join = (
                f"LEFT JOIN {_quote_identifier(stock_table)} s ON {relationship}"
            )
            total_quantity = f"COALESCE(SUM(s.{_quote_identifier(stock_quantity)}), 0)"
        else:
            stock_join = ""
            product_quantity = self._domain_column("products", "quantity_available")
            total_quantity = (
                f"p.{_quote_identifier(product_quantity)}"
                if mode == "product" and product_quantity
                else "NULL"
            )
        conditions = []
        params: list[Any] = []
        if search.strip():
            search_conditions = [
                f"lower(p.{_quote_identifier(product_name)}::text) LIKE ?"
            ]
            if description:
                search_conditions.append(
                    f"lower(p.{_quote_identifier(description)}::text) LIKE ?"
                )
            conditions.append("(" + " OR ".join(search_conditions) + ")")
            needle = f"%{search.strip().lower()}%"
            params.extend([needle] * len(search_conditions))
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        order = "DESC" if sort == "По убыванию цены" else "ASC"
        select_columns = [
            f"p.{_quote_identifier(product_id)} AS product_id",
            f"p.{_quote_identifier(product_name)} AS product_name",
            (
                f"p.{_quote_identifier(category_column)} AS category"
                if category_column
                else "'' AS category"
            ),
            f"p.{_quote_identifier(price)} AS price",
            (
                f"p.{_quote_identifier(description)} AS description"
                if description
                else "'' AS description"
            ),
            (
                f"p.{_quote_identifier(manufacturer)} AS manufacturer"
                if manufacturer
                else "'' AS manufacturer"
            ),
            (
                f"p.{_quote_identifier(subcategory)} AS subcategory"
                if subcategory
                else "'' AS subcategory"
            ),
        ]
        for field in ("composition", "image_path", *EXTRA_PRODUCT_FIELDS):
            column = self._domain_column("products", field)
            alias = _quote_identifier(field) if field in EXTRA_PRODUCT_FIELDS else field
            select_columns.append(
                f"p.{_quote_identifier(column)} AS {alias}"
                if column
                else f"'' AS {alias}"
            )
        group_columns = [
            item.split(" AS ")[0] for item in select_columns if item.startswith("p.")
        ]
        if mode == "product" and product_quantity:
            group_columns.append(f"p.{_quote_identifier(product_quantity)}")
        result = self._safe_fetch_all(
            f"""SELECT {', '.join(select_columns)}, {total_quantity} AS total_quantity
            FROM {_quote_identifier(table)} p {stock_join}{where}
            GROUP BY {', '.join(group_columns)}
            ORDER BY p.{_quote_identifier(price)} {order}, p.{_quote_identifier(product_name)}""",
            tuple(params),
            strict=True,
        )
        result = self._enrich_products(result)
        if category and category != "Все категории":
            result = [r for r in result if str(r.get("category", "")) == str(category)]
        return result

    def product(self, product_id: int):
        return next(
            (
                row
                for row in self.products()
                if str(row.get("product_id")) == str(product_id)
            ),
            None,
        )

    def products_for_id(self, product_id: int):
        return [
            row
            for row in self.products()
            if str(row.get("product_id")) == str(product_id)
        ]
