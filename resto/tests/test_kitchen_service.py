import frappe
from unittest.mock import MagicMock, patch, call
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.kitchen_service import KitchenService


class TestGetAllBranchMenuWithChildren(RestoPOSTestBase):
    """Test KitchenService.get_all_branch_menu_with_children"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_returns_empty_when_no_branch_menus(self):
        """Harus return [] jika tidak ada Branch Menu"""
        self.mock_repo.get_branch_menus.return_value = []
        result = self.service.get_all_branch_menu_with_children()
        self.assertEqual(result, [])

    def test_skips_menu_item_not_in_resto_menus(self):
        """Branch Menu yang resto_menu-nya tidak ada harus dilewati"""
        bm = MagicMock()
        bm.menu_item = "MENU-999"
        bm.name = "BM-001"
        self.mock_repo.get_branch_menus.return_value = [bm]
        self.mock_repo.get_resto_menus_by_names.return_value = {}
        self.mock_repo.get_images_for_menus.return_value = {}

        result = self.service.get_all_branch_menu_with_children()
        self.assertEqual(result, [])

    def test_includes_image_url_when_available(self):
        """Image URL harus disertakan jika ada di File"""
        bm = MagicMock()
        bm.menu_item = "MENU-001"
        bm.name = "BM-001"
        bm.rate = 25000

        rm = MagicMock()
        rm.name = "MENU-001"

        branch_doc = MagicMock()
        branch_doc.as_dict.return_value = {"name": "BM-001", "rate": 25000}

        self.mock_repo.get_branch_menus.return_value = [bm]
        self.mock_repo.get_resto_menus_by_names.return_value = {"MENU-001": rm}
        self.mock_repo.get_images_for_menus.return_value = {"MENU-001": "/files/img.png"}
        self.mock_repo.get_branch_menu_doc.return_value = branch_doc

        result = self.service.get_all_branch_menu_with_children()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["image"], "/files/img.png")

    def test_filters_by_branch_when_provided(self):
        """get_branch_menus harus dipanggil dengan branch filter"""
        self.mock_repo.get_branch_menus.return_value = []
        self.service.get_all_branch_menu_with_children(branch="BR-001")
        self.mock_repo.get_branch_menus.assert_called_once_with(branch="BR-001")


class TestGetBranchMenuForKitchenPrinting(RestoPOSTestBase):
    """Test KitchenService.get_branch_menu_for_kitchen_printing"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_returns_empty_when_no_pos_items(self):
        """Harus return [] jika POS Invoice tidak punya items"""
        self.mock_repo.get_pos_invoice_branch.return_value = "BR-001"
        self.mock_repo.get_pos_invoice_items.return_value = []

        result = self.service.get_branch_menu_for_kitchen_printing("INV-001")
        self.assertEqual(result, [])

    def test_skips_items_without_resto_menu(self):
        """Item tanpa resto_menu harus dilewati"""
        item = MagicMock()
        item.get.side_effect = lambda k, d=None: None if k == "resto_menu" else d

        self.mock_repo.get_pos_invoice_branch.return_value = "BR-001"
        self.mock_repo.get_pos_invoice_items.return_value = [item]

        result = self.service.get_branch_menu_for_kitchen_printing("INV-001")
        self.assertEqual(result, [])

    def test_groups_items_by_station_combine(self):
        """Combine mode: semua item satu station → satu tiket"""
        item1 = {"resto_menu": "MENU-001", "item_name": "Nasi", "qty": 1,
                 "quick_notes": "", "add_ons": "", "name": "ITEM-001"}
        item2 = {"resto_menu": "MENU-001", "item_name": "Ayam", "qty": 2,
                 "quick_notes": "", "add_ons": "", "name": "ITEM-002"}

        printer_entry = MagicMock()
        printer_entry.get.side_effect = lambda k: {
            "printer_name": "PRT-001",
            "kitchen_station": "STATION-A",
            "printing_type": "Combine"
        }.get(k)

        bm_doc = MagicMock()
        bm_doc.printers = [printer_entry]

        self.mock_repo.get_pos_invoice_branch.return_value = "BR-001"
        self.mock_repo.get_pos_invoice_items.return_value = [item1, item2]
        self.mock_repo.get_short_name.return_value = ""
        self.mock_repo.get_branch_menu_docs_for_item.return_value = [bm_doc]

        result = self.service.get_branch_menu_for_kitchen_printing("INV-001")

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["items"]), 2)

    def test_splits_items_by_station_split(self):
        """Split mode: setiap item → tiket terpisah"""
        item1 = {"resto_menu": "MENU-001", "item_name": "Nasi", "qty": 1,
                 "quick_notes": "", "add_ons": "", "name": "ITEM-001"}
        item2 = {"resto_menu": "MENU-001", "item_name": "Ayam", "qty": 2,
                 "quick_notes": "", "add_ons": "", "name": "ITEM-002"}

        printer_entry = MagicMock()
        printer_entry.get.side_effect = lambda k: {
            "printer_name": "PRT-001",
            "kitchen_station": "STATION-A",
            "printing_type": "Split"
        }.get(k)

        bm_doc = MagicMock()
        bm_doc.printers = [printer_entry]

        self.mock_repo.get_pos_invoice_branch.return_value = "BR-001"
        self.mock_repo.get_pos_invoice_items.return_value = [item1, item2]
        self.mock_repo.get_short_name.return_value = ""
        self.mock_repo.get_branch_menu_docs_for_item.return_value = [bm_doc]

        result = self.service.get_branch_menu_for_kitchen_printing("INV-001")

        self.assertEqual(len(result), 2)
        self.assertEqual(len(result[0]["items"]), 1)
        self.assertEqual(len(result[1]["items"]), 1)


