import unittest
from unittest.mock import patch

from interface.formatting import field_rows, product_context, render
from storage.repository import Database, _extra_product_aliases


class PresentationTests(unittest.TestCase):
    def test_optional_fields_and_zero_stock(self):
        fields = (
            {"template": "Автор: {author}", "fields": ("author",), "hide_empty": True},
            {
                "template": "Остаток: {total_quantity}",
                "fields": ("total_quantity",),
                "hide_empty": True,
            },
            {"template": "ISBN: {isbn}", "layout": "list"},
        )
        self.assertEqual(
            list(field_rows(fields, {"total_quantity": 0}, "grid")),
            [("Остаток: 0", "normal")],
        )
        self.assertEqual(
            render("{author} / {unknown}", {"author": "Лев Толстой"}), "Лев Толстой / —"
        )

    def test_templates_only_accept_simple_fields(self):
        for template in ("{item.name}", "{item[0]}", "{price:.2f}", "{item!r}"):
            with self.subTest(template=template), self.assertRaises(ValueError):
                render(template, {"item": "value", "price": 10})

    def test_context_preserves_extra_data_and_formats_price(self):
        values = product_context({"author": "Автор", "price": 2000}, 1500)
        self.assertEqual(values["author"], "Автор")
        self.assertIn("1 500.00", values["price_text"])
        self.assertEqual(values["price"], 2000)

    def test_extra_field_alias_and_quoted_select(self):
        extra = {"author": {"aliases": ("Автор книги",), "label": "Автор"}}
        with patch("storage.repository.EXTRA_PRODUCT_FIELDS", extra):
            aliases = _extra_product_aliases(Database.COLUMN_ALIASES["products"])
            self.assertEqual(aliases["author"], ("author", "Автор книги"))
            db = Database.__new__(Database)
            db.domain_tables = {"products": "Книги"}
            db.domain_columns = {
                "products": {
                    "product_id": "код",
                    "product_name": "название",
                    "price": "цена",
                    "author": 'Автор "книги"',
                }
            }
            queries = []
            db._safe_fetch_all = lambda sql, params, **kw: queries.append(sql) or []
            db.products()
            self.assertIn('p."Автор ""книги""" AS "author"', queries[0])
            db.domain_columns["products"]["author"] = None
            db.products()
            self.assertIn("'' AS \"author\"", queries[1])

    def test_extra_fields_cannot_override_identifiers_or_derived_values(self):
        for field in ("product_id", "total_quantity", "wrong name", "price_text"):
            with patch(
                "storage.repository.EXTRA_PRODUCT_FIELDS", {field: {}}
            ), self.assertRaises(ValueError):
                _extra_product_aliases(Database.COLUMN_ALIASES["products"])


if __name__ == "__main__":
    unittest.main()
