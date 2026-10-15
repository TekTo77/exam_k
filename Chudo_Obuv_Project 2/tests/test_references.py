import unittest
from excel_importer.entities import ColumnEntity, TableEntity, WorkbookModel
from excel_importer.references import prepare_references


class ReferenceTests(unittest.TestCase):
    def model(self, duplicate=False):
        parent = TableEntity(
            "customers_custom",
            "",
            "",
            [
                ColumnEntity("sku", "sku", "TEXT", False, True),
                ColumnEntity("last", "last", "TEXT"),
                ColumnEntity("first", "first", "TEXT"),
            ],
            [{"sku": "U-a", "last": "Иванов", "first": "Иван"}],
        )
        if duplicate:
            parent.rows.append({"sku": "U-b", "last": "Иванов", "first": "Иван"})
        child = TableEntity(
            "sales_custom",
            "",
            "",
            [
                ColumnEntity("buyer", "buyer", "TEXT"),
                ColumnEntity("customer_code", "customer_code", "TEXT"),
            ],
            [
                {"buyer": "  ИВАНОВ\u00a0Иван  "},
                {"buyer": "Неизвестный клиент"},
                {"buyer": "Иванов Иван", "customer_code": "explicit-id"},
            ],
        )
        return WorkbookModel([parent, child])

    def rule(self):
        return {
            "parent_table": "customers_custom",
            "child_table": "sales_custom",
            "column": "customer_code",
            "parent_fields": (("last",), ("first",)),
            "child_fields": (("buyer",),),
        }

    def test_arbitrary_table_names_text_ids_and_explicit_id_priority(self):
        model = prepare_references(self.model(), [self.rule()])
        rows = model.tables[1].rows
        self.assertEqual(rows[0]["customer_code"], "U-a")
        self.assertIsNone(rows[1]["customer_code"])
        self.assertEqual(rows[2]["customer_code"], "explicit-id")
        self.assertTrue(model.warnings)

    def test_duplicate_names_are_not_assigned(self):
        model = prepare_references(self.model(duplicate=True), [self.rule()])
        self.assertIsNone(model.tables[1].rows[0]["customer_code"])

    def test_missing_rule_entities_leave_any_workbook_intact(self):
        model = self.model()
        before = list(model.tables[1].columns)
        prepare_references(
            model, [{"parent_table": "missing", "child_table": "missing"}]
        )
        self.assertEqual(model.tables[1].columns, before)

    def test_missing_column_is_created_with_parent_id_type(self):
        model = self.model()
        child = model.tables[1]
        child.columns = child.columns[:1]
        child.rows = child.rows[:1]
        prepare_references(model, [self.rule()])
        self.assertEqual(child.columns[-1].name, "customer_code")
        self.assertEqual(child.columns[-1].pg_type, "TEXT")
        self.assertEqual(child.rows[0]["customer_code"], "U-a")


if __name__ == "__main__":
    unittest.main()
