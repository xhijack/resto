"""
Integration tests for voucher redemption at POS — validate API + on_submit
hook + on_cancel hook.

Redemption flow:
  1. Cashier inputs voucher code at payment screen.
  2. Frontend calls validate_voucher_code(code) and receives value.
  3. Frontend pushes payment row {mode_of_payment="Voucher",
     voucher_code=<code>, amount=<voucher_value>}.
  4. POS Invoice submit triggers redeem_vouchers_on_pos_invoice_submit:
       - Validates each voucher payment row
       - Marks Voucher.status = Redeemed
       - Sets redeemed_via_invoice + redeemed_at
  5. POS Invoice cancel triggers unredeem_vouchers_on_pos_invoice_cancel:
       - Reverts Voucher.status to Active
       - Clears redeemed_via_invoice / redeemed_at

Rule: payment.amount must equal voucher.voucher_value (single-use, no
partial; cashier always applies the full nominal).
"""

import frappe
from frappe.utils import add_days, nowdate

from resto.tests.resto_pos_test_base import RestoPOSTestBase

VOUCHER_MOP = "Voucher"


class TestVoucherRedemption(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self._ensure_voucher_mop_in_pos_profile()
        # Clean prior voucher rows so cross-test pollution doesn't bias
        # status assertions
        frappe.db.delete("Voucher")

    def tearDown(self):
        frappe.db.delete("Voucher")
        super().tearDown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_voucher_mop_in_pos_profile(self):
        existing = [
            p.mode_of_payment for p in self.pos_profile.payments
        ]
        if VOUCHER_MOP not in existing:
            self.pos_profile.append("payments", {"mode_of_payment": VOUCHER_MOP})
            self.pos_profile.save(ignore_permissions=True)

    def _make_active_voucher(self, value=50000, valid_days=30, source="Sold"):
        return frappe.get_doc(
            {
                "doctype": "Voucher",
                "voucher_kind": "Nominal",
                "voucher_value": value,
                "valid_from": nowdate(),
                "valid_upto": add_days(nowdate(), valid_days),
                "source": source,
            }
        ).insert(ignore_permissions=True)

    def _submit_invoice_with_voucher_payment(self, voucher_code, amount, extra_cash=0):
        total = amount + extra_cash
        payments = [
            {
                "mode_of_payment": VOUCHER_MOP,
                "amount": amount,
                "voucher_code": voucher_code,
            }
        ]
        if extra_cash > 0:
            payments.append(
                {"mode_of_payment": self.mode_of_payment, "amount": extra_cash}
            )
        return self._create_test_pos_invoice(
            items=[
                {
                    "item_code": self.item.name,
                    "qty": 1,
                    "rate": total,
                    "amount": total,
                }
            ],
            payments=payments,
            submit=True,
        )

    # ------------------------------------------------------------------
    # validate_voucher_code API
    # ------------------------------------------------------------------

    def test_api_returns_valid_for_active_voucher(self):
        from resto.api import validate_voucher_code

        v = self._make_active_voucher(value=50000)
        result = validate_voucher_code(v.code)
        self.assertTrue(result["valid"])
        self.assertEqual(result["value"], 50000)
        self.assertEqual(result["kind"], "Nominal")
        self.assertIsNone(result.get("error_message"))

    def test_api_returns_invalid_for_unknown_code(self):
        from resto.api import validate_voucher_code

        result = validate_voucher_code("DOES-NOT-EXIST")
        self.assertFalse(result["valid"])
        self.assertIsNotNone(result["error_message"])

    def test_api_returns_invalid_for_expired_voucher(self):
        from resto.api import validate_voucher_code

        v = frappe.get_doc(
            {
                "doctype": "Voucher",
                "voucher_kind": "Nominal",
                "voucher_value": 50000,
                "valid_from": add_days(nowdate(), -30),
                "valid_upto": add_days(nowdate(), -1),
                "source": "Free",
            }
        ).insert(ignore_permissions=True)
        result = validate_voucher_code(v.code)
        self.assertFalse(result["valid"])
        self.assertIn("expired", result["error_message"].lower())

    def test_api_returns_invalid_for_redeemed_voucher(self):
        from resto.api import validate_voucher_code

        v = self._make_active_voucher()
        v.redeem("FAKE-INV-001")
        result = validate_voucher_code(v.code)
        self.assertFalse(result["valid"])
        self.assertIn("redeemed", result["error_message"].lower())

    def test_api_returns_invalid_for_cancelled_voucher(self):
        from resto.api import validate_voucher_code

        v = self._make_active_voucher()
        v.cancel_voucher()
        result = validate_voucher_code(v.code)
        self.assertFalse(result["valid"])

    # ------------------------------------------------------------------
    # Redemption hook on_submit
    # ------------------------------------------------------------------

    def test_voucher_payment_marks_voucher_redeemed(self):
        v = self._make_active_voucher(value=50000)
        invoice = self._submit_invoice_with_voucher_payment(v.code, amount=50000)
        v.reload()
        self.assertEqual(v.status, "Redeemed")
        self.assertEqual(v.redeemed_via_invoice, invoice.name)
        self.assertIsNotNone(v.redeemed_at)

    def test_voucher_payment_amount_mismatch_throws(self):
        v = self._make_active_voucher(value=50000)
        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice_with_voucher_payment(v.code, amount=30000)
        v.reload()
        self.assertEqual(v.status, "Active")

    def test_voucher_payment_with_unknown_code_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice_with_voucher_payment("NONEXISTENT", amount=50000)

    def test_voucher_payment_with_expired_code_throws(self):
        expired = frappe.get_doc(
            {
                "doctype": "Voucher",
                "voucher_kind": "Nominal",
                "voucher_value": 50000,
                "valid_from": add_days(nowdate(), -30),
                "valid_upto": add_days(nowdate(), -1),
                "source": "Free",
            }
        ).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice_with_voucher_payment(expired.code, amount=50000)

    def test_voucher_payment_with_already_redeemed_code_throws(self):
        v = self._make_active_voucher(value=50000)
        v.redeem("OTHER-INV-001")
        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice_with_voucher_payment(v.code, amount=50000)

    def test_voucher_plus_cash_payment_redeems_voucher_only(self):
        v = self._make_active_voucher(value=50000)
        invoice = self._submit_invoice_with_voucher_payment(
            v.code, amount=50000, extra_cash=30000
        )
        v.reload()
        self.assertEqual(v.status, "Redeemed")
        self.assertEqual(v.redeemed_via_invoice, invoice.name)

    def test_multiple_vouchers_in_one_invoice_all_redeemed(self):
        v1 = self._make_active_voucher(value=50000)
        v2 = self._make_active_voucher(value=25000)
        payments = [
            {
                "mode_of_payment": VOUCHER_MOP,
                "amount": 50000,
                "voucher_code": v1.code,
            },
            {
                "mode_of_payment": VOUCHER_MOP,
                "amount": 25000,
                "voucher_code": v2.code,
            },
        ]
        invoice = self._create_test_pos_invoice(
            items=[
                {
                    "item_code": self.item.name,
                    "qty": 1,
                    "rate": 75000,
                    "amount": 75000,
                }
            ],
            payments=payments,
            submit=True,
        )
        v1.reload()
        v2.reload()
        self.assertEqual(v1.status, "Redeemed")
        self.assertEqual(v2.status, "Redeemed")
        self.assertEqual(v1.redeemed_via_invoice, invoice.name)
        self.assertEqual(v2.redeemed_via_invoice, invoice.name)

    def test_non_voucher_payment_does_not_touch_voucher_records(self):
        # Plain cash invoice, no voucher payment
        self._create_test_pos_invoice(qty=1, rate=100, submit=True)
        count_redeemed = frappe.db.count("Voucher", {"status": "Redeemed"})
        self.assertEqual(count_redeemed, 0)

    # ------------------------------------------------------------------
    # Cancel hook on_cancel
    # ------------------------------------------------------------------

    def test_cancel_invoice_unredeems_voucher(self):
        v = self._make_active_voucher(value=50000)
        invoice = self._submit_invoice_with_voucher_payment(v.code, amount=50000)
        invoice.reload()
        invoice.cancel()
        v.reload()
        self.assertEqual(v.status, "Active")
        self.assertIsNone(v.redeemed_via_invoice)
        self.assertIsNone(v.redeemed_at)
