"""Другая тема, необязательные поля и изоляция старых таблиц."""

import os
import unittest
import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import psycopg
from storage.repository import Database


@unittest.skipUnless(os.getenv("CHUDO_TEST_DSN"), "Нужен CHUDO_TEST_DSN")
class BooksTests(unittest.TestCase):
    def setUp(self):
        self.dsn = os.environ["CHUDO_TEST_DSN"]
        self.schema = "books_" + uuid.uuid4().hex
        self.patches = [
            patch(
                "storage.repository._read_postgres_config",
                return_value={"dsn": self.dsn, "schema": self.schema},
            ),
            patch("storage.repository.read_settings", return_value={}),
            patch("config.NEW_PRODUCT_DISCOUNT", "0"),
        ]
        for p in self.patches:
            p.start()
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(
                f'CREATE SCHEMA "{self.schema}"; SET search_path TO "{self.schema}"'
            )
            c.execute(
                """CREATE TABLE users(user_id text primary key,last_name text,first_name text,login text,role_name text);
                INSERT INTO users VALUES('admin','А','А','admin','admin'),('u1','Иванов','Иван','ivan','Пользователь'),('u2','Петров','Пётр','petr','Пользователь');
                CREATE TABLE products(product_id text primary key,product_name text,price numeric,image_file text,quantity integer);
                INSERT INTO products VALUES ('isbn-1','Книга',350.50,'cover.webp',10),('isbn-2','Альбом',500,'',8);
                CREATE TABLE orders(order_id text primary key,order_date text,user_id text);
                INSERT INTO orders VALUES ('old','2026-04-02T00:00:00.000Z','u1');
                CREATE TABLE order_items(order_item_id text primary key,order_id text,product_id text,quantity integer,unit_price numeric);
                INSERT INTO order_items VALUES('line','old','isbn-1',2,300);"""
            )
        self.db = Database()

    def tearDown(self):
        self.db.close()
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        for p in reversed(self.patches):
            p.stop()

    def test_books_without_sizes_use_product_stock_and_own_orders(self):
        self.assertFalse(self.db.variants_enabled)
        self.assertEqual(self.db.stock_mode, "product")
        self.assertEqual(self.db.product("isbn-1")["image_path"], "cover.webp")
        self.assertEqual(
            self.db.order("old", actor_id="u1")["order_date"], date(2026, 4, 2)
        )
        self.assertEqual(self.db.orders(actor_id="u2"), [])
        key = self.db.create_order(
            "u1", [dict(product_id="isbn-1", quantity=3)], actor_id="u1"
        )
        self.assertEqual(self.db.available_quantity("isbn-1", None), 7)
        self.assertIsNone(self.db.order_items(key, actor_id="u1")[0]["size_id"])
        self.assertAlmostEqual(
            float(self.db.order(key, actor_id="u1")["total_sum"]), 1051.5
        )
        self.db.delete_order(key, actor_id="admin")
        self.assertEqual(self.db.available_quantity("isbn-1", None), 10)

    def test_untracked_stock_does_not_invent_quantity(self):
        with patch("config.STOCK_MODE", "none"):
            self.db._refresh_domain_mapping()
            self.assertIsNone(self.db.product("isbn-1")["total_quantity"])
            self.assertIsNone(self.db.product_sizes("isbn-1")[0]["quantity_available"])
            key = self.db.create_order(
                "u1", [dict(product_id="isbn-1", quantity=500)], actor_id="u1"
            )
            self.assertEqual(
                self.db.order_items(key, actor_id="u1")[0]["quantity"], 500
            )
            self.assertEqual(
                self.db.fetch_one(
                    "SELECT quantity FROM products WHERE product_id='isbn-1'"
                )[0],
                10,
            )

    def test_plain_separate_stock_and_rollback(self):
        with self.db.connection:
            self.db.connection.execute(
                "CREATE TABLE stock_items(stock_item_id text primary key,product_id text,quantity_available integer)"
            )
            self.db.connection.execute(
                "INSERT INTO stock_items VALUES('st1','isbn-1',4),('st2','isbn-2',0)"
            )
        self.db._refresh_domain_mapping()
        self.assertEqual(self.db.stock_mode, "separate")
        with self.assertRaises(ValueError):
            self.db.create_order(
                "u1",
                [
                    dict(product_id="isbn-1", quantity=2),
                    dict(product_id="isbn-2", quantity=1),
                ],
                actor_id="u1",
            )
        self.assertEqual(self.db.available_quantity("isbn-1", None), 4)
        key = self.db.create_order(
            "u1", [dict(product_id="isbn-1", quantity=2)], actor_id="u1"
        )
        self.assertEqual(self.db.available_quantity("isbn-1", None), 2)
        self.db.delete_order(key, actor_id="admin")
        self.assertEqual(self.db.available_quantity("isbn-1", None), 4)

    def test_catalog_does_not_parse_sizes_and_zero_discount_does_not_read_history(self):
        with self.db.connection:
            self.db.connection.execute(
                "ALTER TABLE order_items ADD COLUMN size_id bigint"
            )
            self.db.connection.execute("UPDATE order_items SET size_id=99")
        with patch("config.PRODUCT_VARIANTS_ENABLED", True), patch(
            "config.STOCK_MODE", "none"
        ):
            self.db._refresh_domain_mapping()
            with patch.object(
                self.db,
                "_snapshot",
                side_effect=AssertionError("Каталог читает состав"),
            ):
                self.assertEqual(self.db.discounted_price("isbn-1"), 350.50)
            with patch("config.NEW_PRODUCT_DISCOUNT", "0.25"):
                self.assertEqual(
                    self.db.discounted_price("isbn-1", date(2026, 5, 5)), 350.50
                )
                self.assertEqual(
                    self.db.discounted_price("isbn-1", date(2026, 6, 5)), 262.88
                )

    def test_reference_chain_auto_fk_and_explicit_custom_directory(self):
        with self.db.connection:
            self.db.connection.execute(
                """CREATE TABLE categories(category_id bigint primary key, category_name text);
                INSERT INTO categories VALUES(1,'Литература');
                CREATE TABLE subcategories(subcategory_id bigint primary key,category_id bigint references categories,subcategory_name text);
                INSERT INTO subcategories VALUES(2,1,'Фантастика');
                CREATE TABLE manufacturers(manufacturer_id bigint primary key,manufacturer_name text);
                INSERT INTO manufacturers VALUES(3,'Издательство');
                ALTER TABLE products ADD COLUMN subcategory_id bigint REFERENCES subcategories;
                ALTER TABLE products ADD COLUMN manufacturer_id bigint REFERENCES manufacturers;
                UPDATE products SET subcategory_id=2,manufacturer_id=3"""
            )
        self.db._refresh_domain_mapping()
        row = self.db.product("isbn-1")
        self.assertEqual(
            (row["category"], row["subcategory"], row["manufacturer"]),
            ("Литература", "Фантастика", "Издательство"),
        )
        self.assertEqual(len(self.db.products(category="Литература")), 2)
        self.assertEqual(self.db.categories(), ["Литература"])
        self.assertEqual(
            self.db.order_items("old", actor_id="u1")[0]["manufacturer"], "Издательство"
        )
        with patch(
            "config.DATABASE_LOOKUPS",
            {
                "products": {
                    "manufacturer": {
                        "column": "subcategory_id",
                        "table": "subcategories",
                        "key": "subcategory_id",
                        "value": "subcategory_name",
                    }
                }
            },
        ):
            self.db._refresh_domain_mapping()
            self.assertEqual(self.db.product("isbn-1")["manufacturer"], "Фантастика")

    def test_extra_required_columns_default_and_explicit_mapping_priority(self):
        with self.db.connection:
            self.db.connection.execute(
                "ALTER TABLE orders ADD COLUMN status text NOT NULL DEFAULT 'new'"
            )
        with patch("config.INSERT_DEFAULTS", {"orders": {"status": "created"}}):
            key = self.db.create_order(
                "u1", [dict(product_id="isbn-1", quantity=1)], actor_id="u1"
            )
        self.assertEqual(
            self.db.fetch_one("SELECT status FROM orders WHERE order_id=?", (key,))[0],
            "created",
        )

    def test_current_import_scope_excludes_previous_theme(self):
        self.db.active_tables = ["other_table"]
        self.db._refresh_domain_mapping()
        self.assertEqual(self.db.products(), [])
        self.assertFalse(self.db.orders_enabled)
        self.assertIsNone(self.db.find_user_by_login("ivan"))
        self.assertEqual(self.db.fetch_one("SELECT COUNT(*) FROM products")[0], 2)

    def test_missing_orders_keeps_catalog_usable(self):
        with self.db.connection:
            self.db.connection.execute(
                "DROP TABLE orders CASCADE; DROP TABLE order_items"
            )
        self.db._refresh_domain_mapping()
        self.assertFalse(self.db.orders_enabled)
        self.assertEqual(len(self.db.products()), 2)
        self.assertEqual(self.db.discounted_price("isbn-1"), 350.50)
        with self.assertRaises(ValueError):
            self.db.create_order(
                "u1", [dict(product_id="isbn-1", quantity=1)], actor_id="u1"
            )

    def test_inline_variants_without_size_directory(self):
        with self.db.connection:
            self.db.connection.execute(
                """CREATE TABLE stock_items(stock_item_id text primary key,product_id text,size_value text,quantity_available integer);
                INSERT INTO stock_items VALUES('paper','isbn-1','Бумажная',4),('ebook','isbn-1','Электронная',10);
                ALTER TABLE order_items ADD COLUMN size_value text;
                UPDATE order_items SET size_value='Бумажная';"""
            )
        self.db._refresh_domain_mapping()
        self.assertTrue(self.db.variants_enabled)
        self.assertEqual(
            self.db.order_items("old", actor_id="u1")[0]["size_value"], "Бумажная"
        )
        key = self.db.create_order(
            "u1",
            [dict(product_id="isbn-1", size_id="Бумажная", quantity=2)],
            actor_id="u1",
        )
        self.assertEqual(self.db.available_quantity("isbn-1", "Бумажная"), 2)
        self.assertEqual(
            self.db.order_items(key, actor_id="u1")[0]["size_value"], "Бумажная"
        )
        self.db.delete_order(key, actor_id="admin")
        self.assertEqual(self.db.available_quantity("isbn-1", "Бумажная"), 4)

    def test_untracked_stock_with_variant_directory(self):
        with self.db.connection:
            self.db.connection.execute(
                """CREATE TABLE sizes(size_id text primary key,size_value text);
                INSERT INTO sizes VALUES('paper','Бумажная'),('ebook','Электронная');
                ALTER TABLE order_items ADD COLUMN size_id text;
                UPDATE order_items SET size_id='paper';"""
            )
        with patch("config.STOCK_MODE", "none"):
            self.db._refresh_domain_mapping()
            key = self.db.create_order(
                "u1",
                [dict(product_id="isbn-1", size_id="paper", quantity=50)],
                actor_id="u1",
            )
            self.assertEqual(
                self.db.order_items(key, actor_id="u1")[0]["size_value"], "Бумажная"
            )
            with self.assertRaisesRegex(ValueError, "вариант"):
                self.db.create_order(
                    "u1",
                    [dict(product_id="isbn-1", size_id="missing", quantity=1)],
                    actor_id="u1",
                )

    def test_config_mapping_overrides_saved_mapping(self):
        with patch(
            "storage.repository.read_settings",
            return_value={
                "mappings": {
                    self.db.mapping_key: {
                        "products": {
                            "table": "order_items",
                            "columns": {
                                "product_name": "order_item_id",
                                "price": "unit_price",
                            },
                        }
                    }
                }
            },
        ), patch(
            "storage.repository.DATABASE_MAPPINGS",
            {
                "products": {
                    "table": "products",
                    "columns": {"product_name": "product_name", "price": "price"},
                }
            },
        ):
            self.db._refresh_domain_mapping()
            self.assertEqual(self.db.product("isbn-1")["product_name"], "Книга")

    def test_separate_schema_cannot_fall_back_to_public(self):
        with self.db.connection:
            self.db.connection.execute("SELECT current_schemas(false) AS schemas")
            self.assertEqual(
                self.db.fetch_one("SELECT current_schemas(false)")[0], [self.schema]
            )

    def test_relation_file_applies_to_current_schema_and_repeat_is_safe(self):
        from pathlib import Path

        script = Path("table_relations.sql").read_text()
        self.db.connection.commit()
        self.db.connection.raw.execute(script)
        self.db.connection.raw.execute(script)
        self.assertEqual(
            self.db.fetch_one(
                "SELECT count(*) FROM pg_constraint WHERE contype='f' AND connamespace=current_schema()::regnamespace"
            )[0],
            3,
        )
        self.db.connection.commit()

    def test_role_alias_and_full_name_mapping(self):
        with self.db.connection:
            self.db.connection.execute(
                "UPDATE users SET role_name='Директор',last_name='Иванов Иван Иванович' WHERE user_id='admin'"
            )
        with patch("config.ROLE_ALIASES", {"директор": "Администратор"}), patch(
            "storage.repository.DATABASE_MAPPINGS",
            {
                "users": {
                    "table": "users",
                    "columns": {"first_name": None, "middle_name": None},
                }
            },
        ):
            self.db._refresh_domain_mapping()
            self.assertEqual(
                self.db._role_for_user(self.db._user("admin")), "Администратор"
            )
            self.assertEqual(
                self.db._name(self.db._user("admin")), "Иванов Иван Иванович"
            )
            self.assertEqual(len(self.db.orders(actor_id="admin")), 1)

    def test_quantity_edit_without_variants_with_product_or_untracked_stock(self):
        for mode in ("product", "none"):
            with patch("config.STOCK_MODE", mode):
                self.db._refresh_domain_mapping()
                self.db.update_order(
                    "old", "2026-04-02", [], actor_id="admin", quantities={"line": 1}
                )
                self.assertEqual(
                    self.db.order("old", actor_id="u1")["total_sum"], Decimal("300")
                )
                self.assertEqual(
                    self.db.order_items("old", actor_id="u1")[0]["quantity"], 1
                )
                self.db.update_order(
                    "old", "2026-04-02", [], actor_id="admin", quantities={"line": 2}
                )
        self.assertEqual(self.db.available_quantity("isbn-1", None), None)
        self.assertEqual(
            self.db.fetch_one(
                "SELECT quantity FROM products WHERE product_id='isbn-1'"
            )[0],
            10,
        )

    def test_no_previous_orders_discount_and_round_to_kopecks(self):
        with self.db.connection:
            self.db.connection.execute(
                "DELETE FROM order_items; DELETE FROM orders; UPDATE products SET price=3.50 WHERE product_id='isbn-1'"
            )
        with patch("config.NEW_PRODUCT_DISCOUNT", "0.25"):
            self.assertEqual(self.db.discounted_price("isbn-1", date(2026, 4, 2)), 2.63)
            with self.db.connection:
                self.db.connection.execute("DROP TABLE order_items; DROP TABLE orders")
            self.db._refresh_domain_mapping()
            self.assertEqual(self.db.discounted_price("isbn-1", date(2026, 4, 2)), 2.63)
