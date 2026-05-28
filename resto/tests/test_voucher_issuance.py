"""
Integration tests for voucher issuance hook on POS Invoice submit.

Hook scans POS Invoice items for is_voucher_item=1 and auto-creates
Voucher records (source=Sold, sold_via_invoice=invoice) with value
inherited from item rate and expiry from item's voucher_validity_days
(default 90 days).
"""

import frappe
from frappe.utils import add_days, nowdate

from resto.tests.resto_pos_test_base import RestoPOSTestBase


VOUCHER_ITEM_50K = "_Test Voucher Rp50K"
VOUCHER_ITEM_100K = "_Test Voucher Rp100K"
VOUCHER_ITEM_NO_VALIDITY = "_Test Voucher Default Validity"


class TestVoucherIssuanceHook(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self._ensure_voucher_custom_fields_on_item()
        self.voucher_item_50k = self._make_voucher_item(
            VOUCHER_ITEM_50K, rate=50000, validity_days=30
        )
        # Clean any leftover Voucher rows from previous tests
        frappe.db.delete("Voucher", {"source": "Sold"})

    def tearDown(self):
        frappe.db.delete("Voucher", {"source": "Sold"})
        super().tearDown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_voucher_custom_fields_on_item():
        """Install Item custom fields idempotently for this test."""
        fields = [
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
        ]
        for cf in fields:
            if not frappe.db.exists(
                "Custom Field", {"dt": "Item", "fieldname": cf["fieldname"]}
            ):
                doc = {"doctype": "Custom Field", "dt": "Item", **cf}
                frappe.get_doc(doc).insert(ignore_permissions=True)
        frappe.clear_cache(doctype="Item")

    def _make_voucher_item(self, item_code, rate, validity_days=None):
        if frappe.db.exists("Item", item_code):
            item = frappe.get_doc("Item", item_code)
            item.is_voucher_item = 1
            if validity_days is not None:
                item.voucher_validity_days = validity_days
            item.save(ignore_permissions=True)
            return item
        return frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": item_code,
                "item_name": item_code,
                "item_group": "All Item Groups",
                "stock_uom": "Nos",
                "is_stock_item": 0,
                "is_voucher_item": 1,
                "voucher_validity_days": validity_days if validity_days is not None else 90,
                "standard_rate": rate,
            }
        ).insert(ignore_permissions=True)

    def _submit_invoice_with_voucher_item(self, item_code, qty, rate):
        amount = qty * rate
        invoice = self._create_test_pos_invoice(
            items=[
                {"item_code": item_code, "qty": qty, "rate": rate, "amount": amount}
            ],
            payments=[{"mode_of_payment": self.mode_of_payment, "amount": amount}],
            submit=True,
        )
        return invoice

    # ------------------------------------------------------------------
    # Issuance count + linkage
    # ------------------------------------------------------------------

    def test_voucher_item_qty_2_creates_2_voucher_records(self):
        invoice = self._submit_invoice_with_voucher_item(VOUCHER_ITEM_50K, qty=2, rate=50000)
        count = frappe.db.count("Voucher", {"sold_via_invoice": invoice.name})
        self.assertEqual(count, 2)

    def test_generated_voucher_source_is_sold(self):
        invoice = self._submit_invoice_with_voucher_item(VOUCHER_ITEM_50K, qty=1, rate=50000)
        sources = frappe.get_all(
            "Voucher", filters={"sold_via_invoice": invoice.name}, pluck="source"
        )
        self.assertEqual(sources, ["Sold"])

    def test_generated_voucher_starts_active(self):
        invoice = self._submit_invoice_with_voucher_item(VOUCHER_ITEM_50K, qty=1, rate=50000)
        statuses = frappe.get_all(
            "Voucher", filters={"sold_via_invoice": invoice.name}, pluck="status"
        )
        self.assertEqual(statuses, ["Active"])

    # ------------------------------------------------------------------
    # Value inheritance
    # ------------------------------------------------------------------

    def test_generated_voucher_value_matches_item_rate(self):
        invoice = self._submit_invoice_with_voucher_item(VOUCHER_ITEM_50K, qty=1, rate=75000)
        values = frappe.get_all(
            "Voucher", filters={"sold_via_invoice": invoice.name}, pluck="voucher_value"
        )
        self.assertEqual(values, [75000])

    def test_generated_voucher_kind_is_nominal(self):
        invoice = self._submit_invoice_with_voucher_item(VOUCHER_ITEM_50K, qty=1, rate=50000)
        kinds = frappe.get_all(
            "Voucher", filters={"sold_via_invoice": invoice.name}, pluck="voucher_kind"
        )
        self.assertEqual(kinds, ["Nominal"])

    # ------------------------------------------------------------------
    # Validity inheritance from Item field
    # ------------------------------------------------------------------

    def test_validity_from_item_voucher_validity_days(self):
        # voucher_item_50k was created with validity_days=30
        invoice = self._submit_invoice_with_voucher_item(VOUCHER_ITEM_50K, qty=1, rate=50000)
        valid_upto = frappe.db.get_value(
            "Voucher", {"sold_via_invoice": invoice.name}, "valid_upto"
        )
        self.assertEqual(str(valid_upto), str(add_days(nowdate(), 30)))

    def test_default_validity_90_days_when_item_field_zero(self):
        self._make_voucher_item(VOUCHER_ITEM_NO_VALIDITY, rate=25000, validity_days=0)
        invoice = self._submit_invoice_with_voucher_item(
            VOUCHER_ITEM_NO_VALIDITY, qty=1, rate=25000
        )
        valid_upto = frappe.db.get_value(
            "Voucher", {"sold_via_invoice": invoice.name}, "valid_upto"
        )
        self.assertEqual(str(valid_upto), str(add_days(nowdate(), 90)))

    # ------------------------------------------------------------------
    # Non-voucher items
    # ------------------------------------------------------------------

    def test_non_voucher_item_does_not_create_voucher(self):
        # self.item from RestoPOSTestBase is a regular non-voucher item
        invoice = self._create_test_pos_invoice(qty=1, rate=100, submit=True)
        count = frappe.db.count("Voucher", {"sold_via_invoice": invoice.name})
        self.assertEqual(count, 0)

    def test_mixed_voucher_and_regular_items(self):
        invoice = self._create_test_pos_invoice(
            items=[
                {"item_code": self.item.name, "qty": 1, "rate": 30000, "amount": 30000},
                {
                    "item_code": VOUCHER_ITEM_50K,
                    "qty": 1,
                    "rate": 50000,
                    "amount": 50000,
                },
            ],
            payments=[{"mode_of_payment": self.mode_of_payment, "amount": 80000}],
            submit=True,
        )
        count = frappe.db.count("Voucher", {"sold_via_invoice": invoice.name})
        self.assertEqual(count, 1)

    def test_multiple_voucher_item_lines_in_one_invoice(self):
        self._make_voucher_item(VOUCHER_ITEM_100K, rate=100000, validity_days=30)
        invoice = self._create_test_pos_invoice(
            items=[
                {
                    "item_code": VOUCHER_ITEM_50K,
                    "qty": 2,
                    "rate": 50000,
                    "amount": 100000,
                },
                {
                    "item_code": VOUCHER_ITEM_100K,
                    "qty": 3,
                    "rate": 100000,
                    "amount": 300000,
                },
            ],
            payments=[{"mode_of_payment": self.mode_of_payment, "amount": 400000}],
            submit=True,
        )
        total = frappe.db.count("Voucher", {"sold_via_invoice": invoice.name})
        self.assertEqual(total, 5)
        n50 = frappe.db.count(
            "Voucher", {"sold_via_invoice": invoice.name, "voucher_value": 50000}
        )
        n100 = frappe.db.count(
            "Voucher", {"sold_via_invoice": invoice.name, "voucher_value": 100000}
        )
        self.assertEqual(n50, 2)
        self.assertEqual(n100, 3)


