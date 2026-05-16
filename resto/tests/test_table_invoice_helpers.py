import frappe
from unittest.mock import MagicMock, call, patch
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.table_service import TableService
from resto.services.invoice_service import InvoiceService
from resto.repositories.kitchen_repository import KitchenRepository
from resto.services.kitchen_service import KitchenService
from resto.services.printing_service import PrintingService


# -----------------------------------------------------------------------
# TableService.clear_table
# -----------------------------------------------------------------------

class TestClearTable(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = TableService(repo=self.mock_repo)

    def test_resets_all_table_fields(self):
        """clear_table harus reset orders, customer, taken_by, status, type_customer"""
        mock_table = MagicMock()
        self.mock_repo.get_table.return_value = mock_table

        self.service.clear_table("TBL-001")

        self.assertEqual(mock_table.orders, [])
        self.assertEqual(mock_table.customer, None)
        self.assertEqual(mock_table.taken_by, None)
        self.assertEqual(mock_table.status, "Kosong")
        self.assertEqual(mock_table.type_customer, None)
        self.mock_repo.save_table.assert_called_once_with(mock_table)

    def test_clears_correct_table(self):
        """Harus ambil table dengan nama yang benar"""
        self.mock_repo.get_table.return_value = MagicMock()
        self.service.clear_table("TBL-XYZ")
        self.mock_repo.get_table.assert_called_once_with("TBL-XYZ")


# -----------------------------------------------------------------------
# TableService.clear_table_merged
# -----------------------------------------------------------------------

class TestClearTableMerged(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = TableService(repo=self.mock_repo)

    def test_removes_invoice_from_each_table_and_clears_meta_when_empty(self):
        """Single-invoice / merge flow: remove invoice dari setiap table,
        kalau orders sisa kosong -> clear meta (status=Kosong dst)."""
        self.mock_repo.get_tables_for_invoice.return_value = ["TBL-001", "TBL-002"]

        # Setelah remove_table_order, get_table return doc dengan orders=[]
        empty_doc = MagicMock()
        empty_doc.orders = []
        self.mock_repo.get_table.return_value = empty_doc

        with patch.object(self.service, "remove_table_order") as mock_remove:
            self.service.clear_table_merged("INV-001")

        # remove_table_order dipanggil per table
        mock_remove.assert_has_calls([
            call("TBL-001", "INV-001"),
            call("TBL-002", "INV-001"),
        ])
        self.assertEqual(mock_remove.call_count, 2)
        # Meta cleared & save_table dipanggil (2x, satu per table)
        self.assertEqual(empty_doc.status, "Kosong")
        self.assertEqual(empty_doc.customer, None)
        self.assertEqual(empty_doc.taken_by, None)
        self.assertEqual(empty_doc.type_customer, None)
        self.assertEqual(self.mock_repo.save_table.call_count, 2)

    def test_keeps_table_meta_when_orders_remain_after_removal(self):
        """KEY TEST untuk split bill: kalau setelah remove invoice masih ada
        order lain di table, JANGAN wipe meta — bill sisa tidak boleh hilang."""
        self.mock_repo.get_tables_for_invoice.return_value = ["TBL-001"]

        # Setelah remove INV-A, table masih punya INV-B & INV-C (split bill)
        leftover_doc = MagicMock()
        leftover_doc.orders = [
            MagicMock(invoice_name="INV-B"),
            MagicMock(invoice_name="INV-C"),
        ]
        # Capture initial meta supaya bisa assert tidak ke-overwrite
        leftover_doc.status = "Terisi"
        leftover_doc.customer = "Customer-A"
        leftover_doc.taken_by = "kasir@x.com"
        leftover_doc.type_customer = "Dine In"
        self.mock_repo.get_table.return_value = leftover_doc

        with patch.object(self.service, "remove_table_order") as mock_remove:
            self.service.clear_table_merged("INV-A")

        mock_remove.assert_called_once_with("TBL-001", "INV-A")
        # Meta TIDAK ke-overwrite
        self.assertEqual(leftover_doc.status, "Terisi")
        self.assertEqual(leftover_doc.customer, "Customer-A")
        self.assertEqual(leftover_doc.taken_by, "kasir@x.com")
        self.assertEqual(leftover_doc.type_customer, "Dine In")
        # save_table tidak dipanggil dari clear_table_merged (remove sudah save sendiri)
        self.mock_repo.save_table.assert_not_called()

    def test_skips_empty_table_names(self):
        """Harus skip jika list table kosong"""
        self.mock_repo.get_tables_for_invoice.return_value = []
        with patch.object(self.service, "remove_table_order") as mock_remove:
            self.service.clear_table_merged("INV-001")
        self.mock_repo.get_table.assert_not_called()
        mock_remove.assert_not_called()


# -----------------------------------------------------------------------
# InvoiceService.delete_merge_invoice
# -----------------------------------------------------------------------

class TestDeleteMergeInvoice(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = InvoiceService(repo=self.mock_repo)

    def test_deletes_all_merged_invoices(self):
        """Harus hapus semua invoice yang merge_invoice == pos_invoice"""
        inv1, inv2 = MagicMock(), MagicMock()
        self.mock_repo.get_merged_invoices.return_value = [inv1, inv2]

        self.service.delete_merge_invoice("INV-001")

        inv1.delete.assert_called_once()
        inv2.delete.assert_called_once()

    def test_does_nothing_when_no_merged_invoices(self):
        """Harus aman jika tidak ada invoice yang di-merge"""
        self.mock_repo.get_merged_invoices.return_value = []
        self.service.delete_merge_invoice("INV-001")  # tidak throw


# -----------------------------------------------------------------------
# KitchenRepository.get_branch_menu_by_resto_menu
# -----------------------------------------------------------------------

class TestGetBranchMenuByRestoMenu(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_returns_empty_when_no_items(self):
        """Harus return [] jika POS Invoice tidak punya items dengan resto_menu"""
        self.mock_repo.get_pos_invoice_resto_menus.return_value = []
        result = self.service.get_branch_menu_by_resto_menu("INV-001")
        self.assertEqual(result, [])

    def test_skips_items_without_resto_menu(self):
        """Item tanpa resto_menu harus dilewati"""
        item = MagicMock()
        item.get.return_value = None
        self.mock_repo.get_pos_invoice_resto_menus.return_value = [item]
        result = self.service.get_branch_menu_by_resto_menu("INV-001")
        self.assertEqual(result, [])

    def test_maps_kitchen_printers_correctly(self):
        """Harus return kitchen_printers dari Branch Menu printers"""
        self.mock_repo.get_pos_invoice_resto_menus.return_value = [
            {"resto_menu": "MENU-001"}
        ]

        printer = MagicMock()
        printer.printer_name = "PRT-KS"
        printer.kitchen_station = "STA-A"

        bm = MagicMock()
        bm.branch = "BR-001"
        bm.printers = [printer]

        self.mock_repo.get_branch_menus_for_resto_menu.return_value = [bm]

        result = self.service.get_branch_menu_by_resto_menu("INV-001")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kitchen_printers"][0]["printer_name"], "PRT-KS")


# -----------------------------------------------------------------------
# PrintingService.enqueue_checker_after_kitchen
# -----------------------------------------------------------------------

class TestEnqueueCheckerAfterKitchen(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = PrintingService(repo=self.mock_repo)

    def test_returns_none_when_no_checker_printer(self):
        """Harus return None (bukan crash) jika tidak ada printer checker di branch"""
        self.mock_repo.get_checker_printer.return_value = None
        result = self.service.enqueue_checker_after_kitchen("INV-001", "BR-001")
        self.assertIsNone(result)

    def test_returns_job_id(self):
        """Harus return job_id dari enqueue worker"""
        self.mock_repo.get_checker_printer.return_value = "PRT-CHECK"

        with patch("resto.services.printing_service._enqueue_checker_worker",
                   return_value="JOB-999") as mock_enqueue:
            result = self.service.enqueue_checker_after_kitchen("INV-001", "BR-001")

        self.assertEqual(result, "JOB-999")

    def test_returns_none_on_error(self):
        """Harus return None jika terjadi error, tidak crash"""
        self.mock_repo.get_checker_printer.return_value = "PRT-CHECK"

        with patch("resto.services.printing_service._enqueue_checker_worker",
                   side_effect=Exception("printer offline")):
            result = self.service.enqueue_checker_after_kitchen("INV-001", "BR-001")

        self.assertIsNone(result)
