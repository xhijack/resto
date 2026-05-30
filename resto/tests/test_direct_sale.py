"""
Integration tests for create_direct_sale_invoice — non-kitchen sale flow.

Direct Sale Mode jual item non-kitchen (voucher) tanpa lewat
send_to_kitchen. Endpoint:
  resto.api.create_direct_sale_invoice(payload, payments)

Behavior:
  - Validate items semua is_voucher_item=1 (voucher-only cart Phase 1)
  - Create POS Invoice, set as_pos=1
  - Skip kitchen routing entirely
  - Submit immediately with payments
  - Existing voucher_hooks.issue_vouchers_from_pos_invoice fires on_submit
"""

import frappe
import json

from resto.tests.resto_pos_test_base import RestoPOSTestBase


class TestDirectSaleInvoice(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self._ensure_voucher_custom_fields_on_item()
        self.voucher_item_code = self._make_voucher_item(
            "_Test Direct Voucher Rp50K", rate=50000
        )
        # Cleanup any voucher rows from prior runs
        frappe.db.delete("Voucher", {"source": "Sold"})

    def tearDown(self):
        frappe.db.delete("Voucher", {"source": "Sold"})
        super().tearDown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_voucher_custom_fields_on_item():
        for cf in [
            {
                "fieldname": "is_voucher_item",
                "label": "Is Voucher Item",
                "fieldtype": "Check",
                "default": "0",
                "insert_after": "stock_uom",
            },
            {
                "fieldname": "voucher_validity_days",
                "label": "Voucher Validity Days",
                "fieldtype": "Int",
                "default": "90",
                "insert_after": "is_voucher_item",
                "depends_on": "eval:doc.is_voucher_item",
            },
        ]:
            if not frappe.db.exists(
                "Custom Field", {"dt": "Item", "fieldname": cf["fieldname"]}
            ):
                frappe.get_doc(
                    {"doctype": "Custom Field", "dt": "Item", **cf}
                ).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Item")

    def _make_voucher_item(self, item_code, rate):
        if frappe.db.exists("Item", item_code):
            item = frappe.get_doc("Item", item_code)
            item.is_voucher_item = 1
            item.voucher_validity_days = 90
            item.standard_rate = rate
            item.save(ignore_permissions=True)
            return item_code
        frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_voucher_item": 1,
                "voucher_validity_days": 90,
                "standard_rate": rate,
            }
        ).insert(ignore_permissions=True)
        return item_code

    def _payload(self, items=None, **overrides):
        if items is None:
            items = [
                {
                    "item_code": self.voucher_item_code,
                    "qty": 1,
                    "rate": 50000,
                }
            ]
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "items": items,
        }
        payload.update(overrides)
        return payload

    def _call_endpoint(self, payload, payments):
        from resto.api import create_direct_sale_invoice

        return create_direct_sale_invoice(
            payload=json.dumps(payload),
            payments=json.dumps(payments),
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_create_direct_sale_invoice_returns_paid_invoice(self):
        result = self._call_endpoint(
            self._payload(),
            [{"mode_of_payment": self.mode_of_payment, "amount": 50000}],
        )
        self.assertIn("invoice_name", result)
        invoice = frappe.get_doc("POS Invoice", result["invoice_name"])
        self.assertEqual(invoice.docstatus, 1)  # Submitted
        self.assertEqual(invoice.status, "Paid")

    def test_direct_sale_skips_kitchen_routing(self):
        """Item tanpa resto_menu link & tanpa kitchen station tidak boleh
        throw kitchen error. Direct sale skip send_to_kitchen entirely."""
        # voucher_item_code TIDAK punya Resto Menu / Branch Menu kitchen
        # mapping. Order menu biasa akan gagal/silent-drop. Direct sale OK.
        result = self._call_endpoint(
            self._payload(),
            [{"mode_of_payment": self.mode_of_payment, "amount": 50000}],
        )
        self.assertIn("invoice_name", result)

    def test_direct_sale_triggers_voucher_issuance_hook(self):
        result = self._call_endpoint(
            self._payload(
                items=[
                    {
                        "item_code": self.voucher_item_code,
                        "qty": 2,
                        "rate": 50000,
                    }
                ]
            ),
            [{"mode_of_payment": self.mode_of_payment, "amount": 100000}],
        )
        count = frappe.db.count(
            "Voucher", {"sold_via_invoice": result["invoice_name"]}
        )
        self.assertEqual(count, 2)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def test_direct_sale_with_non_voucher_item_throws_validation(self):
        regular_item = self.item.name  # is_voucher_item=0 by default
        with self.assertRaises(frappe.ValidationError):
            self._call_endpoint(
                self._payload(
                    items=[
                        {"item_code": regular_item, "qty": 1, "rate": 15000}
                    ]
                ),
                [{"mode_of_payment": self.mode_of_payment, "amount": 15000}],
            )

    def test_direct_sale_mixed_voucher_and_regular_item_throws(self):
        regular_item = self.item.name
        with self.assertRaises(frappe.ValidationError):
            self._call_endpoint(
                self._payload(
                    items=[
                        {
                            "item_code": self.voucher_item_code,
                            "qty": 1,
                            "rate": 50000,
                        },
                        {"item_code": regular_item, "qty": 1, "rate": 15000},
                    ]
                ),
                [{"mode_of_payment": self.mode_of_payment, "amount": 65000}],
            )

    def test_direct_sale_payment_must_cover_grand_total(self):
        with self.assertRaises(frappe.ValidationError):
            self._call_endpoint(
                self._payload(),
                [{"mode_of_payment": self.mode_of_payment, "amount": 30000}],
            )

    def test_direct_sale_empty_items_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._call_endpoint(
                self._payload(items=[]),
                [{"mode_of_payment": self.mode_of_payment, "amount": 0}],
            )

    def test_direct_sale_empty_payments_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._call_endpoint(self._payload(), [])

    # ------------------------------------------------------------------
    # Guards (defense-in-depth: clear error vs deep ERPNext 500)
    # ------------------------------------------------------------------

    def test_direct_sale_customer_not_found_throws_clear(self):
        with self.assertRaises(frappe.ValidationError) as ctx:
            self._call_endpoint(
                self._payload(customer="_NonExistentCustomer_XYZ"),
                [{"mode_of_payment": self.mode_of_payment, "amount": 50000}],
            )
        self.assertIn("Customer", str(ctx.exception))

    def test_direct_sale_mop_not_found_throws_clear(self):
        with self.assertRaises(frappe.ValidationError) as ctx:
            self._call_endpoint(
                self._payload(),
                [{"mode_of_payment": "_NonExistentMOP_XYZ", "amount": 50000}],
            )
        self.assertIn("Mode of Payment", str(ctx.exception))

    def test_direct_sale_pos_profile_not_found_throws_clear(self):
        with self.assertRaises(frappe.ValidationError) as ctx:
            self._call_endpoint(
                self._payload(pos_profile="_NonExistentProfile_XYZ"),
                [{"mode_of_payment": self.mode_of_payment, "amount": 50000}],
            )
        self.assertIn("POS Profile", str(ctx.exception))

    # ------------------------------------------------------------------
    # Issued vouchers in response (Phase 2)
    # ------------------------------------------------------------------

    def test_direct_sale_returns_issued_vouchers_list(self):
        result = self._call_endpoint(
            self._payload(
                items=[
                    {
                        "item_code": self.voucher_item_code,
                        "qty": 2,
                        "rate": 50000,
                    }
                ]
            ),
            [{"mode_of_payment": self.mode_of_payment, "amount": 100000}],
        )
        vouchers = result.get("issued_vouchers")
        self.assertIsInstance(vouchers, list)
        self.assertEqual(len(vouchers), 2)
        for v in vouchers:
            self.assertIn("code", v)
            self.assertEqual(v["voucher_value"], 50000)
            self.assertIn("valid_from", v)
            self.assertIn("valid_upto", v)
            self.assertEqual(v["status"], "Active")

    # ------------------------------------------------------------------
    # Payment via PaymentService (split + change)
    # ------------------------------------------------------------------

    def test_direct_sale_overpay_returns_change_amount(self):
        result = self._call_endpoint(
            self._payload(),
            [{"mode_of_payment": self.mode_of_payment, "amount": 75000}],
        )
        self.assertEqual(result.get("change_amount"), 25000)
        self.assertEqual(result.get("total_paid"), 75000)
