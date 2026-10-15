"""Проверки первичных и внешних ключей на разных Excel, включая кириллицу."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import psycopg
from excel_importer.parser import parse_excel_files
from excel_importer.postgres import import_model, create_schema_sql
from storage.order_operations import as_date
from datetime import date


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def excel(self, name, rows):
        path = self.root / (name + ".xlsx")
        pd.DataFrame(rows).to_excel(path, index=False)
        return path

    def test_category_and_order_item_keys_never_use_foreign_ids(self):
        files = [
            self.excel("categories", [dict(category_id=7, category_name="Книги")]),
            self.excel(
                "subcategories",
                [dict(subcategory_id=20, category_id=7, subcategory_name="Роман")],
            ),
            self.excel("order_items", [dict(order_id=1, product_id=8, quantity=1)]),
        ]
        model = parse_excel_files(files)
        self.assertEqual(
            [t.primary_key.name for t in model.tables],
            ["category_id", "subcategory_id", "__row_id"],
        )
        self.assertEqual(
            [
                (t.name, f.column, f.referenced_table, f.referenced_column)
                for t in model.tables
                for f in t.foreign_keys
            ],
            [("subcategories", "category_id", "categories", "category_id")],
        )

    def test_russian_headers_explicit_keys_types_renames_and_links(self):
        files = [
            self.excel("авторы", [{"Код автора": "A1", "Фамилия": "Иванов"}]),
            self.excel(
                "книги",
                [
                    {
                        "Код книги": "B1",
                        "Автор": "A1",
                        "Цена": "350.50",
                        "Дата": "02.04.2026",
                    }
                ],
            ),
        ]
        rules = {
            "авторы": {
                "table": "writers",
                "columns": {"Код автора": "writer_id"},
                "primary_key": "writer_id",
            },
            "книги": {
                "table": "books",
                "columns": {"Код книги": "isbn", "Автор": "author_id", "Цена": "cost"},
                "primary_key": "isbn",
                "types": {"cost": "NUMERIC(12,2)", "дата": "DATE"},
            },
        }
        model = parse_excel_files(
            files,
            table_rules=rules,
            foreign_keys=[("books", "author_id", "writers", "writer_id")],
        )
        self.assertEqual(model.table_names(), ["writers", "books"])
        self.assertEqual(model.tables[1].rows[0]["дата"], date(2026, 4, 2))
        self.assertEqual(model.tables[1].primary_key.name, "isbn")
        self.assertTrue(model.tables[1].foreign_keys[0].enabled)
        self.assertNotIn("__row_id", model.tables[1].rows[0])

    def test_composite_key_and_foreign_key(self):
        files = [
            self.excel("editions", [dict(book="B", edition=1, name="Первое")]),
            self.excel("sales", [dict(id=1, book="B", edition=1)]),
        ]
        model = parse_excel_files(
            files,
            table_rules={"editions": {"primary_key": ("book", "edition")}},
            foreign_keys=[
                ("sales", ("book", "edition"), "editions", ("book", "edition"))
            ],
        )
        schema = create_schema_sql(model)
        self.assertIn('PRIMARY KEY ("book", "edition")', schema)
        self.assertIn('FOREIGN KEY ("book", "edition")', schema)
        self.assertEqual(len(model.tables[0].primary_keys), 2)

    def test_invalid_keys_and_fractional_integer_fail_before_database(self):
        path = self.excel(
            "sample", [dict(code="A", amount=1.5), dict(code="A", amount=2)]
        )
        with self.assertRaisesRegex(ValueError, "первичный ключ"):
            parse_excel_files([path], table_rules={"sample": {"primary_key": "code"}})
        with self.assertRaisesRegex(ValueError, "не подходит"):
            parse_excel_files(
                [path], table_rules={"sample": {"types": {"amount": "BIGINT"}}}
            )

    def test_bad_reference_is_reported_not_created(self):
        files = [
            self.excel("authors", [dict(author_id=1)]),
            self.excel("books", [dict(book_id=1, author_id=99)]),
        ]
        model = parse_excel_files(files)
        self.assertFalse(model.tables[1].foreign_keys[0].enabled)
        self.assertEqual(model.tables[1].foreign_keys[0].orphan_count, 1)

    def test_long_russian_identifiers_fit_postgres_bytes(self):
        path = self.excel(
            "длинное_имя_таблицы" * 6,
            [
                {
                    "Длинное русское название " * 10: 1,
                    "Длинное русское название " * 10 + "!": 2,
                }
            ],
        )
        model = parse_excel_files([path])
        self.assertLessEqual(len(model.tables[0].name.encode()), 63)
        self.assertEqual(
            len({c.name for c in model.tables[0].columns}), len(model.tables[0].columns)
        )
        self.assertTrue(
            all(len(c.name.encode()) <= 63 for c in model.tables[0].columns)
        )

    def test_supported_dates_and_invalid_date(self):
        self.assertEqual(as_date("2026-04-02T00:00:00.000Z"), date(2026, 4, 2))
        self.assertEqual(as_date("02.04.2026"), date(2026, 4, 2))
        with self.assertRaises(ValueError):
            as_date("31.02.2026")

    @unittest.skipUnless(os.getenv("CHUDO_TEST_DSN"), "Нужен CHUDO_TEST_DSN")
    def test_actual_import_composite_fk_and_append_rollback(self):
        dsn = os.environ["CHUDO_TEST_DSN"]
        schema = "import_" + uuid.uuid4().hex
        self.addCleanup(self.drop_schema, dsn, schema)
        files = [
            self.excel("editions", [dict(book="B", edition=1, name="Первое")]),
            self.excel("sales", [dict(id=1, book="B", edition=1)]),
        ]
        model = parse_excel_files(
            files,
            table_rules={"editions": {"primary_key": ("book", "edition")}},
            foreign_keys=[
                ("sales", ("book", "edition"), "editions", ("book", "edition"))
            ],
        )
        result = import_model(model, dsn, schema)
        self.assertEqual((result.rows_inserted, result.foreign_keys_added), (2, 1))
        with psycopg.connect(dsn) as c:
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                c.execute(f"INSERT INTO \"{schema}\".sales VALUES(2,'Z',1)")
        generated = parse_excel_files([self.excel("plain", [dict(title="Текст")])])
        import_model(generated, dsn, schema)
        with self.assertRaisesRegex(ValueError, "__row_id"):
            import_model(generated, dsn, schema, replace=False)
        with psycopg.connect(dsn) as c:
            self.assertEqual(
                c.execute(f'SELECT count(*) FROM "{schema}".plain').fetchone()[0], 1
            )

    def drop_schema(self, dsn, schema):
        with psycopg.connect(dsn, autocommit=True) as c:
            c.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

    def test_empty_named_columns_and_different_header_rows(self):
        path = self.root / "notes.xlsx"
        with pd.ExcelWriter(path) as writer:
            pd.DataFrame([dict(note_id=1, title="Текст", description=None)]).to_excel(
                writer, sheet_name="notes", index=False, startrow=2
            )
            pd.DataFrame([dict(value="Пропустить")]).to_excel(
                writer, sheet_name="help", index=False
            )
        model = parse_excel_files(
            [path],
            header_rows={"notes.xlsx": {"notes": 3, "help": 1}},
            table_rules={"help": {"skip": True}},
        )
        self.assertEqual(model.table_names(), ["notes"])
        self.assertEqual(model.tables[0].header_row, 3)
        self.assertIn("description", [c.name for c in model.tables[0].columns])
        self.assertIsNone(model.tables[0].rows[0]["description"])
        self.assertTrue(model.warnings)

    def test_header_only_sheet_can_be_imported_explicitly(self):
        path = self.root / "empty.xlsx"
        pd.DataFrame(columns=["name", "description"]).to_excel(path, index=False)
        model = parse_excel_files([path], include_empty_sheets=True)
        self.assertEqual(len(model.tables), 1)
        self.assertEqual(model.tables[0].rows, [])
        self.assertIn("description", [c.name for c in model.tables[0].columns])
