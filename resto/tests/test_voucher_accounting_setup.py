"""
Tests for voucher accounting setup — chart of accounts + Mode of Payment.

Setup should be idempotent (safe to call from after_migrate on every
upgrade). For each Company it provisions:
  - Account "Unearned Voucher Revenue" (Liability, leaf)
  - Account "Voucher Promotional Expense" (Expense, leaf)
And globally:
  - Mode of Payment "Voucher" with per-Company default_account pointing
    to the Unearned Voucher Revenue account.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

UNEARNED_NAME = "Unearned Voucher Revenue"
EXPENSE_NAME = "Voucher Promotional Expense"
MOP_VOUCHER = "Voucher"


class TestVoucherAccountingSetup(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.company = frappe.get_doc("Company", "_Test Company")

    def tearDown(self):
        frappe.db.rollback()
        frappe.set_user("Guest")
        super().tearDown()

    def _run_setup(self):
        from resto.voucher_setup import setup_voucher_accounting

        setup_voucher_accounting()

    # ------------------------------------------------------------------
    # Chart of accounts
    # ------------------------------------------------------------------

    def test_setup_creates_unearned_voucher_revenue_account(self):
        self._run_setup()
        self.assertTrue(
            frappe.db.exists(
                "Account",
                {"account_name": UNEARNED_NAME, "company": self.company.name},
            )
        )

    def test_setup_creates_voucher_promotional_expense_account(self):
        self._run_setup()
        self.assertTrue(
            frappe.db.exists(
                "Account",
                {"account_name": EXPENSE_NAME, "company": self.company.name},
            )
        )

    def test_unearned_voucher_revenue_is_liability(self):
        self._run_setup()
        name = frappe.db.get_value(
            "Account",
            {"account_name": UNEARNED_NAME, "company": self.company.name},
            "name",
        )
        root_type = frappe.db.get_value("Account", name, "root_type")
        self.assertEqual(root_type, "Liability")

    def test_voucher_promotional_expense_is_expense(self):
        self._run_setup()
        name = frappe.db.get_value(
            "Account",
            {"account_name": EXPENSE_NAME, "company": self.company.name},
            "name",
        )
        root_type = frappe.db.get_value("Account", name, "root_type")
        self.assertEqual(root_type, "Expense")

    def test_voucher_accounts_are_leaves_not_groups(self):
        self._run_setup()
        for account_name in (UNEARNED_NAME, EXPENSE_NAME):
            name = frappe.db.get_value(
                "Account",
                {"account_name": account_name, "company": self.company.name},
                "name",
            )
            self.assertEqual(
                frappe.db.get_value("Account", name, "is_group"),
                0,
                f"{account_name} must be a leaf (is_group=0)",
            )

    # ------------------------------------------------------------------
    # Mode of Payment
    # ------------------------------------------------------------------

    def test_setup_creates_voucher_mode_of_payment(self):
        self._run_setup()
        self.assertTrue(frappe.db.exists("Mode of Payment", MOP_VOUCHER))

    def test_voucher_mode_of_payment_type_is_general(self):
        self._run_setup()
        mop_type = frappe.db.get_value("Mode of Payment", MOP_VOUCHER, "type")
        self.assertEqual(mop_type, "General")

    def test_voucher_mop_default_account_for_company(self):
        self._run_setup()
        unearned = frappe.db.get_value(
            "Account",
            {"account_name": UNEARNED_NAME, "company": self.company.name},
            "name",
        )
        mop_account = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": MOP_VOUCHER, "company": self.company.name},
            "default_account",
        )
        self.assertEqual(mop_account, unearned)

    # ------------------------------------------------------------------
    # Idempotency
    # ------------------------------------------------------------------

    def test_setup_safe_to_call_twice_no_duplicate_accounts(self):
        self._run_setup()
        self._run_setup()
        unearned_count = frappe.db.count(
            "Account",
            {"account_name": UNEARNED_NAME, "company": self.company.name},
        )
        expense_count = frappe.db.count(
            "Account",
            {"account_name": EXPENSE_NAME, "company": self.company.name},
        )
        self.assertEqual(unearned_count, 1)
        self.assertEqual(expense_count, 1)

    def test_setup_safe_to_call_twice_no_duplicate_mop_account_row(self):
        self._run_setup()
        self._run_setup()
        rows = frappe.db.count(
            "Mode of Payment Account",
            {"parent": MOP_VOUCHER, "company": self.company.name},
        )
        self.assertEqual(rows, 1)
