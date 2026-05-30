"""
Unit tests for Voucher DocType controller.

Phase 1 scope: voucher_kind="Nominal" only (Free Item defer ke Phase 2).
Tests are pure DocType lifecycle — no POS Invoice integration here
(integration tests live in test_voucher_integration_pos.py).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestVoucherController(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user("Guest")
        super().tearDown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_voucher(self, **overrides):
        defaults = {
            "doctype": "Voucher",
            "voucher_kind": "Nominal",
            "voucher_value": 50000,
            "valid_from": nowdate(),
            "valid_upto": add_days(nowdate(), 30),
            "source": "Free",
        }
        defaults.update(overrides)
        return frappe.get_doc(defaults).insert(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Autoname & defaults
    # ------------------------------------------------------------------

    def test_create_voucher_generates_unique_code(self):
        v1 = self._make_voucher()
        v2 = self._make_voucher()
        self.assertNotEqual(v1.code, v2.code)
        self.assertEqual(len(v1.code), 10)
        self.assertTrue(v1.code.isupper())

    def test_voucher_default_status_is_active(self):
        v = self._make_voucher()
        self.assertEqual(v.status, "Active")

    def test_voucher_issued_at_set_on_insert(self):
        v = self._make_voucher()
        self.assertIsNotNone(v.issued_at)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def test_nominal_voucher_requires_positive_value(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_voucher(voucher_value=0)

    def test_nominal_voucher_rejects_negative_value(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_voucher(voucher_value=-100)

    def test_voucher_rejects_expiry_before_valid_from(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_voucher(
                valid_from=nowdate(),
                valid_upto=add_days(nowdate(), -1),
            )

    # ------------------------------------------------------------------
    # is_redeemable
    # ------------------------------------------------------------------

    def test_active_voucher_within_validity_is_redeemable(self):
        v = self._make_voucher()
        self.assertTrue(v.is_redeemable())

    def test_expired_voucher_is_not_redeemable(self):
        v = self._make_voucher(
            valid_from=add_days(nowdate(), -30),
            valid_upto=add_days(nowdate(), -1),
        )
        self.assertFalse(v.is_redeemable())

    def test_not_yet_valid_voucher_is_not_redeemable(self):
        v = self._make_voucher(
            valid_from=add_days(nowdate(), 1),
            valid_upto=add_days(nowdate(), 30),
        )
        self.assertFalse(v.is_redeemable())

    # ------------------------------------------------------------------
    # redeem
    # ------------------------------------------------------------------

    def test_redeem_marks_status_redeemed_and_sets_invoice_link(self):
        v = self._make_voucher()
        v.redeem(pos_invoice_name="POS-INV-0001")
        v.reload()
        self.assertEqual(v.status, "Redeemed")
        self.assertEqual(v.redeemed_via_invoice, "POS-INV-0001")
        self.assertIsNotNone(v.redeemed_at)

    def test_double_redeem_raises_error(self):
        v = self._make_voucher()
        v.redeem(pos_invoice_name="POS-INV-0001")
        with self.assertRaises(frappe.ValidationError):
            v.redeem(pos_invoice_name="POS-INV-0002")

    def test_redeem_expired_voucher_raises_error(self):
        v = self._make_voucher(
            valid_from=add_days(nowdate(), -30),
            valid_upto=add_days(nowdate(), -1),
        )
        with self.assertRaises(frappe.ValidationError):
            v.redeem(pos_invoice_name="POS-INV-0001")

    def test_redeem_cancelled_voucher_raises_error(self):
        v = self._make_voucher()
        v.cancel_voucher()
        with self.assertRaises(frappe.ValidationError):
            v.redeem(pos_invoice_name="POS-INV-0001")

    # ------------------------------------------------------------------
    # cancel_voucher
    # ------------------------------------------------------------------

    def test_cancel_active_voucher_marks_cancelled(self):
        v = self._make_voucher()
        v.cancel_voucher()
        v.reload()
        self.assertEqual(v.status, "Cancelled")

    def test_cancel_redeemed_voucher_raises_error(self):
        v = self._make_voucher()
        v.redeem(pos_invoice_name="POS-INV-0001")
        with self.assertRaises(frappe.ValidationError):
            v.cancel_voucher()

    # ------------------------------------------------------------------
    # un_redeem (rollback redeem state)
    # ------------------------------------------------------------------

    def test_un_redeem_reverts_status_to_active(self):
        v = self._make_voucher()
        v.redeem(pos_invoice_name="POS-INV-0001")
        v.un_redeem()
        v.reload()
        self.assertEqual(v.status, "Active")
        self.assertIsNone(v.redeemed_via_invoice)
        self.assertIsNone(v.redeemed_at)
