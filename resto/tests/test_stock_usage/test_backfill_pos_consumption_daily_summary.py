"""Unit tests for the backfill patch that fills POS Consumption.pos_daily_summary
on rows created before Phase 6.2 of the Stock Usage refactor.
"""

import unittest
from unittest.mock import patch


def _column_exists():
    """Default fake for the column-existence probe — returns a truthy row
    so the patch proceeds to backfill."""
    return [("pos_closing",)]


def _fake_sql_factory(rows, column_present=True):
    """Build a side_effect that routes the two SQL calls inside the patch:
    first the column-check, then the SELECT-rows query."""
    def _side(query, *args, **kwargs):
        if "INFORMATION_SCHEMA.COLUMNS" in query:
            return _column_exists() if column_present else []
        return rows
    return _side


class TestBackfillPosConsumptionDailySummary(unittest.TestCase):
    def test_sets_pos_daily_summary_when_pce_belongs_to_a_daily_summary(self):
        rows = [{"name": "PCN-001", "pos_closing": "PCE-A"}]
        eds_lookup = {"PCE-A": "EDS-001"}

        set_calls = []

        def fake_get_value(doctype, filters, field, *_args, **_kw):
            if doctype == "POS Closing Entry Report":
                return eds_lookup.get(filters["pos_closing_entry"])
            return None

        def fake_set_value(doctype, name, field, value, update_modified=True):
            set_calls.append((doctype, name, field, value))

        with patch("resto.patches.backfill_pos_consumption_daily_summary.frappe") as mock_frappe:
            mock_frappe.db.sql.side_effect = _fake_sql_factory(rows)
            mock_frappe.db.get_value.side_effect = fake_get_value
            mock_frappe.db.set_value.side_effect = fake_set_value

            from resto.patches.backfill_pos_consumption_daily_summary import execute
            execute()

        self.assertEqual(set_calls, [("POS Consumption", "PCN-001", "pos_daily_summary", "EDS-001")])

    def test_skips_pce_with_no_matching_daily_summary(self):
        rows = [{"name": "PCN-002", "pos_closing": "PCE-ORPHAN"}]

        set_calls = []

        with patch("resto.patches.backfill_pos_consumption_daily_summary.frappe") as mock_frappe:
            mock_frappe.db.sql.side_effect = _fake_sql_factory(rows)
            mock_frappe.db.get_value.return_value = None
            mock_frappe.db.set_value.side_effect = lambda *a, **k: set_calls.append(a)

            from resto.patches.backfill_pos_consumption_daily_summary import execute
            execute()

        self.assertEqual(set_calls, [], "orphan PCE rows must not be written")

    def test_idempotent_on_empty_candidate_set(self):
        with patch("resto.patches.backfill_pos_consumption_daily_summary.frappe") as mock_frappe:
            mock_frappe.db.sql.side_effect = _fake_sql_factory([])

            from resto.patches.backfill_pos_consumption_daily_summary import execute
            execute()

            mock_frappe.db.set_value.assert_not_called()
            mock_frappe.db.commit.assert_called_once()

    def test_short_circuits_when_pos_closing_column_already_dropped(self):
        """After Phase 6.3 step 2-final, pos_closing is gone — backfill must
        no-op and not even attempt the SELECT."""
        with patch("resto.patches.backfill_pos_consumption_daily_summary.frappe") as mock_frappe:
            mock_frappe.db.sql.side_effect = _fake_sql_factory([], column_present=False)

            from resto.patches.backfill_pos_consumption_daily_summary import execute
            execute()

            mock_frappe.db.set_value.assert_not_called()
            mock_frappe.db.commit.assert_not_called()
