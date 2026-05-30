# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class VoucherBatch(Document):
    def validate(self):
        self._validate_kind_fields()
        self._validate_voucher_count()

    def _validate_kind_fields(self):
        if self.voucher_kind == "Nominal":
            if not self.voucher_value or self.voucher_value <= 0:
                frappe.throw(
                    "Nominal batch requires voucher_value greater than zero",
                    title="Invalid Voucher Value",
                )
        elif self.voucher_kind == "Free Item":
            if not self.free_item:
                frappe.throw(
                    "Free Item batch requires free_item to be set",
                    title="Invalid Voucher Batch",
                )

    def _validate_voucher_count(self):
        if not self.voucher_count or self.voucher_count <= 0:
            frappe.throw(
                "voucher_count must be a positive integer",
                title="Invalid Voucher Count",
            )

    @frappe.whitelist()
    def generate_vouchers(self):
        if self.is_generated:
            frappe.throw(
                f"Voucher Batch {self.name} has already been generated "
                f"({self.generated_count} vouchers). Create a new batch if more are needed.",
                title="Batch Already Generated",
            )

        for _ in range(int(self.voucher_count)):
            voucher_doc = {
                "doctype": "Voucher",
                "voucher_kind": self.voucher_kind,
                "voucher_value": self.voucher_value,
                "free_item": self.free_item,
                "valid_upto": self.valid_upto,
                "source": "Free",
                "batch_id": self.name,
            }
            frappe.get_doc(voucher_doc).insert(ignore_permissions=True)

        generated_at = now_datetime()
        frappe.db.set_value(
            "Voucher Batch",
            self.name,
            {
                "is_generated": 1,
                "generated_count": int(self.voucher_count),
                "generated_at": generated_at,
                "generated_by": frappe.session.user,
            },
            update_modified=True,
        )
        self.is_generated = 1
        self.generated_count = int(self.voucher_count)
        self.generated_at = generated_at
        self.generated_by = frappe.session.user
