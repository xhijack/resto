"""Unit tests for the backfill patch that fills POS Consumption.pos_daily_summary
on rows created before Phase 6.2 of the Stock Usage refactor.
"""

import unittest
from unittest.mock import patch

from resto.patches.backfill_pos_consumption_daily_summary import execute


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
            mock_frappe.db.sql.return_value = rows
            mock_frappe.db.get_value.side_effect = fake_get_value
            mock_frappe.db.set_value.side_effect = fake_set_value

            execute()

        self.assertEqual(set_calls, [("POS Consumption", "PCN-001", "pos_daily_summary", "EDS-001")])

    def test_skips_pce_with_no_matching_daily_summary(self):
        rows = [{"name": "PCN-002", "pos_closing": "PCE-ORPHAN"}]

        set_calls = []

        with patch("resto.patches.backfill_pos_consumption_daily_summary.frappe") as mock_frappe:
            mock_frappe.db.sql.return_value = rows
            mock_frappe.db.get_value.return_value = None
            mock_frappe.db.set_value.side_effect = lambda *a, **k: set_calls.append(a)

            execute()

        self.assertEqual(set_calls, [], "orphan PCE rows must not be written")

    def test_idempotent_on_empty_candidate_set(self):
        with patch("resto.patches.backfill_pos_consumption_daily_summary.frappe") as mock_frappe:
            mock_frappe.db.sql.return_value = []

            execute()

            mock_frappe.db.set_value.assert_not_called()
            mock_frappe.db.commit.assert_called_once()
