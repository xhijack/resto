import frappe
from unittest.mock import MagicMock, patch
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.kitchen_service import KitchenService


class TestGetBranchMenuByRestoMenu(RestoPOSTestBase):
    """Test KitchenService.get_branch_menu_by_resto_menu"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_returns_empty_when_no_pos_items(self):
        self.mock_repo.get_pos_invoice_resto_menus.return_value = []
        self.assertEqual(self.service.get_branch_menu_by_resto_menu("POS-1"), [])

    def test_skips_items_without_resto_menu(self):
        self.mock_repo.get_pos_invoice_resto_menus.return_value = [{"resto_menu": None}]
        self.assertEqual(self.service.get_branch_menu_by_resto_menu("POS-1"), [])
        self.mock_repo.get_branch_menus_for_resto_menu.assert_not_called()

    def test_supports_dict_and_object_items(self):
        """Item bisa dict atau object — pakai .get atau getattr"""
        obj_item = MagicMock(); obj_item.resto_menu = "MENU-A"
        self.mock_repo.get_pos_invoice_resto_menus.return_value = [
            {"resto_menu": "MENU-B"}, obj_item,
        ]

        bm_a = MagicMock(); bm_a.branch = "BR-1"
        ks = MagicMock(); ks.kitchen_station = "KS1"; ks.printer_name = "P1"
        bm_a.printers = [ks]

        self.mock_repo.get_branch_menus_for_resto_menu.return_value = [bm_a]

        result = self.service.get_branch_menu_by_resto_menu("POS-1")
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["resto_menu"], "MENU-B")
        self.assertEqual(result[1]["resto_menu"], "MENU-A")

    def test_filters_printers_without_printer_name(self):
        self.mock_repo.get_pos_invoice_resto_menus.return_value = [{"resto_menu": "MENU-A"}]

        bm = MagicMock(); bm.branch = "BR-1"
        ks_with = MagicMock(); ks_with.kitchen_station = "KS1"; ks_with.printer_name = "P1"
        ks_no = MagicMock(); ks_no.kitchen_station = "KS2"; ks_no.printer_name = None
        bm.printers = [ks_with, ks_no]

        self.mock_repo.get_branch_menus_for_resto_menu.return_value = [bm]
        result = self.service.get_branch_menu_by_resto_menu("POS-1")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["kitchen_printers"], [{"station": "KS1", "printer_name": "P1"}])


class TestProcessKitchenPrintingWorker(RestoPOSTestBase):
    """Test KitchenService.process_kitchen_printing_worker"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_calls_print_then_enqueue_checker(self):
        self.mock_repo.get_invoice_branch.return_value = "BR-1"
        with patch.object(self.service, "print_to_ks_now") as mock_print, \
             patch("resto.services.printing_service.PrintingService") as MockPrinting:
            mock_printing = MockPrinting.return_value
            self.service.process_kitchen_printing_worker("POS-1")

            mock_print.assert_called_once_with("POS-1")
            mock_printing.enqueue_checker_after_kitchen.assert_called_once_with("POS-1", "BR-1")

    def test_printing_service_uses_its_own_repo(self):
        """PrintingService harus pakai PrintingRepository sendiri,
        bukan repo KitchenService (yang tidak punya get_checker_printer).
        """
        self.mock_repo.get_invoice_branch.return_value = "BR-1"
        with patch.object(self.service, "print_to_ks_now"), \
             patch("resto.services.printing_service.PrintingService") as MockPrinting:
            self.service.process_kitchen_printing_worker("POS-1")
            # PrintingService di-instantiate TANPA repo arg → pakai PrintingRepository default
            MockPrinting.assert_called_once_with()

    def test_swallows_exception_and_logs(self):
        """Worker tidak boleh crash — error ditangkap dan di-log."""
        with patch.object(self.service, "print_to_ks_now", side_effect=RuntimeError("boom")), \
             patch("frappe.log_error") as mock_log:
            # Tidak boleh raise
            self.service.process_kitchen_printing_worker("POS-1")
            mock_log.assert_called_once()
            self.assertIn("POS-1", mock_log.call_args[0][1])
