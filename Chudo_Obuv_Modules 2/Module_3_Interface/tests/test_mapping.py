import unittest
from storage.repository import Database


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.database = Database.__new__(Database)

    def test_original_excel_columns(self):
        columns = {
            "__row_id",
            "Категория",
            "Подкатегория",
            "Изображение",
            "Наименование товара",
            "Производство",
            "Состав",
            "Описание",
            "Цена",
        }
        mapping = self.database.suggest_columns("products", columns)
        self.assertEqual(mapping["product_id"], "__row_id")
        self.assertEqual(mapping["image_path"], "Изображение")
        self.assertEqual(mapping["manufacturer"], "Производство")
        self.assertEqual(mapping["product_name"], "Наименование товара")

    def test_id_does_not_match_other_foreign_key(self):
        mapping = self.database.suggest_columns(
            "products", {"category_id", "video_id", "title", "price"}
        )
        self.assertIsNone(mapping["product_id"])

    def test_size_value_does_not_overwrite_size_identifier(self):
        mapping = self.database.suggest_columns(
            "order_items",
            {
                "order_item_id",
                "order_id",
                "product_id",
                "size_id",
                "quantity",
                "unit_price",
            },
        )
        self.assertEqual(mapping["size_id"], "size_id")
        self.assertIsNone(mapping["size_value"])

    def test_user_typo_and_text_role(self):
        mapping = self.database.suggest_columns(
            "users", {"__row_id", "Фамилия", "Имя", "Отчетсво", "Логин", "Роль"}
        )
        self.assertEqual(mapping["middle_name"], "Отчетсво")
        self.assertEqual(mapping["role_name"], "Роль")

    def test_custom_image_column_is_quoted_and_selected(self):
        db = self.database
        db.domain_tables = {"products": "My Catalog"}
        db.domain_columns = {
            "products": {
                "product_id": "sku",
                "product_name": "caption",
                "price": "cost",
                "image_path": 'file "name"',
            }
        }
        captured = []
        db._safe_fetch_all = (
            lambda sql, params, **kwargs: captured.append((sql, params)) or []
        )
        db.products(search="ботинки")
        sql, params = captured[0]
        self.assertIn('p."file ""name""" AS image_path', sql)
        self.assertIn('FROM "My Catalog"', sql)
        self.assertIn("'' AS category", sql)
        self.assertEqual(params, ("%ботинки%",))


if __name__ == "__main__":
    unittest.main()
