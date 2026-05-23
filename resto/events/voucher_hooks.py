# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

"""Voucher lifecycle hooks tied to POS Invoice."""

import frappe
from frappe.utils import add_days, flt, nowdate

DEFAULT_VOUCHER_VALIDITY_DAYS = 90
VOUCHER_MODE_OF_PAYMENT = "Voucher"
AMOUNT_TOLERANCE = 0.01


def issue_vouchers_from_pos_invoice(doc, method=None):
    """on_submit hook: materialize Voucher records for each voucher item line.

    For every POS Invoice Item where the linked Item has is_voucher_item=1,
    create item.qty Voucher records with:
      - source = "Sold"
      - sold_via_invoice = invoice.name
      - voucher_value = item.rate
      - valid_upto = today + Item.voucher_validity_days (fallback 90 days)
    """
    if not doc.get("items"):
        return

    for item_row in doc.items:
        item_code = item_row.get("item_code")
        if not item_code:
            continue
        if not _is_voucher_item(item_code):
            continue

        validity_days = _voucher_validity_days(item_code)
        valid_upto = add_days(nowdate(), validity_days)
        rate = item_row.get("rate") or 0
        qty = int(item_row.get("qty") or 0)

        for _ in range(qty):
            voucher = frappe.get_doc(
                {
                    "doctype": "Voucher",
                    "voucher_kind": "Nominal",
                    "voucher_value": rate,
                    "valid_from": nowdate(),
                    "valid_upto": valid_upto,
                    "source": "Sold",
                    "sold_via_invoice": doc.name,
                }
            )
            voucher.insert(ignore_permissions=True)


def _is_voucher_item(item_code: str) -> bool:
    flag = frappe.db.get_value("Item", item_code, "is_voucher_item")
    return bool(flag)


def _voucher_validity_days(item_code: str) -> int:
    days = frappe.db.get_value("Item", item_code, "voucher_validity_days") or 0
    days = int(days)
    return days if days > 0 else DEFAULT_VOUCHER_VALIDITY_DAYS


# ---------------------------------------------------------------------------
# Redemption flow
# ---------------------------------------------------------------------------


def _iter_voucher_payments(doc):
    for payment in doc.get("payments") or []:
        if payment.get("mode_of_payment") != VOUCHER_MODE_OF_PAYMENT:
            continue
        yield payment


def validate_voucher_payments(doc, method=None):
    """before_submit: each voucher payment row must reference an active,
    in-window voucher whose value matches payment.amount exactly."""
    for payment in _iter_voucher_payments(doc):
        code = payment.get("voucher_code")
        if not code:
            frappe.throw(
                "Voucher payment row requires voucher_code",
                title="Missing Voucher Code",
            )
        if not frappe.db.exists("Voucher", code):
            frappe.throw(
                f"Voucher {code} not found",
                title="Invalid Voucher",
            )
        voucher = frappe.get_doc("Voucher", code)
        if not voucher.is_redeemable():
            frappe.throw(
                f"Voucher {code} is not redeemable (status={voucher.status})",
                title="Voucher Not Redeemable",
            )
        payment_amount = flt(payment.get("amount") or 0)
        voucher_value = flt(voucher.voucher_value or 0)
        if abs(payment_amount - voucher_value) > AMOUNT_TOLERANCE:
            frappe.throw(
                f"Voucher payment amount ({payment_amount}) must equal voucher "
                f"value ({voucher_value}); single-use vouchers cannot be partially applied",
                title="Voucher Amount Mismatch",
            )


def redeem_vouchers_on_pos_invoice_submit(doc, method=None):
    """on_submit: mark each voucher payment's voucher as Redeemed.

    Validation already ran in before_submit; this hook only mutates state.
    """
    for payment in _iter_voucher_payments(doc):
        code = payment.get("voucher_code")
        if not code:
            continue
        voucher = frappe.get_doc("Voucher", code)
        if voucher.status != "Active":
            # Defensive: validation should have prevented this, but skip
            # any unexpected state to avoid raising in on_submit.
            continue
        voucher.redeem(pos_invoice_name=doc.name)


def unredeem_vouchers_on_pos_invoice_cancel(doc, method=None):
    """on_cancel: revert each voucher this invoice redeemed back to Active."""
    for payment in _iter_voucher_payments(doc):
        code = payment.get("voucher_code")
        if not code:
            continue
        if not frappe.db.exists("Voucher", code):
            continue
        voucher = frappe.get_doc("Voucher", code)
        if (
            voucher.status == "Redeemed"
            and voucher.redeemed_via_invoice == doc.name
        ):
            voucher.un_redeem()
