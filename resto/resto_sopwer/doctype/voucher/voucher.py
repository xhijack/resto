# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime, nowdate


class Voucher(Document):
    def autoname(self):
        if not self.code:
            self.code = self._generate_unique_code()
        self.name = self.code

    @staticmethod
    def _generate_unique_code() -> str:
        code = frappe.generate_hash(length=10).upper()
        while frappe.db.exists("Voucher", code):
            code = frappe.generate_hash(length=10).upper()
        return code

    def before_insert(self):
        if not self.status:
            self.status = "Active"
        if not self.issued_at:
            self.issued_at = now_datetime()
        if not self.source:
            self.source = "Free"

    def validate(self):
        self._validate_kind_fields()
        self._validate_validity_range()

    def _validate_kind_fields(self):
        if self.voucher_kind == "Nominal":
            if not self.voucher_value or self.voucher_value <= 0:
                frappe.throw(
                    "Nominal voucher requires voucher_value greater than zero",
                    title="Invalid Voucher Value",
                )
        elif self.voucher_kind == "Free Item":
            if not self.free_item:
                frappe.throw(
                    "Free Item voucher requires free_item to be set",
                    title="Invalid Voucher",
                )

    def _validate_validity_range(self):
        if not self.valid_upto:
            return
        valid_from = getdate(self.valid_from) if self.valid_from else getdate(nowdate())
        valid_upto = getdate(self.valid_upto)
        if valid_upto < valid_from:
            frappe.throw(
                f"valid_upto ({valid_upto}) must be on or after valid_from ({valid_from})",
                title="Invalid Validity Range",
            )

    def is_redeemable(self) -> bool:
        if self.status != "Active":
            return False
        today = getdate(nowdate())
        if self.valid_from and getdate(self.valid_from) > today:
            return False
        if self.valid_upto and getdate(self.valid_upto) < today:
            return False
        return True

    def redeem(self, pos_invoice_name: str):
        if self.status != "Active":
            frappe.throw(
                f"Voucher {self.code} cannot be redeemed (status={self.status})",
                title="Voucher Not Redeemable",
            )
        if not self.is_redeemable():
            frappe.throw(
                f"Voucher {self.code} is outside its validity window",
                title="Voucher Not Redeemable",
            )
        redeemed_at = now_datetime()
        frappe.db.set_value(
            "Voucher",
            self.name,
            {
                "status": "Redeemed",
                "redeemed_via_invoice": pos_invoice_name,
                "redeemed_at": redeemed_at,
            },
            update_modified=True,
        )
        self.status = "Redeemed"
        self.redeemed_via_invoice = pos_invoice_name
        self.redeemed_at = redeemed_at

    def cancel_voucher(self):
        if self.status == "Redeemed":
            frappe.throw(
                f"Voucher {self.code} is already redeemed and cannot be cancelled",
                title="Cannot Cancel Redeemed Voucher",
            )
        frappe.db.set_value(
            "Voucher", self.name, "status", "Cancelled", update_modified=True
        )
        self.status = "Cancelled"

    def un_redeem(self):
        if self.status != "Redeemed":
            frappe.throw(
                f"Voucher {self.code} is not in Redeemed state (current={self.status})",
                title="Cannot Un-Redeem",
            )
        frappe.db.set_value(
            "Voucher",
            self.name,
            {
                "status": "Active",
                "redeemed_via_invoice": None,
                "redeemed_at": None,
            },
            update_modified=True,
        )
        self.status = "Active"
        self.redeemed_via_invoice = None
        self.redeemed_at = None
