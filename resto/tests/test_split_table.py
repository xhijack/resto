import frappe
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.table_service import TableService, TableAlreadyClaimedError
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
    item._raw_fields = full_fields
    return item


def _make_source_invoice(items, **header):
    """Helper bikin mock POS Invoice doc."""
    source = MagicMock()
    source.docstatus = header.get("docstatus", 0)
    source.customer = header.get("customer", "CUST-1")
    source.pos_profile = header.get("pos_profile", "PROF-1")
    source.order_type = header.get("order_type", "Dine In")
    source.branch = header.get("branch", "BR-1")
    source.company = header.get("company", "_Test Company")
    source.taxes_and_charges = header.get("taxes_and_charges", "Tax Template")
    source.get.side_effect = lambda f, d=None: {
        "items": items,
        "taxes": header.get("taxes", []),
    }.get(f, d if d is not None else [])
    source.set = MagicMock()
    source.save = MagicMock()
    return source


class TestSplitInvoice(RestoPOSTestBase):
    """Unit test InvoiceService.split_invoice — mock-based."""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = InvoiceService(repo=self.mock_repo)

    def _patch_frappe(self):
        return [
            patch("resto.services.invoice_service.frappe.get_doc"),
            patch("resto.services.invoice_service.frappe.db.commit"),
        ]

    def test_throws_when_items_empty(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice("INV-1", [])

    def test_throws_when_source_submitted(self):
        items = [_make_item("row1", 2)]
        source = _make_source_invoice(items, docstatus=1)
        self.mock_repo.get_invoice.return_value = source

        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice("INV-1", [{"item_row_name": "row1", "qty": 1}])

    def test_throws_when_row_not_found(self):
        items = [_make_item("row1", 2)]
        source = _make_source_invoice(items)
        self.mock_repo.get_invoice.return_value = source

        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice(
                "INV-1", [{"item_row_name": "ghost-row", "qty": 1}]
            )

    def test_throws_when_qty_exceeds_source(self):
        items = [_make_item("row1", 2)]
        source = _make_source_invoice(items)
        self.mock_repo.get_invoice.return_value = source

        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice(
                "INV-1", [{"item_row_name": "row1", "qty": 5}]
            )

    def test_throws_when_split_empties_source(self):
        """Kalau semua qty di-split sampai source kosong → throw, suruh pakai move_table."""
        items = [_make_item("row1", 2), _make_item("row2", 3)]
        source = _make_source_invoice(items)
        self.mock_repo.get_invoice.return_value = source

        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice(
                "INV-1",
                [
                    {"item_row_name": "row1", "qty": 2},
                    {"item_row_name": "row2", "qty": 3},
                ],
            )

    def test_throws_when_qty_zero_or_negative(self):
        items = [_make_item("row1", 2)]
        source = _make_source_invoice(items)
        self.mock_repo.get_invoice.return_value = source

        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice("INV-1", [{"item_row_name": "row1", "qty": 0}])
        with self.assertRaises(frappe.ValidationError):
            self.service.split_invoice("INV-1", [{"item_row_name": "row1", "qty": -1}])

    def test_reduces_source_row_qty(self):
        """Source row qty harus berkurang dengan split_qty."""
        items = [_make_item("row1", 5), _make_item("row2", 3)]
        source = _make_source_invoice(items)
        self.mock_repo.get_invoice.return_value = source

        new_invoice_doc = MagicMock()
        new_invoice_doc.name = "INV-NEW"

        with patch("resto.services.invoice_service.frappe.get_doc", return_value=new_invoice_doc), \
             patch("resto.services.invoice_service.frappe.db.commit"):
            result = self.service.split_invoice(
                "INV-1", [{"item_row_name": "row1", "qty": 2}]
            )

        self.assertEqual(result, "INV-NEW")
        # row1 qty harus jadi 3 (5-2), row2 tetap 3
        kept_call = source.set.call_args_list[-1]
        self.assertEqual(kept_call[0][0], "items")
        kept_items = kept_call[0][1]
        self.assertEqual(len(kept_items), 2)
        self.assertEqual(kept_items[0].qty, 3)
        self.assertEqual(kept_items[1].qty, 3)

    def test_drops_source_row_when_qty_zero(self):
        """Kalau split_qty == source qty (untuk row tertentu, bukan semua), row di-drop."""
        items = [_make_item("row1", 2), _make_item("row2", 5)]
        source = _make_source_invoice(items)
        self.mock_repo.get_invoice.return_value = source

        new_invoice_doc = MagicMock()
        new_invoice_doc.name = "INV-NEW"

        with patch("resto.services.invoice_service.frappe.get_doc", return_value=new_invoice_doc), \
             patch("resto.services.invoice_service.frappe.db.commit"):
            self.service.split_invoice(
                "INV-1", [{"item_row_name": "row1", "qty": 2}]
            )

        kept_call = source.set.call_args_list[-1]
        kept_items = kept_call[0][1]
        # row1 ter-drop, hanya row2 yang tersisa
        self.assertEqual(len(kept_items), 1)
        self.assertEqual(kept_items[0].name, "row2")


class TestSplitTable(RestoPOSTestBase):
    """Unit test TableService.split_table — mock-based."""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = TableService(repo=self.mock_repo)

    def _src_table(self, invoice_name="INV-1", status="Terisi"):
        doc = MagicMock()
        doc.status = status
        doc.customer = "CUST-1"
        doc.pax = 4
        doc.type_customer = "Personal"
        doc.taken_by = "kasir@test.com"
        order = MagicMock()
        order.invoice_name = invoice_name
        doc.orders = [order]
        return doc

    def _tgt_table(self, status="Kosong"):
        doc = MagicMock()
        doc.status = status
        doc.orders = []
        return doc

    def test_throws_when_source_table_missing(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.split_table(
                source_table="", source_invoice="INV-1",
                items=[{"item_row_name": "row1", "qty": 1}], target_table="T-2",
            )

    def test_throws_when_source_eq_target(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.split_table(
                source_table="T-1", source_invoice="INV-1",
                items=[{"item_row_name": "row1", "qty": 1}], target_table="T-1",
            )

    def test_throws_when_source_table_not_exists(self):
        self.mock_repo.table_exists.return_value = False
        with self.assertRaises(frappe.ValidationError):
            self.service.split_table(
                source_table="T-1", source_invoice="INV-1",
                items=[{"item_row_name": "row1", "qty": 1}], target_table="T-2",
            )

    def test_throws_when_invoice_not_in_source_table(self):
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.return_value = self._src_table(invoice_name="INV-OTHER")
        with self.assertRaises(frappe.ValidationError):
            self.service.split_table(
                source_table="T-1", source_invoice="INV-1",
                items=[{"item_row_name": "row1", "qty": 1}], target_table="T-2",
            )

    def test_throws_when_target_not_empty(self):
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.return_value = self._src_table()
        self.mock_repo.get_table_for_update.return_value = self._tgt_table(status="Terisi")
        with self.assertRaises(TableAlreadyClaimedError):
            self.service.split_table(
                source_table="T-1", source_invoice="INV-1",
                items=[{"item_row_name": "row1", "qty": 1}], target_table="T-2",
            )

    def test_happy_path_appends_target_order_and_publishes(self):
        self.mock_repo.table_exists.return_value = True
        src = self._src_table()
        tgt = self._tgt_table()
        self.mock_repo.get_table.return_value = src
        self.mock_repo.get_table_for_update.return_value = tgt

        with patch("resto.services.table_service.InvoiceService") as MockSvc, \
             patch("resto.services.table_service.frappe.publish_realtime") as mock_pub:
            MockSvc.return_value.split_invoice.return_value = "INV-NEW"
            result = self.service.split_table(
                source_table="T-1", source_invoice="INV-1",
                items=[{"item_row_name": "row1", "qty": 1}], target_table="T-2",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["target_invoice"], "INV-NEW")
        tgt.append.assert_called_once_with("orders", {"invoice_name": "INV-NEW"})
        self.mock_repo.save_table.assert_called_once_with(tgt)
        # 2 publish event: target.table_order_added + source.table_meta_updated
        events = [c.args[0] for c in mock_pub.call_args_list]
        self.assertIn("table_order_added", events)
        self.assertIn("table_meta_updated", events)
