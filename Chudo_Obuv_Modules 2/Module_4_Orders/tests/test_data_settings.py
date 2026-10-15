"""Выбор источников не зависит от наличия папки фото."""

import unittest
from unittest.mock import Mock, patch
from interface.data_mapping import DataSettings, FIELDS, EMPTY


class Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DataSettingsTests(unittest.TestCase):
    def panel(self):
        panel = DataSettings.__new__(DataSettings)
        panel.app = Mock()
        panel.app.database.mapping_key = "test"
        columns = {
            "product_id",
            "product_name",
            "price",
            "image_path",
            "user_id",
            "login",
        }
        panel.app.database._table_columns.return_value = columns
        panel.app.database.suggest_columns.side_effect = lambda domain, cols: {
            f: f if f in cols else None for f in FIELDS[domain]
        }
        panel.tables = {"products": Variable("products"), "users": Variable(EMPTY)}
        panel.fields = {
            d: {f: Variable(f if f in columns else EMPTY) for f in FIELDS[d]}
            for d in FIELDS
        }
        panel.boxes = {d: {f: Mock() for f in FIELDS[d]} for d in FIELDS}
        panel.destroy = Mock()
        panel.on_saved = Mock()
        return panel

    def test_save_does_not_validate_or_change_photo_folder_or_other_mappings(self):
        panel = self.panel()
        settings = {
            "images_folder": "missing-folder",
            "mappings": {"test": {"orders": {"table": "old_orders"}}},
        }
        with patch("interface.data_mapping.read_settings", return_value=settings), patch(
            "interface.data_mapping.write_settings"
        ) as save:
            panel.save()
        saved = save.call_args.args[0]
        self.assertEqual(saved["images_folder"], "missing-folder")
        self.assertEqual(saved["mappings"]["test"]["orders"], {"table": "old_orders"})
        self.assertIsNone(saved["mappings"]["test"]["users"])
        panel.on_saved.assert_called_once()

    def test_auto_fills_columns_without_saving(self):
        panel = self.panel()
        panel.fields["products"]["price"].set(EMPTY)
        with patch("interface.data_mapping.write_settings") as save:
            panel.reset()
        self.assertEqual(panel.fields["products"]["price"].get(), "price")
        self.assertEqual(panel.fields["users"]["login"].get(), EMPTY)
        save.assert_not_called()
