import os
import unittest
from unittest.mock import patch
import test_adaptation_pg as fixtures


@unittest.skipUnless(
    os.getenv("DISPLAY") and os.getenv("CHUDO_TEST_DSN"), "Нужны DISPLAY и тестовая БД"
)
class ModuleUiTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.BooksTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_catalog_stage_starts_without_login_or_order_controls(self):
        from interface.application import Application
        from interface.catalog_view import CatalogFrame
        from interface.components.product_tile import ProductCard

        app = Application(module_number=2)
        self.addCleanup(app.close)
        app.update()
        page = next(
            w for w in app.navigation.winfo_children() if isinstance(w, CatalogFrame)
        )
        self.assertFalse(app.can_order())
        self.assertIsNone(app.current_user)
        cards = page.content.winfo_children()
        self.assertTrue(any(isinstance(w, ProductCard) for w in cards))
        app.show_product("isbn-1")
        self.assertIn(page, app.navigation.winfo_children())

    def test_customer_stage_disables_staff_management_even_for_admin(self):
        from interface.application import Application

        app = Application(module_number=3)
        self.addCleanup(app.close)
        app.login(app.database.find_user_by_login("admin"))
        app.update()
        self.assertTrue(app.can_order())
        self.assertFalse(app.is_admin())
        self.assertFalse(app.is_manager_or_admin())
        page = app.navigation.winfo_children()[0]
        app.show_orders()
        self.assertIn(page, app.navigation.winfo_children())
        with patch("interface.application.show_error") as error:
            app.show_order_edit("old")
            error.assert_called_once()
        app.show_product("isbn-1")
        app.update()
