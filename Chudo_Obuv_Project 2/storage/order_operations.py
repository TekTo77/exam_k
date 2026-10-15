"""Заказы, остатки и права пользователей."""

import unicodedata
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def quote(value):
    return '"' + str(value).replace('"', '""') + '"'


def normalized(value):
    return " ".join(unicodedata.normalize("NFKC", str(value or "")).split()).casefold()


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        text = str(value).strip()
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, TypeError) as error:
        from config import DATE_INPUT_FORMATS

        for fmt in DATE_INPUT_FORMATS:
            try:
                return datetime.strptime(str(value).strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError(
            f"Не удалось прочитать дату {value!r}. Используйте ГГГГ-ММ-ДД или настройте DATE_INPUT_FORMATS."
        ) from error


def size_text(value):
    if value is None:
        return ""
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except InvalidOperation:
        return str(value)


class OrdersMixin:
    STAFF = {"Менеджер", "Администратор"}

    def _all(self, domain):
        table = self._domain_table(domain)
        return (
            self._safe_fetch_all(f"SELECT * FROM {quote(table)}", strict=True)
            if table
            else []
        )

    def _value(self, row, domain, field, default=None):
        if domain == "products" and field in row.get("_display_fields", {}):
            return row["_display_fields"][field]
        column = self._domain_column(domain, field)
        return row.get(column, default) if column else default

    def _name(self, user):
        return " ".join(
            str(self._value(user, "users", field, "") or "").strip()
            for field in ("last_name", "first_name", "middle_name")
        ).strip()

    def clients(self, actor_id):
        self._authorize(actor_id, self.STAFF)
        rows = [
            dict(
                user_id=self._value(row, "users", "user_id"),
                client_name=self._name(row),
                login=self._value(row, "users", "login", ""),
            )
            for row in self._all("users")
        ]
        return sorted(
            rows, key=lambda row: (row["client_name"].casefold(), str(row["user_id"]))
        )

    def _user(self, user_id):
        table, pk = self._domain_table("users"), self._domain_column("users", "user_id")
        if not table or not pk or user_id is None:
            raise PermissionError("Необходимо войти в приложение.")
        row = self._safe_fetch_one(
            f"SELECT * FROM {quote(table)} WHERE {quote(pk)}=?", (user_id,), strict=True
        )
        if row is None:
            raise PermissionError("Пользователь больше не найден в базе данных.")
        return row

    def _authorize(self, actor_id, allowed=None):
        user = self._user(actor_id)
        role = self._role_for_user(user)
        if allowed is not None and role not in allowed:
            raise PermissionError("У этой роли нет доступа к выбранному действию.")
        return role

    def _role_for_user(self, user):
        value = self._value(user, "users", "role_name")
        role_id = self._value(user, "users", "role_id")
        table = self._domain_table("roles")
        pk = self._domain_column("roles", "role_id")
        name = self._domain_column("roles", "role_name")
        if role_id is not None and table and pk and name:
            row = self._safe_fetch_one(
                f"SELECT {quote(name)} AS role_name FROM {quote(table)} WHERE {quote(pk)}=?",
                (role_id,),
                strict=True,
            )
            if row:
                value = row["role_name"]
        role = str(value or "Пользователь").strip()
        from config import ROLE_ALIASES

        aliases = {str(k).casefold(): v for k, v in ROLE_ALIASES.items()}
        return {
            "admin": "Администратор",
            "administrator": "Администратор",
            "администратор": "Администратор",
            "manager": "Менеджер",
            "менеджер": "Менеджер",
            **aliases,
        }.get(role.casefold(), role)

    def _entity(self, domain, key):
        field = {"products": "product_id", "sizes": "size_id"}[domain]
        table, column = self._domain_table(domain), self._domain_column(domain, field)
        if not table or not column:
            raise ValueError(f"Не настроена таблица или идентификатор: {domain}.")
        row = self._safe_fetch_one(
            f"SELECT * FROM {quote(table)} WHERE {quote(column)}=?", (key,), strict=True
        )
        if row is None:
            raise ValueError(f"Объект {domain} с идентификатором {key} не найден.")
        return row

    def _product_match(self, row, domain, products):
        identifier = self._value(row, domain, "product_id")
        if identifier is not None:
            matches = [
                p
                for p in products
                if str(self._value(p, "products", "product_id")) == str(identifier)
            ]
        else:
            name = normalized(self._value(row, domain, "product_name"))
            brand = normalized(self._value(row, domain, "manufacturer"))
            candidates = [
                p
                for p in products
                if not brand
                or normalized(self._value(p, "products", "manufacturer")) == brand
            ]
            matches = [
                p
                for p in candidates
                if normalized(self._value(p, "products", "product_name")) == name
            ]
            if not matches and name:
                # Допускаем короткое название только при одном совпадении.
                matches = [
                    p
                    for p in candidates
                    if normalized(
                        self._value(p, "products", "product_name")
                    ).startswith(name + " — ")
                ]
        if len(matches) != 1:
            raise ValueError(
                f"Неоднозначный или отсутствующий товар: {self._value(row, domain, 'product_name', identifier)}."
            )
        return matches[0]

    @staticmethod
    def _sql_name(expression):
        return f"lower(btrim(regexp_replace(replace({expression}::text, chr(160), ' '), '[[:space:]]+', ' ', 'g')))"

    def _stock_join(self):
        pk = self._domain_column("products", "product_id")
        stock_pk = self._domain_column("stock_items", "product_id")
        if stock_pk:
            return f"s.{quote(stock_pk)}=p.{quote(pk)}"
        name = self._domain_column("stock_items", "product_name")
        parent_name = self._domain_column("products", "product_name")
        if not name or not parent_name:
            return None
        a = self._sql_name(f"s.{quote(name)}")
        b = self._sql_name(f"p.{quote(parent_name)}")
        condition = f"({a}={b} OR strpos({b}, {a} || ' — ')=1)"
        brand = self._domain_column("stock_items", "manufacturer")
        parent_brand = self._domain_column("products", "manufacturer")
        if brand and parent_brand:
            condition += f" AND {self._sql_name(f's.{quote(brand)}')}={self._sql_name(f'p.{quote(parent_brand)}')}"
        return condition

    def product_sizes(self, product_id):
        if not self.variants_enabled:
            return self._plain_choices(product_id)
        stock, sizes = self._domain_table("stock_items"), self._domain_table("sizes")
        if self.stock_mode == "none":
            if not sizes:
                raise ValueError("Варианты включены, но справочник sizes не настроен.")
            return [
                dict(
                    stock_item_id=None,
                    product_id=product_id,
                    size_id=self._value(row, "sizes", "size_id"),
                    size_value=self._value(row, "sizes", "size_value"),
                    quantity_available=None,
                )
                for row in self._all("sizes")
            ]
        if not sizes:
            return self._inline_choices(product_id)
        pk = self._domain_column("products", "product_id")
        stock_id = self._domain_column("stock_items", "stock_item_id")
        quantity = self._domain_column("stock_items", "quantity_available")
        size_id = self._domain_column("sizes", "size_id")
        size_value = self._domain_column("sizes", "size_value")
        stock_size = self._domain_column("stock_items", "size_id")
        stock_value = self._domain_column("stock_items", "size_value")
        join = self._stock_join()
        if not all(
            (stock, sizes, pk, stock_id, quantity, size_id, size_value, join)
        ) or not (stock_size or stock_value):
            raise ValueError(
                "Для выбора размера настройте таблицы товаров, размеров и остатков."
            )
        size_join = (
            f"s.{quote(stock_size)}=z.{quote(size_id)}"
            if stock_size
            else f"s.{quote(stock_value)}=z.{quote(size_value)}"
        )
        return self._safe_fetch_all(
            f"""SELECT s.{quote(stock_id)} AS stock_item_id,
            p.{quote(pk)} AS product_id, z.{quote(size_id)} AS size_id,
            z.{quote(size_value)} AS size_value, s.{quote(quantity)} AS quantity_available
            FROM {quote(stock)} s JOIN {quote(self._domain_table("products"))} p ON {join}
            JOIN {quote(sizes)} z ON {size_join} WHERE p.{quote(pk)}=?
            ORDER BY z.{quote(size_value)}""",
            (product_id,),
            strict=True,
        )

    def _stock(self, product_id, size_id, lock=False):
        if self.stock_mode == "none":
            self._entity("products", product_id)
            if (
                self.variants_enabled
                and len(
                    [
                        r
                        for r in self.product_sizes(product_id)
                        if str(r["size_id"]) == str(size_id)
                    ]
                )
                != 1
            ):
                raise ValueError("Выбранный вариант не найден.")
            return None, None, None, None, None
        if self.stock_mode == "product":
            table = self._domain_table("products")
            pk = self._domain_column("products", "product_id")
            column = self._domain_column("products", "quantity_available")
            current = self.fetch_one(
                f"SELECT {quote(column)} AS quantity FROM {quote(table)} WHERE {quote(pk)}=?"
                + (" FOR UPDATE" if lock else ""),
                (product_id,),
            )
            if not current:
                raise ValueError("Товар больше не найден.")
            return (
                table,
                pk,
                column,
                product_id,
                self._stock_quantity(current["quantity"]),
            )
        choices = [
            r
            for r in self.product_sizes(product_id)
            if str(r["size_id"]) == str(size_id)
        ]
        if len(choices) != 1:
            raise ValueError(
                "Для товара и размера требуется одна однозначная строка остатка."
            )
        row = choices[0]
        table = self._domain_table("stock_items")
        pk = self._domain_column("stock_items", "stock_item_id")
        column = self._domain_column("stock_items", "quantity_available")
        current = self.fetch_one(
            f"SELECT {quote(column)} AS quantity FROM {quote(table)} "
            f"WHERE {quote(pk)}=?" + (" FOR UPDATE" if lock else ""),
            (row["stock_item_id"],),
        )
        if current is None:
            raise ValueError("Остаток был удалён. Обновите каталог.")
        return (
            table,
            pk,
            column,
            row["stock_item_id"],
            self._stock_quantity(current["quantity"]),
        )

    def available_quantity(self, product_id, size_id):
        return self._stock(product_id, size_id)[4]

    def _change_stock(self, product_id, size_id, delta):
        table, pk, column, identifier, available = self._stock(
            product_id, size_id, lock=True
        )
        if table is None:
            return
        if available + delta < 0:
            raise ValueError("Недостаточный остаток товара. Обновите каталог.")
        self.connection.execute(
            f"UPDATE {quote(table)} SET {quote(column)}={quote(column)}+? WHERE {quote(pk)}=?",
            (delta, identifier),
        )

    def _layout(self):
        fields = self.domain_columns.get("orders", {})
        flat = bool(
            fields.get("quantity")
            and fields.get("unit_price")
            and (fields.get("product_id") or fields.get("product_name"))
        )
        if (
            not self._domain_table("orders")
            or not fields.get("order_id")
            or not fields.get("order_date")
        ):
            raise ValueError(
                "Не найдены номер и дата заказа в импортированной таблице."
            )
        return "flat" if flat else "separate"

    def _ensure_order_money_column(self):
        """Разрешаем дробные цены после скидки."""
        domain = "orders" if self._layout() == "flat" else "order_items"
        table = self._domain_table(domain)
        column = self._domain_column(domain, "unit_price")
        if not table or not column:
            return
        with self.connection:
            metadata = self.fetch_one(
                """SELECT data_type FROM information_schema.columns
                WHERE table_schema=current_schema() AND table_name=? AND column_name=?""",
                (table, column),
            )
            if metadata and metadata["data_type"] in {
                "smallint",
                "integer",
                "bigint",
                "real",
                "double precision",
            }:
                self.connection.execute("SET LOCAL lock_timeout = '5s'")
                self.connection.execute(
                    f"ALTER TABLE {quote(table)} ALTER COLUMN {quote(column)} "
                    f"TYPE NUMERIC USING {quote(column)}::numeric"
                )

    def _primary_key(self, table):
        rows = self._safe_fetch_all(
            """SELECT k.column_name, c.data_type, c.column_default, c.is_identity
            FROM information_schema.table_constraints t
            JOIN information_schema.key_column_usage k ON k.constraint_name=t.constraint_name
             AND k.table_schema=t.table_schema AND k.table_name=t.table_name
            JOIN information_schema.columns c ON c.table_schema=k.table_schema
             AND c.table_name=k.table_name AND c.column_name=k.column_name
            WHERE t.table_schema=current_schema() AND t.table_name=? AND t.constraint_type='PRIMARY KEY'
            ORDER BY k.ordinal_position""",
            (table,),
            strict=True,
        )
        if len(rows) != 1:
            raise ValueError(
                f"Таблица {table} должна иметь один первичный ключ для идентификатора строки."
            )
        return rows[0]

    def _next_identifier(self, table, column, data_type):
        if data_type in {
            "smallint",
            "integer",
            "bigint",
            "numeric",
            "real",
            "double precision",
        }:
            row = self.fetch_one(
                f"SELECT COALESCE(MAX({quote(column)}),0)+1 AS next_id FROM {quote(table)}"
            )
            return int(row["next_id"])
        return uuid.uuid4() if data_type == "uuid" else uuid.uuid4().hex

    def _insert(self, table, values):
        from config import INSERT_DEFAULTS

        defaults = dict(INSERT_DEFAULTS.get(table, {}))
        domain = next((d for d, t in self.domain_tables.items() if t == table), None)
        defaults.update(INSERT_DEFAULTS.get(domain, {}))
        values = {**defaults, **dict(values)}
        columns = self._table_columns(table)
        unknown = set(values) - set(columns)
        if unknown:
            raise ValueError(
                f"INSERT_DEFAULTS: в {table} нет колонок {sorted(unknown)}."
            )
        pk = self._primary_key(table)
        if (
            pk["column_name"] not in values
            and not pk["column_default"]
            and pk["is_identity"] != "YES"
        ):
            values[pk["column_name"]] = self._next_identifier(
                table, pk["column_name"], pk["data_type"]
            )
        names = list(values)
        return self.connection.execute(
            f"INSERT INTO {quote(table)} ({', '.join(map(quote, names))}) "
            f"VALUES ({', '.join('?' for _ in names)}) RETURNING {quote(pk['column_name'])}",
            tuple(values[n] for n in names),
        ).fetchone()[0]

    def _ensure_order_user_link(self):
        """Добавляем ID клиента старым заказам. Неоднозначные ФИО не связываем."""
        table = self._domain_table("orders")
        users = self._domain_table("users")
        pk = self._domain_column("users", "user_id")
        name = self._domain_column("orders", "client_name")
        if not all((table, users, pk, name)):
            return
        column = self._domain_column("orders", "user_id")
        with self.connection:
            if not column:
                metadata = self.fetch_one(
                    """SELECT udt_schema, udt_name FROM information_schema.columns
                    WHERE table_schema=current_schema() AND table_name=? AND column_name=?""",
                    (users, pk),
                )
                if not metadata:
                    return
                column = "user_id"
                self.connection.execute(
                    f"ALTER TABLE {quote(table)} ADD COLUMN IF NOT EXISTS {quote(column)} "
                    f"{quote(metadata['udt_schema'])}.{quote(metadata['udt_name'])}"
                )
                self.domain_columns["orders"]["user_id"] = column
            candidates = defaultdict(list)
            for user in self._all("users"):
                key = normalized(self._name(user))
                if key:
                    candidates[key].append(self._value(user, "users", "user_id"))
            for row in self._all("orders"):
                raw_name = row.get(name)
                identifiers = candidates.get(normalized(raw_name), [])
                if (
                    row.get(column) is None
                    and raw_name is not None
                    and len(identifiers) == 1
                ):
                    self.connection.execute(
                        f"UPDATE {quote(table)} SET {quote(column)}=? WHERE {quote(column)} IS NULL AND {quote(name)}=?",
                        (identifiers[0], raw_name),
                    )
            unresolved = self.fetch_one(
                f"SELECT COUNT(*) AS n FROM {quote(table)} WHERE {quote(column)} IS NULL"
            )["n"]
        if unresolved:
            self.mapping_warnings.append(
                f"Заказы: {unresolved} строк без однозначного клиента. "
                "Укажите ID клиента в БД; эти строки доступны только сотрудникам."
            )

    def _snapshot(self, refresh=False, customer_id=None):
        if not self.orders_enabled:
            return {}, defaultdict(list), self._order_products()
        if (
            customer_id is None
            and not refresh
            and getattr(self, "_order_cache", None) is not None
        ):
            return self._order_cache
        layout = self._layout()
        users, products, sizes = (
            self._all("users"),
            self._order_products(),
            self._all("sizes") if self.variants_enabled else [],
        )
        user_ids = {str(self._value(u, "users", "user_id")): u for u in users}
        names = defaultdict(list)
        for user in users:
            names[normalized(self._name(user))].append(user)
        headers, lines = {}, defaultdict(list)
        source = self._all("orders")
        item_source = source if layout == "flat" else self._all("order_items")
        # Все позиции одного заказа должны принадлежать одному клиенту.
        hidden_keys = set()
        if customer_id is not None:
            for row in source:
                owner = self._value(row, "orders", "user_id")
                if owner is None:
                    candidates = names[
                        normalized(self._value(row, "orders", "client_name"))
                    ]
                    if len(candidates) == 1:
                        owner = self._value(candidates[0], "users", "user_id")
                if owner is None or str(owner) != str(customer_id):
                    hidden_keys.add(self._value(row, "orders", "order_id"))
        for row in source:
            key = self._value(row, "orders", "order_id")
            if key in hidden_keys:
                continue
            user_id = self._value(row, "orders", "user_id")
            client = user_ids.get(str(user_id)) if user_id is not None else None
            fullname = self._value(row, "orders", "client_name", "")
            # Если ID указан, не заменяем владельца по ФИО.
            if user_id is None and fullname:
                candidates = names[normalized(fullname)]
                if len(candidates) == 1:
                    client = candidates[0]
                    user_id = self._value(client, "users", "user_id")
            if customer_id is not None and (
                user_id is None or str(user_id) != str(customer_id)
            ):
                continue
            header = dict(
                order_id=key,
                order_date=as_date(self._value(row, "orders", "order_date")),
                user_id=user_id,
                client_name=(
                    self._name(client)
                    if client
                    else str(fullname or f"Клиент ID {user_id}")
                ),
                total_sum=Decimal("0.00"),
            )
            if key in headers and any(
                headers[key][f] != header[f]
                for f in ("order_date", "user_id", "client_name")
            ):
                raise ValueError(
                    f"У строк заказа №{key} разные даты или клиенты. Исправьте исходные данные."
                )
            headers[key] = header
        domain = "orders" if layout == "flat" else "order_items"
        line_pk = self._primary_key(self._domain_table(domain))["column_name"]
        for row in item_source:
            key = self._value(row, domain, "order_id")
            if key not in headers:
                if customer_id is not None:
                    continue
                raise ValueError(
                    f"У позиции заказа отсутствует родительский заказ №{key}."
                )
            product = self._product_match(row, domain, products)
            size_id = self._value(row, domain, "size_id")
            size_value = self._value(row, domain, "size_value")
            matching_sizes = [
                z
                for z in sizes
                if (
                    str(self._value(z, "sizes", "size_id")) == str(size_id)
                    if size_id is not None
                    else size_text(self._value(z, "sizes", "size_value"))
                    == size_text(size_value)
                )
            ]
            if self.variants_enabled and not self._domain_table("sizes"):
                value = size_value if size_value is not None else size_id
                if value is None:
                    raise ValueError(f"У позиции заказа №{key} не указан вариант.")
                size = {
                    "_inline_id": size_id if size_id is not None else value,
                    "_inline_value": value,
                }
            elif self.variants_enabled and len(matching_sizes) != 1:
                raise ValueError(
                    f"Не найден однозначный вариант позиции заказа №{key}. Проверьте mappings sizes и size_id/size_value либо отключите PRODUCT_VARIANTS_ENABLED."
                )
            else:
                size = matching_sizes[0] if self.variants_enabled else {}
            quantity = self._stock_quantity(self._value(row, domain, "quantity"))
            price = Decimal(str(self._value(row, domain, "unit_price")))
            if quantity == 0 or not price.is_finite() or price < 0:
                raise ValueError(
                    f"У позиции заказа №{key} некорректное количество или цена."
                )
            item = dict(
                order_item_id=row[line_pk],
                product_id=self._value(product, "products", "product_id"),
                size_id=size.get("_inline_id", self._value(size, "sizes", "size_id")),
                size_value=size.get(
                    "_inline_value", self._value(size, "sizes", "size_value")
                ),
                product_name=self._value(product, "products", "product_name"),
                manufacturer=self._value(product, "products", "manufacturer", ""),
                quantity=quantity,
                unit_price=price,
                line_total=quantity * price,
            )
            lines[key].append(item)
            headers[key]["total_sum"] += item["line_total"]
        result = headers, lines, products
        if customer_id is None:
            self._order_cache = result
        return result

    def _visible_orders(self, actor_id):
        role = self._authorize(actor_id)
        return self._snapshot(
            refresh=True, customer_id=None if role in self.STAFF else actor_id
        )

    def orders(self, actor_id=None):
        headers, _, _ = self._visible_orders(actor_id)
        return sorted(
            headers.values(),
            key=lambda o: (o["order_date"], str(o["order_id"]).zfill(20)),
            reverse=True,
        )

    def order(self, order_id, actor_id=None):
        return self._visible_orders(actor_id)[0].get(order_id)

    def order_items(self, order_id, actor_id=None):
        headers, lines, _ = self._visible_orders(actor_id)
        if order_id not in headers:
            raise PermissionError("Заказ не найден или недоступен этому пользователю.")
        return lines.get(order_id, [])

    def discounted_price(self, product_id, on_date=None):
        return float(self.discount_info(product_id, on_date)["price"])

    def discount_info(self, product_id, on_date=None):
        """Цена и объяснение скидки для каталога и карточки товара."""
        from config import NEW_PRODUCT_DISCOUNT

        try:
            discount = Decimal(str(NEW_PRODUCT_DISCOUNT))
        except InvalidOperation as error:
            raise ValueError(
                "NEW_PRODUCT_DISCOUNT должен быть числом от 0 до 1."
            ) from error
        if not discount.is_finite() or not 0 <= discount <= 1:
            raise ValueError("NEW_PRODUCT_DISCOUNT должен быть числом от 0 до 1.")
        product = self._entity("products", product_id)
        price = Decimal(str(self._value(product, "products", "price")))
        if not price.is_finite() or price < 0:
            raise ValueError(f"У товара {product_id} некорректная цена.")
        first = as_date(on_date or date.today()).replace(day=1)
        end = first - timedelta(days=1)
        start = end.replace(day=1)

        def result(previous=False, history=True):
            applied = discount > 0 and not previous
            final = price * (Decimal("1") - discount if applied else Decimal("1"))
            period = f"{start:%d.%m.%Y}–{end:%d.%m.%Y}"
            if discount == 0:
                reason = "Скидка отключена в config.py: NEW_PRODUCT_DISCOUNT = 0."
            elif previous:
                reason = (
                    f"За {period} были заказы этого товара — скидка не применяется."
                )
            elif history:
                reason = (
                    f"За {period} не было заказов этого товара — применяется скидка."
                )
            else:
                reason = f"История заказов не подключена. Заказы за {period} не найдены — применяется скидка. Проверьте источники данных, если история есть."
            return {
                "original_price": price.quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                ),
                "price": final.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "percent": discount * 100 if applied else Decimal("0"),
                "applied": applied,
                "period_start": start,
                "period_end": end,
                "has_previous_order": previous,
                "reason": reason,
            }

        if discount == 0:
            return result()
        fields = self.domain_columns.get("orders", {})
        if (
            not self._domain_table("orders")
            or not fields.get("order_date")
            or not fields.get("order_id")
        ):
            return result(history=False)
        # Для скидки нужны только дата и товар. Размеры и владельцы здесь не читаем.
        previous_orders = set()
        source = self._all("orders")
        for row in source:
            try:
                day = as_date(self._value(row, "orders", "order_date"))
            except ValueError:
                # Некорректная дата не должна блокировать весь каталог.
                continue
            if start <= day <= end:
                previous_orders.add(self._value(row, "orders", "order_id"))
        domain = (
            "orders"
            if fields.get("product_id") or fields.get("product_name")
            else "order_items"
        )
        rows = source if domain == "orders" else self._all(domain)
        previous = False
        products = None
        actual_product_id = self._value(product, "products", "product_id")
        for row in rows:
            if self._value(row, domain, "order_id") not in previous_orders:
                continue
            key = self._value(row, domain, "product_id")
            if key is None:
                products = products if products is not None else self._order_products()
                key = self._value(
                    self._product_match(row, domain, products), "products", "product_id"
                )
            if key == actual_product_id or str(key) == str(actual_product_id):
                previous = True
                break
        return result(previous)

    def _lock_orders(self):
        domains = ["orders"] if self._layout() == "flat" else ["orders", "order_items"]
        for table in sorted({self._domain_table(d) for d in domains}):
            self.connection.execute(
                f"LOCK TABLE {quote(table)} IN SHARE ROW EXCLUSIVE MODE"
            )

    def _line_values(self, domain, item, order_id, user, day, price):
        product = next(
            p
            for p in self._order_products()
            if str(self._value(p, "products", "product_id")) == str(item["product_id"])
        )
        size = (
            self._entity("sizes", item["size_id"])
            if self.variants_enabled and self._domain_table("sizes")
            else {}
        )
        variant_value = self._value(size, "sizes", "size_value")
        if self.variants_enabled and not self._domain_table("sizes"):
            choices = [
                r
                for r in self.product_sizes(item["product_id"])
                if str(r["size_id"]) == str(item["size_id"])
            ]
            if len(choices) != 1:
                raise ValueError("Вариант товара больше не найден.")
            variant_value = choices[0]["size_value"]
        canonical = dict(
            order_id=order_id,
            order_date=day,
            user_id=self._value(user, "users", "user_id"),
            client_name=self._name(user),
            product_id=item["product_id"],
            size_id=item["size_id"],
            product_name=self._value(product, "products", "product_name"),
            manufacturer=self._value(product, "products", "manufacturer", ""),
            category=self._value(product, "products", "category", ""),
            size_value=variant_value,
            quantity=item["quantity"],
            unit_price=price,
        )
        return {
            column: canonical[field]
            for field, column in self.domain_columns[domain].items()
            if column and field in canonical
        }

    def create_order(self, user_id, items, order_date=None, actor_id=None):
        if not self.orders_enabled:
            raise ValueError(
                "Заказы отключены. Настройте таблицы orders/order_items и ORDERS_ENABLED."
            )
        role = self._authorize(actor_id)
        if role not in self.STAFF and str(actor_id) != str(user_id):
            raise PermissionError("Покупатель может оформлять заказ только на себя.")
        user = self._user(user_id)
        day = as_date(order_date or date.today())
        combined = {}
        for item in items:
            quantity = item.get("quantity")
            if (
                isinstance(quantity, bool)
                or not isinstance(quantity, int)
                or quantity <= 0
            ):
                raise ValueError("Количество должно быть положительным целым числом.")
            item = dict(item)
            item.setdefault("size_id", None)
            if not self.variants_enabled:
                item["size_id"] = None
            key = str(item["product_id"]), str(item["size_id"])
            if key not in combined:
                combined[key] = dict(item)
            else:
                combined[key]["quantity"] += quantity
        if not combined:
            raise ValueError("Нельзя оформить пустой заказ.")
        with self.connection:
            self._lock_orders()
            self._order_cache = None
            priced = [
                (item, Decimal(str(self.discounted_price(item["product_id"], day))))
                for _, item in sorted(combined.items())
            ]
            for item, price in priced:
                if (
                    "unit_price" in item
                    and Decimal(str(item["unit_price"])).quantize(Decimal("0.01"))
                    != price
                ):
                    raise ValueError(
                        "Цена изменилась. Откройте корзину заново и подтвердите обновлённую сумму."
                    )
            for item, _ in priced:
                self._change_stock(
                    item["product_id"], item["size_id"], -item["quantity"]
                )
            table = self._domain_table("orders")
            if self._layout() == "flat":
                number = self._domain_column("orders", "order_id")
                primary = self._primary_key(table)
                if number == primary["column_name"]:
                    raise ValueError(
                        "В таблице позиций нужен отдельный номер заказа, общий для нескольких строк."
                    )
                metadata = self.fetch_one(
                    """SELECT data_type FROM information_schema.columns
                    WHERE table_schema=current_schema() AND table_name=? AND column_name=?""",
                    (table, number),
                )
                identifier = self._next_identifier(table, number, metadata["data_type"])
                for item, price in priced:
                    self._insert(
                        table,
                        self._line_values("orders", item, identifier, user, day, price),
                    )
            else:
                fields = self.domain_columns["orders"]
                values = {fields["order_date"]: day, fields["user_id"]: user_id}
                if fields.get("client_name"):
                    values[fields["client_name"]] = self._name(user)
                identifier = self._insert(table, values)
                for item, price in priced:
                    self._insert(
                        self._domain_table("order_items"),
                        self._line_values(
                            "order_items", item, identifier, user, day, price
                        ),
                    )
        self._order_cache = None
        return identifier

    def delete_order(self, order_id, actor_id=None):
        self._authorize(actor_id, self.STAFF)
        with self.connection:
            self._lock_orders()
            headers, lines, _ = self._snapshot(refresh=True)
            if order_id not in headers:
                raise ValueError("Заказ уже удалён. Обновите список.")
            for item in sorted(
                lines.get(order_id, []),
                key=lambda i: (str(i["product_id"]), str(i["size_id"])),
            ):
                self._change_stock(
                    item["product_id"], item["size_id"], item["quantity"]
                )
            if self._layout() == "separate":
                self.connection.execute(
                    f"DELETE FROM {quote(self._domain_table('order_items'))} "
                    f"WHERE {quote(self._domain_column('order_items', 'order_id'))}=?",
                    (order_id,),
                )
            self.connection.execute(
                f"DELETE FROM {quote(self._domain_table('orders'))} "
                f"WHERE {quote(self._domain_column('orders', 'order_id'))}=?",
                (order_id,),
            )
        self._order_cache = None

    def update_order(
        self,
        order_id,
        order_date,
        removed_item_ids,
        actor_id=None,
        quantities=None,
        expected_quantities=None,
    ):
        """Меняем дату и количество. Разницу возвращаем на склад или списываем."""
        self._authorize(actor_id, {"Администратор"})
        day = as_date(order_date)
        quantities = dict(quantities or {})
        if any(
            isinstance(q, bool) or not isinstance(q, int) or q <= 0
            for q in quantities.values()
        ):
            raise ValueError("Количество должно быть положительным целым числом.")
        with self.connection:
            self._lock_orders()
            headers, lines, _ = self._snapshot(refresh=True)
            if order_id not in headers:
                raise ValueError("Заказ уже удалён. Обновите список.")
            items = lines.get(order_id, [])
            existing = {i["order_item_id"]: i for i in items}
            removed = set(removed_item_ids)
            if not (removed | set(quantities)).issubset(existing):
                raise ValueError("Состав заказа изменился. Откройте его заново.")
            if expected_quantities is not None and any(
                key not in existing or existing[key]["quantity"] != value
                for key, value in expected_quantities.items()
            ):
                raise ValueError(
                    "Количество в заказе уже изменилось. Откройте заказ заново."
                )
            if items and len(removed) == len(items):
                raise ValueError(
                    "В заказе должна остаться хотя бы одна позиция. Для удаления всего заказа используйте список заказов."
                )
            domain = "orders" if self._layout() == "flat" else "order_items"
            table = self._domain_table(domain)
            pk = self._primary_key(table)["column_name"]
            quantity_column = self._domain_column(domain, "quantity")
            order_column = self._domain_column(domain, "order_id")
            changes = []
            for item in sorted(
                items, key=lambda i: (str(i["product_id"]), str(i["size_id"]))
            ):
                key = item["order_item_id"]
                new_quantity = (
                    0 if key in removed else quantities.get(key, item["quantity"])
                )
                delta = item["quantity"] - new_quantity
                if delta:
                    changes.append((item, new_quantity, delta))
            # Сначала возвращаем уменьшенное количество, потом списываем добавленное.
            for item, new_quantity, delta in sorted(changes, key=lambda c: c[2] < 0):
                self._change_stock(item["product_id"], item["size_id"], delta)
                if new_quantity == 0:
                    self.connection.execute(
                        f"DELETE FROM {quote(table)} WHERE {quote(pk)}=? AND {quote(order_column)}=?",
                        (item["order_item_id"], order_id),
                    )
                else:
                    self.connection.execute(
                        f"UPDATE {quote(table)} SET {quote(quantity_column)}=? WHERE {quote(pk)}=? AND {quote(order_column)}=?",
                        (new_quantity, item["order_item_id"], order_id),
                    )
            self.connection.execute(
                f"UPDATE {quote(self._domain_table('orders'))} "
                f"SET {quote(self._domain_column('orders', 'order_date'))}=? "
                f"WHERE {quote(self._domain_column('orders', 'order_id'))}=?",
                (day, order_id),
            )
        self._order_cache = None
