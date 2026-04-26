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
