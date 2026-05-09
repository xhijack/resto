import sys
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


class TestPrintCheckNow(RestoPOSTestBase):
    """Test PrintingService.print_check_now"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = PrintingService(repo=self.mock_repo)

    def test_throws_when_no_printer_found(self):
        """Harus throw jika tidak ada printer bill di branch"""
        self.mock_repo.get_bill_printer.return_value = None
        with self.assertRaises(frappe.ValidationError):
            self.service.print_check_now("INV-001", branch="BR-001")

    def test_returns_ok_with_job_id(self):
        """Harus return ok=True dan job_id"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"

        with patch("resto.services.printing_service._enqueue_check_worker",
                   return_value="JOB-CHK"):
            result = self.service.print_check_now("INV-001", branch="BR-001")

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], "JOB-CHK")

    def test_enqueues_correct_printer(self):
        """Harus enqueue ke printer Bill (sama dengan print_bill_now)"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"

        with patch("resto.services.printing_service._enqueue_check_worker",
                   return_value="J") as mock_enqueue:
            self.service.print_check_now("INV-001", branch="BR-001")

        mock_enqueue.assert_called_once_with("INV-001", "PRT-BILL")

    def test_uses_check_worker_not_bill_worker(self):
        """Harus pakai _enqueue_check_worker, bukan _enqueue_bill_worker"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"

        with patch("resto.services.printing_service._enqueue_bill_worker") as mock_bill:
            with patch("resto.services.printing_service._enqueue_check_worker",
                       return_value="J"):
                self.service.print_check_now("INV-001", branch="BR-001")

        mock_bill.assert_not_called()

    def test_updates_table_when_table_name_given(self):
        """Harus update table status ke 'Print Bill' jika table_name diberikan"""
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"
        mock_table_svc = MagicMock()

        with patch("resto.services.printing_service._enqueue_check_worker", return_value="J"):
            self.service.print_check_now(
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

        with patch("resto.services.printing_service._enqueue_check_worker", return_value="J"):
            self.service.print_check_now("INV-001", branch="BR-001",
                                         table_service=mock_table_svc)

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

    def test_passes_printer_name_to_default_void_builder(self):
        """build_void_item_receipt harus dipanggil dengan printer_name di default void print"""
        void_item = {"name": "ITEM-001", "item_code": "FOOD-001", "item_name": "Nasi",
                     "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_void_items_to_print.return_value = [void_item]
        self.mock_repo.get_void_printer.return_value = "PRT-VOID"
        self.mock_repo.get_invoice_branch.return_value = "BR-001"

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw", return_value="J"):
                with patch.object(self.service, "_print_void_to_other_stations"):
                    self.service.print_void_item("INV-001")

        mock_build.assert_called_with("INV-001", [void_item], "PRT-VOID")

    def test_passes_printer_name_to_other_station_builder(self):
        """_print_void_to_other_stations harus pass printer_name per station"""
        void_item = {"name": "ITEM-001", "item_code": "FOOD-001", "item_name": "Nasi",
                     "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_branch_menu_printers_for_item.return_value = ["PRT-KITCHEN-A"]

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw", return_value="J"):
                self.service._print_void_to_other_stations("INV-001", [void_item], "BR-001")

        mock_build.assert_called_with("INV-001", [void_item], "PRT-KITCHEN-A")


class TestListPrintersWithStatus(RestoPOSTestBase):
    """Test PrintingService.list_printers_with_status"""

    def setUp(self):
        super().setUp()
        self.service = PrintingService(repo=MagicMock())

    @staticmethod
    def _stations(*specs):
        return [
            {"name": n, "printer_name": p, "description": d}
            for (n, p, d) in specs
        ]

    def test_happy_path_all_online(self):
        """Semua station online → is_online=True dan state='idle'"""
        stations = self._stations(
            ("KS-001", "Kitchen-Epson", "Kitchen 1"),
            ("KS-002", "Bar-XP58", "Bar"),
        )
        with patch.dict(sys.modules, {"cups": MagicMock()}):
            with patch("frappe.get_all", return_value=stations):
                with patch(
                    "resto.services.printing_service.get_printer_state",
                    return_value={"state": "idle", "is_online": True, "state_reasons": []},
                ):
                    result = self.service.list_printers_with_status()

        self.assertEqual(len(result), 2)
        self.assertTrue(all(r["is_online"] for r in result))
        self.assertEqual(result[0]["label"], "Kitchen 1")

    def test_mixed_online_and_stopped(self):
        """1 idle + 1 stopped → mixed status"""
        stations = self._stations(
            ("KS-001", "Kitchen-Epson", "Kitchen"),
            ("KS-002", "Bar-XP58", "Bar"),
        )

        def fake_state(printer, conn=None):
            if printer == "Kitchen-Epson":
                return {"state": "idle", "is_online": True, "state_reasons": []}
            return {"state": "stopped", "is_online": False, "state_reasons": ["offline-report"]}

        with patch.dict(sys.modules, {"cups": MagicMock()}):
            with patch("frappe.get_all", return_value=stations):
                with patch(
                    "resto.services.printing_service.get_printer_state",
                    side_effect=fake_state,
                ):
                    result = self.service.list_printers_with_status()

        by_name = {r["name"]: r for r in result}
        self.assertTrue(by_name["KS-001"]["is_online"])
        self.assertFalse(by_name["KS-002"]["is_online"])
        self.assertEqual(by_name["KS-002"]["state"], "stopped")

    def test_printer_not_registered_in_cups(self):
        """Printer Kitchen Station tidak ada di CUPS → state='not_found', is_online=False"""
        stations = self._stations(("KS-009", "Lama-Printer", "Old"))

        with patch.dict(sys.modules, {"cups": MagicMock()}):
            with patch("frappe.get_all", return_value=stations):
                with patch(
                    "resto.services.printing_service.get_printer_state",
                    side_effect=frappe.ValidationError("not found"),
                ):
                    result = self.service.list_printers_with_status()

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0]["is_online"])
        self.assertEqual(result[0]["state"], "not_found")

    def test_cups_daemon_unavailable(self):
        """Connection raise → semua entry state='cups_unavailable'"""
        stations = self._stations(
            ("KS-001", "P1", "Bar"),
            ("KS-002", "P2", "Kitchen"),
        )
        fake_cups = MagicMock()
        fake_cups.Connection.side_effect = Exception("CUPS daemon down")

        with patch.dict(sys.modules, {"cups": fake_cups}):
            with patch("frappe.get_all", return_value=stations):
                result = self.service.list_printers_with_status()

        self.assertEqual(len(result), 2)
        self.assertTrue(all(r["state"] == "cups_unavailable" for r in result))
        self.assertTrue(all(not r["is_online"] for r in result))

    def test_skips_station_with_empty_printer_name(self):
        """Station tanpa printer_name tidak crash; entry tetap dikembalikan as not_found"""
        stations = [{"name": "KS-X", "printer_name": "", "description": "Tanpa Printer"}]

        with patch.dict(sys.modules, {"cups": MagicMock()}):
            with patch("frappe.get_all", return_value=stations):
                with patch(
                    "resto.services.printing_service.get_printer_state",
                ) as mock_state:
                    result = self.service.list_printers_with_status()
                    mock_state.assert_not_called()

        self.assertEqual(result[0]["state"], "not_found")
        self.assertFalse(result[0]["is_online"])
