import unittest
import pandas as pd
from excel2pg.parser import _make_table


class CompatibilityTests(unittest.TestCase):
    def test_map_is_used_without_accessing_removed_applymap(self):
        class CurrentFrame(pd.DataFrame):
            @property
            def applymap(self):
                raise AssertionError("Нельзя читать удалённый applymap")
            def map(self, function):
                return self.apply(lambda column: column.map(function))
        table = _make_table("sample.xlsx", "Sheet1", CurrentFrame({"code": ["001", "002"], "note": ["", "NA"]}), "sample", 1)
        self.assertEqual([r["code"] for r in table.rows], ["001", "002"])
        self.assertIsNone(table.rows[0]["note"])
        self.assertEqual(table.rows[1]["note"], "NA")
