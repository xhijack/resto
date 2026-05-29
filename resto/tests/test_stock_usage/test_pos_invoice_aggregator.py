"""Unit tests for PosInvoiceAggregatorService."""

import unittest
from unittest.mock import MagicMock, patch

from resto.services.stock_usage.pos_invoice_aggregator import PosInvoiceAggregatorService


class TestPosInvoiceAggregatorService(unittest.TestCase):
    def setUp(self):
        self.service = PosInvoiceAggregatorService()

    def test_extract_invoice_names_from_child_tables(self):
        """PCE dengan child table 'pos_transactions' → extract invoice names."""
        pce = MagicMock()
        tf = MagicMock()
        tf.fieldname = "pos_transactions"
        pce.meta.get_table_fields.return_value = [tf]
        child_row = MagicMock()
        child_row.get.side_effect = lambda k: {"sales_invoice": "SI-001",
                                                "pos_invoice": None, "invoice": None,
                                                "name": "row1"}.get(k)
        pce.get.return_value = [child_row]

        with patch("resto.services.stock_usage.pos_invoice_aggregator.frappe.db.exists",
                   return_value=True):
            names = self.service.extract_invoice_names(pce)

        self.assertIn("SI-001", names)

    def test_extract_invoice_names_fallback_to_date_range_query(self):
        """Tidak ada di child table → fallback ke frappe.get_all by date range."""
        pce = MagicMock()
        pce.meta.get_table_fields.return_value = []
        pce.period_start_date = "2026-05-01"
        pce.period_end_date = "2026-05-31"
        pce.pos_profile = "Riau"
        pce.company = "TestCo"

        mock_si_rows = [MagicMock(name="row1"), MagicMock(name="row2")]
        mock_si_rows[0].name = "SI-100"
        mock_si_rows[1].name = "SI-101"

        with patch("resto.services.stock_usage.pos_invoice_aggregator.frappe.get_all",
                   return_value=mock_si_rows) as mock_get_all:
            names = self.service.extract_invoice_names(pce)

        self.assertEqual(set(names), {"SI-100", "SI-101"})
        # verify filter includes is_pos=1
        call_kwargs = mock_get_all.call_args.kwargs
        self.assertEqual(call_kwargs.get("filters", {}).get("is_pos"), 1)

    def test_aggregate_skips_voucher_items(self):
        """Item dengan is_voucher_item=1 di-skip dari RM aggregation."""
        # Mock invoices with mixed items
        with patch("resto.services.stock_usage.pos_invoice_aggregator.frappe") as mock_frappe:
            mock_frappe.db.exists.return_value = True
            si_items = [
                {"item_code": "VOUCHER-50K", "qty": 1, "net_amount": 50000, "is_voucher_item": 1},
                {"item_code": "NASI-GORENG", "qty": 2, "net_amount": 50000, "is_voucher_item": 0},
            ]
            mock_frappe.get_all.return_value = si_items

            agg = self.service.aggregate_by_fg(["SI-001"], "TestCo")

        # Voucher item should be skipped
        self.assertNotIn("VOUCHER-50K", agg)
        self.assertIn("NASI-GORENG", agg)

    def test_aggregate_dedups_invoice_in_both_si_and_pi(self):
        """Same invoice name di Sales Invoice + POS Invoice → cuma dihitung sekali."""
        # Both exists check returns True for both; aggregator must dedup
        with patch("resto.services.stock_usage.pos_invoice_aggregator.frappe") as mock_frappe:
            mock_frappe.db.exists.return_value = True  # both tables
            mock_frappe.get_all.return_value = [
                {"item_code": "ITEM-A", "qty": 1, "net_amount": 10000, "is_voucher_item": 0},
            ]

            agg = self.service.aggregate_by_fg(["INVDUP-001"], "TestCo")

        # ITEM-A should appear once, qty=1 (not 2)
        self.assertEqual(agg["ITEM-A"]["qty"], 1)

    def test_aggregate_uses_bulk_get_all_not_n_plus_one(self):
        """Bulk fetch — call frappe.get_all once, not per-invoice."""
        with patch("resto.services.stock_usage.pos_invoice_aggregator.frappe") as mock_frappe:
            mock_frappe.db.exists.return_value = True
            mock_frappe.get_all.return_value = [
                {"item_code": "ITEM-A", "qty": 1, "net_amount": 1000, "is_voucher_item": 0},
            ]

            self.service.aggregate_by_fg(["SI-001", "SI-002", "SI-003"], "TestCo")

        # Should be called ONCE (bulk) with filters parent IN [list], not 3 times
        # Allow 2x calls (one for SI, one for PI fallback) but not 3+ (N+1 anti-pattern)
        self.assertLessEqual(mock_frappe.get_all.call_count, 2,
                             "N+1 detected — get_all called per invoice instead of bulk")

    def test_aggregate_throws_when_net_amount_missing(self):
        """net_amount missing → throw clear error (strict mode, no silent fallback)."""
        import frappe  # ValidationError
        with patch("resto.services.stock_usage.pos_invoice_aggregator.frappe") as mock_frappe:
            mock_frappe.db.exists.return_value = True
            mock_frappe.ValidationError = frappe.ValidationError
            mock_frappe.throw.side_effect = frappe.ValidationError(
                "net_amount missing"
            )
            mock_frappe.get_all.return_value = [
                {"item_code": "ITEM-A", "qty": 1, "net_amount": None, "amount": 1000,
                 "is_voucher_item": 0},
            ]

            with self.assertRaises(frappe.ValidationError):
                self.service.aggregate_by_fg(["SI-001"], "TestCo")
