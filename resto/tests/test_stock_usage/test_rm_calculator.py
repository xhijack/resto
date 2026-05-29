"""Unit tests for RawMaterialCalculatorService — orchestrator service."""

import unittest
from unittest.mock import MagicMock, patch

from resto.services.stock_usage.rm_calculator import RawMaterialCalculatorService


class TestRawMaterialCalculatorService(unittest.TestCase):
    def test_compute_breakdown_returns_items_with_rm_and_actual_qty(self):
        """compute_breakdown orchestrator return list FG dengan rm_items dan actual_qty."""
        mock_pce = MagicMock()
        mock_pce.company = "TestCo"
        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   return_value=mock_pce), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg, \
             patch("resto.services.stock_usage.rm_calculator.BomResolverService") as MockBom, \
             patch("resto.services.stock_usage.rm_calculator.BatchAllocatorService") as MockBatch:

            MockAgg.return_value.extract_invoice_names.return_value = ["SI-001"]
            MockAgg.return_value.aggregate_by_fg.return_value = {
                "NASI-GORENG": {"item_code": "NASI-GORENG", "item_name": "Nasi Goreng",
                                "qty": 3, "selling_amount": 75000, "stock_uom": "Plate"}
            }
            MockBom.return_value.resolve_fg.return_value = {
                "item_code": "NASI-GORENG", "item_name": "Nasi Goreng",
                "stock_uom": "Plate", "bom_no": "BOM-001"
            }
            MockBom.return_value.explode_bom_flat.return_value = [
                {"item_code": "RM-RICE", "item_name": "Rice", "qty": 0.3,
                 "stock_uom": "Kg", "unit_cost": 10000}
            ]
            MockBom.return_value.build_tree.return_value = []
            MockBatch.return_value.is_item_batched.return_value = False

            service = RawMaterialCalculatorService()
            result = service.compute_breakdown("PCE-001", warehouse="Stores - M")

        self.assertEqual(len(result["items"]), 1)
        fg = result["items"][0]
        self.assertEqual(fg["item_code"], "NASI-GORENG")
        self.assertEqual(fg["qty"], 3)
        self.assertEqual(len(fg["rm_items"]), 1)

    def test_breakdown_marks_is_batched_and_includes_allocations(self):
        """RM dengan has_batch_no=1 → is_batched=True + batch_allocations populated."""
        mock_pce = MagicMock(); mock_pce.company = "TestCo"
        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   return_value=mock_pce), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg, \
             patch("resto.services.stock_usage.rm_calculator.BomResolverService") as MockBom, \
             patch("resto.services.stock_usage.rm_calculator.BatchAllocatorService") as MockBatch:

            MockAgg.return_value.extract_invoice_names.return_value = ["SI-001"]
            MockAgg.return_value.aggregate_by_fg.return_value = {
                "MENU-A": {"item_code": "MENU-A", "item_name": "Menu A", "qty": 1,
                           "selling_amount": 100000, "stock_uom": "Plate"}
            }
            MockBom.return_value.resolve_fg.return_value = {
                "item_code": "MENU-A", "item_name": "Menu A",
                "stock_uom": "Plate", "bom_no": "BOM-A"
            }
            MockBom.return_value.explode_bom_flat.return_value = [
                {"item_code": "RM-BATCH", "item_name": "Batched Item",
                 "qty": 0.5, "stock_uom": "Kg", "unit_cost": 5000}
            ]
            MockBom.return_value.build_tree.return_value = []
            MockBatch.return_value.is_item_batched.return_value = True
            MockBatch.return_value.allocate_fifo.return_value = {
                "allocations": [{"batch_no": "B-001", "allocated_qty": 0.5,
                                 "available_qty": 5, "expiry_date": "2026-12-31"}],
                "partial": False, "shortage_qty": 0
            }

            service = RawMaterialCalculatorService()
            result = service.compute_breakdown("PCE-001", warehouse="Stores - M")

        rm = result["items"][0]["rm_items"][0]
        self.assertTrue(rm["is_batched"])
        self.assertEqual(len(rm["batch_allocations"]), 1)
        self.assertEqual(rm["batch_allocations"][0]["batch_no"], "B-001")

    def test_breakdown_with_no_invoices_returns_empty(self):
        """PCE tanpa invoice → return items: []."""
        mock_pce = MagicMock(); mock_pce.company = "TestCo"
        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   return_value=mock_pce), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg:
            MockAgg.return_value.extract_invoice_names.return_value = []

            service = RawMaterialCalculatorService()
            result = service.compute_breakdown("PCE-EMPTY", warehouse="Stores - M")

        self.assertEqual(result["items"], [])

    def test_breakdown_skips_fg_with_zero_qty(self):
        """FG dengan qty=0 di aggregator → skip dari output."""
        mock_pce = MagicMock(); mock_pce.company = "TestCo"
        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   return_value=mock_pce), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg:

            MockAgg.return_value.extract_invoice_names.return_value = ["SI-001"]
            MockAgg.return_value.aggregate_by_fg.return_value = {
                "FG-ZERO": {"item_code": "FG-ZERO", "qty": 0, "selling_amount": 0,
                            "stock_uom": "Plate", "item_name": "Zero"}
            }

            service = RawMaterialCalculatorService()
            result = service.compute_breakdown("PCE-001", warehouse="Stores - M")

        self.assertEqual(result["items"], [])
