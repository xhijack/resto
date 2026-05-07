import frappe
from unittest.mock import patch, MagicMock, call
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.table_service import TableService
from resto.services.invoice_service import InvoiceService


class TestMoveItemsFromInvoice(RestoPOSTestBase):
    """Test InvoiceService.move_items_from_invoice"""

    def setUp(self):
        super().setUp()
        self.service = InvoiceService()

    # ------------------------------------------------------------------
    # Unit tests (mock)
    # ------------------------------------------------------------------

    def test_copies_items_to_target_invoice(self):
        """Semua item dari source harus disalin ke target"""
        mock_item = MagicMock()
        mock_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty"]
        mock_item.get.side_effect = lambda f: {"item_code": "ITEM-001", "qty": 2}.get(f)

        source = MagicMock()
        source.get.return_value = [mock_item]
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        service.move_items_from_invoice("SRC", "TGT")

        target.append.assert_called_once()
        self.assertEqual(target.append.call_args[0][0], "items")

    def test_marks_source_as_merged(self):
        """Source invoice harus ditandai is_merged=1 dan merge_invoice diisi.
        Implementasi pakai frappe.db.set_value (bukan doc.save) untuk menghindari
        ValidationError dari calculate_taxes_and_totals di tax rows source."""
        source = MagicMock()
        source.get.return_value = []
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        with patch("frappe.db.set_value") as mock_set_value, \
             patch("frappe.db.sql"), \
             patch("frappe.db.commit"):
            service.move_items_from_invoice("SRC", "TGT")

        mock_set_value.assert_called_once_with(
            "POS Invoice", "SRC", {"is_merged": 1, "merge_invoice": "TGT"}
        )

    def test_saves_target_only_not_source(self):
        """Hanya target.save() yang dipanggil — source di-update via set_value
        supaya tidak trigger validate() di source (kena ValidationError tax)."""
        source = MagicMock()
        source.get.return_value = []
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        with patch("frappe.db.set_value"), \
             patch("frappe.db.sql"), \
             patch("frappe.db.commit"):
            service.move_items_from_invoice("SRC", "TGT")

        target.save.assert_called_once()
        source.save.assert_not_called()

    def test_repoints_table_order_rows_pointing_to_source(self):
        """Regression: chained merge — kalau source invoice sebelumnya sudah jadi
        kept-invoice untuk table-table lain (mis. A1, A10 → 770), Table Order row
        mereka harus ikut di-repoint ke target saat 770 di-merge ke 771.
        Tanpa ini, delete_merge_invoice(771) bakal throw LinkExistsError karena
        Table Order milik A1/A10 masih punya invoice_name=770 sehingga 770 tidak
        bisa di-delete (POS Invoice link via Table Order child table)."""
        source = MagicMock()
        source.get.return_value = []
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "INV-770" else target
        service = InvoiceService(repo=mock_repo)

        sql_calls = []

        def capture_sql(query, values=None, *a, **kw):
            sql_calls.append((query, values))

        with patch("frappe.db.sql", side_effect=capture_sql), \
             patch("frappe.db.set_value"), \
             patch("frappe.db.commit"):
            service.move_items_from_invoice("INV-770", "INV-771")

        # Harus ada UPDATE ke tabTable Order yang me-repoint INV-770 → INV-771
        update_calls = [c for c in sql_calls if "tabTable Order" in c[0] and "UPDATE" in c[0]]
        self.assertEqual(len(update_calls), 1, "Harus ada 1 UPDATE pada Table Order")
        _, args = update_calls[0]
        self.assertEqual(args, ("INV-771", "INV-770"))

    def test_repoint_runs_after_marking_source_merged(self):
        """Repoint Table Order HARUS terjadi setelah set_value is_merged=1, supaya
        kalau ada interleaving query, source sudah konsisten ditandai merged."""
        source = MagicMock()
        source.get.return_value = []
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        order_log = []

        def log_set_value(*a, **kw):
            order_log.append("set_value")

        def log_sql(*a, **kw):
            order_log.append("sql_update")

        with patch("frappe.db.set_value", side_effect=log_set_value), \
             patch("frappe.db.sql", side_effect=log_sql), \
             patch("frappe.db.commit"):
            service.move_items_from_invoice("SRC", "TGT")

        self.assertEqual(order_log[:2], ["set_value", "sql_update"])

    def test_skips_system_fields_when_copying(self):
        """Field name, parent, idx tidak boleh disalin"""
        mock_item = MagicMock()
        mock_item.meta.get_fieldnames_with_value.return_value = [
            "name", "parent", "parenttype", "parentfield", "idx", "item_code"
        ]
        mock_item.get.side_effect = lambda f: f  # return field name as value

        source = MagicMock()
        source.get.return_value = [mock_item]
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        service.move_items_from_invoice("SRC", "TGT")

        copied = target.append.call_args[0][1]
        self.assertNotIn("name", copied)
        self.assertNotIn("parent", copied)
        self.assertNotIn("idx", copied)
        self.assertIn("item_code", copied)


