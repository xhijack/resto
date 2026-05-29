"""Unit tests for RawMaterialCalculatorService — orchestrator service.

Scope unit is one POS Daily Summary, which fans out to all linked
POS Closing Entries via its `pos_transactions` child table.
"""

import unittest
from unittest.mock import MagicMock, patch

from resto.services.stock_usage.rm_calculator import RawMaterialCalculatorService


def _eds(branch="BR-1", child_pce_names=("PCE-001",)):
    """Build a mock POS Daily Summary doc with pos_transactions rows."""
    eds = MagicMock()
    eds.branch = branch
    eds.pos_transactions = [
        _child(pce_name) for pce_name in child_pce_names
    ]
    return eds


def _child(pce_name):
    row = MagicMock()
    row.pos_closing_entry = pce_name
    return row


def _pce(name, company="TestCo"):
    pce = MagicMock()
    pce.name = name
    pce.company = company
    return pce


def _mk_get_doc(eds, pce_by_name):
    """side_effect for frappe.get_doc that routes by doctype."""
    def _side(doctype, name=None):
        if doctype == "POS Daily Summary":
            return eds
        if doctype == "POS Closing Entry":
            return pce_by_name[name]
        raise AssertionError(f"unexpected get_doc({doctype}, {name})")
    return _side


class TestRawMaterialCalculatorService(unittest.TestCase):
    def test_compute_breakdown_returns_items_with_rm_and_actual_qty(self):
        """Single-PCE summary still works — orchestrator fans out, hits one PCE."""
        eds = _eds(child_pce_names=("PCE-001",))
        pce_by_name = {"PCE-001": _pce("PCE-001")}

        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   side_effect=_mk_get_doc(eds, pce_by_name)), \
             patch("resto.services.stock_usage.rm_calculator.frappe.db.get_value",
                   return_value=None), \
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
            result = service.compute_breakdown("EDS-001", warehouse="Stores - M")

        self.assertEqual(len(result["items"]), 1)
        fg = result["items"][0]
        self.assertEqual(fg["item_code"], "NASI-GORENG")
        self.assertEqual(fg["qty"], 3)
        self.assertEqual(len(fg["rm_items"]), 1)

    def test_breakdown_marks_is_batched_and_includes_allocations(self):
        """RM dengan has_batch_no=1 → is_batched=True + batch_allocations populated."""
        eds = _eds(child_pce_names=("PCE-001",))
        pce_by_name = {"PCE-001": _pce("PCE-001")}

        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   side_effect=_mk_get_doc(eds, pce_by_name)), \
             patch("resto.services.stock_usage.rm_calculator.frappe.db.get_value",
                   return_value=None), \
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
            result = service.compute_breakdown("EDS-001", warehouse="Stores - M")

        rm = result["items"][0]["rm_items"][0]
        self.assertTrue(rm["is_batched"])
        self.assertEqual(len(rm["batch_allocations"]), 1)
        self.assertEqual(rm["batch_allocations"][0]["batch_no"], "B-001")

    def test_breakdown_with_no_invoices_returns_empty(self):
        """Daily Summary tanpa invoice (semua PCE kosong) → return items: []."""
        eds = _eds(child_pce_names=("PCE-EMPTY",))
        pce_by_name = {"PCE-EMPTY": _pce("PCE-EMPTY")}

        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   side_effect=_mk_get_doc(eds, pce_by_name)), \
             patch("resto.services.stock_usage.rm_calculator.frappe.db.get_value",
                   return_value=None), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg:
            MockAgg.return_value.extract_invoice_names.return_value = []

            service = RawMaterialCalculatorService()
            result = service.compute_breakdown("EDS-EMPTY", warehouse="Stores - M")

        self.assertEqual(result["items"], [])

    def test_breakdown_skips_fg_with_zero_qty(self):
        """FG dengan qty=0 di aggregator → skip dari output."""
        eds = _eds(child_pce_names=("PCE-001",))
        pce_by_name = {"PCE-001": _pce("PCE-001")}

        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   side_effect=_mk_get_doc(eds, pce_by_name)), \
             patch("resto.services.stock_usage.rm_calculator.frappe.db.get_value",
                   return_value=None), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg:

            MockAgg.return_value.extract_invoice_names.return_value = ["SI-001"]
            MockAgg.return_value.aggregate_by_fg.return_value = {
                "FG-ZERO": {"item_code": "FG-ZERO", "qty": 0, "selling_amount": 0,
                            "stock_uom": "Plate", "item_name": "Zero"}
            }

            service = RawMaterialCalculatorService()
            result = service.compute_breakdown("EDS-001", warehouse="Stores - M")

        self.assertEqual(result["items"], [])

    def test_compute_breakdown_fans_out_across_multiple_pces(self):
        """Daily Summary with 3 child PCEs → orchestrator calls extract_invoice_names
        for EACH PCE; combined-and-deduped invoice list is passed to aggregate_by_fg.
        """
        eds = _eds(child_pce_names=("PCE-A", "PCE-B", "PCE-C"))
        pce_by_name = {
            "PCE-A": _pce("PCE-A"),
            "PCE-B": _pce("PCE-B"),
            "PCE-C": _pce("PCE-C"),
        }

        with patch("resto.services.stock_usage.rm_calculator.frappe.get_doc",
                   side_effect=_mk_get_doc(eds, pce_by_name)), \
             patch("resto.services.stock_usage.rm_calculator.frappe.db.get_value",
                   return_value=None), \
             patch("resto.services.stock_usage.rm_calculator.PosInvoiceAggregatorService") as MockAgg:

            # Each PCE contributes one invoice; PCE-C overlaps PCE-A to prove dedup
            MockAgg.return_value.extract_invoice_names.side_effect = [
                ["SI-A"],
                ["SI-B"],
                ["SI-A", "SI-C"],
            ]
            MockAgg.return_value.aggregate_by_fg.return_value = {}

            RawMaterialCalculatorService().compute_breakdown(
                "EDS-MULTI", warehouse="Stores - M",
            )

        self.assertEqual(
            MockAgg.return_value.extract_invoice_names.call_count, 3,
            "expected one extract_invoice_names call per child PCE",
        )
        agg_call = MockAgg.return_value.aggregate_by_fg.call_args
        self.assertEqual(agg_call.args[0], ["SI-A", "SI-B", "SI-C"],
                         "combined invoice list must dedupe across PCEs")
