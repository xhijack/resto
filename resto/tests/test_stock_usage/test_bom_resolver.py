"""Unit tests for BomResolverService.

TDD red-phase: written before service exists. Drives the API contract.
Run via: bench --site resto.test run-tests --app resto --module resto.tests.test_stock_usage.test_bom_resolver
"""

import unittest
from unittest.mock import MagicMock, patch

from resto.services.stock_usage.bom_resolver import BomResolverService


class TestBomResolverService(unittest.TestCase):
    def setUp(self):
        self.service = BomResolverService()

    def test_resolve_fg_via_resto_menu_mapping(self):
        """sell_item dengan Resto Menu mapping → return recipe_item sebagai FG."""
        with patch("resto.services.stock_usage.bom_resolver.frappe") as mock_frappe:
            mock_frappe.db.get_value.side_effect = [
                "Menu-001",
                {"name": "Menu-001", "sell_item": "VOUCHER-50K", "recipe_item": "RM-001",
                 "default_bom": "BOM-001", "menu_category": "Voucher"},
                {"item_name": "Voucher Recipe", "stock_uom": "Nos"},
            ]
            mock_frappe.get_meta.return_value.fields = []

            fg = self.service.resolve_fg("VOUCHER-50K", "TestCo")

        self.assertEqual(fg["item_code"], "RM-001")
        self.assertEqual(fg["bom_no"], "BOM-001")

    def test_resolve_fg_falls_back_to_sold_item_when_no_menu(self):
        """Tidak ada Resto Menu mapping → fallback ke sold_item sebagai FG."""
        with patch("resto.services.stock_usage.bom_resolver.frappe") as mock_frappe:
            mock_frappe.db.get_value.side_effect = [
                None,  # no Resto Menu found
                {"item_name": "Nasi Goreng", "stock_uom": "Plate"},
                None,  # no resto menu BOM
                "BOM-DEFAULT-001",  # default BOM via item
            ]
            mock_frappe.get_meta.return_value.fields = []

            fg = self.service.resolve_fg("ITEM-NG", "TestCo")

        self.assertEqual(fg["item_code"], "ITEM-NG")
        self.assertEqual(fg["bom_no"], "BOM-DEFAULT-001")

    def test_explode_bom_returns_flat_rm_list(self):
        """explode_bom_flat return list dict dengan item_code+qty+stock_uom."""
        mock_bom_items = {
            "RM-001": {"item_code": "RM-001", "item_name": "Sugar", "qty": 2.5,
                       "stock_uom": "Kg", "uom": "Kg"},
            "RM-002": {"item_code": "RM-002", "item_name": "Flour", "qty": 1.0,
                       "stock_uom": "Kg", "uom": "Kg"},
        }
        with patch("resto.services.stock_usage.bom_resolver.get_bom_items_as_dict",
                   return_value=mock_bom_items):
            with patch("resto.services.stock_usage.bom_resolver.frappe.db.get_value",
                       return_value={"valuation_rate": 10000, "last_purchase_rate": None,
                                     "standard_rate": None}):
                rm_list = self.service.explode_bom_flat("BOM-001", qty=2, company="TestCo")

        self.assertEqual(len(rm_list), 2)
        codes = {r["item_code"] for r in rm_list}
        self.assertEqual(codes, {"RM-001", "RM-002"})

    def test_build_tree_caches_bom_lookups(self):
        """Multi-call same BOM tidak harus frappe.get_doc berkali — cache hit."""
        bom_doc = MagicMock()
        bom_doc.quantity = 1.0
        bom_item = MagicMock()
        bom_item.item_code = "RM-001"
        bom_item.item_name = "Sugar"
        bom_item.qty = 0.5
        bom_item.uom = "Kg"
        bom_item.bom_no = None
        bom_doc.items = [bom_item]

        with patch("resto.services.stock_usage.bom_resolver.frappe.get_doc",
                   return_value=bom_doc) as mock_get_doc, \
             patch("resto.services.stock_usage.bom_resolver.frappe.db.get_value",
                   return_value={"valuation_rate": 1000}):
            self.service.build_tree("BOM-001", fg_qty=2)
            self.service.build_tree("BOM-001", fg_qty=5)  # cached → no 2nd call

        # Both calls used SAME bom — cache should serve 2nd
        # Strict: get_doc called exactly 1 time
        self.assertEqual(mock_get_doc.call_count, 1,
                         "BOM cache not working — get_doc called more than once for same bom_no")

    def test_resolve_fg_returns_none_bom_when_no_match_anywhere(self):
        """Item tanpa Resto Menu + tanpa Item default BOM → bom_no = None."""
        with patch("resto.services.stock_usage.bom_resolver.frappe") as mock_frappe:
            mock_frappe.db.get_value.side_effect = [
                None,  # no Resto Menu
                {"item_name": "Random Item", "stock_uom": "Nos"},
                None,  # no Resto Menu BOM
                None,  # no Item default BOM
                None,  # no latest active BOM
            ]
            mock_frappe.get_meta.return_value.fields = []

            fg = self.service.resolve_fg("ITEM-UNKNOWN", "TestCo")

        self.assertEqual(fg["item_code"], "ITEM-UNKNOWN")
        self.assertIsNone(fg["bom_no"])
