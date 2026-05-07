"""Unit tests untuk endpoint @frappe.whitelist di resto/api.py yang punya
logika sendiri (bukan thin wrapper). Test ini fokus ke perilaku api.py — logika
service-level sudah ditest terpisah.

Patch path note: api.py impor service inline (`from resto.services.x import Y`),
jadi patch di lokasi sumber (`resto.services.x.Y`), bukan di `resto.api.Y`.
"""

import frappe
from contextlib import contextmanager
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto import api


@contextmanager
def session_user(user):
    """frappe.session adalah _dict — patch.object tidak bisa, jadi save/restore manual."""
    prev = frappe.session.user
    frappe.session.user = user
    try:
        yield
    finally:
        frappe.session.user = prev


class TestMergeTableEndpoint(RestoPOSTestBase):
    """api.merge_table — parsing target_table (string JSON / list / fallback)"""

    def test_parses_json_string_target_table(self):
        with patch("resto.services.table_service.TableService") as MockSvc:
            api.merge_table("INV-1", "TBL-A", target_table='["TBL-B", "TBL-C"]')
            MockSvc.return_value.merge_table.assert_called_once_with(
                "INV-1", source_table="TBL-A", target_table=["TBL-B", "TBL-C"]
            )

    def test_falls_back_to_single_item_list_when_invalid_json(self):
        with patch("resto.services.table_service.TableService") as MockSvc:
            api.merge_table("INV-1", "TBL-A", target_table="TBL-B")
            MockSvc.return_value.merge_table.assert_called_once_with(
                "INV-1", source_table="TBL-A", target_table=["TBL-B"]
            )

    def test_passes_list_through_unchanged(self):
        with patch("resto.services.table_service.TableService") as MockSvc:
            api.merge_table("INV-1", "TBL-A", target_table=["TBL-B"])
            MockSvc.return_value.merge_table.assert_called_once_with(
                "INV-1", source_table="TBL-A", target_table=["TBL-B"]
            )

    def test_passes_none_through(self):
        with patch("resto.services.table_service.TableService") as MockSvc:
            api.merge_table("INV-1", "TBL-A")
            MockSvc.return_value.merge_table.assert_called_once_with(
                "INV-1", source_table="TBL-A", target_table=None
            )


class TestGetSelectOptions(RestoPOSTestBase):
    """api.get_select_options — validasi + parsing options."""

    def test_throws_when_doctype_missing(self):
        with self.assertRaises(frappe.ValidationError):
            api.get_select_options("", "status")

    def test_throws_when_fieldname_missing(self):
        with self.assertRaises(frappe.ValidationError):
            api.get_select_options("Table", "")

    def test_throws_when_field_not_found(self):
        mock_meta = MagicMock()
        mock_meta.get_field.return_value = None
        with patch("frappe.get_meta", return_value=mock_meta):
            with self.assertRaises(frappe.ValidationError):
                api.get_select_options("Table", "nonexistent")

    def test_returns_split_options_list(self):
        mock_meta = MagicMock()
        mock_field = MagicMock()
        mock_field.options = "Kosong\nTerisi\nHas Ordered"
        mock_meta.get_field.return_value = mock_field
        with patch("frappe.get_meta", return_value=mock_meta):
            self.assertEqual(
                api.get_select_options("Table", "status"),
                ["Kosong", "Terisi", "Has Ordered"],
            )

    def test_returns_empty_when_no_options(self):
        mock_meta = MagicMock()
        mock_field = MagicMock()
        mock_field.options = ""
        mock_meta.get_field.return_value = mock_field
        with patch("frappe.get_meta", return_value=mock_meta):
            self.assertEqual(api.get_select_options("Table", "status"), [])

    def test_strips_whitespace_and_skips_blank_lines(self):
        mock_meta = MagicMock()
        mock_field = MagicMock()
        mock_field.options = "  Kosong  \n\n  Terisi\n"
        mock_meta.get_field.return_value = mock_field
        with patch("frappe.get_meta", return_value=mock_meta):
            self.assertEqual(
                api.get_select_options("Table", "status"), ["Kosong", "Terisi"]
            )


class TestProcessKitchenPrintingEndpoint(RestoPOSTestBase):
    """api.process_kitchen_printing — verifikasi enqueue dengan kwargs benar."""

    def test_enqueues_worker_with_correct_kwargs(self):
        with patch("frappe.enqueue") as mock_enqueue:
            result = api.process_kitchen_printing("INV-1")
            self.assertTrue(result)
            mock_enqueue.assert_called_once_with(
                "resto.api._process_kitchen_printing_worker",
                queue="long",
                timeout=300,
                pos_invoice="INV-1",
            )

    def test_worker_delegates_to_kitchen_service(self):
        with patch("resto.services.kitchen_service.KitchenService") as MockSvc:
            api._process_kitchen_printing_worker("INV-1")
            MockSvc.return_value.process_kitchen_printing_worker.assert_called_once_with("INV-1")


