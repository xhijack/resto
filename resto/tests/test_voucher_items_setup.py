"""
Tests for voucher Item Group + sample Item provisioning.

Setup wires three "voucher items" (Rp50K / Rp100K / Rp250K) under Item
Group "Voucher" so cashiers can sell vouchers via POS without manual
master-data setup. Idempotent: safe to re-run on every after_migrate.
End-to-end smoke checks that selling one of these items via POS Invoice
still triggers the Chunk 3 issuance hook and creates a Voucher record.
"""

import frappe

from resto.tests.resto_pos_test_base import RestoPOSTestBase

VOUCHER_GROUP = "Voucher"
ITEM_50K = "Voucher Rp50.000"
ITEM_100K = "Voucher Rp100.000"
ITEM_250K = "Voucher Rp250.000"
ALL_ITEMS = [ITEM_50K, ITEM_100K, ITEM_250K]


class TestVoucherItemsSetup(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

    def tearDown(self):
        # Clean any Voucher rows created during smoke tests so other
        # voucher test modules start clean.
        frappe.db.delete("Voucher", {"source": "Sold"})
        super().tearDown()

    def _run_setup(self):
        from resto.voucher_setup import setup_voucher_items

        setup_voucher_items()

    # ------------------------------------------------------------------
    # Item Group
    # ------------------------------------------------------------------

    def test_setup_creates_voucher_item_group(self):
        self._run_setup()
        self.assertTrue(frappe.db.exists("Item Group", VOUCHER_GROUP))

    def test_voucher_item_group_parent_is_all_item_groups(self):
        self._run_setup()
        parent = frappe.db.get_value(
            "Item Group", VOUCHER_GROUP, "parent_item_group"
        )
        self.assertEqual(parent, "All Item Groups")

    # ------------------------------------------------------------------
    # Sample items
    # ------------------------------------------------------------------

    def test_setup_creates_all_three_sample_items(self):
        self._run_setup()
        for item_code in ALL_ITEMS:
            self.assertTrue(
                frappe.db.exists("Item", item_code),
                f"Expected Item {item_code} to exist after setup",
            )

    def test_voucher_items_have_correct_standard_rate(self):
        self._run_setup()
        rates = {
            ITEM_50K: 50000,
            ITEM_100K: 100000,
            ITEM_250K: 250000,
        }
        for code, expected_rate in rates.items():
            rate = frappe.db.get_value("Item", code, "standard_rate")
            self.assertEqual(
                float(rate),
                float(expected_rate),
                f"{code} standard_rate mismatch",
            )

    def test_voucher_items_are_non_stock(self):
        self._run_setup()
        for code in ALL_ITEMS:
            is_stock = frappe.db.get_value("Item", code, "is_stock_item")
            self.assertEqual(int(is_stock), 0, f"{code} should be non-stock")

    def test_voucher_items_belong_to_voucher_group(self):
        self._run_setup()
        for code in ALL_ITEMS:
            group = frappe.db.get_value("Item", code, "item_group")
            self.assertEqual(group, VOUCHER_GROUP)

    def test_voucher_items_have_is_voucher_item_flag(self):
        self._run_setup()
        for code in ALL_ITEMS:
            flag = frappe.db.get_value("Item", code, "is_voucher_item")
            self.assertEqual(
                int(flag or 0), 1, f"{code} should have is_voucher_item=1"
            )

    def test_voucher_items_have_default_validity_90(self):
        self._run_setup()
        for code in ALL_ITEMS:
            days = frappe.db.get_value("Item", code, "voucher_validity_days")
            self.assertEqual(int(days or 0), 90)

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def test_setup_is_idempotent_no_duplicate_items(self):
        self._run_setup()
        self._run_setup()
        for code in ALL_ITEMS:
            count = frappe.db.count("Item", {"item_code": code})
            self.assertEqual(count, 1, f"Duplicate {code} after re-run")

    def test_setup_is_idempotent_no_duplicate_group(self):
        self._run_setup()
        self._run_setup()
        count = frappe.db.count("Item Group", {"item_group_name": VOUCHER_GROUP})
        self.assertEqual(count, 1)

    # ------------------------------------------------------------------
    # Integration smoke (cross-chunk: Chunk 3 issuance hook)
    # ------------------------------------------------------------------

    def test_selling_voucher_item_creates_voucher_record(self):
        self._run_setup()
        invoice = self._create_test_pos_invoice(
            items=[
                {
                    "item_code": ITEM_50K,
                    "qty": 1,
                    "rate": 50000,
                    "amount": 50000,
                }
            ],
            payments=[
                {"mode_of_payment": self.mode_of_payment, "amount": 50000}
            ],
            submit=True,
        )
        count = frappe.db.count("Voucher", {"sold_via_invoice": invoice.name})
        self.assertEqual(count, 1)

    # ------------------------------------------------------------------
    # Resto Menu auto-create (mobile catalog requirement)
    # ------------------------------------------------------------------

    def test_setup_creates_resto_menu_for_each_voucher_item(self):
        self._run_setup()
        for code in ALL_ITEMS:
            self.assertTrue(
                frappe.db.exists("Resto Menu", {"sell_item": code}),
                f"Expected Resto Menu for sell_item={code}",
            )

    def test_voucher_resto_menu_links_to_voucher_item_group(self):
        self._run_setup()
        for code in ALL_ITEMS:
            rm = frappe.db.get_value(
                "Resto Menu",
                {"sell_item": code},
                "menu_category",
            )
            self.assertEqual(rm, VOUCHER_GROUP)

    def test_voucher_resto_menu_setup_is_idempotent(self):
        self._run_setup()
        self._run_setup()
        for code in ALL_ITEMS:
            count = frappe.db.count("Resto Menu", {"sell_item": code})
            self.assertEqual(count, 1, f"Duplicate Resto Menu for {code}")

    def test_setup_does_not_raise_when_link_mandatory_field_has_no_records(self):
        """Production server (sopwerp) punya custom mandatory Link field di
        Resto Menu (mis. Brand) tapi belum populate records. Sebelum hotfix,
        setup throw LinkValidationError yang rollback bench update --patch.

        Sekarang harus graceful degrade: Item + Item Group tetap tercipta,
        Resto Menu skip + log warning."""
        from unittest.mock import patch
        from resto.voucher_setup import _VoucherSetupSkipped

        # Simulate the scenario: _apply_extra_mandatory_defaults raises
        # because a Link target doctype is empty on this site
        def raise_skip(*args, **kwargs):
            raise _VoucherSetupSkipped("Brand has no records")

        with patch(
            "resto.voucher_setup._apply_extra_mandatory_defaults",
            side_effect=raise_skip,
        ):
            try:
                self._run_setup()
            except Exception as e:
                self.fail(
                    f"setup_voucher_items() should NOT raise when Link "
                    f"mandatory field has no records; got: {type(e).__name__}: {e}"
                )

        # Item + Item Group tetap tercipta
        self.assertTrue(frappe.db.exists("Item Group", VOUCHER_GROUP))
        for code in ALL_ITEMS:
            self.assertTrue(frappe.db.exists("Item", code))
        # Resto Menu di-skip (kalau tidak ada existing dari prior runs)
        # Note: kalau test sebelumnya bikin Resto Menu, mereka tetap ada
        # karena _ensure_voucher_resto_menu skip-if-exists. Yang penting
        # function tidak raise.
