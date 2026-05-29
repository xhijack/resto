"""Unit tests for StockEntryService — auto-create Material Issue dari POS Consumption."""

import unittest
from unittest.mock import MagicMock, patch

from resto.services.stock_usage.stock_entry_service import StockEntryService


class TestStockEntryService(unittest.TestCase):
    def setUp(self):
        self.service = StockEntryService()

    def test_create_material_issue_from_submitted_consumption(self):
        """POS Consumption Submitted → bikin SE Material Issue dengan items dari rm_breakdown."""
        mock_pcn = MagicMock()
        mock_pcn.docstatus = 1
        mock_pcn.company = "TestCo"
        mock_pcn.warehouse = "Stores - M"
        rm_row = MagicMock()
        rm_row.rm_item = "RM-001"
        rm_row.final_qty = 5
        rm_row.uom = "Kg"
        rm_row.is_batched = 0
        rm_row.batch_no = None
        mock_pcn.rm_breakdown = [rm_row]

        mock_se = MagicMock()
        mock_se.name = "STE-001"
        appended_items = []
        mock_se.append.side_effect = lambda field, row: appended_items.append(row) if field == "items" else None

        with patch("resto.services.stock_usage.stock_entry_service.frappe.get_doc",
                   return_value=mock_pcn), \
             patch("resto.services.stock_usage.stock_entry_service.frappe.new_doc",
                   return_value=mock_se):
            name = self.service.create_material_issue("PCN-001")

        self.assertEqual(name, "STE-001")
        # Single item appended
        self.assertEqual(len(appended_items), 1)
        item = appended_items[0]
        self.assertEqual(item["item_code"], "RM-001")
        self.assertEqual(item["qty"], 5)

    def test_create_material_issue_includes_batch_no_for_batched_rm(self):
        """RM dengan is_batched=1 → SE row include batch_no.
        Fixes Phase 1 high bug #5 (SE append missing batch_no).
        """
        mock_pcn = MagicMock()
        mock_pcn.docstatus = 1
        mock_pcn.company = "TestCo"
        mock_pcn.warehouse = "Stores - M"
        rm_row = MagicMock()
        rm_row.rm_item = "RM-BATCHED"
        rm_row.final_qty = 2
        rm_row.uom = "Kg"
        rm_row.is_batched = 1
        rm_row.batch_no = "BATCH-001"
        mock_pcn.rm_breakdown = [rm_row]

        mock_se = MagicMock()
        mock_se.name = "STE-002"
        appended_items = []
        mock_se.append.side_effect = lambda field, row: appended_items.append(row) if field == "items" else None

        with patch("resto.services.stock_usage.stock_entry_service.frappe.get_doc",
                   return_value=mock_pcn), \
             patch("resto.services.stock_usage.stock_entry_service.frappe.new_doc",
                   return_value=mock_se):
            self.service.create_material_issue("PCN-002")

        item = appended_items[0]
        self.assertEqual(item["batch_no"], "BATCH-001")

    def test_throws_when_pos_consumption_not_submitted(self):
        """POS Consumption Draft → reject (harus Submitted dulu)."""
        import frappe
        mock_pcn = MagicMock()
        mock_pcn.docstatus = 0  # Draft, not submitted
        with patch("resto.services.stock_usage.stock_entry_service.frappe") as mock_frappe:
            mock_frappe.get_doc.return_value = mock_pcn
            mock_frappe.ValidationError = frappe.ValidationError
            mock_frappe.throw.side_effect = frappe.ValidationError("Not submitted")

            with self.assertRaises(frappe.ValidationError):
                self.service.create_material_issue("PCN-DRAFT")
