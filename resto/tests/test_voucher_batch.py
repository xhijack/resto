"""
Unit tests for Voucher Batch DocType + bulk generate flow.

Voucher Batch = bulk-issue free vouchers untuk event/marketing.
Sekali generate; setelah is_generated=1, batch immutable (bikin batch baru
kalau perlu lagi).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate


class TestVoucherBatch(FrappeTestCase):
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

    def _make_batch(self, **overrides):
        defaults = {
            "doctype": "Voucher Batch",
            "batch_name": "Test Batch " + frappe.generate_hash(length=6),
            "voucher_kind": "Nominal",
            "voucher_value": 25000,
            "valid_upto": add_days(nowdate(), 30),
            "voucher_count": 5,
            "purpose": "Test event giveaway",
        }
        defaults.update(overrides)
        return frappe.get_doc(defaults).insert(ignore_permissions=True)

    # ------------------------------------------------------------------
    # Create / defaults
    # ------------------------------------------------------------------

    def test_create_batch_starts_in_pending_state(self):
        batch = self._make_batch()
        self.assertEqual(batch.is_generated, 0)
        self.assertEqual(batch.generated_count, 0)
        self.assertIsNone(batch.generated_at)

    def test_batch_name_must_be_unique(self):
        b1 = self._make_batch(batch_name="Same Name Batch")
        with self.assertRaises(frappe.exceptions.DuplicateEntryError):
            self._make_batch(batch_name="Same Name Batch")

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def test_nominal_batch_requires_positive_value(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_batch(voucher_value=0)

    def test_batch_requires_positive_voucher_count(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_batch(voucher_count=0)

    def test_batch_rejects_negative_voucher_count(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_batch(voucher_count=-5)

    def test_free_item_batch_requires_free_item(self):
        with self.assertRaises(frappe.ValidationError):
            self._make_batch(voucher_kind="Free Item", voucher_value=None, free_item=None)

    # ------------------------------------------------------------------
    # generate_vouchers
    # ------------------------------------------------------------------

    def test_generate_creates_requested_number_of_vouchers(self):
        batch = self._make_batch(voucher_count=7)
        batch.generate_vouchers()
        count = frappe.db.count("Voucher", {"batch_id": batch.name})
        self.assertEqual(count, 7)

    def test_generated_vouchers_have_batch_id_link(self):
        batch = self._make_batch(voucher_count=3)
        batch.generate_vouchers()
        vouchers = frappe.get_all("Voucher", filters={"batch_id": batch.name}, pluck="name")
        self.assertEqual(len(vouchers), 3)
        for vname in vouchers:
            v = frappe.get_doc("Voucher", vname)
            self.assertEqual(v.batch_id, batch.name)

    def test_generated_vouchers_inherit_value_and_kind(self):
        batch = self._make_batch(voucher_value=75000, voucher_count=2)
        batch.generate_vouchers()
        vouchers = frappe.get_all(
            "Voucher",
            filters={"batch_id": batch.name},
            fields=["voucher_kind", "voucher_value"],
        )
        self.assertEqual(len(vouchers), 2)
        for v in vouchers:
            self.assertEqual(v.voucher_kind, "Nominal")
            self.assertEqual(v.voucher_value, 75000)

    def test_generated_vouchers_have_source_free(self):
        batch = self._make_batch(voucher_count=2)
        batch.generate_vouchers()
        vouchers = frappe.get_all(
            "Voucher", filters={"batch_id": batch.name}, fields=["source"]
        )
        for v in vouchers:
            self.assertEqual(v.source, "Free")

    def test_generated_vouchers_inherit_validity(self):
        upto = add_days(nowdate(), 60)
        batch = self._make_batch(voucher_count=2, valid_upto=upto)
        batch.generate_vouchers()
        vouchers = frappe.get_all(
            "Voucher",
            filters={"batch_id": batch.name},
            fields=["valid_upto"],
        )
        for v in vouchers:
            self.assertEqual(str(v.valid_upto), str(upto))

    def test_generated_vouchers_start_active(self):
        batch = self._make_batch(voucher_count=3)
        batch.generate_vouchers()
        statuses = frappe.get_all(
            "Voucher", filters={"batch_id": batch.name}, pluck="status"
        )
        self.assertTrue(all(s == "Active" for s in statuses))

    def test_generate_marks_batch_as_generated(self):
        batch = self._make_batch(voucher_count=4)
        batch.generate_vouchers()
        batch.reload()
        self.assertEqual(batch.is_generated, 1)
        self.assertEqual(batch.generated_count, 4)
        self.assertIsNotNone(batch.generated_at)
        self.assertEqual(batch.generated_by, "Administrator")

    def test_double_generate_raises_error(self):
        batch = self._make_batch(voucher_count=2)
        batch.generate_vouchers()
        with self.assertRaises(frappe.ValidationError):
            batch.generate_vouchers()

    def test_generated_voucher_codes_are_unique(self):
        batch = self._make_batch(voucher_count=10)
        batch.generate_vouchers()
        codes = frappe.get_all(
            "Voucher", filters={"batch_id": batch.name}, pluck="code"
        )
        self.assertEqual(len(codes), len(set(codes)))
