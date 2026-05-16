import frappe
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.invoice_service import InvoiceService


def _make_item(name, qty, **fields):
    """Helper bikin mock item child row dari POS Invoice."""
    item = MagicMock()
    item.name = name
    item.qty = qty
    default_fields = {
        "item_code": fields.get("item_code", "ITEM-001"),
        "rate": fields.get("rate", 100),
        "amount": fields.get("amount", qty * 100),
        "status_kitchen": fields.get("status_kitchen", "Sudah Dipesan"),
    }
    item.meta.get_fieldnames_with_value.return_value = list(default_fields.keys()) + ["name", "qty"]
    full_fields = {**default_fields, "qty": qty, "name": name}
    item.get.side_effect = lambda f: full_fields.get(f)
    return item


def _make_invoice(items, name="INV-X", **header):
    inv = MagicMock()
    inv.name = name
    inv.docstatus = header.get("docstatus", 0)
    inv.get.side_effect = lambda f, d=None: {
        "items": items,
        "taxes": header.get("taxes", []),
    }.get(f, d if d is not None else [])
    inv.set = MagicMock()
    inv.save = MagicMock()
    inv.append = MagicMock()
    return inv


class TestMoveInvoiceItems(RestoPOSTestBase):
    """Unit test InvoiceService.move_invoice_items — mock-based."""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = InvoiceService(repo=self.mock_repo)

    def _setup_invoices(self, source_items, target_items=None):
        source = _make_invoice(source_items, name="INV-SRC")
        target = _make_invoice(target_items or [_make_item("trow1", 1)], name="INV-TGT")
        self.mock_repo.get_invoice.side_effect = lambda n: (
            source if n == "INV-SRC" else target
        )
        return source, target

    def test_throws_when_items_empty(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items("INV-SRC", "INV-TGT", [])

    def test_throws_when_source_equals_target(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC", "INV-SRC", [{"item_row_name": "row1", "qty": 1}]
            )

    def test_throws_when_source_submitted(self):
        source = _make_invoice([_make_item("row1", 2)], name="INV-SRC", docstatus=1)
        target = _make_invoice([_make_item("trow1", 1)], name="INV-TGT")
        self.mock_repo.get_invoice.side_effect = lambda n: (
            source if n == "INV-SRC" else target
        )

        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "row1", "qty": 1}]
            )

    def test_throws_when_target_submitted(self):
        source = _make_invoice([_make_item("row1", 2)], name="INV-SRC")
        target = _make_invoice([_make_item("trow1", 1)], name="INV-TGT", docstatus=1)
        self.mock_repo.get_invoice.side_effect = lambda n: (
            source if n == "INV-SRC" else target
        )

        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "row1", "qty": 1}]
            )

    def test_throws_when_row_not_in_source(self):
        self._setup_invoices([_make_item("row1", 2)])

        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "ghost", "qty": 1}]
            )

    def test_throws_when_qty_exceeds_source(self):
        self._setup_invoices([_make_item("row1", 2)])

        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "row1", "qty": 5}]
            )

    def test_throws_when_qty_zero(self):
        self._setup_invoices([_make_item("row1", 2)])

        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "row1", "qty": 0}]
            )

    def test_throws_when_move_empties_source(self):
        self._setup_invoices([_make_item("row1", 2), _make_item("row2", 1)])

        with self.assertRaises(frappe.ValidationError):
            self.service.move_invoice_items(
                "INV-SRC",
                "INV-TGT",
                [
                    {"item_row_name": "row1", "qty": 2},
                    {"item_row_name": "row2", "qty": 1},
                ],
            )

    def test_appends_to_target_and_reduces_source(self):
        source, target = self._setup_invoices(
            [_make_item("row1", 5), _make_item("row2", 3)]
        )

        with patch("resto.services.invoice_service.frappe.db.commit"):
            result = self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "row1", "qty": 2}]
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], "INV-SRC")
        self.assertEqual(result["target"], "INV-TGT")
        # Target append dipanggil dengan qty=2
        append_calls = [c for c in target.append.call_args_list if c[0][0] == "items"]
        self.assertEqual(len(append_calls), 1)
        self.assertEqual(append_calls[0][0][1]["qty"], 2)
        # Source set("items", ...) dipanggil dengan row1 qty=3, row2 tetap 3
        kept_call = source.set.call_args_list[-1]
        kept_items = kept_call[0][1]
        self.assertEqual(len(kept_items), 2)
        self.assertEqual(kept_items[0].qty, 3)
        self.assertEqual(kept_items[1].qty, 3)

    def test_drops_source_row_when_qty_moves_all(self):
        source, target = self._setup_invoices(
            [_make_item("row1", 2), _make_item("row2", 5)]
        )

        with patch("resto.services.invoice_service.frappe.db.commit"):
            self.service.move_invoice_items(
                "INV-SRC", "INV-TGT", [{"item_row_name": "row1", "qty": 2}]
            )

        kept_call = source.set.call_args_list[-1]
        kept_items = kept_call[0][1]
        self.assertEqual(len(kept_items), 1)
        self.assertEqual(kept_items[0].name, "row2")