class TestEnqueueCheckerAfterKitchenEndpoint(RestoPOSTestBase):
    """api.enqueue_checker_after_kitchen — wrapper PrintingService."""

    def test_delegates_with_pos_name_and_branch(self):
        with patch("resto.services.printing_service.PrintingService") as MockSvc:
            MockSvc.return_value.enqueue_checker_after_kitchen.return_value = "OK"
            result = api.enqueue_checker_after_kitchen("POS-1", "BR-1")
            self.assertEqual(result, "OK")
            MockSvc.return_value.enqueue_checker_after_kitchen.assert_called_once_with(
                "POS-1", "BR-1"
            )


class TestCreatePaymentEndpoint(RestoPOSTestBase):
    """api.create_payment — wrapper PaymentService."""

    def test_delegates_with_all_params(self):
        with patch("resto.services.payment_service.PaymentService") as MockSvc:
            MockSvc.return_value.create_payment.return_value = {"ok": True}
            result = api.create_payment("INV-1", 50000, "Cash")
            self.assertEqual(result, {"ok": True})
            MockSvc.return_value.create_payment.assert_called_once_with(
                "INV-1", 50000, "Cash"
            )


class TestCheckPosStatusForUserEndpoint(RestoPOSTestBase):
    """api.check_pos_status_for_user — fallback ke session.user kalau user None."""

    def test_uses_session_user_when_none(self):
        with patch("resto.services.pos_service.POSService") as MockSvc, \
             session_user("ses-user@example.com"):
            MockSvc.return_value.check_pos_status_for_user.return_value = {"end_day_pending": False}
            api.check_pos_status_for_user(user=None)
            MockSvc.return_value.check_pos_status_for_user.assert_called_once_with(
                "ses-user@example.com"
            )

    def test_uses_provided_user_directly(self):
        with patch("resto.services.pos_service.POSService") as MockSvc:
            api.check_pos_status_for_user(user="explicit@example.com")
            MockSvc.return_value.check_pos_status_for_user.assert_called_once_with(
                "explicit@example.com"
            )


class TestOpenPosEndpoint(RestoPOSTestBase):
    """api.open_pos — POS Opening Entry creation + lookup fallback."""

    def test_throws_when_no_pos_profile_for_user(self):
        with session_user("u@x.com"), patch("frappe.get_all", return_value=[]):
            with self.assertRaises(frappe.ValidationError):
                api.open_pos()

    def test_throws_when_branch_not_resolved(self):
        with session_user("u@x.com"), \
             patch("frappe.get_all", return_value=["PP-1"]), \
             patch("frappe.db.get_value", return_value=None):
            with self.assertRaises(frappe.ValidationError):
                api.open_pos(pos_profile="PP-1")

    def test_creates_opening_entry_with_balance_details(self):
        """Patch resto.api.now_datetime supaya tidak trigger frappe.get_cached_doc
        (yang akan poison redis dengan MagicMock saat frappe.get_doc di-patch)."""
        captured = {}

        def fake_get_doc(doc_dict):
            doc = MagicMock()
            doc.name = "POE-1"
            doc.append.side_effect = lambda field, row: captured.setdefault("balance_row", row)
            captured["doc_dict"] = doc_dict
            return doc

        with session_user("u@x.com"), \
             patch("resto.api.now_datetime", return_value="FIXED-DT"), \
             patch("frappe.get_doc", side_effect=fake_get_doc), \
             patch("frappe.db.get_value", return_value=None):
            result = api.open_pos(pos_profile="PP-1", opening_balance=100, branch="BR-1")

        self.assertEqual(result["name"], "POE-1")
        self.assertEqual(result["pos_profile"], "PP-1")
        self.assertEqual(result["branch"], "BR-1")
        self.assertEqual(captured["doc_dict"]["doctype"], "POS Opening Entry")
        self.assertEqual(captured["doc_dict"]["opening_balance"], 100)
        self.assertEqual(captured["balance_row"], {"mode_of_payment": "Cash", "opening_amount": 100})

    def test_falls_back_to_branch_from_pos_profile(self):
        with session_user("u@x.com"), \
             patch("resto.api.now_datetime", return_value="FIXED-DT"), \
             patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.get_value", return_value="BR-AUTO") as mock_dbget:
            mock_doc = MagicMock(); mock_doc.name = "POE-1"
            mock_get_doc.return_value = mock_doc
            result = api.open_pos(pos_profile="PP-1", opening_balance=0)
            self.assertEqual(result["branch"], "BR-AUTO")
            mock_dbget.assert_called_once_with("POS Profile", "PP-1", "branch")

    def test_falls_back_to_pos_profile_lookup_by_user(self):
        with session_user("u@x.com"), \
             patch("resto.api.now_datetime", return_value="FIXED-DT"), \
             patch("frappe.get_all", return_value=["PP-AUTO"]) as mock_getall, \
             patch("frappe.get_doc") as mock_get_doc, \
             patch("frappe.db.get_value", return_value="BR-1"):
            mock_doc = MagicMock(); mock_doc.name = "POE-1"
            mock_get_doc.return_value = mock_doc
            result = api.open_pos(opening_balance=0)
            self.assertEqual(result["pos_profile"], "PP-AUTO")
            mock_getall.assert_called_once_with(
                "POS Profile User", filters={"user": "u@x.com"}, pluck="parent", limit=1
            )
