import os
import unittest
from unittest.mock import patch


@unittest.skipUnless(os.getenv("DISPLAY"), "Нужен графический экран")
class ConfigStartupTests(unittest.TestCase):
    def test_bad_connection_opens_help_without_connection_form(self):
        from interface.application import Application

        with patch(
            "interface.application.Database",
            side_effect=ValueError("Проверь postgres_connection.json"),
        ):
            app = Application()
        try:
            self.assertIsNone(app.database)
            self.assertFalse(hasattr(app, "show_connection_settings"))
            self.assertTrue(app.winfo_exists())
        finally:
            app.close()
