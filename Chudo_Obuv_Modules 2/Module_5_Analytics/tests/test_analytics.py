import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from analytics import calculate, load_csv


def example():
    sessions = pd.DataFrame(
        [
            dict(
                session_id="s1",
                user_id="u1",
                session_start="2026-01-01 10:00",
                device_type="mobile",
                traffic_source="email",
            ),
            dict(
                session_id="s2",
                user_id="u2",
                session_start="2026-01-02 10:00",
                device_type="desktop",
                traffic_source="search",
            ),
            dict(
                session_id="s3",
                user_id="u3",
                session_start="2026-01-03 10:00",
                device_type="mobile",
                traffic_source="email",
            ),
            dict(
                session_id="s4",
                user_id="u4",
                session_start="2026-01-04 10:00",
                device_type="desktop",
                traffic_source="search",
            ),
            dict(
                session_id="s5",
                user_id="u1",
                session_start="2026-02-01 10:00",
                device_type="mobile",
                traffic_source="email",
            ),
        ]
    )
    users = ["u1", "u2", "u3", "u1", "u1", "u1", "u1", "u1"]
    sessions_ids = ["s1", "s2", "s3", "s1", "s1", "s1", "s1", "s1"]
    dates = ["2026-01-01 11:00", "2026-01-02 12:00", "2026-01-13 10:00"] + [
        "2026-01-20 12:00"
    ] * 5
    orders = pd.DataFrame(
        [
            dict(
                order_id=str(n + 1),
                user_id=users[n],
                session_id=sessions_ids[n],
                order_date=dates[n],
                status="completed",
                discount_percent=n + 1,
            )
            for n in range(8)
        ]
    )
    costs = [100, 110, 120, 130, 140, 150, 160, 10000]
    items = pd.DataFrame(
        [
            dict(
                order_id=str(n + 1),
                model_id="m1",
                quantity=n + 1,
                unit_price=costs[n] / (n + 1),
            )
            for n in range(8)
        ]
    )
    models = pd.DataFrame([dict(model_id="m1", category="Кеды")])
    return dict(sessions=sessions, orders=orders, items=items, models=models)


class AnalyticsTests(unittest.TestCase):
    def test_all_six_results_use_users_calendar_period_and_iqr(self):
        result = calculate(example())
        self.assertEqual(
            result,
            {
                "5.1": "mobile",
                "5.2": 90.0,
                "5.3": "email",
                "5.4": 7,
                "5.5": 1.0,
                "5.6": "Кеды",
            },
        )

    def test_cancelled_and_april_orders_are_not_counted(self):
        frames = example()
        extra = frames["orders"].iloc[[0]].copy()
        extra["order_id"] = "april"
        extra["order_date"] = "2026-04-01"
        frames["orders"] = pd.concat([frames["orders"], extra])
        extra2 = frames["items"].iloc[[0]].copy()
        extra2["order_id"] = "april"
        extra2["quantity"] = 999999
        frames["items"] = pd.concat([frames["items"], extra2])
        self.assertEqual(calculate(frames)["5.4"], 7)
        frames["orders"].loc[
            frames["orders"]["order_id"].eq("2"), "status"
        ] = "cancelled"
        self.assertEqual(calculate(frames)["5.2"], 60)

    def test_discount_on_items_uses_item_quantity(self):
        frames = example()
        frames["items"]["discount_percent"] = range(1, 9)
        with patch("config.CORRELATION_LEVEL", "items"):
            self.assertAlmostEqual(calculate(frames)["5.5"], 1)

    def test_custom_names_and_csv_separator(self):
        frames = example()
        frames["sessions"] = frames["sessions"].rename(
            columns={"session_start": "visit_time"}
        )
        with tempfile.TemporaryDirectory() as folder:
            import config

            for domain, frame in frames.items():
                frame.to_csv(Path(folder) / config.FILES[domain], index=False, sep=";")
            with patch("config.COLUMNS", {"sessions": {"started": "visit_time"}}):
                self.assertEqual(calculate(load_csv(folder))["5.3"], "email")

    def test_no_orders_produces_explicit_missing_results(self):
        frames = example()
        frames["orders"] = frames["orders"].iloc[:0]
        frames["items"] = frames["items"].iloc[:0]
        result = calculate(frames)
        self.assertIsNone(result["5.2"])
        self.assertIsNone(result["5.5"])
        self.assertEqual(result["5.4"], 0)

    def test_missing_model_and_duplicate_session_are_errors(self):
        frames = example()
        frames["items"].loc[0, "model_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "модели"):
            calculate(frames)
        frames = example()
        frames["sessions"] = pd.concat(
            [frames["sessions"], frames["sessions"].iloc[[0]]]
        )
        with self.assertRaisesRegex(ValueError, "уникальным"):
            calculate(frames)
