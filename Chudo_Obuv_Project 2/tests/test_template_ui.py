"""Прогон настоящих окон Tkinter. Нужен DISPLAY и отдельная тестовая БД."""

import os
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import test_adaptation_pg as fixtures
from module_settings import MODULE_NUMBER


@unittest.skipUnless(
    MODULE_NUMBER >= 3 and os.getenv("DISPLAY") and os.getenv("CHUDO_TEST_DSN"),
    "Нужны DISPLAY и CHUDO_TEST_DSN",
)
class TemplateUiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BooksTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        dialogs = ExitStack()
        self.addCleanup(dialogs.close)
        for module in ("interface.application", "interface.customer_views", "interface.order_views"):
            if module != "interface.application":
                dialogs.enter_context(patch(module + ".show_info"))
            dialogs.enter_context(
                patch(
                    module + ".show_error",
                    side_effect=lambda title, message: (_ for _ in ()).throw(
                        AssertionError(f"{title}: {message}")
                    ),
                )
            )
        from interface.application import Application

        self.app = Application()
        self.addCleanup(self.app.close)

    def test_book_detail_cart_and_own_orders_without_variant_widgets(self):
        from interface.application import ProductFrame

        self.app.login(self.app.database.find_user_by_login("ivan"))
        self.app.update()
        self.app.show_product("isbn-1")
        self.app.update()
        detail = next(
            w
            for w in self.app.navigation.winfo_children()
            if isinstance(w, ProductFrame)
        )
        self.assertEqual(detail.size_box.winfo_manager(), "")
        detail.quantity_value.set("2")
        detail.add_to_cart()
        self.app.update()
        self.assertIsNone(self.app.cart[0]["size_id"])
        self.app.show_cart()
        self.app.update()
        self.app.show_orders()
        self.app.update()
        self.app.show_order_detail("old")
        self.app.update()

    def test_none_stock_and_catalog_only_frames(self):
        with patch("config.STOCK_MODE", "none"), patch("config.ORDERS_ENABLED", False):
            self.app.database._refresh_domain_mapping()
            self.app.login(self.app.database.find_user_by_login("ivan"))
            self.app.update()
            self.assertFalse(self.app.can_order())
            self.app.show_product("isbn-1")
            self.app.update()

    @unittest.skipUnless(MODULE_NUMBER >= 4, "Редактирование появляется в модуле 4")
    def test_admin_can_edit_quantity_and_see_live_total(self):
        from interface.application import OrderEditFrame

        self.app.login(self.app.database.find_user_by_login("admin"))
        self.app.show_order_edit("old")
        self.app.update()
        edit = next(
            w
            for w in self.app.navigation.winfo_children()
            if isinstance(w, OrderEditFrame)
        )
        edit.quantity_vars["line"].set("1")
        self.app.update()
        self.assertIn("300", edit.edit_total.get())
        edit.save()
        self.app.update()
        self.assertEqual(
            self.app.database.order_items("old", actor_id="u1")[0]["quantity"], 1
        )
        self.assertEqual(self.app.database.available_quantity("isbn-1", None), 11)

    def test_settings_simple_fields_auto_and_save_without_photo_folder(self):
        from interface.data_mapping import DataSettings
        from unittest.mock import Mock

        saved = Mock()
        window = DataSettings(self.app, saved)
        self.app.update()
        self.addCleanup(lambda: window.destroy() if window.winfo_exists() else None)
        self.assertFalse(hasattr(window, "folder"))
        self.assertEqual(window.boxes["products"]["description"].winfo_manager(), "")
        window.show_optional.set(True)
        window.toggle_optional()
        self.app.update()
        self.assertEqual(
            window.boxes["products"]["description"].winfo_manager(), "grid"
        )
        window.fields["products"]["price"].set("— Не используется —")
        window.reset()
        self.assertEqual(window.fields["products"]["price"].get(), "price")
        with patch(
            "interface.data_mapping.read_settings",
            return_value={"images_folder": "/missing/path"},
        ), patch("interface.data_mapping.write_settings") as write:
            window.save()
        write.assert_called_once()
        saved.assert_called_once()

    def test_discount_is_visible_in_catalog_and_product_details(self):
        from interface.components.product_tile import ProductCard

        def labels(widget):
            result = []
            if widget.winfo_class() in ("Label", "TLabel"):
                result.append(str(widget.cget("text")))
            for child in widget.winfo_children():
                result.extend(labels(child))
            return result

        def cards(widget):
            result = [widget] if isinstance(widget, ProductCard) else []
            for child in widget.winfo_children():
                result.extend(cards(child))
            return result

        with patch("config.NEW_PRODUCT_DISCOUNT", "0.25"):
            self.app.login(None)
            self.app.update()
            card = next(
                c
                for c in cards(self.app.navigation)
                if c.product["product_id"] == "isbn-1"
            )
            values = labels(card)
            self.assertIn("Скидка −25%", values)
            self.assertTrue(any("350.50" in v for v in values))
            self.assertTrue(any("262.88" in v for v in values))
            self.app.show_product("isbn-1")
            self.app.update()
            self.assertTrue(
                any("не было заказов" in v for v in labels(self.app.navigation))
            )
