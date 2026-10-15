import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from psycopg.conninfo import conninfo_to_dict
from storage.connection import (
    config_path,
    read_connection_config,
    read_connection_settings,
)


class FileConfigTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "postgres_connection.json"
        self.values = dict(
            host="localhost",
            port="5432",
            database="books",
            user="reader",
            password="a'b c",
            schema="public",
            active_tables=None,
        )
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.values), encoding="utf-8")

    def test_file_wins_environment_and_password_is_quoted(self):
        with patch.dict(
            os.environ, {"CHUDO_DB_DSN": "dbname=wrong", "CHUDO_DB_SCHEMA": "wrong"}
        ):
            result = read_connection_config(self.path)
        parsed = conninfo_to_dict(result["dsn"])
        self.assertEqual(parsed["dbname"], "books")
        self.assertEqual(parsed["password"], "a'b c")
        self.assertEqual(result["schema"], "public")

    def test_invalid_port(self):
        for port in ("word", "0", "65536", "1.5"):
            self.values["port"] = port
            self.write()
            with self.assertRaisesRegex(ValueError, "Порт"):
                read_connection_config(self.path)

    def test_missing_or_invalid_file(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "файл подключения"):
            read_connection_settings(self.path)
        self.path.write_text("[]")
        with self.assertRaisesRegex(ValueError, "JSON-объект"):
            read_connection_settings(self.path)

    def test_module_reads_shared_config_and_standalone_reads_local(self):
        module = Path(self.folder.name) / "Module_4_Orders"
        module.mkdir()
        with patch("storage.connection.PROJECT_DIR", module):
            self.assertEqual(config_path(), self.path)
            local = module / self.path.name
            local.write_text(self.path.read_text())
            self.assertEqual(config_path(), local)
        self.assertEqual(read_connection_settings(local)["database"], "books")

    def test_config_is_not_modified_by_reading(self):
        before = self.path.read_bytes()
        read_connection_settings(self.path)
        read_connection_config(self.path)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