class TestPrintToKsNow(RestoPOSTestBase):
    """Test KitchenService.print_to_ks_now"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_only_sends_unprinted_items(self):
        """Hanya item dengan is_print_kitchen=0 yang dikirim ke printer"""
        ticket = {
            "kitchen_station": "STATION-A",
            "printer_name": "PRT-001",
            "pos_invoice": "INV-001",
            "items": [
                {"name": "ITEM-001"},
                {"name": "ITEM-002"},
            ]
        }

        self.mock_repo.get_item_print_status.side_effect = lambda name: (
            0 if name == "ITEM-001" else 1
        )

        with patch.object(self.service, "get_branch_menu_for_kitchen_printing",
                          return_value=[ticket]):
            with patch("resto.services.kitchen_service.kitchen_print_from_payload") as mock_print:
                self.service.print_to_ks_now("INV-001")

        mock_print.assert_called_once()
        sent_items = mock_print.call_args[0][0]["items"]
        self.assertEqual(len(sent_items), 1)
        self.assertEqual(sent_items[0]["name"], "ITEM-001")

    def test_marks_printed_items(self):
        """Item yang dikirim harus ditandai is_print_kitchen=1"""
        ticket = {
            "kitchen_station": "STATION-A",
            "printer_name": "PRT-001",
            "pos_invoice": "INV-001",
            "items": [{"name": "ITEM-001"}]
        }

        self.mock_repo.get_item_print_status.return_value = 0

        with patch.object(self.service, "get_branch_menu_for_kitchen_printing",
                          return_value=[ticket]):
            with patch("resto.services.kitchen_service.kitchen_print_from_payload"):
                self.service.print_to_ks_now("INV-001")

        self.mock_repo.mark_item_printed.assert_called_once_with("ITEM-001")

    def test_no_print_when_all_already_printed(self):
        """Tidak ada yang dikirim jika semua item sudah dicetak"""
        ticket = {
            "kitchen_station": "STATION-A",
            "printer_name": "PRT-001",
            "pos_invoice": "INV-001",
            "items": [{"name": "ITEM-001"}]
        }

        self.mock_repo.get_item_print_status.return_value = 1

        with patch.object(self.service, "get_branch_menu_for_kitchen_printing",
                          return_value=[ticket]):
            with patch("resto.services.kitchen_service.kitchen_print_from_payload") as mock_print:
                self.service.print_to_ks_now("INV-001")

        mock_print.assert_not_called()


class TestSendToKitchen(RestoPOSTestBase):
    """Test KitchenService.send_to_kitchen"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = KitchenService(repo=self.mock_repo)

    def test_returns_success_with_pos_invoice_name(self):
        """Harus return status success dan pos_invoice name"""
        mock_invoice_svc = MagicMock()
        mock_invoice_svc.create_pos_invoice.return_value = {"status": "success", "name": "INV-001"}

        mock_table_svc = MagicMock()

        with patch.object(self.service, "print_to_ks_now"):
            result = self.service.send_to_kitchen(
                payload={"customer": "C", "items": [{"item_code": "X", "qty": 1, "rate": 100}],
                         "pos_profile": "P", "order_type": None},
                invoice_service=mock_invoice_svc,
                table_service=mock_table_svc,
                table_name=None
            )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["pos_invoice"], "INV-001")

    def test_updates_table_when_table_name_given(self):
        """Harus update table jika table_name diberikan"""
        mock_invoice_svc = MagicMock()
        mock_invoice_svc.create_pos_invoice.return_value = {"status": "success", "name": "INV-001"}

        mock_table_svc = MagicMock()
        self.mock_repo.table_exists.return_value = True

        with patch.object(self.service, "print_to_ks_now"):
            self.service.send_to_kitchen(
                payload={"customer": "C", "items": [], "pos_profile": "P", "order_type": None},
                invoice_service=mock_invoice_svc,
                table_service=mock_table_svc,
                table_name="TBL-001",
                status="Terisi"
            )

        mock_table_svc.update_table_status.assert_called_once()

    def test_skips_table_update_when_table_not_found(self):
        """Jika table tidak ada, skip update table (Take Away)"""
        mock_invoice_svc = MagicMock()
        mock_invoice_svc.create_pos_invoice.return_value = {"status": "success", "name": "INV-001"}

        mock_table_svc = MagicMock()
        self.mock_repo.table_exists.return_value = False

        with patch.object(self.service, "print_to_ks_now"):
            self.service.send_to_kitchen(
                payload={"customer": "C", "items": [], "pos_profile": "P", "order_type": None},
                invoice_service=mock_invoice_svc,
                table_service=mock_table_svc,
                table_name="TBL-NOTFOUND"
            )

        mock_table_svc.update_table_status.assert_not_called()

    def test_print_error_does_not_crash(self):
        """Error saat printing tidak boleh crash send_to_kitchen"""
        mock_invoice_svc = MagicMock()
        mock_invoice_svc.create_pos_invoice.return_value = {"status": "success", "name": "INV-001"}
        mock_table_svc = MagicMock()

        with patch.object(self.service, "print_to_ks_now", side_effect=Exception("printer offline")):
            result = self.service.send_to_kitchen(
                payload={"customer": "C", "items": [], "pos_profile": "P", "order_type": None},
                invoice_service=mock_invoice_svc,
                table_service=mock_table_svc,
                table_name=None
            )

        self.assertEqual(result["status"], "success")
        self.assertIn("Printing gagal", result["message"])