class TestMergeTable(RestoPOSTestBase):
    """Test TableService.merge_table"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = TableService(repo=self.mock_repo)

    # ------------------------------------------------------------------
    # Validasi input
    # ------------------------------------------------------------------

    def test_throws_when_source_table_empty(self):
        """Harus throw jika source_table kosong"""
        with self.assertRaises(frappe.ValidationError):
            self.service.merge_table("INV-001", source_table="", target_table=["TBL-002"])

    def test_throws_when_target_table_empty(self):
        """Harus throw jika target_table kosong"""
        with self.assertRaises(frappe.ValidationError):
            self.service.merge_table("INV-001", source_table="TBL-001", target_table=[])

    def test_throws_when_source_table_not_found(self):
        """Harus throw jika source_table tidak ada di DB"""
        self.mock_repo.table_exists.return_value = False
        with self.assertRaises(frappe.ValidationError):
            self.service.merge_table("INV-001", source_table="TBL-NOTFOUND", target_table=["TBL-002"])

    def test_throws_when_pos_invoice_not_found(self):
        """Harus throw jika pos_invoice tidak ada di DB"""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = False
        with self.assertRaises(frappe.ValidationError):
            self.service.merge_table("INV-NOTFOUND", source_table="TBL-001", target_table=["TBL-002"])

    def test_mutable_default_not_shared(self):
        """target_table default None harus aman — tidak shared antar calls"""
        # Pastikan signature tidak pakai [] sebagai default
        import inspect
        sig = inspect.signature(self.service.merge_table)
        default = sig.parameters["target_table"].default
        self.assertIsNone(default)

    # ------------------------------------------------------------------
    # Business logic
    # ------------------------------------------------------------------

    def test_skips_target_same_as_source(self):
        """Target table yang sama dengan source harus dilewati"""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True

        mock_target_table = MagicMock()
        mock_target_table.get.return_value = []
        self.mock_repo.get_table.return_value = mock_target_table

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService"):
            self.service.merge_table("INV-001", source_table="TBL-001", target_table=["TBL-001"])

        # get_table tidak dipanggil untuk proses merge (dilewati)
        self.mock_repo.get_table.assert_not_called()

    def test_skips_nonexistent_target_table(self):
        """Target table yang tidak ada harus dilewati, bukan throw"""
        self.mock_repo.table_exists.side_effect = lambda name: name != "TBL-NOTFOUND"
        self.mock_repo.invoice_exists.return_value = True

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService"):
            result = self.service.merge_table(
                "INV-001", source_table="TBL-001", target_table=["TBL-NOTFOUND"]
            )

        self.assertTrue(result["ok"])

    def test_returns_ok_true_on_success(self):
        """Harus return ok=True setelah merge"""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        mock_target_table = MagicMock()
        mock_target_table.get.return_value = []
        self.mock_repo.get_table.return_value = mock_target_table

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService"):
            result = self.service.merge_table(
                "INV-001", source_table="TBL-001", target_table=["TBL-002"]
            )

        self.assertTrue(result["ok"])

    def test_throws_when_invoice_already_submitted(self):
        """Harus throw jika pos_invoice sudah submitted (docstatus=1)"""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_invoice.return_value = MagicMock(docstatus=1)

        with self.assertRaises(frappe.ValidationError):
            self.service.merge_table("INV-001", source_table="TBL-001", target_table=["TBL-002"])

    # ------------------------------------------------------------------
    # Regression: avoid LinkExistsError on delete_merge_invoice
    # ------------------------------------------------------------------

    def test_repoints_target_table_orders_to_kept_invoice(self):
        """Setiap row Table Order di absorbed table harus di-repoint ke pos_invoice
        (kept invoice) sebelum invoice lama dihapus, biar tidak LinkExistsError +
        biar clear_table_merged() saat payment ketemu absorbed table itu."""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True

        order_a = MagicMock()
        order_a.invoice_name = "INV-A1-OLD"
        target_doc = MagicMock()
        target_doc.get.return_value = [order_a]
        self.mock_repo.get_table.return_value = target_doc

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)
        mock_invoice_service = MagicMock()

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table(
                "INV-KEPT", source_table="TBL-KEPT", target_table=["TBL-ABSORB"]
            )

        # move_items dipanggil dengan invoice lama
        mock_invoice_service.move_items_from_invoice.assert_called_once_with(
            "INV-A1-OLD", "INV-KEPT"
        )
        # invoice_name di row dipindah ke pos_invoice (INV-KEPT)
        self.assertEqual(order_a.invoice_name, "INV-KEPT")
        # absorbed table doc disimpan supaya perubahan persist
        self.mock_repo.save_table.assert_called_once_with(target_doc)

    def test_save_table_skipped_when_target_has_no_orders(self):
        """Kalau absorbed table tidak punya orders, save_table tidak perlu dipanggil
        (hindari write/timestamp churn yang tidak perlu)."""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True

        target_doc = MagicMock()
        target_doc.get.return_value = []
        self.mock_repo.get_table.return_value = target_doc

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)
        mock_invoice_service = MagicMock()

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table(
                "INV-KEPT", source_table="TBL-KEPT", target_table=["TBL-ABSORB"]
            )

        self.mock_repo.save_table.assert_not_called()

    def test_repoints_orders_for_multiple_targets(self):
        """2 absorbed tables, masing-masing punya 1 order — semua di-repoint ke pos_invoice
        + save_table dipanggil 2x (1x per target)."""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True

        order_a = MagicMock(); order_a.invoice_name = "INV-OLD-A"
        doc_a = MagicMock(); doc_a.get.return_value = [order_a]

        order_b = MagicMock(); order_b.invoice_name = "INV-OLD-B"
        doc_b = MagicMock(); doc_b.get.return_value = [order_b]

        self.mock_repo.get_table.side_effect = lambda name: doc_a if name == "TBL-A" else doc_b

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)
        mock_invoice_service = MagicMock()

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table(
                "INV-KEPT", source_table="TBL-KEPT", target_table=["TBL-A", "TBL-B"]
            )

        self.assertEqual(order_a.invoice_name, "INV-KEPT")
        self.assertEqual(order_b.invoice_name, "INV-KEPT")
        self.assertEqual(self.mock_repo.save_table.call_count, 2)

    def test_repoint_happens_before_delete_merge_invoice(self):
        """Repoint + save_table HARUS terjadi sebelum delete_merge_invoice,
        kalau urutannya kebalik delete tetap akan kena LinkExistsError."""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True

        order_a = MagicMock(); order_a.invoice_name = "INV-OLD"
        target_doc = MagicMock(); target_doc.get.return_value = [order_a]
        self.mock_repo.get_table.return_value = target_doc

        call_log = []
        self.mock_repo.save_table.side_effect = lambda doc: call_log.append("save_table")

        mock_inv_repo = MagicMock()
        mock_inv_repo.get_invoice.return_value = MagicMock(docstatus=0)
        mock_invoice_service = MagicMock()
        mock_invoice_service.delete_merge_invoice.side_effect = lambda inv: call_log.append("delete")

        with patch("resto.services.table_service.InvoiceRepository", return_value=mock_inv_repo), \
             patch("resto.services.table_service.InvoiceService", return_value=mock_invoice_service):
            self.service.merge_table(
                "INV-KEPT", source_table="TBL-KEPT", target_table=["TBL-A"]
            )

        self.assertEqual(call_log, ["save_table", "delete"])
