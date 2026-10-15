import queue
import unittest
from unittest.mock import Mock, patch

from interface.import_window import ExcelImportPanel


class ImportUiTests(unittest.TestCase):
    def test_connection_error_reaches_window_after_worker_returns(self):
        panel = ExcelImportPanel.__new__(ExcelImportPanel)
        panel.results = queue.Queue()
        errors = []
        panel._import_failed = errors.append
        error = ConnectionError("PostgreSQL недоступен")
        with patch("excel_importer.postgres.import_model", side_effect=error):
            panel._import_worker(None, "", "public", True)
        panel._poll_import()
        self.assertEqual(errors, [error])

    def test_import_rechecks_files_after_preview(self):
        panel = ExcelImportPanel.__new__(ExcelImportPanel)
        panel.model = object()
        panel._parse = Mock(return_value=None)
        panel.start_import()
        panel._parse.assert_called_once_with()

    def test_saved_sql_rechecks_files_after_preview(self):
        panel = ExcelImportPanel.__new__(ExcelImportPanel)
        panel.model = object()
        panel._parse = Mock(return_value=None)
        panel.save_sql()
        panel._parse.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
