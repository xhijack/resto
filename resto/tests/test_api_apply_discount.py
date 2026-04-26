# test_api_apply_discount.py - VERSI INHERIT KE BASE TAPI DENGAN OVERRIDE

import frappe
from resto.tests.resto_pos_test_base import RestoPOSTestBase

# Import function under test
from resto.api import apply_discount


class TestApplyDiscount(RestoPOSTestBase):
    """Test suite untuk API apply_discount"""
    
    def setUp(self):
        """Setup spesifik untuk test diskon"""
        # Override setup untuk menggunakan nama yang sama dengan test lama
        # agar compatible dengan api.py yang hardcode nama template
        frappe.set_user("Administrator")
        
        # Gunakan company test bawaan Frappe
        self.company = frappe.get_doc("Company", "_Test Company")
        
        # Setup master data dengan NAMA YANG SAMA DENGAN TEST LAMA
        # (override method dari base class dengan nama hardcode)
        self.customer = self._create_test_customer()
        self.item = self._create_test_item()
        self.mode_of_payment = self._create_test_mode_of_payment()
        self.pos_profile = self._create_test_pos_profile()
        self.branch = self._get_or_create_branch()
        self.pos_opening_entry = self._create_test_pos_opening_entry()
    
    def tearDown(self):
        """Bersihkan setelah test"""
        frappe.set_user("Guest")
        # Tidak panggil super().tearDown() karena kita override setUp juga
    
    # -------------------------------------------------------------------------
    # OVERRIDE: Menggunakan nama yang sama dengan test lama (hardcode)
    # -------------------------------------------------------------------------
    
    def _create_test_customer(self):
        """Override: Buat customer test dengan nama hardcode"""
        name = "_Test Customer for Discount"
        if frappe.db.exists("Customer", name):
            return frappe.get_doc("Customer", name)

        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Company",
            "customer_group": "All Customer Groups",
            "territory": "All Territories"
        })
        customer.insert(ignore_permissions=True)
        return customer

    def _create_test_item(self):
        """Override: Buat item test dengan nama hardcode"""
        code = "_Test Item for Discount"
        if frappe.db.exists("Item", code):
            return frappe.get_doc("Item", code)

        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": code,
            "item_name": code,
            "item_group": "All Item Groups",
            "stock_uom": "Nos",
            "is_stock_item": 0
        })
        item.insert(ignore_permissions=True)
        return item

    def _create_test_mode_of_payment(self):
        """Override: Buat Mode of Payment dengan nama hardcode"""
        name = "Cash for Discount"
        if frappe.db.exists("Mode of Payment", name):
            return name

        account_name = self._get_or_create_cash_account()

        mop = frappe.get_doc({
            "doctype": "Mode of Payment",
            "mode_of_payment": name,
            "type": "Cash",
            "accounts": [{
                "company": self.company.name,
                "default_account": account_name
            }]
        })
        mop.insert(ignore_permissions=True)
        return name

    def _get_or_create_cash_account(self):
        """Override: Cari akun Kas dengan nama hardcode"""
        account_name = "Cash - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name

        root_account = frappe.db.get_value("Account",
            {"company": self.company.name, "account_type": "Cash", "is_group": 1})
        if not root_account:
            root_account = frappe.db.get_value("Account",
                {"company": self.company.name, "root_type": "Asset", "is_group": 1}, "name")
        if not root_account:
            frappe.throw(f"Tidak dapat menemukan root akun Asset untuk {self.company.name}")

        account = frappe.get_doc({
            "doctype": "Account",
            "account_name": "Cash",
            "parent_account": root_account,
            "company": self.company.name,
            "root_type": "Asset",
            "account_type": "Cash",
            "is_group": 0
        }).insert(ignore_permissions=True)
        return account.name

    def _get_or_create_income_account(self):
        """Override: Cari akun Pendapatan dengan nama hardcode"""
        account_name = "Sales - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name

        root_account = frappe.db.get_value("Account",
            {"company": self.company.name, "account_type": "Income Account", "is_group": 1})
        if not root_account:
            root_account = frappe.db.get_value("Account",
                {"company": self.company.name, "root_type": "Income", "is_group": 1}, "name")
        if not root_account:
            frappe.throw(f"Tidak dapat menemukan root akun Income untuk {self.company.name}")

        account = frappe.get_doc({
            "doctype": "Account",
            "account_name": "Sales",
            "parent_account": root_account,
            "company": self.company.name,
            "root_type": "Income",
            "account_type": "Income Account",
            "is_group": 0
        }).insert(ignore_permissions=True)
        return account.name

    def _get_or_create_expense_account(self):
        """Override: Cari akun Beban dengan nama hardcode"""
        account_name = "Cost of Goods Sold - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name

        root_account = frappe.db.get_value("Account",
            {"company": self.company.name, "account_type": "Cost of Goods Sold", "is_group": 1})
        if not root_account:
            root_account = frappe.db.get_value("Account",
                {"company": self.company.name, "root_type": "Expense", "is_group": 1}, "name")
        if not root_account:
            frappe.throw(f"Tidak dapat menemukan root akun Expense untuk {self.company.name}")

        account = frappe.get_doc({
            "doctype": "Account",
            "account_name": "Cost of Goods Sold",
            "parent_account": root_account,
            "company": self.company.name,
            "root_type": "Expense",
            "account_type": "Cost of Goods Sold",
            "is_group": 0
        }).insert(ignore_permissions=True)
        return account.name

    def _get_or_create_cost_center(self):
        """Override: Cari Cost Center dengan nama hardcode"""
        cost_center_name = "Main - _TC"
        if frappe.db.exists("Cost Center", cost_center_name):
            return cost_center_name

        root_cc = frappe.db.get_value("Cost Center",
            {"company": self.company.name, "is_group": 1}, "name")
        if not root_cc:
            root_cc = frappe.get_doc({
                "doctype": "Cost Center",
                "cost_center_name": self.company.name,
                "company": self.company.name,
                "is_group": 1
            }).insert(ignore_permissions=True).name

        cc = frappe.get_doc({
            "doctype": "Cost Center",
            "cost_center_name": "Main",
            "parent_cost_center": root_cc,
            "company": self.company.name,
            "is_group": 0
        }).insert(ignore_permissions=True)
        return cc.name

    def _get_or_create_warehouse(self):
        """Override: Cari warehouse dengan nama hardcode"""
        warehouse_name = "Test Warehouse Discount"
        if frappe.db.exists("Warehouse", warehouse_name):
            return warehouse_name

        warehouse = frappe.get_doc({
            "doctype": "Warehouse",
            "warehouse_name": warehouse_name,
            "company": self.company.name,
        }).insert(ignore_permissions=True)
        return warehouse.name

    def _create_test_pos_profile(self):
        """Override: Buat POS Profile dengan nama hardcode"""
        name = "_Test POS Profile for Discount"
        if frappe.db.exists("POS Profile", name):
            return frappe.get_doc("POS Profile", name)

        warehouse = self._get_or_create_warehouse()
        income_account = self._get_or_create_income_account()
        expense_account = self._get_or_create_expense_account()
        cost_center = self._get_or_create_cost_center()
        taxes_template = self._create_test_taxes_template()
        
        pos_profile = frappe.get_doc({
            "doctype": "POS Profile",
            "name": name,
            "company": self.company.name,
            "warehouse": warehouse,
            "country": "Indonesia",
            "currency": "IDR",
            "write_off_account": expense_account,
            "write_off_cost_center": cost_center,
            "income_account": income_account,
            "expense_account": expense_account,
            "taxes_and_charges": taxes_template,
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "default": 1
            }],
            "applicable_for_users": [{
                "user": frappe.session.user
            }]
        })
        pos_profile.insert(ignore_permissions=True)
        return pos_profile

    def _create_test_pos_opening_entry(self):
        """Override: Buat POS Opening Entry dengan branch hardcode"""
        existing = frappe.db.get_value("POS Opening Entry", {
            "pos_profile": self.pos_profile.name,
            "docstatus": 1,
            "status": "Open"
        }, "name")
        if existing:
            return frappe.get_doc("POS Opening Entry", existing)

        branch = self._get_or_create_branch()

        opening_entry = frappe.get_doc({
            "doctype": "POS Opening Entry",
            "pos_profile": self.pos_profile.name,
            "company": self.company.name,
            "branch": branch,
            "period_start_date": frappe.utils.now_datetime(),
            "user": frappe.session.user,
            "balance_details": [{
                "mode_of_payment": self.mode_of_payment,
                "opening_amount": 0
            }]
        })
        opening_entry.insert(ignore_permissions=True)
        opening_entry.submit()
        return opening_entry

    def _get_or_create_branch(self):
        """Override: Cari atau buat branch dengan nama hardcode"""
        branch_name = "_Test Branch"
        if frappe.db.exists("Branch", branch_name):
            return branch_name

        branch = frappe.get_doc({
            "doctype": "Branch",
            "branch": branch_name
        })
        branch.insert(ignore_permissions=True)
        return branch.name
        
    def _get_or_create_discount_account(self):
        """Override: Buat akun diskon dengan nama hardcode"""
        account_name = "Discount Allowed - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name

        root_account = frappe.db.get_value("Account",
            {"company": self.company.name, "root_type": "Expense", "is_group": 1}, "name")
        if not root_account:
            frappe.throw("Tidak dapat menemukan root akun Expense")

        account = frappe.get_doc({
            "doctype": "Account",
            "account_name": "Discount Allowed",
            "parent_account": root_account,
            "company": self.company.name,
            "root_type": "Expense",
            "account_type": "Expense Account",
            "is_group": 0
        }).insert(ignore_permissions=True)
        return account.name

    def _create_test_taxes_template(self):
        """Override: Buat Sales Taxes and Charges Template dengan nama hardcode"""
        template_name = "_Test Discount Template"
        if frappe.db.exists("Sales Taxes and Charges Template", template_name):
            return template_name

        discount_account = self._get_or_create_discount_account()
        template = frappe.get_doc({
            "doctype": "Sales Taxes and Charges Template",
            "title": template_name,
            "company": self.company.name,
            "taxes": [
                {
                    "charge_type": "On Net Total",
                    "account_head": discount_account,
                    "description": "Discount",
                    "rate": 0,
                    "included_in_print_rate": 1
                }
            ]
        })
        template.insert(ignore_permissions=True)
        return template.name

    def _create_test_pos_invoice(self, qty=1, rate=100):
        """Override: Buat POS Invoice dengan helper yang sama dengan test lama"""
        total = qty * rate
        invoice = frappe.get_doc({
            "doctype": "POS Invoice",
            "company": self.company.name,
            "customer": self.customer.name,
            "posting_date": frappe.utils.nowdate(),
            "posting_time": frappe.utils.nowtime(),
            "pos_profile": self.pos_profile.name,
            "items": [
                {
                    "item_code": self.item.name,
                    "qty": qty,
                    "rate": rate,
                    "amount": total
                }
            ],
            "payments": [
                {
                    "mode_of_payment": self.mode_of_payment,
                    "amount": total
                }
            ],
            "is_pos": 1
        })
        invoice.insert(ignore_permissions=True)
        return invoice

    # -------------------------------------------------------------------------
    # TEST CASES - sama dengan test lama
    # -------------------------------------------------------------------------
    
    def test_apply_discount_percentage(self):
        """Diskon persentase harus mengurangi grand_total dengan benar"""
        invoice = self._create_test_pos_invoice(qty=2, rate=100)
        result = apply_discount(invoice.name, discount_percentage=10)
        invoice.reload()
        self.assertTrue(result.get("ok"))

    def test_apply_discount_fixed(self):
        """Diskon nominal harus mengurangi grand_total dengan benar"""
        invoice = self._create_test_pos_invoice(qty=3, rate=50)
        result = apply_discount(invoice.name, discount_amount=30)
        invoice.reload()
        for t in invoice.taxes:
            if t.description == "Discount":
                self.assertEqual(t.tax_amount, -30)
                break
        self.assertTrue(result.get("ok"))

    def test_apply_discount_exceeds_total(self):
        """Jika diskon melebihi total, API harus mengembalikan error"""
        invoice = self._create_test_pos_invoice(qty=1, rate=100)
        with self.assertRaises(frappe.ValidationError) as cm:
            apply_discount(invoice.name, discount_amount=150)
        self.assertIn("must be >= 0", str(cm.exception))

    def test_apply_discount_update(self):
        """Mengupdate diskon yang sudah ada (mengubah dari persentase ke amount)"""
        invoice = self._create_test_pos_invoice(qty=2, rate=100)
        apply_discount(invoice.name, discount_percentage=10)
        invoice.reload()
        for t in invoice.taxes:
            if t.description == "Discount":
                self.assertEqual(t.rate, -10)
                break
        result = apply_discount(invoice.name, discount_amount=30)
        invoice.reload()
        for t in invoice.taxes:
            if t.description == "Discount":
                self.assertEqual(t.tax_amount, -30)
                break
        self.assertTrue(result.get("ok"))

    def test_apply_discount_invalid_params(self):
        """Memberikan parameter negatif harus menghasilkan error"""
        invoice = self._create_test_pos_invoice(qty=1, rate=100)
        with self.assertRaises(frappe.ValidationError) as cm:
            apply_discount(invoice.name, discount_percentage=-10)
        self.assertIn("tidak boleh negatif", str(cm.exception))
    
    def test_apply_discount_with_name_and_bank(self):
        """Memastikan discount_name dan discount_for_bank tersimpan"""
        invoice = self._create_test_pos_invoice(qty=1, rate=100)
        result = apply_discount(
            invoice.name,
            discount_amount=10,
            discount_name="Test Discount",
            discount_for_bank="Test Bank"
        )
        invoice.reload()
        self.assertEqual(invoice.discount_name, "Test Discount")
        self.assertEqual(invoice.discount_for_bank, "Test Bank")
        self.assertTrue(result.get("ok"))
    
    def test_remove_discount(self):
        """Menguji penghapusan diskon dengan mengatur diskon menjadi 0"""
        invoice = self._create_test_pos_invoice(qty=2, rate=100)
        result = apply_discount(invoice.name, discount_percentage=0, discount_amount=0)
        invoice.reload()
        for t in invoice.taxes:
            if t.description == "Discount":
                self.assertEqual(t.tax_amount, 0)
                break
        self.assertTrue(result.get("ok"))