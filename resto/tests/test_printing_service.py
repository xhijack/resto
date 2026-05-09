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


class TestMergedTablesStatusUpdate(RestoPOSTestBase):
    """Item 3: print_check_now & print_bill_now harus update status SEMUA meja
    yang ter-link ke invoice (kasus merged tables)."""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = PrintingService(repo=self.mock_repo)
        self.mock_repo.get_bill_printer.return_value = "PRT-BILL"

    def _build_table_service_with_related(self, related):
        ts = MagicMock()
        ts.repo.get_tables_for_invoice.return_value = related
        return ts

    def test_print_check_updates_all_merged_tables(self):
        related = ["TBL-001", "TBL-002", "TBL-003"]
        ts = self._build_table_service_with_related(related)

        with patch("resto.services.printing_service._enqueue_check_worker",
                   return_value="J"):
            self.service.print_check_now(
                "INV-MERGE", branch="BR-001",
                table_name="TBL-001", table_service=ts,
            )

        self.assertEqual(ts.update_table_status.call_count, 3)
        called_names = [c.kwargs["name"] for c in ts.update_table_status.call_args_list]
        self.assertEqual(set(called_names), set(related))
        for c in ts.update_table_status.call_args_list:
            self.assertEqual(c.kwargs["status"], "Print Bill")

    def test_print_bill_updates_all_merged_tables(self):
        related = ["TBL-A", "TBL-B"]
        ts = self._build_table_service_with_related(related)

        with patch("resto.services.printing_service._enqueue_bill_worker",
                   return_value="J"):
            self.service.print_bill_now(
                "INV-MERGE", branch="BR-001",
                table_name="TBL-A", table_service=ts,
            )

        self.assertEqual(ts.update_table_status.call_count, 2)
        called_names = [c.kwargs["name"] for c in ts.update_table_status.call_args_list]
        self.assertEqual(set(called_names), set(related))
        for c in ts.update_table_status.call_args_list:
            self.assertEqual(c.kwargs["status"], "Print Bill")

    def test_includes_table_name_when_not_in_related(self):
        """Fallback safety: kalau get_tables_for_invoice return [] tapi
        table_name diberikan, tetap update meja itu."""
        ts = self._build_table_service_with_related([])

        with patch("resto.services.printing_service._enqueue_check_worker",
                   return_value="J"):
            self.service.print_check_now(
                "INV-001", branch="BR-001",
                table_name="TBL-X", table_service=ts,
            )

        ts.update_table_status.assert_called_once()
        self.assertEqual(ts.update_table_status.call_args.kwargs["name"], "TBL-X")


class TestTestPrintEndpoint(RestoPOSTestBase):
    """Item 1b: PrintingService.test_print()"""

    def setUp(self):
        super().setUp()
        self.service = PrintingService(repo=MagicMock())

    def test_throws_when_no_printer_name(self):
        with self.assertRaises(frappe.ValidationError):
            self.service.test_print("")

    def test_calls_cups_print_raw_with_payload(self):
        with patch("resto.services.printing_service.build_test_print_payload",
                   return_value=b"PAYLOAD") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value=42) as mock_print:
                result = self.service.test_print("BAR-PRINTER")

        mock_build.assert_called_once_with("BAR-PRINTER")
        mock_print.assert_called_once_with(b"PAYLOAD", "BAR-PRINTER")
        self.assertTrue(result["ok"])
        self.assertEqual(result["job_id"], 42)
        self.assertEqual(result["printer"], "BAR-PRINTER")


class TestPrintTemplates(RestoPOSTestBase):
    """Item 4 & 5: ESC/POS payload mengandung label header yang benar."""

    def test_check_print_includes_check_header(self):
        with patch.dict(sys.modules, {"cups": MagicMock()}):
            from resto.printing import build_escpos_bill
        with patch("resto.printing._collect_pos_invoice", return_value={
            "name": "INV-001",
            "items": [],
            "payments": [],
            "taxes": [],
            "company": "TEST",
            "order_type": "Dine In",
            "customer_name": "X",
            "customer": "X",
            "total": 0, "discount_amount": 0, "total_taxes_and_charges": 0,
            "grand_total": 0, "paid_amount": 0, "change_amount": 0,
            "queue": None, "branch": "BR-001",
        }):
            with patch("resto.printing.frappe.get_all", return_value=[]):
                with patch("resto.printing.get_table_names_from_pos_invoice",
                           return_value="T-1"):
                    with patch("resto.printing.get_total_pax_from_pos_invoice",
                               return_value=1):
                        with patch("resto.printing.get_current_cashier_name",
                                   return_value="Kasir"):
                            raw = build_escpos_bill(
                                "INV-001",
                                include_header_address=False,
                                print_label="CHECK",
                            )
        self.assertIn(b"CHECK", raw)

    def test_void_print_includes_kitchen_label(self):
        with patch.dict(sys.modules, {"cups": MagicMock()}):
            from resto.printing import build_void_item_receipt
        with patch("resto.printing._collect_pos_invoice", return_value={
            "name": "INV-001", "posting_date": "2026-05-09",
            "posting_time": "12:00:00",
        }), \
            patch("resto.printing.get_table_names_from_pos_invoice",
                  return_value="T-1"), \
            patch("resto.printing.get_total_pax_from_pos_invoice",
                  return_value=1), \
            patch("resto.printing.get_waiter_name", return_value="W"), \
            patch("resto.printing.frappe.session") as mock_sess, \
            patch("resto.printing.frappe.db.get_value",
                  side_effect=[
                      "User Full Name",
                      {"name": "BAR Station", "description": "Kitchen Bar"},
                  ]):
            mock_sess.user = "user@x.com"
            raw = build_void_item_receipt(
                "INV-001",
                items=[{"qty": 1, "item_name": "Nasi"}],
                printer_name="BAR",
            )
        self.assertIn(b"VOID MENU", raw)
        self.assertIn(b"KITCHEN BAR", raw)
        self.assertNotIn(b"Kitchen :", raw)
        self.assertNotIn(b"Station :", raw)


class TestUserFullNameLookup(RestoPOSTestBase):
    """Item 2: TableRepository.get_user_full_names harus tetap mengembalikan
    mapping (fallback ke email) supaya UI selalu punya display name."""

    def test_fallback_to_email_when_user_doc_not_found(self):
        from resto.repositories.table_repository import TableRepository
        with patch("frappe.get_all", return_value=[]):
            result = TableRepository().get_user_full_names(["unknown@x.com"])
        self.assertEqual(result, {"unknown@x.com": "unknown@x.com"})

    def test_uses_full_name_when_user_doc_found(self):
        from resto.repositories.table_repository import TableRepository
        with patch("frappe.get_all", return_value=[
            {"name": "alice@x.com", "full_name": "Alice Wonderland"},
        ]):
            result = TableRepository().get_user_full_names(["alice@x.com"])
        self.assertEqual(result["alice@x.com"], "Alice Wonderland")

    def test_mixes_known_and_unknown(self):
        from resto.repositories.table_repository import TableRepository
        with patch("frappe.get_all", return_value=[
            {"name": "alice@x.com", "full_name": "Alice"},
        ]):
            result = TableRepository().get_user_full_names(
                ["alice@x.com", "ghost@x.com"]
            )
        self.assertEqual(result["alice@x.com"], "Alice")
        self.assertEqual(result["ghost@x.com"], "ghost@x.com")