class TestExistingVoucherCode(RestoPOSTestBase):
    """Issuance dengan voucher_code dari mobile (voucher fisik yang sudah
    dicetak). Hook harus pakai code itu instead of auto-generate."""

    def setUp(self):
        super().setUp()
        TestVoucherIssuanceHook._ensure_voucher_custom_fields_on_item()
        self._ensure_pos_invoice_item_voucher_code_field()
        self.voucher_item = self._make_voucher_item(VOUCHER_ITEM_50K, rate=50000, validity_days=30)
        frappe.db.delete("Voucher", {"source": "Sold"})

    def tearDown(self):
        frappe.db.delete("Voucher", {"source": "Sold"})
        super().tearDown()

    @staticmethod
    def _ensure_pos_invoice_item_voucher_code_field():
        if not frappe.db.exists("Custom Field", {"dt": "POS Invoice Item", "fieldname": "voucher_code"}):
            frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "POS Invoice Item",
                "fieldname": "voucher_code",
                "label": "Voucher Code (Existing)",
                "fieldtype": "Data",
                "insert_after": "is_print_kitchen",
            }).insert(ignore_permissions=True)
            frappe.clear_cache(doctype="POS Invoice Item")

    def _make_voucher_item(self, item_code, rate, validity_days=None):
        return TestVoucherIssuanceHook._make_voucher_item(self, item_code, rate, validity_days)

    def _submit_invoice(self, items):
        total = sum(it["qty"] * it["rate"] for it in items)
        return self._create_test_pos_invoice(
            items=items,
            payments=[{"mode_of_payment": self.mode_of_payment, "amount": total}],
            submit=True,
        )

    def test_existing_code_persists_to_voucher_record(self):
        """voucher_code di POS Invoice Item → Voucher.code = code itu, bukan random hash."""
        invoice = self._submit_invoice([{
            "item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000,
            "voucher_code": "TEST-ABC-001",
        }])
        codes = frappe.get_all(
            "Voucher",
            filters={"sold_via_invoice": invoice.name},
            pluck="code",
        )
        self.assertEqual(codes, ["TEST-ABC-001"])

    def test_existing_code_duplicate_throws(self):
        """Kode yang sudah ada di Voucher (apapun status) tidak boleh dipakai ulang."""
        # Seed Voucher Active dengan kode tertentu
        frappe.get_doc({
            "doctype": "Voucher",
            "code": "DUPLICATE-CODE",
            "voucher_kind": "Nominal",
            "voucher_value": 50000,
            "valid_from": nowdate(),
            "valid_upto": add_days(nowdate(), 90),
            "source": "Free",
            "status": "Active",
        }).insert(ignore_permissions=True)

        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice([{
                "item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000,
                "voucher_code": "DUPLICATE-CODE",
            }])

    def test_existing_code_invalid_format_throws(self):
        """Kode harus 3-20 char alfanumerik + dash. Karakter lain ditolak."""
        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice([{
                "item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000,
                "voucher_code": "AB",  # too short
            }])

    def test_existing_code_with_special_char_throws(self):
        with self.assertRaises(frappe.ValidationError):
            self._submit_invoice([{
                "item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000,
                "voucher_code": "CODE WITH SPACE",
            }])

    def test_existing_code_uppercased_in_storage(self):
        """Kode auto-uppercase saat di-store, supaya unique check konsisten."""
        invoice = self._submit_invoice([{
            "item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000,
            "voucher_code": "lower-case-001",
        }])
        codes = frappe.get_all(
            "Voucher",
            filters={"sold_via_invoice": invoice.name},
            pluck="code",
        )
        self.assertEqual(codes, ["LOWER-CASE-001"])

    def test_mixed_cart_generate_and_existing(self):
        """1 item generate + 1 item existing → 1 Voucher random + 1 Voucher dengan code user."""
        invoice = self._submit_invoice([
            {"item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000},  # generate
            {"item_code": VOUCHER_ITEM_50K, "qty": 1, "rate": 50000, "amount": 50000,
             "voucher_code": "MIX-EXISTING-1"},
        ])
        all_codes = sorted(frappe.get_all(
            "Voucher",
            filters={"sold_via_invoice": invoice.name},
            pluck="code",
        ))
        self.assertEqual(len(all_codes), 2)
        self.assertIn("MIX-EXISTING-1", all_codes)
        # The other code must be a random 10-char hash, not the user code
        other = [c for c in all_codes if c != "MIX-EXISTING-1"][0]
        self.assertEqual(len(other), 10)
        self.assertTrue(other.isalnum())
