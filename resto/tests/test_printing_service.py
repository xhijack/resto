import sys
import frappe
from unittest.mock import MagicMock, patch

# pycups (modul `cups`) bisa tidak tersedia di environment test. Stub
# sebagai MagicMock supaya `resto.printing` (yang ada top-level `import cups`)
# bisa di-load. Test individual yang butuh CUPS behavior tertentu tetap
# pakai `patch.dict(sys.modules, {"cups": ...})` override.
sys.modules.setdefault("cups", MagicMock())

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

    def test_void_two_items_same_printer_prints_once_with_both_items(self):
        """Regresi v1.2.15: 2 item void ke printer yang sama harus print 1x, bukan 2x.
        Sebelumnya: loop per-item × per-printer → BAR dapat receipt 2x dengan full items.
        Trigger jelas pasca merge table (3 meja jadi 1, banyak minuman → BAR sama)."""
        item_a = {"name": "ITEM-A", "item_code": "DRINK-JUS-JERUK", "item_name": "Jus Jeruk",
                  "qty": 1, "add_ons": "", "quick_notes": ""}
        item_b = {"name": "ITEM-B", "item_code": "DRINK-JUS-MELON", "item_name": "Jus Melon",
                  "qty": 1, "add_ons": "", "quick_notes": ""}
        # kedua item routed ke printer yang sama (BAR)
        self.mock_repo.get_branch_menu_printers_for_item.return_value = ["PRT-BAR"]

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value="J") as mock_print:
                self.service._print_void_to_other_stations(
                    "INV-001", [item_a, item_b], "BR-001"
                )

        # BAR hanya menerima 1 job print dengan 2 items
        mock_build.assert_called_once_with("INV-001", [item_a, item_b], "PRT-BAR")
        self.assertEqual(mock_print.call_count, 1)

    def test_void_one_item_multi_printer_prints_to_each_printer(self):
        """1 item routed ke BAR + GRILL → kedua printer dapat receipt dengan item itu."""
        item = {"name": "ITEM-A", "item_code": "FOOD-001", "item_name": "Steak Combo",
                "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_branch_menu_printers_for_item.return_value = ["PRT-BAR", "PRT-GRILL"]

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value="J") as mock_print:
                self.service._print_void_to_other_stations("INV-001", [item], "BR-001")

        self.assertEqual(mock_build.call_count, 2)
        self.assertEqual(mock_print.call_count, 2)
        called_printers = {call.args[2] for call in mock_build.call_args_list}
        self.assertEqual(called_printers, {"PRT-BAR", "PRT-GRILL"})
        # tiap printer dapat item itu
        for call in mock_build.call_args_list:
            self.assertEqual(call.args[1], [item])

    def test_void_different_items_different_printers_split_correctly(self):
        """Items ke printer berbeda harus terpecah benar (BAR dapat drink, GRILL dapat food)."""
        drink = {"name": "ITEM-D", "item_code": "DRINK-JERUK", "item_name": "Jus Jeruk",
                 "qty": 1, "add_ons": "", "quick_notes": ""}
        food = {"name": "ITEM-F", "item_code": "FOOD-STEAK", "item_name": "Steak",
                "qty": 1, "add_ons": "", "quick_notes": ""}

        def fake_printers(item_code, branch):
            if item_code == "DRINK-JERUK":
                return ["PRT-BAR"]
            if item_code == "FOOD-STEAK":
                return ["PRT-GRILL"]
            return []
        self.mock_repo.get_branch_menu_printers_for_item.side_effect = fake_printers

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw", return_value="J"):
                self.service._print_void_to_other_stations(
                    "INV-001", [drink, food], "BR-001"
                )

        self.assertEqual(mock_build.call_count, 2)
        per_printer = {call.args[2]: call.args[1] for call in mock_build.call_args_list}
        self.assertEqual(per_printer["PRT-BAR"], [drink])
        self.assertEqual(per_printer["PRT-GRILL"], [food])

    def test_void_two_items_mixed_routing_dedupes_shared_printer(self):
        """Item A → BAR; Item B → BAR + GRILL. BAR dapat 1 print dengan [A, B], GRILL dapat [B]."""
        item_a = {"name": "ITEM-A", "item_code": "DRINK-A", "item_name": "Jus A",
                  "qty": 1, "add_ons": "", "quick_notes": ""}
        item_b = {"name": "ITEM-B", "item_code": "COMBO-B", "item_name": "Combo B",
                  "qty": 1, "add_ons": "", "quick_notes": ""}

        def fake_printers(item_code, branch):
            if item_code == "DRINK-A":
                return ["PRT-BAR"]
            if item_code == "COMBO-B":
                return ["PRT-BAR", "PRT-GRILL"]
            return []
        self.mock_repo.get_branch_menu_printers_for_item.side_effect = fake_printers

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value="J") as mock_print:
                self.service._print_void_to_other_stations(
                    "INV-001", [item_a, item_b], "BR-001"
                )

        # 2 printers terlibat → 2 print job (BAR sekali, GRILL sekali)
        self.assertEqual(mock_print.call_count, 2)
        per_printer = {call.args[2]: call.args[1] for call in mock_build.call_args_list}
        self.assertEqual(per_printer["PRT-BAR"], [item_a, item_b])
        self.assertEqual(per_printer["PRT-GRILL"], [item_b])

    # v1.2.18 Issue #4: void cetak 2x ketika void_printer sama dengan kitchen
    # station printer. Top-level print_void_item sudah cetak ke void_printer
    # dengan full items. Kalau station routing juga ngarah ke printer yang sama,
    # printer itu dapet 2 ticket. Fix: skip station printer kalau == void_printer.
    def test_void_printer_equals_station_printer_skips_duplicate(self):
        """void_printer=BAR + item routed ke BAR: station routing skip BAR (top-level
        sudah cover). Trigger jelas pasca merge meja dengan default void = kitchen."""
        item = {"name": "ITEM-A", "item_code": "DRINK-A", "item_name": "Jus",
                "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_branch_menu_printers_for_item.return_value = ["PRT-BAR"]

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value="J") as mock_print:
                self.service._print_void_to_other_stations(
                    "INV-001", [item], "BR-001", void_printer="PRT-BAR"
                )

        # Tidak ada print station — top-level (PRT-BAR via print_void_item)
        # sudah cover. station call_count = 0.
        self.assertEqual(mock_print.call_count, 0)
        self.assertEqual(mock_build.call_count, 0)

    def test_void_printer_differs_from_station_printer_still_prints(self):
        """void_printer=KASIR, station=BAR: BAR tetap dicetak (printer beda)."""
        item = {"name": "ITEM-A", "item_code": "DRINK-A", "item_name": "Jus",
                "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_branch_menu_printers_for_item.return_value = ["PRT-BAR"]

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value="J") as mock_print:
                self.service._print_void_to_other_stations(
                    "INV-001", [item], "BR-001", void_printer="PRT-KASIR"
                )

        # Station BAR dicetak karena beda dengan void_printer KASIR.
        self.assertEqual(mock_print.call_count, 1)
        mock_build.assert_called_once_with("INV-001", [item], "PRT-BAR")

    def test_void_printer_skips_only_matching_printer(self):
        """item route ke BAR + GRILL, void_printer=BAR. GRILL tetap dicetak,
        BAR di-skip (top-level sudah cover)."""
        item = {"name": "ITEM-A", "item_code": "COMBO-A", "item_name": "Combo",
                "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_branch_menu_printers_for_item.return_value = ["PRT-BAR", "PRT-GRILL"]

        with patch("resto.services.printing_service.build_void_item_receipt",
                   return_value=b"RAW") as mock_build:
            with patch("resto.services.printing_service.cups_print_raw",
                       return_value="J") as mock_print:
                self.service._print_void_to_other_stations(
                    "INV-001", [item], "BR-001", void_printer="PRT-BAR"
                )

        self.assertEqual(mock_print.call_count, 1)
        mock_build.assert_called_once_with("INV-001", [item], "PRT-GRILL")

    def test_print_void_item_passes_void_printer_to_other_stations(self):
        """End-to-end via print_void_item: void_printer harus diteruskan ke
        _print_void_to_other_stations supaya dedup logic punya context."""
        void_item = {"name": "ITEM-A", "item_code": "DRINK-A", "item_name": "Jus",
                     "qty": 1, "add_ons": "", "quick_notes": ""}
        self.mock_repo.get_void_items_to_print.return_value = [void_item]
        self.mock_repo.get_void_printer.return_value = "PRT-BAR"
        self.mock_repo.get_invoice_branch.return_value = "BR-001"

        with patch("resto.services.printing_service.build_void_item_receipt", return_value=b"RAW"):
            with patch("resto.services.printing_service.cups_print_raw", return_value="J"):
                with patch.object(self.service, "_print_void_to_other_stations") as mock_other:
                    self.service.print_void_item("INV-001")

        mock_other.assert_called_once()
        kwargs = mock_other.call_args.kwargs
        self.assertEqual(kwargs.get("void_printer"), "PRT-BAR")


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
        online = {"state": "idle", "is_online": True, "state_reasons": []}
        with patch("resto.services.printing_service.get_printer_state",
                   return_value=online):
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

    def test_throws_when_printer_offline(self):
        """Printer offline → throw error sebelum submit job ke CUPS."""
        offline = {
            "state": "idle",  # state code idle tapi reasons bilang offline
            "is_online": False,
            "state_reasons": ["offline-report"],
        }
        with patch("resto.services.printing_service.get_printer_state",
                   return_value=offline):
            with patch("resto.services.printing_service.cups_print_raw") as mock_print:
                with self.assertRaises(frappe.ValidationError) as ctx:
                    self.service.test_print("BAR-PRINTER")

        # cups_print_raw TIDAK boleh dipanggil — kita refuse sebelum submit
        mock_print.assert_not_called()
        self.assertIn("offline", str(ctx.exception).lower())
        # alasan dari CUPS ditampilkan ke user supaya bisa diagnose
        self.assertIn("offline-report", str(ctx.exception))

    def test_throws_when_printer_not_in_cups(self):
        """Printer tidak terdaftar di CUPS → ValidationError dari get_printer_state propagated."""
        with patch("resto.services.printing_service.get_printer_state",
                   side_effect=frappe.ValidationError("Printer 'X' tidak ditemukan di CUPS")):
            with patch("resto.services.printing_service.cups_print_raw") as mock_print:
                with self.assertRaises(frappe.ValidationError):
                    self.service.test_print("X")

        mock_print.assert_not_called()

    def test_throws_when_cups_daemon_down(self):
        """CUPS daemon down (Exception generic) → fail safe, jangan submit."""
        with patch("resto.services.printing_service.get_printer_state",
                   side_effect=Exception("CUPS daemon connection refused")):
            with patch("resto.services.printing_service.cups_print_raw") as mock_print:
                with self.assertRaises(frappe.ValidationError) as ctx:
                    self.service.test_print("BAR-PRINTER")

        mock_print.assert_not_called()
        self.assertIn("BAR-PRINTER", str(ctx.exception))


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


class TestPrintReceiptPaymentFiltering(RestoPOSTestBase):
    """v1.2.6 fix: payment row dengan amount=0 (default POS Profile) tidak boleh muncul di struk."""

    def _make_doc(self, payments):
        fake_doc = MagicMock()
        fake_doc.reload.return_value = fake_doc
        data = {
            "currency": "IDR",
            "items": [],
            "taxes": [],
            "payments": payments,
            "branch": "",
            "company": "TEST",
            "customer": "X",
            "customer_name": "X",
            "order_type": "Dine In",
            "name": "INV-001",
            "posting_date": "2026-05-09",
            "posting_time": "12:00:00",
            "total": 500000,
            "discount_amount": 0,
            "total_taxes_and_charges": 0,
            "grand_total": 500000,
            "rounded_total": 500000,
            "paid_amount": 500000,
            "change_amount": 0,
            "remarks": "",
        }
        fake_doc.get.side_effect = lambda k, default=None: data.get(k, default)
        return fake_doc

    def test_zero_amount_payment_row_excluded(self):
        with patch.dict(sys.modules, {"cups": MagicMock()}):
            from resto.printing import _collect_pos_invoice

        fake_doc = self._make_doc([
            {"mode_of_payment": "Cash", "amount": 0},
            {"mode_of_payment": "Debit BCA", "amount": 500000},
        ])

        with patch("resto.printing.frappe.get_doc", return_value=fake_doc):
            result = _collect_pos_invoice("INV-001")

        modes = [p["mode_of_payment"] for p in result["payments"]]
        self.assertEqual(modes, ["Debit BCA"])
        self.assertEqual(result["payments"][0]["amount"], 500000)

    def test_negative_amount_payment_row_excluded(self):
        with patch.dict(sys.modules, {"cups": MagicMock()}):
            from resto.printing import _collect_pos_invoice

        fake_doc = self._make_doc([
            {"mode_of_payment": "Cash", "amount": -100},
            {"mode_of_payment": "Cash", "amount": 500000},
        ])

        with patch("resto.printing.frappe.get_doc", return_value=fake_doc):
            result = _collect_pos_invoice("INV-001")

        self.assertEqual(len(result["payments"]), 1)
        self.assertEqual(result["payments"][0]["amount"], 500000)

    def test_split_payment_keeps_all_positive_rows(self):
        with patch.dict(sys.modules, {"cups": MagicMock()}):
            from resto.printing import _collect_pos_invoice

        fake_doc = self._make_doc([
            {"mode_of_payment": "Cash", "amount": 0},
            {"mode_of_payment": "Cash", "amount": 200000},
            {"mode_of_payment": "Debit BCA", "amount": 300000},
        ])

        with patch("resto.printing.frappe.get_doc", return_value=fake_doc):
            result = _collect_pos_invoice("INV-001")

        modes = [p["mode_of_payment"] for p in result["payments"]]
        amounts = [p["amount"] for p in result["payments"]]
        self.assertEqual(modes, ["Cash", "Debit BCA"])
        self.assertEqual(amounts, [200000, 300000])


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


class TestGetPrinterState(RestoPOSTestBase):
    """Test resto.printing.get_printer_state — fokus pada deteksi offline via
    state_reasons (CUPS tidak otomatis ubah state code saat printer fisik mati)."""

    def _patched_get_state(self, state_code, reasons, device_uri=""):
        """Return get_printer_state hasil dengan CUPS yang di-mock penuh.

        Mock memerlukan: cups.Connection().getPrinters() returns dict berisi
        printer_name, dan getPrinterAttributes() returns dict dengan
        printer-state + printer-state-reasons + device-uri.
        """
        fake_cups = MagicMock()
        fake_conn = MagicMock()
        fake_conn.getPrinters.return_value = {"P1": {}}
        fake_conn.getPrinterAttributes.return_value = {
            "printer-state": state_code,
            "printer-state-reasons": reasons,
            "device-uri": device_uri,
        }
        fake_cups.Connection.return_value = fake_conn

        with patch.dict(sys.modules, {"cups": fake_cups}):
            from resto.printing import get_printer_state
            return get_printer_state("P1")

    def test_idle_no_reasons_is_online(self):
        """state=idle (3), reasons=[] → is_online=True"""
        result = self._patched_get_state(3, [])
        self.assertEqual(result["state"], "idle")
        self.assertTrue(result["is_online"])

    def test_idle_with_none_reason_is_online(self):
        """state=idle, reasons=['none'] → is_online=True (CUPS standard noop)"""
        result = self._patched_get_state(3, ["none"])
        self.assertTrue(result["is_online"])

    def test_idle_but_offline_report_is_offline(self):
        """state=idle (3) tapi reasons=['offline-report'] → is_online=False.

        Ini kasus utama: CUPS belum update state code tapi sudah tahu printer
        offline via reason.
        """
        result = self._patched_get_state(3, ["offline-report"])
        self.assertEqual(result["state"], "idle")
        self.assertFalse(result["is_online"])
        self.assertIn("offline-report", result["state_reasons"])

    def test_idle_but_connecting_to_device_is_offline(self):
        """state=idle tapi reasons=['connecting-to-device-warning'] → offline"""
        result = self._patched_get_state(3, ["connecting-to-device-warning"])
        self.assertFalse(result["is_online"])

    def test_idle_but_paused_is_offline(self):
        """state=idle tapi reasons=['paused'] → offline (queue paused manual)"""
        result = self._patched_get_state(3, ["paused"])
        self.assertFalse(result["is_online"])

    def test_idle_but_cups_paused_is_offline(self):
        """reasons=['cups-paused'] → offline (alias paused)"""
        result = self._patched_get_state(3, ["cups-paused"])
        self.assertFalse(result["is_online"])

    def test_idle_but_timed_out_is_offline(self):
        """reasons=['timed-out'] → offline (device connection timeout)"""
        result = self._patched_get_state(3, ["timed-out"])
        self.assertFalse(result["is_online"])

    def test_stopped_is_offline(self):
        """state=stopped (5) → is_online=False regardless of reasons"""
        result = self._patched_get_state(5, [])
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["is_online"])

    def test_unknown_state_code_is_offline(self):
        """state code unknown → state='unknown', is_online=False"""
        result = self._patched_get_state(99, [])
        self.assertEqual(result["state"], "unknown")
        self.assertFalse(result["is_online"])

    def test_processing_is_online(self):
        """state=processing (4) → is_online=True (printer sedang cetak)"""
        result = self._patched_get_state(4, [])
        self.assertEqual(result["state"], "processing")
        self.assertTrue(result["is_online"])

    def test_case_insensitive_offline_detection(self):
        """Reason uppercase tetap ke-detect offline"""
        result = self._patched_get_state(3, ["OFFLINE-REPORT"])
        self.assertFalse(result["is_online"])

    def test_multiple_reasons_one_offline_marks_offline(self):
        """Salah satu reason offline → is_online=False meski yang lain benign"""
        result = self._patched_get_state(3, ["none", "offline-report", "media-low"])
        self.assertFalse(result["is_online"])

    def test_printer_not_registered_raises(self):
        """Printer tidak ada di CUPS → ValidationError"""
        fake_cups = MagicMock()
        fake_conn = MagicMock()
        fake_conn.getPrinters.return_value = {"OTHER": {}}
        fake_cups.Connection.return_value = fake_conn

        with patch.dict(sys.modules, {"cups": fake_cups}):
            from resto.printing import get_printer_state
            with self.assertRaises(frappe.ValidationError):
                get_printer_state("P1")

    # ---------------------------------------------------------------
    # Active TCP probe via device-uri — CUPS lazy state machine: kalau
    # printer fisik dicabut, state tetap idle/none sampai ada job gagal.
    # Probe TCP wajib untuk deteksi real-time.
    # ---------------------------------------------------------------

    def test_probe_overrides_when_device_unreachable(self):
        """state=idle, reasons=['none'], TAPI device-uri probe → False
        ⇒ is_online=False + reason 'offline-via-probe' di-append."""
        with patch("resto.printing._probe_device_uri", return_value=False):
            result = self._patched_get_state(3, ["none"], device_uri="socket://1.2.3.4:9100")
        self.assertFalse(result["is_online"])
        self.assertIn("offline-via-probe", result["state_reasons"])
        self.assertEqual(result["device_uri"], "socket://1.2.3.4:9100")

    def test_probe_skipped_for_usb_uri(self):
        """device-uri = usb://... → probe return None (skip).
        is_online jatuh ke layer 1 (state+reasons)."""
        # Tidak perlu patch — _probe_device_uri sendiri yang return None
        # untuk scheme non-network. Verifikasi via integrasi.
        result = self._patched_get_state(3, ["none"], device_uri="usb://EPSON/TM-T82")
        self.assertTrue(result["is_online"])  # layer 1 lolos, layer 2 skipped
        self.assertNotIn("offline-via-probe", result["state_reasons"])

    def test_probe_success_keeps_online(self):
        """device-uri network + probe sukses → tetap online dari layer 1."""
        with patch("resto.printing._probe_device_uri", return_value=True):
            result = self._patched_get_state(3, ["none"], device_uri="socket://1.2.3.4:9100")
        self.assertTrue(result["is_online"])
        self.assertNotIn("offline-via-probe", result["state_reasons"])

    def test_probe_empty_device_uri_skipped(self):
        """device-uri kosong → probe return None, jangan override."""
        result = self._patched_get_state(3, [], device_uri="")
        self.assertTrue(result["is_online"])

    def test_probe_does_not_override_offline_already(self):
        """Kalau layer 1 sudah offline (state=stopped), probe tidak perlu
        flip ke online walau secara teknis reachable."""
        with patch("resto.printing._probe_device_uri", return_value=True):
            result = self._patched_get_state(5, [], device_uri="socket://1.2.3.4:9100")
        self.assertFalse(result["is_online"])  # state=5 stopped tetap menang


