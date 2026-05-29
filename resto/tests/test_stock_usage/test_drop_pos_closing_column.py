"""Unit tests for the patch that drops the legacy pos_closing column."""

import unittest
from unittest.mock import patch

from resto.patches.drop_pos_consumption_pos_closing_column import execute


class TestDropPosClosingColumn(unittest.TestCase):
    def test_drops_column_when_still_present(self):
        sql_calls = []

        def fake_sql(query, *args, **kwargs):
            sql_calls.append(query.strip())
            if "INFORMATION_SCHEMA.COLUMNS" in query:
                return [("pos_closing",)]
            return None

        with patch("resto.patches.drop_pos_consumption_pos_closing_column.frappe") as mock_frappe:
            mock_frappe.db.sql.side_effect = fake_sql

            execute()

        self.assertTrue(any("DROP COLUMN" in q for q in sql_calls),
                        "expected ALTER TABLE ... DROP COLUMN to fire")
        mock_frappe.db.commit.assert_called_once()

    def test_skips_when_column_already_dropped(self):
        def fake_sql(query, *args, **kwargs):
            if "INFORMATION_SCHEMA.COLUMNS" in query:
                return []
            raise AssertionError("ALTER TABLE must not fire when column is already gone")

        with patch("resto.patches.drop_pos_consumption_pos_closing_column.frappe") as mock_frappe:
            mock_frappe.db.sql.side_effect = fake_sql

            execute()

        mock_frappe.db.commit.assert_not_called()
