import frappe
import json
from unittest.mock import patch, MagicMock, call
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
        self.mock_repo.get_table_for_update.return_value = doc
        with self.assertRaises(frappe.ValidationError):
            self.service.add_table_order("TBL-001", {})

    def test_add_table_order_returns_false_if_duplicate(self):
        """Harus return success=False jika invoice sudah ada"""
        existing = MagicMock()
        existing.invoice_name = "INV-001"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        result = self.service.add_table_order("TBL-001", {"invoice_name": "INV-001"})

        self.assertFalse(result["success"])

    def test_add_table_order_appends_and_saves(self):
        """Harus append order dan save"""
        doc = self._make_table_doc()
        self.mock_repo.get_table_for_update.return_value = doc

        result = self.service.add_table_order("TBL-001", {"invoice_name": "INV-NEW"})

        doc.append.assert_called_once_with("orders", {"invoice_name": "INV-NEW"})
        self.mock_repo.save_table.assert_called_once_with(doc)
        self.assertTrue(result["success"])

    def test_add_table_order_changes_status_to_terisi(self):
        """Status harus berubah jadi Terisi jika sebelumnya Kosong"""
        doc = self._make_table_doc(status="Kosong")
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.add_table_order("TBL-001", {"invoice_name": "INV-NEW"})

        self.assertEqual(doc.status, "Terisi")

    def test_add_table_order_parses_json_string(self):
        """order berupa JSON string harus di-parse"""
        doc = self._make_table_doc()
        self.mock_repo.get_table_for_update.return_value = doc
        order_json = json.dumps({"invoice_name": "INV-001"})

        result = self.service.add_table_order("TBL-001", order_json)

        self.assertTrue(result["success"])

    def test_add_table_order_uses_locking_read(self):
        """Race condition guard: harus pakai get_table_for_update (locking read,
        SELECT ... FOR UPDATE) — bukan get_table biasa. Tanpa locking read, di
        REPEATABLE READ MySQL akan dapat snapshot transaksi (stale) → check_if_latest
        TimestampMismatchError saat 2 thread sequential modify meja yang sama."""
        doc = self._make_table_doc()
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.add_table_order("TBL-001", {"invoice_name": "INV-NEW"})

        self.mock_repo.get_table_for_update.assert_called_once_with("TBL-001")
        # get_table biasa (non-locking) TIDAK boleh dipanggil di flow ini
        self.mock_repo.get_table.assert_not_called()

    # ------------------------------------------------------------------
    # Unit tests — remove_table_order (atomic removal)
    # ------------------------------------------------------------------

    def test_remove_table_order_throws_when_no_table_name(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.remove_table_order("", "INV-001")

    def test_remove_table_order_throws_when_no_invoice_name(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.remove_table_order("TBL-001", "")

    def test_remove_table_order_uses_locking_read(self):
        """Harus pakai get_table_for_update (locking read) — sama pattern dengan add."""
        existing = MagicMock(); existing.invoice_name = "INV-001"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.remove_table_order("TBL-001", "INV-001")

        self.mock_repo.get_table_for_update.assert_called_once_with("TBL-001")
        self.mock_repo.get_table.assert_not_called()

    def test_remove_table_order_removes_matching_invoice(self):
        existing_a = MagicMock(); existing_a.invoice_name = "INV-A"
        existing_b = MagicMock(); existing_b.invoice_name = "INV-B"
        doc = self._make_table_doc(orders=[existing_a, existing_b])
        self.mock_repo.get_table_for_update.return_value = doc

        result = self.service.remove_table_order("TBL-001", "INV-A")

        self.assertTrue(result["success"])
        doc.set.assert_called_once_with(
            "orders", [{"invoice_name": "INV-B"}]
        )
        self.mock_repo.save_table.assert_called_once_with(doc)

    def test_remove_table_order_no_op_when_invoice_not_present(self):
        """Invoice tidak ada di table → return success=False, no save (idempoten)."""
        existing = MagicMock(); existing.invoice_name = "INV-A"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        with patch("resto.services.table_service.frappe.db.commit"):
            result = self.service.remove_table_order("TBL-001", "INV-NOT-THERE")

        self.assertFalse(result["success"])
        self.mock_repo.save_table.assert_not_called()

    # ------------------------------------------------------------------
    # Unit tests — update_table_meta (no orders touch)
    # ------------------------------------------------------------------

    def test_update_table_meta_does_not_touch_orders(self):
        """Critical invariant: update_table_meta TIDAK boleh menyentuh
        doc.orders — itu otoritasnya add_table_order/remove_table_order."""
        existing = MagicMock(); existing.invoice_name = "INV-X"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.update_table_meta("TBL-001", status="Terisi", taken_by="John", pax=2)

        # set() tidak boleh dipanggil dengan key 'orders'
        for c in doc.set.call_args_list:
            self.assertNotEqual(c.args[0] if c.args else None, "orders")
        # Original orders array tidak disentuh (still same reference)
        self.assertEqual(doc.orders, [existing])

    def test_update_table_meta_kosong_resets_meta_but_keeps_orders_field(self):
        """Status Kosong reset meta fields (taken_by, pax, customer, dll) tapi
        TIDAK mengkosongkan doc.orders — itu tugas remove_table_order."""
        existing = MagicMock(); existing.invoice_name = "INV-X"
        doc = self._make_table_doc(status="Terisi", orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.update_table_meta("TBL-001", status="Kosong")

        self.assertEqual(doc.status, "Kosong")
        self.assertEqual(doc.taken_by, "")
        self.assertEqual(doc.pax, 0)
        # orders tidak di-clear
        self.assertEqual(doc.orders, [existing])

    def test_update_table_meta_skips_none_fields(self):
        doc = self._make_table_doc(status="Terisi")
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.update_table_meta("TBL-001", taken_by=None, pax=None)

        self.assertEqual(doc.status, "Terisi")

    def test_update_table_meta_saves(self):
        doc = self._make_table_doc()
        self.mock_repo.get_table_for_update.return_value = doc
        self.service.update_table_meta("TBL-001", status="Terisi")
        self.mock_repo.save_table.assert_called_once_with(doc)

    def test_update_table_meta_uses_locking_read(self):
        """Harus pakai get_table_for_update (locking read SELECT ... FOR UPDATE)
        — tanpa ini, gap antara add_table_order dan update_table_meta jadi race
        window (TimestampMismatchError check_if_latest Frappe)."""
        doc = self._make_table_doc()
        self.mock_repo.get_table_for_update.return_value = doc

        self.service.update_table_meta("TBL-001", status="Terisi")

        self.mock_repo.get_table_for_update.assert_called_once_with("TBL-001")
        self.mock_repo.get_table.assert_not_called()

    def test_update_table_meta_throws_when_no_name(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.update_table_meta("")

    # ------------------------------------------------------------------
    # Unit tests — Realtime publish (Paket 2 Stage A)
    # ------------------------------------------------------------------
    # Backend broadcast event ke socket.io subscriber setiap mutation table
    # berhasil commit. Mobile listen via socket.io (Stage B) → instant
    # cross-device update. after_commit=True wajib supaya event tidak terbang
    # sebelum DB commit (rollback → ghost event).

    def test_add_table_order_publishes_realtime_event(self):
        doc = self._make_table_doc(status="Kosong")
        self.mock_repo.get_table_for_update.return_value = doc

        with patch("resto.services.table_service.frappe.publish_realtime") as mock_pub:
            self.service.add_table_order("TBL-001", {"invoice_name": "INV-NEW"})

        mock_pub.assert_called_once()
        args, kwargs = mock_pub.call_args
        self.assertEqual(args[0], "table_order_added")
        payload = args[1]
        self.assertEqual(payload["table_name"], "TBL-001")
        self.assertEqual(payload["invoice_name"], "INV-NEW")
        self.assertEqual(payload["status"], "Terisi")
        self.assertTrue(kwargs.get("after_commit"))
        self.assertEqual(kwargs.get("room"), "website")

    def test_remove_table_order_publishes_realtime_event(self):
        existing = MagicMock(); existing.invoice_name = "INV-001"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        with patch("resto.services.table_service.frappe.publish_realtime") as mock_pub:
            self.service.remove_table_order("TBL-001", "INV-001")

        mock_pub.assert_called_once()
        args, kwargs = mock_pub.call_args
        self.assertEqual(args[0], "table_order_removed")
        self.assertEqual(args[1], {"table_name": "TBL-001", "invoice_name": "INV-001"})
        self.assertTrue(kwargs.get("after_commit"))
        self.assertEqual(kwargs.get("room"), "website")

    def test_update_table_meta_publishes_realtime_event(self):
        doc = self._make_table_doc(status="Kosong")
        self.mock_repo.get_table_for_update.return_value = doc

        with patch("resto.services.table_service.frappe.publish_realtime") as mock_pub:
            self.service.update_table_meta(
                "TBL-001", status="Terisi", taken_by="kasir@x.com",
                pax=3, customer="Budi", type_customer="Personal",
            )

        mock_pub.assert_called_once()
        args, kwargs = mock_pub.call_args
        self.assertEqual(args[0], "table_meta_updated")
        payload = args[1]
        self.assertEqual(payload["table_name"], "TBL-001")
        self.assertEqual(payload["status"], "Terisi")
        self.assertEqual(payload["pax"], 3)
        self.assertEqual(payload["customer"], "Budi")
        self.assertEqual(payload["type_customer"], "Personal")
        self.assertEqual(payload["taken_by"], "kasir@x.com")
        self.assertTrue(kwargs.get("after_commit"))
        self.assertEqual(kwargs.get("room"), "website")

    def test_update_table_status_publishes_realtime_event(self):
        """update_table_status (legacy hot-path endpoint dari useHandleSelectTable
        dkk) harus fire `table_meta_updated` supaya mobile lain instant reload."""
        doc = self._make_table_doc(status="Kosong")
        doc.pax = 3
        doc.customer = "Budi"
        doc.type_customer = "Personal"
        doc.taken_by = "kasir@x.com"
        self.mock_repo.get_table.return_value = doc

        with patch("resto.services.table_service.frappe.publish_realtime") as mock_pub:
            self.service.update_table_status(
                "TBL-001", status="Terisi", taken_by="kasir@x.com",
                pax=3, customer="Budi", type_customer="Personal",
            )

        mock_pub.assert_called_once()
        args, kwargs = mock_pub.call_args
        self.assertEqual(args[0], "table_meta_updated")
        payload = args[1]
        self.assertEqual(payload["table_name"], "TBL-001")
        self.assertEqual(payload["status"], "Terisi")
        self.assertEqual(payload["pax"], 3)
        self.assertEqual(payload["customer"], "Budi")
        self.assertEqual(payload["type_customer"], "Personal")
        self.assertEqual(payload["taken_by"], "kasir@x.com")
        self.assertTrue(kwargs.get("after_commit"))
        self.assertEqual(kwargs.get("room"), "website")

    def test_remove_table_order_no_op_does_not_publish(self):
        """Kalau invoice tidak ada di table, no event terbang (tidak ada perubahan)."""
        existing = MagicMock(); existing.invoice_name = "INV-001"
        doc = self._make_table_doc(orders=[existing])
        self.mock_repo.get_table_for_update.return_value = doc

        with patch("resto.services.table_service.frappe.publish_realtime") as mock_pub:
            result = self.service.remove_table_order("TBL-001", "INV-NOT-EXISTING")

        self.assertFalse(result["success"])
        mock_pub.assert_not_called()

    # ------------------------------------------------------------------
    # Unit tests — update_table_status: atomic claim (expected_status)
    # ------------------------------------------------------------------

    def test_update_status_expected_status_match_proceeds(self):
        """Kalau expected_status sama dengan current status di DB, update jalan."""
        from resto.services.table_service import TableAlreadyClaimedError
        doc = self._make_table_doc(status="Kosong")
        self.mock_repo.get_table_for_update.return_value = doc

        result = self.service.update_table_status(
            "TBL-001", status="Terisi", taken_by="kasir@a.com",
            pax=2, customer="Andi", type_customer="Personal",
            expected_status="Kosong",
        )

        self.assertTrue(result["success"])
        self.mock_repo.get_table_for_update.assert_called_once_with("TBL-001")
        self.mock_repo.get_table.assert_not_called()
        self.mock_repo.save_table.assert_called_once()
        self.assertEqual(doc.status, "Terisi")
        self.assertEqual(doc.taken_by, "kasir@a.com")

    def test_update_status_expected_status_mismatch_raises(self):
        """Kalau expected_status beda dengan current di DB (race-loss),
        raise TableAlreadyClaimedError dan TIDAK save."""
        from resto.services.table_service import TableAlreadyClaimedError
        doc = self._make_table_doc(status="Terisi")
        doc.taken_by = "kasir@a.com"
        self.mock_repo.get_table_for_update.return_value = doc

        with self.assertRaises(TableAlreadyClaimedError):
            self.service.update_table_status(
                "TBL-001", status="Terisi", taken_by="kasir@b.com",
                pax=2, customer="Budi", type_customer="Personal",
                expected_status="Kosong",
            )

        self.mock_repo.save_table.assert_not_called()

    def test_update_status_no_expected_uses_non_locking_read(self):
        """Tanpa expected_status (legacy caller), pakai get_table biasa
        — backward compatible, tidak ada lock overhead."""
        doc = self._make_table_doc(status="Terisi")
        self.mock_repo.get_table.return_value = doc

        self.service.update_table_status("TBL-001", status="Terisi", pax=4)

        self.mock_repo.get_table.assert_called_once_with("TBL-001")
        self.mock_repo.get_table_for_update.assert_not_called()

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

    # ------------------------------------------------------------------
    # Unit tests — get_merged_group_size & move_merged_group
    # ------------------------------------------------------------------

    def test_get_merged_group_size_throws_when_source_missing(self):
        """Source table tidak ada → throw"""
        self.mock_repo.table_exists.return_value = False
        with self.assertRaises(frappe.ValidationError):
            self.service.get_merged_group_size("MISSING")

    def test_get_merged_group_size_returns_1_when_no_orders(self):
        """Tidak ada orders → bukan merged → return 1"""
        self.mock_repo.table_exists.return_value = True
        doc = self._make_table_doc(orders=[])
        self.mock_repo.get_table.return_value = doc

        with patch("resto.services.table_service.frappe.get_all", return_value=[]):
            self.assertEqual(self.service.get_merged_group_size("TBL-001"), 1)

    def test_get_merged_group_size_returns_member_count_when_merged(self):
        """2 meja share 1 invoice → member count = 2"""
        self.mock_repo.table_exists.return_value = True
        order = MagicMock(); order.invoice_name = "INV-X"
        doc = self._make_table_doc(orders=[order])
        self.mock_repo.get_table.return_value = doc

        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001", "TBL-002"],
        ):
            self.assertEqual(self.service.get_merged_group_size("TBL-001"), 2)

    def test_get_merged_group_size_includes_source_in_members(self):
        """Walaupun frappe.get_all hanya return parent yang lain,
        source_table tetap masuk hitungan via union."""
        self.mock_repo.table_exists.return_value = True
        order = MagicMock(); order.invoice_name = "INV-X"
        doc = self._make_table_doc(orders=[order])
        self.mock_repo.get_table.return_value = doc

        # frappe.get_all hanya return dirinya sendiri (kasus belum ada sibling)
        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001"],
        ):
            self.assertEqual(self.service.get_merged_group_size("TBL-001"), 1)

    def test_move_merged_group_rejects_empty_target(self):
        """target_tables=[] → throw"""
        with self.assertRaises(frappe.ValidationError):
            self.service.move_merged_group("TBL-001", [])

    def test_move_merged_group_rejects_count_mismatch(self):
        """Source merged 2 meja → target 1 meja → throw dengan pesan jelas"""
        self.mock_repo.table_exists.return_value = True
        order = MagicMock(); order.invoice_name = "INV-X"
        source_doc = self._make_table_doc(orders=[order])
        self.mock_repo.get_table.return_value = source_doc

        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001", "TBL-002"],
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                self.service.move_merged_group("TBL-001", ["TBL-NEW"])
            self.assertIn("2", str(ctx.exception))
            self.assertIn("1", str(ctx.exception))

    def test_move_merged_group_rejects_target_in_source_set(self):
        """Target overlap dengan source members → throw"""
        self.mock_repo.table_exists.return_value = True
        order = MagicMock(); order.invoice_name = "INV-X"
        source_doc = self._make_table_doc(orders=[order])
        self.mock_repo.get_table.return_value = source_doc

        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001", "TBL-002"],
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                self.service.move_merged_group("TBL-001", ["TBL-002", "TBL-NEW"])
            self.assertIn("TBL-002", str(ctx.exception))

    def test_move_merged_group_rejects_non_kosong_target(self):
        """Salah satu target status != Kosong → throw"""
        order = MagicMock(); order.invoice_name = "INV-X"
        source_doc = self._make_table_doc(orders=[order])
        source_doc.status = "Terisi"

        occupied_target = MagicMock()
        occupied_target.status = "Terisi"

        empty_target = self._make_table_doc(status="Kosong")
        empty_target.name = "TBL-EMPTY"

        def get_table_side(name):
            if name == "TBL-001":
                return source_doc
            if name == "TBL-002":
                # second source member
                return self._make_table_doc(status="Terisi")
            if name == "TBL-OCC":
                return occupied_target
            return empty_target

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = get_table_side

        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001", "TBL-002"],
        ):
            with self.assertRaises(frappe.ValidationError) as ctx:
                self.service.move_merged_group("TBL-001", ["TBL-OCC", "TBL-EMPTY"])
            self.assertIn("TBL-OCC", str(ctx.exception))

    def test_move_merged_group_single_source_to_single_target_succeeds(self):
        """Source bukan merged (1 meja) → target 1 meja → sukses, transfer state"""
        # source memiliki 1 order tapi tidak ada sibling parent → group size = 1
        order = MagicMock(); order.invoice_name = "INV-X"
        source_doc = self._make_table_doc(status="Terisi", orders=[order])
        source_doc.taken_by = "kasir@x.com"
        source_doc.pax = 3
        source_doc.customer = "Budi"
        source_doc.type_customer = "Walk In"
        source_doc.checked = 1

        target_doc = self._make_table_doc(status="Kosong", orders=[])
        target_doc.name = "TBL-NEW"

        def get_table_side(name):
            return source_doc if name == "TBL-001" else target_doc

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = get_table_side

        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001"],  # only itself
        ):
            result = self.service.move_merged_group("TBL-001", ["TBL-NEW"])

        self.assertTrue(result["ok"])
        self.assertEqual(result["moved_count"], 1)
        # state copied
        self.assertEqual(target_doc.status, "Terisi")
        self.assertEqual(target_doc.taken_by, "kasir@x.com")
        self.assertEqual(target_doc.pax, 3)
        # source cleared
        self.assertEqual(source_doc.status, "Kosong")
        self.assertEqual(source_doc.taken_by, "")
        self.assertEqual(source_doc.pax, 0)
        # save called for both per pair
        self.assertEqual(self.mock_repo.save_table.call_count, 2)

    def test_move_merged_group_two_source_to_two_target_succeeds(self):
        """Source merged 2 meja → target 2 meja → sukses, transfer 1:1"""
        order = MagicMock(); order.invoice_name = "INV-X"
        src1 = self._make_table_doc(status="Terisi", orders=[order])
        src2 = self._make_table_doc(status="Terisi", orders=[order])
        src2.name = "TBL-002"

        tgt1 = self._make_table_doc(status="Kosong"); tgt1.name = "TBL-NEW1"
        tgt2 = self._make_table_doc(status="Kosong"); tgt2.name = "TBL-NEW2"

        table_map = {
            "TBL-001": src1, "TBL-002": src2,
            "TBL-NEW1": tgt1, "TBL-NEW2": tgt2,
        }
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = lambda n: table_map[n]

        with patch(
            "resto.services.table_service.frappe.get_all",
            return_value=["TBL-001", "TBL-002"],
        ):
            result = self.service.move_merged_group("TBL-001", ["TBL-NEW1", "TBL-NEW2"])

        self.assertTrue(result["ok"])
        self.assertEqual(result["moved_count"], 2)
        # both sources cleared
        self.assertEqual(src1.status, "Kosong")
        self.assertEqual(src2.status, "Kosong")
        # both targets occupied
        self.assertEqual(tgt1.status, "Terisi")
        self.assertEqual(tgt2.status, "Terisi")
        # 4 saves total (2 pair × 2)
        self.assertEqual(self.mock_repo.save_table.call_count, 4)

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

    # ------------------------------------------------------------------
    # Unit tests — move_table (single move, atomic)
    # ------------------------------------------------------------------

    def _stub_print_service(self):
        """Patch PrintingService di table_service supaya enqueue print
        tidak ke-trigger di test (move_table & move_merged_group sekarang
        panggil _print_move_slips di akhir)."""
        return patch(
            "resto.services.printing_service.PrintingService",
            return_value=MagicMock(),
        )

    def test_move_table_throws_when_missing_args(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.move_table("", "TBL-NEW")
        with self.assertRaises(frappe.ValidationError):
            self.service.move_table("TBL-001", "")

    def test_move_table_throws_when_source_equals_target(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.move_table("TBL-001", "TBL-001")

    def test_move_table_throws_when_source_not_exists(self):
        self.mock_repo.table_exists.side_effect = lambda n: n != "TBL-001"
        with self.assertRaises(frappe.ValidationError):
            self.service.move_table("TBL-001", "TBL-NEW")

    def test_move_table_throws_when_target_not_kosong(self):
        from resto.services.table_service import TableAlreadyClaimedError
        order = MagicMock(); order.invoice_name = "INV-X"
        src = self._make_table_doc(status="Terisi", orders=[order])
        tgt = self._make_table_doc(status="Terisi", orders=[])
        tgt.name = "TBL-NEW"

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = lambda n: src if n == "TBL-001" else tgt

        with self._stub_print_service(), self.assertRaises(TableAlreadyClaimedError):
            self.service.move_table("TBL-001", "TBL-NEW")

    def test_move_table_happy_path_swaps_state(self):
        order = MagicMock(); order.invoice_name = "INV-X"
        src = self._make_table_doc(status="Terisi", orders=[order])
        src.taken_by = "kasir@x.com"
        src.pax = 4
        src.customer = "Pak Budi"
        src.type_customer = "Walk In"
        src.checked = 1

        tgt = self._make_table_doc(status="Kosong", orders=[])
        tgt.name = "TBL-NEW"

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = lambda n: src if n == "TBL-001" else tgt

        with self._stub_print_service(), \
             patch("resto.services.table_service.frappe.publish_realtime"):
            result = self.service.move_table("TBL-001", "TBL-NEW")

        self.assertTrue(result["ok"])
        self.assertEqual(result["moved_count"], 1)
        # state ter-copy ke target
        self.assertEqual(tgt.status, "Terisi")
        self.assertEqual(tgt.taken_by, "kasir@x.com")
        self.assertEqual(tgt.pax, 4)
        self.assertEqual(tgt.customer, "Pak Budi")
        # source ter-clear
        self.assertEqual(src.status, "Kosong")
        self.assertEqual(src.taken_by, "")
        self.assertEqual(src.pax, 0)
        self.assertEqual(src.customer, "")
        # save sekali untuk masing-masing
        self.assertEqual(self.mock_repo.save_table.call_count, 2)

    def test_move_table_calls_print_enqueue_with_pair_payload(self):
        """move_table harus panggil enqueue_move_table_slip 1x dengan
        payload (source, target, branch dari POS Invoice, invoices, customer, pax)."""
        order = MagicMock(); order.invoice_name = "INV-X"
        src = self._make_table_doc(status="Terisi", orders=[order])
        src.customer = "Pak Budi"
        src.pax = 3
        tgt = self._make_table_doc(status="Kosong", orders=[])
        tgt.name = "TBL-NEW"

        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = lambda n: src if n == "TBL-001" else tgt

        mock_ps = MagicMock()
        with patch("resto.services.printing_service.PrintingService", return_value=mock_ps), \
             patch("resto.services.table_service.frappe.db.get_value", return_value="BR-001"), \
             patch("resto.services.table_service.frappe.publish_realtime"):
            self.service.move_table("TBL-001", "TBL-NEW")

        mock_ps.enqueue_move_table_slip.assert_called_once()
        kwargs = mock_ps.enqueue_move_table_slip.call_args.kwargs
        self.assertEqual(kwargs["source_table"], "TBL-001")
        self.assertEqual(kwargs["target_table"], "TBL-NEW")
        self.assertEqual(kwargs["branch"], "BR-001")
        self.assertEqual(kwargs["invoices"], ["INV-X"])
        self.assertEqual(kwargs["customer"], "Pak Budi")
        self.assertEqual(kwargs["pax"], 3)

    def test_move_merged_group_calls_print_enqueue_per_pair(self):
        order = MagicMock(); order.invoice_name = "INV-X"
        src1 = self._make_table_doc(status="Terisi", orders=[order])
        src2 = self._make_table_doc(status="Terisi", orders=[order])
        src2.name = "TBL-002"
        tgt1 = self._make_table_doc(status="Kosong"); tgt1.name = "TBL-NEW1"
        tgt2 = self._make_table_doc(status="Kosong"); tgt2.name = "TBL-NEW2"
        table_map = {
            "TBL-001": src1, "TBL-002": src2,
            "TBL-NEW1": tgt1, "TBL-NEW2": tgt2,
        }
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.get_table.side_effect = lambda n: table_map[n]

        mock_ps = MagicMock()
        with patch("resto.services.printing_service.PrintingService", return_value=mock_ps), \
             patch("resto.services.table_service.frappe.db.get_value", return_value="BR-001"), \
             patch(
                "resto.services.table_service.frappe.get_all",
                return_value=["TBL-001", "TBL-002"],
             ):
            self.service.move_merged_group("TBL-001", ["TBL-NEW1", "TBL-NEW2"])

        self.assertEqual(mock_ps.enqueue_move_table_slip.call_count, 2)