class TestProbeDeviceUri(RestoPOSTestBase):
    """Unit test untuk _probe_device_uri — TCP probe helper."""

    def test_socket_scheme_uses_uri_port(self):
        """socket://host:9100 → connect ke (host, 9100)"""
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()  # context manager auto-handled
            result = _probe_device_uri("socket://192.168.1.50:9100")
        self.assertTrue(result)
        args, kwargs = mock_conn.call_args
        self.assertEqual(args[0], ("192.168.1.50", 9100))

    def test_lpd_scheme_default_port_515(self):
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            _probe_device_uri("lpd://printer.local")
        args, _ = mock_conn.call_args
        self.assertEqual(args[0], ("printer.local", 515))

    def test_ipp_scheme_default_port_631(self):
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection") as mock_conn:
            mock_conn.return_value = MagicMock()
            _probe_device_uri("ipp://192.168.1.99/ipp/print")
        args, _ = mock_conn.call_args
        self.assertEqual(args[0], ("192.168.1.99", 631))

    def test_socket_timeout_returns_false(self):
        """socket.timeout saat connect → False (printer mati/firewall)."""
        import socket as _sock
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection", side_effect=_sock.timeout()):
            result = _probe_device_uri("socket://10.0.0.99:9100", timeout=0.1)
        self.assertFalse(result)

    def test_connection_refused_returns_false(self):
        """OSError (mis. connection refused) → False."""
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection", side_effect=OSError("Connection refused")):
            result = _probe_device_uri("socket://10.0.0.99:9100", timeout=0.1)
        self.assertFalse(result)

    def test_usb_scheme_returns_none(self):
        """USB / non-network scheme → None (skip), tidak call socket."""
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection") as mock_conn:
            result = _probe_device_uri("usb://EPSON/TM-T82")
        self.assertIsNone(result)
        mock_conn.assert_not_called()

    def test_empty_uri_returns_none(self):
        from resto.printing import _probe_device_uri
        self.assertIsNone(_probe_device_uri(""))
        self.assertIsNone(_probe_device_uri(None))

    def test_uri_without_host_returns_none(self):
        """Malformed URI tanpa host → None."""
        from resto.printing import _probe_device_uri
        with patch("socket.create_connection") as mock_conn:
            result = _probe_device_uri("socket://")
        self.assertIsNone(result)
        mock_conn.assert_not_called()
