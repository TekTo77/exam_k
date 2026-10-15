import contextlib
import io
import json
import os
from pathlib import Path
import queue
import tempfile
import unittest
import uuid
from unittest.mock import patch

from openpyxl import Workbook
import psycopg
from psycopg.conninfo import conninfo_to_dict


@unittest.skipUnless(os.getenv("CHUDO_TEST_DSN"), "Нужна тестовая PostgreSQL")
class ImportFileConfigTests(unittest.TestCase):
    def test_gui_and_cli_import_use_file_without_changing_it(self):
        from storage.connection import read_connection_config
        from excel_importer.parser import parse_excel_files
        from interface.import_window import ExcelImportPanel
        from excel_importer.cli import main

        dsn = os.environ["CHUDO_TEST_DSN"]
        schema = "test_config_" + uuid.uuid4().hex
        info = conninfo_to_dict(dsn)
        try:
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                path = folder / "postgres_connection.json"
                path.write_text(
                    json.dumps(
                        dict(
                            host=info.get("host", "localhost"),
                            port=info.get("port", "5432"),
                            database=info["dbname"],
                            user=info["user"],
                            password=info.get("password", ""),
                            schema=schema,
                            active_tables=None,
                        )
                    )
                )
                before = path.read_bytes()
                excel = folder / "products.xlsx"
                book = Workbook()
                book.active.append(["product_id", "product_name", "price"])
                book.active.append([1, "Книга", 200])
                book.save(excel)
                with patch("storage.connection.config_path", return_value=path):
                    settings = read_connection_config()
                    model = parse_excel_files(
                        [excel],
                        reference_rules=(),
                        table_rules={},
                        foreign_keys=(),
                        auto_foreign_keys=False,
                    )
                    panel = ExcelImportPanel.__new__(ExcelImportPanel)
                    panel.results = queue.Queue()
                    panel._import_worker(model, settings["dsn"], schema, True)
                    ok, result = panel.results.get_nowait()
                    self.assertTrue(ok, result)
                    self.assertEqual(result.rows_inserted, 1)
                    with patch(
                        "sys.argv", ["excel_importer.cli", str(excel)]
                    ), contextlib.redirect_stdout(io.StringIO()):
                        main()
                    self.assertEqual(path.read_bytes(), before)
                    with psycopg.connect(dsn) as connection:
                        rows = connection.execute(
                            psycopg.sql.SQL(
                                "SELECT product_name FROM {}.products"
                            ).format(psycopg.sql.Identifier(schema))
                        ).fetchall()
                    self.assertEqual(rows, [("Книга",)])
                    # В цельной поставке проверяем чтение приложением той же БД.
                    import storage.repository as db_module

                    if hasattr(db_module, "Database"):
                        with patch("storage.repository.read_settings", return_value={}):
                            database = db_module.Database()
                            try:
                                self.assertEqual(
                                    database.products()[0]["product_name"], "Книга"
                                )
                            finally:
                                database.close()
        finally:
            with psycopg.connect(dsn, autocommit=True) as connection:
                connection.execute(
                    psycopg.sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        psycopg.sql.Identifier(schema)
                    )
                )


if __name__ == "__main__":
    unittest.main()
