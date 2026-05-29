"""Unit tests for PosConsumptionService — draft + submit workflow."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from resto.services.stock_usage.pos_consumption_service import PosConsumptionService


class TestPosConsumptionService(unittest.TestCase):
    def setUp(self):
        self.service = PosConsumptionService()

    def test_create_draft_inserts_without_submit(self):
        """create_draft → insert dengan docstatus=0, TIDAK auto-submit.
        Fixes Phase 1 high bug #6 (doc.submit langsung tanpa save()).
        """
        mock_doc = MagicMock()
        mock_doc.name = "PCN-001"
        with patch("resto.services.stock_usage.pos_consumption_service.frappe.new_doc",
                   return_value=mock_doc), \
             patch("resto.services.stock_usage.pos_consumption_service.frappe.get_doc"):
            payload = {
                "pos_closing": "PCE-001",
                "company": "TestCo",
                "warehouse": "Stores - M",
                "menu_summaries": [],
                "rm_breakdown": [],
            }
            name = self.service.create_draft(payload)

        self.assertEqual(name, "PCN-001")
        mock_doc.insert.assert_called_once()
        mock_doc.submit.assert_not_called()  # KEY assertion: TIDAK submit di draft

    def test_submit_consumption_calls_submit_only_for_draft(self):
        """submit_consumption pada Draft → success. Submitted → reject."""
        mock_doc = MagicMock()
        mock_doc.docstatus = 0  # Draft
        with patch("resto.services.stock_usage.pos_consumption_service.frappe.get_doc",
                   return_value=mock_doc):
            self.service.submit_consumption("PCN-001")
        mock_doc.submit.assert_called_once()

    def test_submit_throws_when_already_submitted(self):
        mock_doc = MagicMock()
        mock_doc.docstatus = 1  # Submitted
        with patch("resto.services.stock_usage.pos_consumption_service.frappe") as mock_frappe:
            mock_frappe.get_doc.return_value = mock_doc
            mock_frappe.ValidationError = frappe.ValidationError
            mock_frappe.throw.side_effect = frappe.ValidationError("Already submitted")

            with self.assertRaises(frappe.ValidationError):
                self.service.submit_consumption("PCN-001")

    def test_submit_validates_batch_availability(self):
        """Submit panggil BatchAllocator.validate_allocation untuk RM batched."""
        mock_doc = MagicMock()
        mock_doc.docstatus = 0
        mock_doc.warehouse = "Stores - M"
        rm_row = MagicMock()
        rm_row.rm_item = "BATCH-ITEM"
        rm_row.batch_no = "B-001"
        rm_row.final_qty = 10
        rm_row.is_batched = 1
        mock_doc.rm_breakdown = [rm_row]

        with patch("resto.services.stock_usage.pos_consumption_service.frappe.get_doc",
                   return_value=mock_doc), \
             patch("resto.services.stock_usage.pos_consumption_service.BatchAllocatorService") as MockBatch:
            MockBatch.return_value.validate_allocation.return_value = {
                "valid": False, "shortage_qty": 5, "message": "Insufficient"
            }
            MockBatch.return_value.is_item_batched.return_value = True
            with patch("resto.services.stock_usage.pos_consumption_service.frappe.throw",
                       side_effect=frappe.ValidationError("Insufficient")):
                with self.assertRaises(frappe.ValidationError):
                    self.service.submit_consumption("PCN-001")

    def test_create_draft_snapshots_valuation_rate(self):
        """create_draft snapshot valuation_rate per RM kalau tidak di-provide."""
        mock_doc = MagicMock()
        mock_doc.name = "PCN-002"
        rm_rows = []
        mock_doc.append.side_effect = lambda field, row: rm_rows.append(row) if field == "rm_breakdown" else None

        with patch("resto.services.stock_usage.pos_consumption_service.frappe.new_doc",
                   return_value=mock_doc), \
             patch("resto.services.stock_usage.pos_consumption_service.frappe.get_doc"), \
             patch("resto.services.stock_usage.pos_consumption_service._get_item_unit_cost",
                   return_value=15000):
            payload = {
                "pos_closing": "PCE-001",
                "company": "TestCo",
                "warehouse": "Stores - M",
                "menu_summaries": [],
                "rm_breakdown": [
                    {"rm_item": "RM-001", "uom": "Kg", "planned_qty": 1, "actual_qty": 1}
                ],
            }
            self.service.create_draft(payload)

        # Verify snapshot was set
        rm_appended = next((r for r in rm_rows if r.get("rm_item") == "RM-001"), None)
        self.assertIsNotNone(rm_appended)
        self.assertEqual(rm_appended.get("valuation_rate_snapshot"), 15000)
