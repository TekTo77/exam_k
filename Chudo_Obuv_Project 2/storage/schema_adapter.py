"""Настройки возможностей и чтение справочников. Строки хранятся только в PostgreSQL."""

from decimal import Decimal, InvalidOperation
import config
from storage.order_operations import quote


class AdaptationMixin:
    def _configure_features(self):
        variant = config.PRODUCT_VARIANTS_ENABLED
        if variant != "auto" and not isinstance(variant, bool):
            raise ValueError('PRODUCT_VARIANTS_ENABLED: True, False или "auto".')
        domains = ("orders", "order_items", "stock_items")
        inferred = any(
            self._domain_column(d, "size_id") or self._domain_column(d, "size_value")
            for d in domains
        )
        self.variants_enabled = inferred if variant == "auto" else variant
        mode = config.STOCK_MODE
        if mode not in {"auto", "separate", "product", "none"}:
            raise ValueError('STOCK_MODE: "auto", "separate", "product" или "none".')
        if mode == "auto":
            if self._domain_table("stock_items") and self._domain_column(
                "stock_items", "quantity_available"
            ):
                mode = "separate"
            elif self._domain_column("products", "quantity_available"):
                mode = "product"
            else:
                mode = "none"
        if mode == "product" and self.variants_enabled:
            raise ValueError(
                'Остатки по вариантам храните отдельно: STOCK_MODE="separate"; либо отключите варианты.'
            )
        if mode == "product" and not self._domain_column(
            "products", "quantity_available"
        ):
            raise ValueError(
                'Для STOCK_MODE="product" укажите products.quantity_available в DATABASE_MAPPINGS.'
            )
        if mode == "separate" and not self._domain_column(
            "stock_items", "quantity_available"
        ):
            raise ValueError(
                'Для STOCK_MODE="separate" укажите stock_items.quantity_available.'
            )
        self.stock_mode = mode
        orders = config.ORDERS_ENABLED
        if orders != "auto" and not isinstance(orders, bool):
            raise ValueError('ORDERS_ENABLED: True, False или "auto".')
        fields = self.domain_columns.get("orders", {})
        ready = bool(
            self._domain_table("orders")
            and fields.get("order_id")
            and fields.get("order_date")
        )
        if ready:
            lines = (
                fields
                if fields.get("quantity")
                and fields.get("unit_price")
                and (fields.get("product_id") or fields.get("product_name"))
                else self.domain_columns.get("order_items", {})
            )
            ready = bool(
                lines.get("order_id")
                and lines.get("quantity")
                and lines.get("unit_price")
                and (lines.get("product_id") or lines.get("product_name"))
            )
            if not ready:
                self.mapping_warnings.append(
                    "Заказы отключены: для позиций нужны номер заказа, товар, количество и цена за единицу. Настройте DATABASE_MAPPINGS."
                )
        self.orders_enabled = ready if orders == "auto" else orders
        if self.orders_enabled and not ready:
            raise ValueError(
                "Настройте orders/order_items в DATABASE_MAPPINGS или отключите ORDERS_ENABLED."
            )
        self._lookup_paths = None

    @staticmethod
    def _stock_quantity(value):
        try:
            number = Decimal(str(value))
        except InvalidOperation as error:
            raise ValueError(f"Некорректный остаток: {value!r}.") from error
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError(
                f"Остаток должен быть целым неотрицательным числом: {value!r}."
            )
        return int(number)

    def _plain_choices(self, product_id):
        product = self._entity("products", product_id)
        if self.stock_mode == "none":
            quantity, identifier = None, None
        elif self.stock_mode == "product":
            quantity = self._stock_quantity(
                self._value(product, "products", "quantity_available")
            )
            identifier = product_id
        else:
            table = self._domain_table("stock_items")
            key = self._domain_column("stock_items", "stock_item_id")
            qty = self._domain_column("stock_items", "quantity_available")
            join = self._stock_join()
            if not all((table, key, qty, join)):
                raise ValueError("Настройте ID товара и строки остатка в stock_items.")
            rows = self._safe_fetch_all(
                f"SELECT s.{quote(key)} AS identifier, s.{quote(qty)} AS quantity FROM {quote(table)} s "
                f"JOIN {quote(self._domain_table('products'))} p ON {join} "
                f"WHERE p.{quote(self._domain_column('products', 'product_id'))}=?",
                (product_id,),
                strict=True,
            )
            if not rows:
                return []
            if len(rows) != 1:
                raise ValueError(
                    "У товара несколько остатков без вариантов. Оставьте одну строку либо включите варианты."
                )
            quantity, identifier = (
                self._stock_quantity(rows[0]["quantity"]),
                rows[0]["identifier"],
            )
        return [
            dict(
                stock_item_id=identifier,
                product_id=product_id,
                size_id=None,
                size_value=None,
                quantity_available=quantity,
            )
        ]

    def _build_lookup_paths(self):
        paths = dict(config.DATABASE_LOOKUPS.get("products", {}))
        table = self._domain_table("products")
        if not table:
            return paths
        # Только реальные FK. Сходство ID само по себе не доказывает связь.
        foreign = self._safe_fetch_all(
            """SELECT tc.table_name AS child_table, kcu.column_name AS child_column,
            ccu.table_name AS parent_table, ccu.column_name AS parent_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON kcu.constraint_name=tc.constraint_name AND kcu.constraint_schema=tc.constraint_schema AND kcu.table_name=tc.table_name
            JOIN information_schema.referential_constraints rc ON rc.constraint_name=tc.constraint_name AND rc.constraint_schema=tc.constraint_schema
            JOIN information_schema.key_column_usage ccu ON ccu.constraint_name=rc.unique_constraint_name AND ccu.constraint_schema=rc.unique_constraint_schema AND ccu.ordinal_position=kcu.position_in_unique_constraint
            WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema=current_schema() AND ccu.table_schema=current_schema()
            AND (SELECT count(*) FROM information_schema.key_column_usage k WHERE k.constraint_name=tc.constraint_name AND k.constraint_schema=tc.constraint_schema AND k.table_name=tc.table_name)=1""",
            strict=True,
        )
        semantics = {
            "manufacturer": (
                "manufacturers",
                "manufacturer",
                "производители",
                "производитель",
            ),
            "subcategory": (
                "subcategories",
                "subcategory",
                "подкатегории",
                "подкатегория",
            ),
            "category": ("categories", "category", "категории", "категория"),
        }
        for field, names in semantics.items():
            if (
                field in paths
                or field in getattr(self, "_disabled_product_fields", set())
                or self._domain_column("products", field)
            ):
                continue
            candidates = []

            def visit(current, steps, seen):
                for fk in foreign:
                    parent = fk["parent_table"]
                    if fk["child_table"] != current or parent in seen:
                        continue
                    step = {
                        "column": fk["child_column"],
                        "table": parent,
                        "key": fk["parent_column"],
                    }
                    chain = [*steps, step]
                    if parent.lower() in names:
                        columns = self._table_columns(parent)
                        labels = (
                            f"{field}_name",
                            "name",
                            "название",
                            "наименование",
                            *self.COLUMN_ALIASES["products"].get(field, ()),
                        )
                        display = next((c for c in labels if c in columns), None)
                        if display:
                            candidates.append([*chain[:-1], {**step, "value": display}])
                    elif len(chain) < 3:
                        visit(parent, chain, seen | {parent})

            visit(table, [], {table})
            if len(candidates) == 1:
                paths[field] = candidates[0]
        return paths

    def _enrich_products(self, rows):
        if not rows or not hasattr(self, "connection"):
            return rows
        if self._lookup_paths is None:
            self._lookup_paths = self._build_lookup_paths()
        if not self._lookup_paths:
            return rows
        source_table = self._domain_table("products")
        pk = self._domain_column("products", "product_id")
        sources = {str(r[pk]): r for r in self._all("products")}
        cache = {}
        for field, spec in self._lookup_paths.items():
            if field not in self.COLUMN_ALIASES["products"]:
                raise ValueError(
                    f"DATABASE_LOOKUPS: поле products.{field} не настроено."
                )
            steps = [spec] if isinstance(spec, dict) else list(spec)
            if not steps or "value" not in steps[-1]:
                raise ValueError(
                    f"DATABASE_LOOKUPS.{field}: последний шаг должен содержать value."
                )
            current_table = source_table
            indexes = []
            for step in steps:
                parent, key, child = step["table"], step["key"], step["column"]
                if child not in self._table_columns(
                    current_table
                ) or key not in self._table_columns(parent):
                    raise ValueError(
                        f"DATABASE_LOOKUPS.{field}: проверьте {current_table}.{child} → {parent}.{key}."
                    )
                if parent not in cache:
                    cache[parent] = self._safe_fetch_all(
                        f"SELECT * FROM {quote(parent)}", strict=True
                    )
                index = {}
                for row in cache[parent]:
                    value = row.get(key)
                    if value is not None:
                        if str(value) in index:
                            raise ValueError(
                                f"Справочник {parent}.{key} содержит повторяющиеся ключи."
                            )
                        index[str(value)] = row
                indexes.append(index)
                current_table = parent
            value_column = steps[-1]["value"]
            if value_column not in self._table_columns(current_table):
                raise ValueError(
                    f"DATABASE_LOOKUPS.{field}: нет колонки {current_table}.{value_column}."
                )
            for row in rows:
                current = sources.get(str(row["product_id"]), {})
                for step, index in zip(steps, indexes):
                    current = index.get(str(current.get(step["column"])), {})
                row[field] = current.get(value_column, "")
        return rows

    def _order_products(self):
        raw = self._all("products")
        displayed = {str(r["product_id"]): r for r in self.products()}
        for row in raw:
            row["_display_fields"] = displayed.get(
                str(self._value(row, "products", "product_id")), {}
            )
        return raw

    def _inline_choices(self, product_id):
        table = self._domain_table("stock_items")
        key = self._domain_column("stock_items", "stock_item_id")
        quantity = self._domain_column("stock_items", "quantity_available")
        value = self._domain_column("stock_items", "size_value") or self._domain_column(
            "stock_items", "size_id"
        )
        join = self._stock_join()
        if not all((table, key, quantity, value, join)):
            raise ValueError(
                "Для вариантов без sizes укажите stock_items.size_value, ID товара, ID строки и остаток."
            )
        return self._safe_fetch_all(
            f"SELECT s.{quote(key)} AS stock_item_id, p.{quote(self._domain_column('products', 'product_id'))} AS product_id, "
            f"s.{quote(value)} AS size_id, s.{quote(value)} AS size_value, s.{quote(quantity)} AS quantity_available "
            f"FROM {quote(table)} s JOIN {quote(self._domain_table('products'))} p ON {join} "
            f"WHERE p.{quote(self._domain_column('products', 'product_id'))}=? ORDER BY s.{quote(value)}",
            (product_id,),
            strict=True,
        )
