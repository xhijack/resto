# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

"""Voucher lifecycle hooks tied to POS Invoice."""

import frappe
from frappe.utils import add_days, nowdate

DEFAULT_VOUCHER_VALIDITY_DAYS = 90


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
