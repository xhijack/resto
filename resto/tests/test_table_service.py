import frappe
import json
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.table_service import TableService


class TestTableService(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = TableService(repo=self.mock_repo)

    def _make_table_doc(self, status="Kosong", orders=None):
        doc = MagicMock()
        doc.name = "TBL-001"
        doc.status = status
        doc.orders = orders or []
        return doc

    # ------------------------------------------------------------------
    # Unit tests — update_table_status: reset ke Kosong
    # ------------------------------------------------------------------

    def test_update_status_kosong_resets_all_fields(self):
        """Status Kosong harus reset semua field"""
        doc = self._make_table_doc(status="Terisi")
        self.mock_repo.get_table.return_value = doc

        self.service.update_table_status("TBL-001", status="Kosong")

        self.assertEqual(doc.status, "Kosong")
        self.assertEqual(doc.taken_by, "")
        self.assertEqual(doc.pax, 0)
        self.assertEqual(doc.customer, "")
        self.assertEqual(doc.type_customer, "")
        self.assertEqual(doc.checked, 0)
        self.assertEqual(doc.orders, [])

    def test_update_status_saves_table(self):
        """Harus memanggil repo.save_table setelah update"""
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc

        self.service.update_table_status("TBL-001", status="Terisi")

        self.mock_repo.save_table.assert_called_once_with(doc)

    # ------------------------------------------------------------------
    # Unit tests — update_table_status: update field individual
    # ------------------------------------------------------------------

    def test_update_status_sets_taken_by(self):
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc
        self.service.update_table_status("TBL-001", taken_by="John")
        self.assertEqual(doc.taken_by, "John")

    def test_update_status_sets_pax_as_int(self):
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc
        self.service.update_table_status("TBL-001", pax="4")
        self.assertEqual(doc.pax, 4)

    def test_update_status_sets_customer(self):
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc
        self.service.update_table_status("TBL-001", customer="Budi")
        self.assertEqual(doc.customer, "Budi")

    def test_update_status_skips_none_fields(self):
        """Field yang None tidak boleh diubah"""
        doc = self._make_table_doc(status="Terisi")
        self.mock_repo.get_table.return_value = doc
        self.service.update_table_status("TBL-001", taken_by=None, pax=None)
        self.assertEqual(doc.status, "Terisi")

    # ------------------------------------------------------------------
    # Unit tests — update_table_status: orders parsing
    # ------------------------------------------------------------------

    def test_update_status_replaces_orders_with_payload(self):
        """REPLACE semantic: payload = state baru orders. Existing yang tidak
        ada di payload harus dihapus (kalau tidak, MoveItemModal tidak bisa
        clear source invoice → LinkExistsError)."""
        existing = MagicMock()
        existing.invoice_name = "INV-OLD"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table.return_value = doc

        self.service.update_table_status("TBL-001", orders=[{"invoice_name": "INV-NEW"}])

        # set("orders", new_orders) dipanggil dengan list HANYA INV-NEW
        # (INV-OLD tidak boleh ada — itulah inti replace semantic)
        doc.set.assert_called_once_with("orders", [{"invoice_name": "INV-NEW"}])

    def test_update_status_dedupes_duplicate_orders_in_payload(self):
        """Payload dengan invoice_name duplikat → hanya 1 yang masuk."""
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc

        self.service.update_table_status(
            "TBL-001",
            orders=[{"invoice_name": "INV-001"}, {"invoice_name": "INV-001"}],
        )

        doc.set.assert_called_once_with("orders", [{"invoice_name": "INV-001"}])

    def test_update_status_removes_existing_when_payload_subset(self):
        """Regression case: B010 punya 10 invoice, payload kirim 9 (tanpa
        salah satu). Yang tidak ada di payload HARUS hilang dari orders."""
        existing_a = MagicMock(); existing_a.invoice_name = "INV-A"
        existing_b = MagicMock(); existing_b.invoice_name = "INV-B"
        existing_c = MagicMock(); existing_c.invoice_name = "INV-C"
        doc = self._make_table_doc(orders=[existing_a, existing_b, existing_c])
        self.mock_repo.get_table.return_value = doc

        # kirim hanya A & C (B di-skip — simulasi user move semua item dari INV-B)
        self.service.update_table_status(
            "TBL-001",
            orders=[{"invoice_name": "INV-A"}, {"invoice_name": "INV-C"}],
        )

        doc.set.assert_called_once_with(
            "orders",
            [{"invoice_name": "INV-A"}, {"invoice_name": "INV-C"}],
        )

    def test_update_status_parses_json_string_orders(self):
        """orders berupa JSON string harus di-parse, lalu di-replace"""
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc
        orders_json = json.dumps([{"invoice_name": "INV-001"}])

        self.service.update_table_status("TBL-001", orders=orders_json)

        doc.set.assert_called_once_with("orders", [{"invoice_name": "INV-001"}])

    def test_update_status_returns_success_with_checked(self):
        """Harus return dict dengan success=True dan checked"""
        doc = self._make_table_doc()
        doc.checked = 1
        self.mock_repo.get_table.return_value = doc

        result = self.service.update_table_status("TBL-001")

        self.assertTrue(result["success"])
        self.assertEqual(result["checked"], 1)

    # ------------------------------------------------------------------
    # Unit tests — add_table_order
    # ------------------------------------------------------------------

    def test_add_table_order_throws_when_no_table_name(self):
        """Harus throw jika table_name kosong"""
        with self.assertRaises(frappe.ValidationError):
            self.service.add_table_order("", {"invoice_name": "INV-001"})

    def test_add_table_order_throws_when_no_invoice_name(self):
        """Harus throw jika invoice_name tidak ada di order"""
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc
        with self.assertRaises(frappe.ValidationError):
            self.service.add_table_order("TBL-001", {})

    def test_add_table_order_returns_false_if_duplicate(self):
        """Harus return success=False jika invoice sudah ada"""
        existing = MagicMock()
        existing.invoice_name = "INV-001"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table.return_value = doc

        result = self.service.add_table_order("TBL-001", {"invoice_name": "INV-001"})

        self.assertFalse(result["success"])

    def test_add_table_order_appends_and_saves(self):
        """Harus append order dan save"""
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc

        result = self.service.add_table_order("TBL-001", {"invoice_name": "INV-NEW"})

        doc.append.assert_called_once_with("orders", {"invoice_name": "INV-NEW"})
        self.mock_repo.save_table.assert_called_once_with(doc)
        self.assertTrue(result["success"])

    def test_add_table_order_changes_status_to_terisi(self):
        """Status harus berubah jadi Terisi jika sebelumnya Kosong"""
        doc = self._make_table_doc(status="Kosong")
        self.mock_repo.get_table.return_value = doc

        self.service.add_table_order("TBL-001", {"invoice_name": "INV-NEW"})

        self.assertEqual(doc.status, "Terisi")

    def test_add_table_order_parses_json_string(self):
        """order berupa JSON string harus di-parse"""
        doc = self._make_table_doc()
        self.mock_repo.get_table.return_value = doc
        order_json = json.dumps({"invoice_name": "INV-001"})

        result = self.service.add_table_order("TBL-001", order_json)

        self.assertTrue(result["success"])

    # ------------------------------------------------------------------
    # Unit tests — get_all_tables_with_details
    # ------------------------------------------------------------------

    def test_get_all_tables_returns_list(self):
        """Harus return list"""
        self.mock_repo.get_all_tables.return_value = []
        self.mock_repo.get_user_full_names.return_value = {}
        result = self.service.get_all_tables_with_details()
        self.assertIsInstance(result, list)

    def test_get_all_tables_maps_fields_correctly(self):
        """Harus map fields Table ke format response yang benar"""
        mock_order = MagicMock()
        mock_order.invoice_name = "INV-001"
        mock_doc = MagicMock()
        mock_doc.orders = [mock_order]

        table_row = frappe._dict({
            "name": "TBL-001", "table_name": "Meja 1", "status": "Terisi",
            "table_type": "Regular", "zone": "A", "customer": "Budi",
            "pax": 2, "type_customer": "Walk In", "floor": "1",
            "taken_by": "john@example.com", "checked": 0
        })
        self.mock_repo.get_all_tables.return_value = [table_row]
        self.mock_repo.get_table.return_value = mock_doc
        self.mock_repo.get_user_full_names.return_value = {"john@example.com": "John Doe"}

        result = self.service.get_all_tables_with_details()

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertEqual(item["id"], "TBL-001")
        self.assertEqual(item["name"], "Meja 1")
        self.assertEqual(item["status"], "Terisi")
        self.assertEqual(item["orders"], [{"invoice_name": "INV-001"}])
        self.assertEqual(item["takenBy"], "john@example.com")
        self.assertEqual(item["takenByName"], "John Doe")

    def test_get_all_tables_defaults_status_to_kosong(self):
        """Status None harus default ke 'Kosong'"""
        mock_doc = MagicMock()
        mock_doc.orders = []
        table_row = frappe._dict({
            "name": "TBL-001", "table_name": "Meja 1", "status": None,
            "table_type": None, "zone": None, "customer": None,
            "pax": None, "type_customer": None, "floor": None,
            "taken_by": None, "checked": None
        })
        self.mock_repo.get_all_tables.return_value = [table_row]
        self.mock_repo.get_table.return_value = mock_doc
        self.mock_repo.get_user_full_names.return_value = {}

        result = self.service.get_all_tables_with_details()

        self.assertEqual(result[0]["status"], "Kosong")
        self.assertEqual(result[0]["pax"], 0)
        self.assertEqual(result[0]["floor"], "1")
        self.assertIsNone(result[0]["takenByName"])

    def test_get_all_tables_taken_by_without_user_record_falls_back_to_email(self):
        """Kalau User record tidak ada, repo fallback ke email — service pass through"""
        mock_doc = MagicMock()
        mock_doc.orders = []
        table_row = frappe._dict({
            "name": "TBL-001", "table_name": "Meja 1", "status": "Has Taken",
            "table_type": None, "zone": None, "customer": None,
            "pax": None, "type_customer": None, "floor": None,
            "taken_by": "ghost@example.com", "checked": None
        })
        self.mock_repo.get_all_tables.return_value = [table_row]
        self.mock_repo.get_table.return_value = mock_doc
        # User tidak ada → repo return empty map
        self.mock_repo.get_user_full_names.return_value = {}

        result = self.service.get_all_tables_with_details()

        self.assertEqual(result[0]["takenBy"], "ghost@example.com")
        self.assertIsNone(result[0]["takenByName"])

    def test_get_all_tables_bulk_fetches_full_names_once(self):
        """Optimisasi: get_user_full_names dipanggil 1x dengan list semua taken_by, bukan N+1"""
        mock_doc = MagicMock()
        mock_doc.orders = []
        rows = [
            frappe._dict({"name": "T1", "table_name": "M1", "status": "Has Taken",
                          "table_type": None, "zone": None, "customer": None, "pax": 0,
                          "type_customer": None, "floor": "1", "taken_by": "a@x.com", "checked": 0}),
            frappe._dict({"name": "T2", "table_name": "M2", "status": "Has Taken",
                          "table_type": None, "zone": None, "customer": None, "pax": 0,
                          "type_customer": None, "floor": "1", "taken_by": "b@x.com", "checked": 0}),
            frappe._dict({"name": "T3", "table_name": "M3", "status": "Kosong",
                          "table_type": None, "zone": None, "customer": None, "pax": 0,
                          "type_customer": None, "floor": "1", "taken_by": None, "checked": 0}),
        ]
        self.mock_repo.get_all_tables.return_value = rows
        self.mock_repo.get_table.return_value = mock_doc
        self.mock_repo.get_user_full_names.return_value = {
            "a@x.com": "Alice", "b@x.com": "Bob"
        }

        result = self.service.get_all_tables_with_details()

        self.mock_repo.get_user_full_names.assert_called_once()
        called_arg = self.mock_repo.get_user_full_names.call_args[0][0]
        self.assertIn("a@x.com", called_arg)
        self.assertIn("b@x.com", called_arg)
        self.assertEqual(result[0]["takenByName"], "Alice")
        self.assertEqual(result[1]["takenByName"], "Bob")
        self.assertIsNone(result[2]["takenByName"])

    # ------------------------------------------------------------------
    # Integration tests
    # ------------------------------------------------------------------

    def _get_or_create_table(self, table_name):
        if frappe.db.exists("Table", table_name):
            t = frappe.get_doc("Table", table_name)
            t.orders = []
            t.status = "Kosong"
            t.save(ignore_permissions=True)
            return t
        return frappe.get_doc({
            "doctype": "Table", "table_name": table_name, "branch": self.branch
        }).insert(ignore_permissions=True)

    def test_update_table_status_integration(self):
        """Harus update table di database"""
        table = self._get_or_create_table("_Test SVC Update")
        real_service = TableService()
        real_service.update_table_status(table.name, status="Terisi", taken_by=frappe.session.user, pax=3)

        reloaded = frappe.get_doc("Table", table.name)
        self.assertEqual(reloaded.status, "Terisi")
        self.assertEqual(reloaded.taken_by, frappe.session.user)
        self.assertEqual(reloaded.pax, 3)

    def test_add_table_order_integration(self):
        """Harus tambahkan order ke table di database"""
        invoice = self._create_test_pos_invoice()
        table = self._get_or_create_table("_Test SVC AddOrder")
        real_service = TableService()
        result = real_service.add_table_order(table.name, {"invoice_name": invoice.name})

        self.assertTrue(result["success"])
        reloaded = frappe.get_doc("Table", table.name)
        invoice_names = [o.invoice_name for o in reloaded.orders]
        self.assertIn(invoice.name, invoice_names)

    # ------------------------------------------------------------------
    # Unit tests — merge_table (scenario 1: print check + table move)
    # ------------------------------------------------------------------

    def test_merge_table_calls_move_items_for_each_target_order(self):
        """move_items_from_invoice harus dipanggil untuk setiap order di target table"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 0
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        mock_invoice_service = MagicMock()

        order1 = MagicMock()
        order1.invoice_name = "INV-TGT-001"
        order2 = MagicMock()
        order2.invoice_name = "INV-TGT-002"
        target_doc = MagicMock()
        target_doc.get.return_value = [order1, order2]

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_table.return_value = target_doc

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table("INV-SRC", source_table="TBL-SRC", target_table=["TBL-TGT"])

        self.assertEqual(mock_invoice_service.move_items_from_invoice.call_count, 2)

    def test_merge_table_rejects_submitted_invoice(self):
        """Harus throw jika source invoice sudah disubmit (docstatus=1)"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 1
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo):
            with self.assertRaises(frappe.ValidationError):
                self.service.merge_table("INV-SRC", source_table="TBL-SRC", target_table=["TBL-TGT"])

    def test_merge_table_skips_missing_target_table(self):
        """Target table yang tidak ada di DB harus di-skip, tidak error"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 0
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        mock_invoice_service = MagicMock()

        def table_exists_side_effect(name):
            return name != "TBL-MISSING"

        self.mock_repo.table_exists.side_effect = table_exists_side_effect
        self.mock_repo.invoice_exists.return_value = True

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            result = self.service.merge_table(
                "INV-SRC",
                source_table="TBL-SRC",
                target_table=["TBL-MISSING"]
            )

        mock_invoice_service.move_items_from_invoice.assert_not_called()
        self.assertTrue(result["ok"])

    def test_merge_table_skips_self_as_target(self):
        """Source table yang muncul di target_table harus di-skip"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 0
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        mock_invoice_service = MagicMock()
        target_doc = MagicMock()
        target_doc.get.return_value = []

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_table.return_value = target_doc

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            result = self.service.merge_table(
                "INV-SRC",
                source_table="TBL-SRC",
                target_table=["TBL-SRC"]
            )

        mock_invoice_service.move_items_from_invoice.assert_not_called()
        self.assertTrue(result["ok"])

    # ------------------------------------------------------------------
    # Extreme variation tests — merge_table edge cases
    # ------------------------------------------------------------------

    def test_merge_table_with_empty_target_table_list_throws(self):
        """target_table=[] → frappe.throw('target_table wajib diisi'). Sejajar dengan
        validasi source_table — kalau kedua sisi kosong tidak ada yang harus di-merge."""
        with self.assertRaises(frappe.ValidationError):
            self.service.merge_table("INV-SRC", source_table="TBL-SRC", target_table=[])

    def test_merge_table_calls_delete_merge_invoice_at_end(self):
        """delete_merge_invoice harus dipanggil sekali dengan pos_invoice source"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 0
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        mock_invoice_service = MagicMock()
        target_doc = MagicMock()
        order1 = MagicMock()
        order1.invoice_name = "INV-TGT-001"
        target_doc.get.return_value = [order1]

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_table.return_value = target_doc

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table("INV-SRC", source_table="TBL-SRC", target_table=["TBL-TGT"])

        mock_invoice_service.delete_merge_invoice.assert_called_once_with("INV-SRC")

    def test_merge_table_target_with_no_orders_skips_move_items(self):
        """Target table dengan 0 orders → move_items tidak dipanggil untuk table itu"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 0
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        mock_invoice_service = MagicMock()
        target_doc = MagicMock()
        target_doc.get.return_value = []  # no orders in target

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_table.return_value = target_doc

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            result = self.service.merge_table("INV-SRC", source_table="TBL-SRC", target_table=["TBL-TGT"])

        mock_invoice_service.move_items_from_invoice.assert_not_called()
        self.assertTrue(result["ok"])

    def test_merge_table_multiple_targets_move_items_called_per_order(self):
        """2 target tables, masing-masing punya 1 order → move_items dipanggil 2x"""
        mock_inv_repo = MagicMock()
        mock_source_invoice = MagicMock()
        mock_source_invoice.docstatus = 0
        mock_inv_repo.get_invoice.return_value = mock_source_invoice

        mock_invoice_service = MagicMock()

        order_t1 = MagicMock()
        order_t1.invoice_name = "INV-TGT-A"
        doc_t1 = MagicMock()
        doc_t1.get.return_value = [order_t1]

        order_t2 = MagicMock()
        order_t2.invoice_name = "INV-TGT-B"
        doc_t2 = MagicMock()
        doc_t2.get.return_value = [order_t2]

        call_count = [0]
        def get_table_side(name):
            call_count[0] += 1
            return doc_t1 if name == "TBL-A" else doc_t2

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_table.side_effect = get_table_side

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table("INV-SRC", source_table="TBL-SRC", target_table=["TBL-A", "TBL-B"])

        self.assertEqual(mock_invoice_service.move_items_from_invoice.call_count, 2)
