import sys
import frappe
from unittest.mock import MagicMock, patch, call
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.kitchen_service import KitchenService

# resto.printing does `import cups` at module top — pycups isn't installed in
# the test environment. Inject a fake before any test imports the module.
sys.modules.setdefault("cups", MagicMock())


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

    def test_one_station_failure_does_not_abort_others(self):
        """Satu station gagal print tidak boleh menggagalkan station lain (multi-station fault isolation)"""
        tickets = [
            {"kitchen_station": "BUTCHER", "printer_name": "PRT-BUTCHER",
             "pos_invoice": "INV-001", "items": [{"name": "ITEM-001"}]},
            {"kitchen_station": "PANTRY", "printer_name": "PRT-PANTRY",
             "pos_invoice": "INV-001", "items": [{"name": "ITEM-002"}]},
            {"kitchen_station": "TAHO", "printer_name": "PRT-TAHO",
             "pos_invoice": "INV-001", "items": [{"name": "ITEM-003"}]},
        ]

        self.mock_repo.get_item_print_status.return_value = 0

        def side_effect(payload):
            if payload["kitchen_station"] == "PANTRY":
                raise Exception("CUPS printer not found")

        with patch.object(self.service, "get_branch_menu_for_kitchen_printing",
                          return_value=tickets):
            with patch("resto.services.kitchen_service.kitchen_print_from_payload",
                       side_effect=side_effect) as mock_print:
                self.service.print_to_ks_now("INV-001")

        # All 3 stations attempted (no abort cascade)
        self.assertEqual(mock_print.call_count, 3)

        # Only successful items get marked printed (PANTRY's ITEM-002 retried later)
        marked = [c.args[0] for c in self.mock_repo.mark_item_printed.call_args_list]
        self.assertIn("ITEM-001", marked)
        self.assertIn("ITEM-003", marked)
        self.assertNotIn("ITEM-002", marked)


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
        """Harus update table jika table_name diberikan — pakai atomic
        add_table_order + update_table_meta (post-refactor race condition fix)."""
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

        mock_table_svc.add_table_order.assert_called_once_with(
            "TBL-001", {"invoice_name": "INV-001"}
        )
        mock_table_svc.update_table_meta.assert_called_once()
        # Legacy REPLACE TIDAK boleh dipanggil — itu yang dulu menyebabkan race.
        mock_table_svc.update_table_status.assert_not_called()

    def test_send_to_kitchen_sets_table_field_on_payload(self):
        """Field `table` di payload harus di-set ke table_name supaya
        invoice baru ter-link langsung ke meja via custom field."""
        mock_invoice_svc = MagicMock()
        mock_invoice_svc.create_pos_invoice.return_value = {"status": "success", "name": "INV-001"}
        mock_table_svc = MagicMock()
        self.mock_repo.table_exists.return_value = True

        payload = {"customer": "C", "items": [], "pos_profile": "P", "order_type": None}
        with patch.object(self.service, "print_to_ks_now"):
            self.service.send_to_kitchen(
                payload=payload,
                invoice_service=mock_invoice_svc,
                table_service=mock_table_svc,
                table_name="TBL-001",
            )

        sent_payload = mock_invoice_svc.create_pos_invoice.call_args[0][0]
        self.assertEqual(sent_payload.get("table"), "TBL-001")

    def test_send_to_kitchen_ignores_orders_param_legacy(self):
        """Param `orders` dari frontend SUDAH TIDAK DIPAKAI — backwards-compat
        signature, tapi tidak boleh re-introduce REPLACE semantic."""
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
                orders=[{"invoice_name": "STALE-001"}],
            )

        # update_table_status (yang menerima orders) TIDAK dipanggil sama sekali.
        mock_table_svc.update_table_status.assert_not_called()
        # add_table_order tetap dipanggil dengan invoice baru, BUKAN yang stale.
        mock_table_svc.add_table_order.assert_called_once_with(
            "TBL-001", {"invoice_name": "INV-001"}
        )

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
        mock_table_svc.add_table_order.assert_not_called()
        mock_table_svc.update_table_meta.assert_not_called()

    def test_take_away_does_not_set_table_field_on_payload(self):
        """Bug Take Away (2026-05-13): mobile kirim table_name='No. Antrian {queue}'
        sebagai virtual ID. Field `table` di payload TIDAK boleh di-set karena
        POS Invoice `table` adalah Link ke Table doctype → LinkValidationError saat
        insert. Bukti regression: 'Could not find Table: No. Antrian 1305001'."""
        mock_invoice_svc = MagicMock()
        mock_invoice_svc.create_pos_invoice.return_value = {"status": "success", "name": "INV-001"}
        mock_table_svc = MagicMock()
        self.mock_repo.table_exists.return_value = False

        payload = {"customer": "Aul", "items": [], "pos_profile": "Riau",
                   "order_type": "Take Away"}
        with patch.object(self.service, "print_to_ks_now"):
            self.service.send_to_kitchen(
                payload=payload,
                invoice_service=mock_invoice_svc,
                table_service=mock_table_svc,
                table_name="No. Antrian 1305001",
            )

        sent_payload = mock_invoice_svc.create_pos_invoice.call_args[0][0]
        self.assertNotIn("table", sent_payload,
                         "payload['table'] tidak boleh di-set untuk Take Away (table_name virtual)")

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


class TestBuildKitchenReceiptFromPayload(RestoPOSTestBase):
    """Test build_kitchen_receipt_from_payload — queue rendering untuk Take Away."""

    ENTRY = {
        "kitchen_station": "Hot Kitchen",
        "printer_name": "kitchen-1",
        "pos_invoice": "INV-001",
        "transaction_date": "2026-05-12 10:00:00",
        "items": [{"resto_menu": "RM-001", "item_name": "Nasi Goreng",
                   "short_name": "NG", "qty": 1}],
    }

    def _build(self, order_type, queue):
        from resto import printing
        with patch.object(printing.frappe.db, "get_value") as mock_get_value, \
             patch.object(printing, "get_table_names_from_pos_invoice", return_value=""), \
             patch.object(printing, "get_total_pax_from_pos_invoice", return_value=0), \
             patch.object(printing.frappe, "get_all", return_value=[]):

            def side_effect(doctype, name, fields, *args, **kwargs):
                if doctype == "POS Invoice":
                    return {"order_type": order_type, "queue": queue}
                if doctype == "User":
                    return "Test User"
                return None

            mock_get_value.side_effect = side_effect
            return printing.build_kitchen_receipt_from_payload(self.ENTRY)

    def test_take_away_with_queue_renders_block(self):
        """Take Away + queue terisi → block 'Your Queue Number' muncul."""
        out = self._build(order_type="Take Away", queue="A123")
        self.assertIn(b"Your Queue Number:", out)
        self.assertIn(b"A123", out)

    def test_dine_in_does_not_render_queue_block(self):
        """Dine In meski queue ada → block queue TIDAK muncul."""
        out = self._build(order_type="Dine In", queue="A123")
        self.assertNotIn(b"Your Queue Number:", out)

    def test_take_away_without_queue_does_not_render_block(self):
        """Take Away tapi queue kosong → block queue TIDAK muncul."""
        out = self._build(order_type="Take Away", queue=None)
        self.assertNotIn(b"Your Queue Number:", out)
