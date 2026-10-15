"""Тесты заказов. CHUDO_TEST_DSN — отдельная тестовая БД."""

import os
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import psycopg
from storage.repository import Database


@unittest.skipUnless(
    os.getenv("CHUDO_TEST_DSN"), "Для интеграционных тестов нужен CHUDO_TEST_DSN"
)
class OrderTests(unittest.TestCase):
    layout = "flat"

    def setUp(self):
        self.dsn = os.environ["CHUDO_TEST_DSN"]
        self.schema = "test_orders_" + uuid.uuid4().hex
        self.config = dict(dsn=self.dsn, schema=self.schema)
        self.patch_config = patch(
            "storage.repository._read_postgres_config", return_value=self.config
        )
        self.patch_settings = patch("storage.repository.read_settings", return_value={})
        self.patch_config.start()
        self.patch_settings.start()
        self.bootstrap = patch(
            "config.CREATE_COMPATIBILITY_TABLES", self.layout == "separate"
        )
        self.bootstrap.start()
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(f'CREATE SCHEMA "{self.schema}"')
            c.execute(f'SET search_path TO "{self.schema}"')
            if self.layout == "flat":
                c.execute(
                    """CREATE TABLE users (__row_id bigint primary key, last_name text,
                  first_name text, "отчетсво" text, login text, "роль" text);
                  INSERT INTO users VALUES (1,'Иванов','Иван','Сергеевич','admin','Администратор'),
                    (2,'Петров','Пётр','Алексеевич','manager','Менеджер'),
                    (3,'Сидорова','Анна','Дмитриевна','client','Авторизованный пользователь');
                  CREATE TABLE products (__row_id bigint primary key, category text,
                    "наименование_товара" text, "производство" text, price numeric);
                  INSERT INTO products VALUES (1,'Обувь','Модель А','Фабрика',100),
                    (2,'Обувь','Модель Б — описание','Фабрика',200);
                  CREATE TABLE sizes (__row_id bigint primary key, size_value double precision);
                  INSERT INTO sizes VALUES (1,20),(2,21.5);
                  CREATE TABLE stock_items (__row_id bigint primary key, "наименование_товара" text,
                    "производство" text, "размер" double precision, "количество_доступное_для_заказа" bigint);
                  INSERT INTO stock_items VALUES (1,'Модель А ','Фабрика',20,20),
                    (2,'Модель Б','Фабрика',21.5,20);
                  CREATE TABLE orders (__row_id bigint primary key, "номер_заказа" bigint,
                    "дата_заказа" timestamp, "фио" text, "наименование_товара" text,
                    "производство" text, "размер" double precision, "количество" bigint,
                    "цена_за_единицу" numeric);
                  INSERT INTO orders VALUES
                    (1,1,'2025-01-01','Сидорова Анна Дмитриевна','Модель А','Фабрика',20,2,100),
                    (2,1,'2025-01-01','Сидорова Анна Дмитриевна','Модель Б','Фабрика',21.5,1,200),
                    (3,2,'2025-01-02','Сидорова Анна Дмитриевна','Модель А','Фабрика',20,1,100)"""
                )
        self.db = Database()
        if self.layout == "separate":
            with self.db.connection:
                self.db.connection.execute(
                    "INSERT INTO roles(role_id,role_name) VALUES (1,'Администратор'),(2,'Менеджер'),(3,'Пользователь')"
                )
                self.db.connection.execute(
                    "INSERT INTO users(user_id,last_name,first_name,middle_name,login,role_id) VALUES (1,'Иванов','Иван','Сергеевич','admin',1),(2,'Петров','Пётр','Алексеевич','manager',2),(3,'Сидорова','Анна','Дмитриевна','client',3)"
                )
                self.db.connection.execute(
                    "INSERT INTO products(product_id,category,product_name,manufacturer,price) VALUES (1,'Обувь','Модель А','Фабрика',100),(2,'Обувь','Модель Б','Фабрика',200)"
                )
                self.db.connection.execute(
                    "INSERT INTO sizes(size_id,size_value) VALUES (1,20),(2,21)"
                )
                self.db.connection.execute(
                    "INSERT INTO stock_items(product_id,size_id,quantity_available) VALUES (1,1,20),(2,2,20)"
                )
                self.db.connection.execute(
                    "INSERT INTO orders(order_id,order_date,user_id) VALUES (1,'2025-01-01',3),(2,'2025-01-02',3)"
                )
                self.db.connection.execute(
                    "INSERT INTO order_items(order_id,product_id,size_id,quantity,unit_price) VALUES (1,1,1,2,100),(1,2,2,1,200),(2,1,1,1,100)"
                )
                # Проверяем удаление при строгом внешнем ключе.
                self.db.connection.execute(
                    "ALTER TABLE order_items ADD CONSTRAINT test_order_fk FOREIGN KEY(order_id) REFERENCES orders(order_id)"
                )
            self.db._refresh_domain_mapping()
            # Обновляем счётчик после вставки тестовых ID.
            with self.db.connection:
                self.db.connection.execute(
                    "SELECT setval(pg_get_serial_sequence('orders','order_id'),2)"
                )

    def tearDown(self):
        self.db.close()
        with psycopg.connect(self.dsn, autocommit=True) as c:
            c.execute(f'DROP SCHEMA "{self.schema}" CASCADE')
        self.patch_config.stop()
        self.patch_settings.stop()
        self.bootstrap.stop()

    def test_lists_grouped_orders_and_exact_total(self):
        rows = self.db.orders(actor_id=2)
        self.assertEqual(len(rows), 2)
        order = self.db.order(1, actor_id=1)
        self.assertEqual(order["client_name"], "Сидорова Анна Дмитриевна")
        self.assertEqual(order["total_sum"], Decimal("400"))
        self.assertEqual(len(self.db.order_items(1, actor_id=2)), 2)

    def test_discount_can_be_disabled_for_another_assignment(self):
        with patch("config.NEW_PRODUCT_DISCOUNT", "0"):
            self.assertEqual(self.db.discounted_price(1), 100)
            order_id = self.db.create_order(
                3, [dict(product_id=1, size_id=1, quantity=1)], actor_id=2
            )
            self.assertEqual(
                self.db.order(order_id, actor_id=2)["total_sum"], Decimal("100")
            )

    def test_discount_explanation_matches_price_and_calendar_period(self):
        with patch("config.NEW_PRODUCT_DISCOUNT", "0.25"):
            info = self.db.discount_info(1, date(2025, 2, 20))
            self.assertFalse(info["applied"])
            self.assertEqual(info["price"], Decimal("100.00"))
            self.assertTrue(info["has_previous_order"])
            self.assertEqual(info["period_start"], date(2025, 1, 1))
            self.assertEqual(info["period_end"], date(2025, 1, 31))
            self.assertIn("были заказы", info["reason"])
            info = self.db.discount_info(1, date(2025, 3, 1))
            self.assertTrue(info["applied"])
            self.assertEqual(info["price"], Decimal("75.00"))
            self.assertEqual(info["percent"], Decimal("25"))
            self.assertIn("не было заказов", info["reason"])
            self.assertEqual(self.db.discounted_price(1, date(2025, 3, 1)), 75)

    def test_manager_creates_for_selected_client_and_deletes(self):
        identifier = self.db.create_order(
            3,
            [
                dict(product_id=1, size_id=1, quantity=2),
                dict(product_id=2, size_id=2, quantity=1),
            ],
            actor_id=2,
        )
        self.assertEqual(self.db.order(identifier, actor_id=2)["user_id"], 3)
        self.assertEqual(self.db.available_quantity(1, 1), 18)
        items = self.db.order_items(identifier, actor_id=1)
        self.assertEqual(len(items), 2)
        self.assertEqual(
            self.db.order(identifier, actor_id=1)["total_sum"],
            sum(i["line_total"] for i in items),
        )
        self.db.delete_order(identifier, actor_id=2)
        self.assertEqual(self.db.available_quantity(1, 1), 20)
        self.assertIsNone(self.db.order(identifier, actor_id=1))

    def test_admin_changes_date_and_removes_one_line(self):
        item = self.db.order_items(1, actor_id=1)[0]
        self.db.update_order(1, "2026-05-09", [item["order_item_id"]], actor_id=1)
        self.assertEqual(self.db.order(1, actor_id=1)["order_date"], date(2026, 5, 9))
        self.assertEqual(len(self.db.order_items(1, actor_id=1)), 1)
        self.assertEqual(
            self.db.available_quantity(item["product_id"], item["size_id"]),
            20 + item["quantity"],
        )

    def test_permissions_are_checked_in_database_layer(self):
        for actor in (None, 3):
            with self.assertRaises(PermissionError):
                self.db.delete_order(1, actor_id=actor)
        with self.assertRaises(PermissionError):
            self.db.orders(actor_id=None)
        with self.assertRaises(PermissionError):
            self.db.update_order(1, "2026-01-01", [], actor_id=2)
        with self.assertRaises(PermissionError):
            self.db.create_order(
                1, [dict(product_id=1, size_id=1, quantity=1)], actor_id=3
            )
        self.assertEqual(len(self.db.orders(actor_id=1)), 2)

    def test_customer_sees_only_own_orders_and_cannot_read_other_details(self):
        own = self.db.orders(actor_id=3)
        self.assertEqual({r["order_id"] for r in own}, {1, 2})
        self.assertEqual(len(self.db.order_items(1, actor_id=3)), 2)
        other = self.db.create_order(
            2, [dict(product_id=1, size_id=1, quantity=1)], actor_id=1
        )
        self.assertNotIn(other, {r["order_id"] for r in self.db.orders(actor_id=3)})
        self.assertIsNone(self.db.order(other, actor_id=3))
        with self.assertRaises(PermissionError):
            self.db.order_items(other, actor_id=3)
        self.assertEqual(len(self.db.orders(actor_id=1)), 3)

    def test_new_customer_order_is_persisted_by_id(self):
        order_id = self.db.create_order(
            3, [dict(product_id=1, size_id=1, quantity=1)], actor_id=3
        )
        self.assertIn(order_id, {r["order_id"] for r in self.db.orders(actor_id=3)})
        self.assertEqual(self.db.order(order_id, actor_id=3)["user_id"], 3)

    def test_id_link_survives_user_rename(self):
        column = self.db._domain_column("orders", "user_id")
        self.assertIsNotNone(column)
        with self.db.connection:
            name = self.db._domain_column("users", "last_name")
            key = self.db._domain_column("users", "user_id")
            self.db.connection.execute(
                f'UPDATE users SET "{name}"=? WHERE "{key}"=?', ("НоваяФамилия", 3)
            )
        self.assertEqual({r["order_id"] for r in self.db.orders(actor_id=3)}, {1, 2})

    def test_explicit_invalid_user_id_never_falls_back_to_name(self):
        column = self.db._domain_column("orders", "user_id")
        number = self.db._domain_column("orders", "order_id")
        with self.db.connection:
            self.db.connection.execute(
                f'UPDATE orders SET "{column}"=? WHERE "{number}"=?', (999, 1)
            )
        self.assertEqual({r["order_id"] for r in self.db.orders(actor_id=3)}, {2})
        self.assertIsNone(self.db.order(1, actor_id=3))

    def test_duplicate_fio_is_not_backfilled_and_not_visible_to_customer(self):
        if self.layout != "flat":
            self.skipTest("Проверка старого импорта с ФИО")
        with self.db.connection:
            self.db.connection.execute(
                'UPDATE orders SET user_id=NULL WHERE "номер_заказа"=1'
            )
            self.db.connection.execute(
                """INSERT INTO users VALUES
                (4,'Сидорова','Анна','Дмитриевна','other','Авторизованный пользователь')"""
            )
        self.db._refresh_domain_mapping()
        self.assertEqual({r["order_id"] for r in self.db.orders(actor_id=3)}, {2})
        self.assertEqual(self.db.orders(actor_id=4), [])
        self.assertIsNone(
            self.db.fetch_one("SELECT user_id FROM orders WHERE __row_id=1")["user_id"]
        )

    def test_mixed_owner_order_is_hidden_as_a_whole(self):
        if self.layout != "flat":
            self.skipTest("Проверка нескольких Excel-строк одного заказа")
        with self.db.connection:
            self.db.connection.execute("UPDATE orders SET user_id=2 WHERE __row_id=1")
        self.assertEqual({r["order_id"] for r in self.db.orders(actor_id=3)}, {2})
        self.assertIsNone(self.db.order(1, actor_id=3))

    def test_custom_mapping_uses_text_user_key_without_shoe_table_names(self):
        with self.db.connection:
            self.db.connection.execute(
                """CREATE TABLE "People Custom" (code TEXT PRIMARY KEY, family TEXT, given TEXT);
                INSERT INTO "People Custom" VALUES ('customer-A','Иванов','Иван');
                CREATE TABLE "Purchases Custom" (row_code TEXT PRIMARY KEY, buyer TEXT);
                INSERT INTO "Purchases Custom" VALUES ('order-A','Иванов Иван')"""
            )
        self.db.domain_tables.update(users="People Custom", orders="Purchases Custom")
        self.db.domain_columns["users"] = dict(
            user_id="code", last_name="family", first_name="given"
        )
        self.db.domain_columns["orders"] = dict(client_name="buyer")
        self.db._ensure_order_user_link()
        self.assertEqual(
            self.db.fetch_one('SELECT user_id FROM "Purchases Custom"')["user_id"],
            "customer-A",
        )
        self.assertEqual(
            self.db.fetch_one(
                """SELECT data_type FROM information_schema.columns
            WHERE table_schema=current_schema() AND table_name='Purchases Custom' AND column_name='user_id' """
            )["data_type"],
            "text",
        )

    def test_failed_order_rolls_back_stock_and_header(self):
        with self.assertRaises(ValueError):
            self.db.create_order(
                3,
                [
                    dict(product_id=1, size_id=1, quantity=2),
                    dict(product_id=2, size_id=2, quantity=100),
                ],
                actor_id=2,
            )
        self.assertEqual(self.db.available_quantity(1, 1), 20)
        self.assertEqual(len(self.db.orders(actor_id=2)), 2)

    def test_invalid_date_and_foreign_line_do_not_modify_order(self):
        before = self.db.order(1, actor_id=1)
        with self.assertRaises(ValueError):
            self.db.update_order(1, "2026-02-30", [], actor_id=1)
        foreign = self.db.order_items(2, actor_id=1)[0]["order_item_id"]
        with self.assertRaises(ValueError):
            self.db.update_order(1, "2026-05-09", [foreign], actor_id=1)
        self.assertEqual(
            self.db.order(1, actor_id=1)["order_date"], before["order_date"]
        )

    def test_duplicate_cart_rows_are_merged(self):
        identifier = self.db.create_order(
            3,
            [
                dict(product_id=1, size_id=1, quantity=2),
                dict(product_id=1, size_id=1, quantity=3),
            ],
            actor_id=2,
        )
        items = self.db.order_items(identifier, actor_id=2)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["quantity"], 5)
        self.assertEqual(self.db.available_quantity(1, 1), 15)

    def test_two_connections_cannot_oversell_stock(self):
        other = Database()
        with self.db.connection:
            table, pk, quantity, identifier, _ = self.db._stock(1, 1)
            self.db.connection.execute(
                f'UPDATE "{table}" SET "{quantity}"=5 WHERE "{pk}"=?', (identifier,)
            )

        def purchase(db):
            try:
                db.create_order(
                    3, [dict(product_id=1, size_id=1, quantity=5)], actor_id=2
                )
                return True
            except ValueError:
                return False

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(purchase, [self.db, other]))
            self.assertEqual(sorted(results), [False, True])
            self.assertEqual(self.db.available_quantity(1, 1), 0)
        finally:
            other.close()

    def test_admin_reduces_quantity_without_deleting_line_and_restores_stock(self):
        item = self.db.order_items(1, actor_id=1)[0]
        before = self.db.available_quantity(item["product_id"], item["size_id"])
        price = item["unit_price"]
        self.db.update_order(
            1, "2026-05-09", [], actor_id=1, quantities={item["order_item_id"]: 1}
        )
        changed = next(
            i
            for i in self.db.order_items(1, actor_id=1)
            if i["order_item_id"] == item["order_item_id"]
        )
        self.assertEqual(changed["quantity"], 1)
        self.assertEqual(changed["unit_price"], price)
        self.assertEqual(len(self.db.order_items(1, actor_id=1)), 2)
        self.assertEqual(
            self.db.available_quantity(item["product_id"], item["size_id"]),
            before + item["quantity"] - 1,
        )
        self.assertEqual(self.db.order(1, actor_id=1)["total_sum"], Decimal("300"))

    def test_quantity_increase_checks_stock_and_rolls_back_all_changes(self):
        items = self.db.order_items(1, actor_id=1)
        a, b = items
        before = self.db.order(1, actor_id=1)
        qa = self.db.available_quantity(a["product_id"], a["size_id"])
        qb = self.db.available_quantity(b["product_id"], b["size_id"])
        with self.assertRaisesRegex(ValueError, "остаток"):
            self.db.update_order(
                1,
                "2026-05-09",
                [],
                actor_id=1,
                quantities={a["order_item_id"]: 1, b["order_item_id"]: 999},
            )
        self.assertEqual(self.db.order(1, actor_id=1), before)
        self.assertEqual(self.db.available_quantity(a["product_id"], a["size_id"]), qa)
        self.assertEqual(self.db.available_quantity(b["product_id"], b["size_id"]), qb)
        self.db.update_order(
            1, "2026-05-09", [], actor_id=1, quantities={a["order_item_id"]: 3}
        )
        self.assertEqual(
            self.db.available_quantity(a["product_id"], a["size_id"]), qa - 1
        )

    def test_bad_quantity_foreign_line_permissions_and_stale_form(self):
        item = self.db.order_items(1, actor_id=1)[0]
        key = item["order_item_id"]
        foreign = self.db.order_items(2, actor_id=1)[0]["order_item_id"]
        for value in (0, -1, 1.5, True, "2"):
            with self.assertRaises(ValueError):
                self.db.update_order(
                    1, "2026-05-09", [], actor_id=1, quantities={key: value}
                )
        with self.assertRaises(ValueError):
            self.db.update_order(
                1, "2026-05-09", [], actor_id=1, quantities={foreign: 1}
            )
        for actor in (None, 2, 3):
            with self.assertRaises(PermissionError):
                self.db.update_order(
                    1, "2026-05-09", [], actor_id=actor, quantities={key: 1}
                )
        self.db.update_order(1, "2026-05-09", [], actor_id=1, quantities={key: 1})
        with self.assertRaisesRegex(ValueError, "уже изменилось"):
            self.db.update_order(
                1,
                "2026-05-10",
                [],
                actor_id=1,
                quantities={key: 3},
                expected_quantities={key: 2},
            )
        self.assertEqual(self.db.order(1, actor_id=1)["order_date"], date(2026, 5, 9))

    def test_remove_one_line_and_change_another_in_single_edit(self):
        a, b = self.db.order_items(1, actor_id=1)
        self.db.update_order(
            1,
            "2026-05-09",
            [b["order_item_id"]],
            actor_id=1,
            quantities={a["order_item_id"]: 1},
        )
        self.assertEqual(len(self.db.order_items(1, actor_id=1)), 1)
        self.assertEqual(self.db.order(1, actor_id=1)["total_sum"], Decimal("100"))

    def test_discount_uses_calendar_month_boundaries(self):
        cases = [
            (date(2026, 1, 15), "2025-12-01", "2025-12-31", "2025-11-30", "2026-01-01"),
            (date(2024, 3, 31), "2024-02-01", "2024-02-29", "2024-01-31", "2024-03-01"),
        ]
        table = self.db._domain_table("orders")
        column = self.db._domain_column("orders", "order_date")
        number = self.db._domain_column("orders", "order_id")
        with patch("config.NEW_PRODUCT_DISCOUNT", "0.25"):
            for calculation, first, last, before, after in cases:
                for ordered, expected in [
                    (first, 100),
                    (last, 100),
                    (before, 75),
                    (after, 75),
                ]:
                    with self.db.connection:
                        self.db.connection.execute(
                            f'UPDATE "{table}" SET "{column}"=? WHERE "{number}"=1',
                            (ordered,),
                        )
                        self.db.connection.execute(
                            f'UPDATE "{table}" SET "{column}"=? WHERE "{number}"=2',
                            (before,),
                        )
                    self.assertEqual(self.db.discounted_price(1, calculation), expected)


class SeparateOrderTests(OrderTests):
    layout = "separate"

    def test_discount_numeric_id_1_00_matches_integer_product_id(self):
        with self.db.connection:
            self.db.connection.execute(
                "ALTER TABLE order_items ALTER COLUMN product_id TYPE numeric(12,2)"
            )
        self.db._refresh_domain_mapping()
        with patch("config.NEW_PRODUCT_DISCOUNT", "0.25"):
            self.assertEqual(self.db.discounted_price(1, date(2025, 2, 1)), 100)
            self.assertTrue(
                self.db.discount_info(1, date(2025, 2, 1))["has_previous_order"]
            )


if __name__ == "__main__":
    unittest.main()
