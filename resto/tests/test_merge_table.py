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
        """Source invoice harus ditandai is_merged=1 dan merge_invoice diisi"""
        source = MagicMock()
        source.get.return_value = []
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        service.move_items_from_invoice("SRC", "TGT")

        self.assertEqual(source.is_merged, 1)
        self.assertEqual(source.merge_invoice, "TGT")

    def test_saves_both_source_and_target(self):
        """Harus save source dan target invoice"""
        source = MagicMock()
        source.get.return_value = []
        target = MagicMock()

        mock_repo = MagicMock()
        mock_repo.get_invoice.side_effect = lambda name: source if name == "SRC" else target
        service = InvoiceService(repo=mock_repo)

        service.move_items_from_invoice("SRC", "TGT")

        source.save.assert_called_once()
        target.save.assert_called_once()

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
        self.mock_repo.get_invoice.return_value = MagicMock(docstatus=0)

        mock_target_table = MagicMock()
        mock_target_table.get.return_value = []
        self.mock_repo.get_table.return_value = mock_target_table

        self.service.merge_table("INV-001", source_table="TBL-001", target_table=["TBL-001"])

        # get_table tidak dipanggil untuk proses merge (dilewati)
        self.mock_repo.get_table.assert_not_called()

    def test_skips_nonexistent_target_table(self):
        """Target table yang tidak ada harus dilewati, bukan throw"""
        self.mock_repo.table_exists.side_effect = lambda name: name != "TBL-NOTFOUND"
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_invoice.return_value = MagicMock(docstatus=0)

        result = self.service.merge_table(
            "INV-001", source_table="TBL-001", target_table=["TBL-NOTFOUND"]
        )

        self.assertTrue(result["ok"])

    def test_returns_ok_true_on_success(self):
        """Harus return ok=True setelah merge"""
        self.mock_repo.table_exists.return_value = True
        self.mock_repo.invoice_exists.return_value = True
        self.mock_repo.get_invoice.return_value = MagicMock(docstatus=0)
        mock_target_table = MagicMock()
        mock_target_table.get.return_value = []
        self.mock_repo.get_table.return_value = mock_target_table

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
