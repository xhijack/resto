import frappe
from unittest.mock import MagicMock, patch
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.printing_service import PrintingService


class TestPrintBillNow(RestoPOSTestBase):
    """Test PrintingService.print_bill_now"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = PrintingService(repo=self.mock_repo)

    def test_throws_when_no_printer_found(self):
        """Harus throw jika tidak ada printer bill di branch"""
        self.mock_repo.get_bill_printer.return_value = None
        with self.assertRaises(frappe.ValidationError):
            self.service.print_bill_now("INV-001", branch="BR-001")

    def test_returns_ok_with_job_id(self):
        """Harus return ok=True dan job_id"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"

        with patch("resto.services.printing_service._enqueue_bill_worker",
                   return_value="JOB-123") as mock_enqueue:
            result = self.service.print_bill_now("INV-001", branch="BR-001")

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], "JOB-123")

    def test_enqueues_correct_printer(self):
        """Harus enqueue ke printer yang sesuai branch"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"

        with patch("resto.services.printing_service._enqueue_bill_worker",
                   return_value="JOB-001") as mock_enqueue:
            self.service.print_bill_now("INV-001", branch="BR-001")

        mock_enqueue.assert_called_once_with("INV-001", "PRT-BILL")

    def test_updates_table_when_table_name_given(self):
        """Harus update table status ke 'Print Bill' jika table_name diberikan"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"
        mock_table_svc = MagicMock()

        with patch("resto.services.printing_service._enqueue_bill_worker", return_value="J"):
            self.service.print_bill_now(
                "INV-001", branch="BR-001",
                table_name="TBL-001", table_service=mock_table_svc
            )

        mock_table_svc.update_table_status.assert_called_once()
        call_kwargs = mock_table_svc.update_table_status.call_args[1]
        self.assertEqual(call_kwargs["status"], "Print Bill")

    def test_skips_table_update_when_no_table(self):
        """Tidak update table jika table_name tidak diberikan"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"
        mock_table_svc = MagicMock()

        with patch("resto.services.printing_service._enqueue_bill_worker", return_value="J"):
            self.service.print_bill_now("INV-001", branch="BR-001", table_service=mock_table_svc)

        mock_table_svc.update_table_status.assert_not_called()


class TestPrintReceiptNow(RestoPOSTestBase):
    """Test PrintingService.print_receipt_now"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = PrintingService(repo=self.mock_repo)

    def test_throws_when_no_receipt_printer(self):
        """Harus throw jika tidak ada printer receipt di branch"""
        self.mock_repo.get_receipt_printer.return_value = None
        with self.assertRaises(frappe.ValidationError):
            self.service.print_receipt_now("INV-001", branch="BR-001")

    def test_returns_ok_with_job_id(self):
        """Harus return ok=True dan job_id"""
        self.mock_repo.get_receipt_printer.return_value = "PRT-RCPT"

        with patch("resto.services.printing_service._enqueue_receipt_worker",
                   return_value="JOB-456") as mock_enqueue:
            result = self.service.print_receipt_now("INV-001", branch="BR-001")

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], "JOB-456")

    def test_enqueues_correct_printer(self):
        """Harus enqueue ke printer receipt yang sesuai branch"""
        self.mock_repo.get_receipt_printer.return_value = "PRT-RCPT"

        with patch("resto.services.printing_service._enqueue_receipt_worker",
                   return_value="J") as mock_enqueue:
            self.service.print_receipt_now("INV-001", branch="BR-002")

        mock_enqueue.assert_called_once_with("INV-001", "PRT-RCPT")


class TestPrintVoidItem(RestoPOSTestBase):
    """Test PrintingService.print_void_item"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = PrintingService(repo=self.mock_repo)

    def test_returns_ok_when_no_void_items(self):
        """Harus return ok=True dengan pesan jika tidak ada void item"""
        self.mock_repo.get_void_items_to_print.return_value = []
        result = self.service.print_void_item("INV-001")
        self.assertTrue(result["ok"])
        self.assertIn("Tidak ada", result["message"])

    def test_throws_when_no_void_printer(self):
        """Harus throw jika tidak ada void printer di branch"""
        void_item = {"name": "ITEM-001", "item_code": "FOOD-001", "item_name": "Nasi",
                     "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_void_items_to_print.return_value = [void_item]
        self.mock_repo.get_void_printer.return_value = None
        self.mock_repo.get_invoice_branch.return_value = "BR-001"

        with self.assertRaises(frappe.ValidationError):
            self.service.print_void_item("INV-001")

    def test_marks_items_as_void_printed(self):
        """Item void yang dicetak harus ditandai is_void_printed=1"""
        void_item = {"name": "ITEM-001", "item_code": "FOOD-001", "item_name": "Nasi",
                     "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_void_items_to_print.return_value = [void_item]
        self.mock_repo.get_void_printer.return_value = "PRT-VOID"
        self.mock_repo.get_invoice_branch.return_value = "BR-001"

        with patch("resto.services.printing_service.build_void_item_receipt", return_value=b"RAW"):
            with patch("resto.services.printing_service.cups_print_raw", return_value="JOB-1"):
                with patch.object(self.service, "_print_void_to_other_stations"):
                    self.service.print_void_item("INV-001")

        self.mock_repo.mark_void_printed.assert_called_once_with("ITEM-001")

    def test_returns_items_printed_count(self):
        """Harus return jumlah item yang dicetak"""
        items = [
            {"name": "ITEM-001", "item_code": "FOOD-001", "item_name": "Nasi",
             "qty": 1, "add_ons": "", "quick_notes": ""},
            {"name": "ITEM-002", "item_code": "FOOD-002", "item_name": "Ayam",
             "qty": 2, "add_ons": "", "quick_notes": ""},
        ]
        self.mock_repo.get_void_items_to_print.return_value = items
        self.mock_repo.get_void_printer.return_value = "PRT-VOID"
        self.mock_repo.get_invoice_branch.return_value = "BR-001"

        with patch("resto.services.printing_service.build_void_item_receipt", return_value=b"RAW"):
            with patch("resto.services.printing_service.cups_print_raw", return_value="JOB-1"):
                with patch.object(self.service, "_print_void_to_other_stations"):
                    result = self.service.print_void_item("INV-001")

        self.assertEqual(result["items_printed"], 2)
