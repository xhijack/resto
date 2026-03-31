# resto_pos_test_base.py - VERSI COMPATIBLE

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate, nowtime, now_datetime


class RestoPOSTestBase(FrappeTestCase):
    """
    Base test class untuk semua test terkait Resto/POS.
    Menyediakan fixtures dan helpers yang sering digunakan.
    """
    
    def setUp(self):
        """Setup dasar: company, customer, item, payment method, pos profile"""
        super().setUp()
        frappe.set_user("Administrator")
        
        # Gunakan company test bawaan Frappe
        self.company = frappe.get_doc("Company", "_Test Company")
        
        # Setup master data umum - menggunakan nama yang sama dengan test lama
        self.customer = self._get_or_create_customer()
        self.item = self._get_or_create_item()
        self.mode_of_payment = self._get_or_create_mode_of_payment()
        self.pos_profile = self._get_or_create_pos_profile()
        self.branch = self._get_or_create_branch()
        
    def tearDown(self):
        """Cleanup setelah test"""
        frappe.set_user("Guest")
        super().tearDown()
    
    # -------------------------------------------------------------------------
    # HELPERS - Customer & Item (menggunakan nama yang sama dengan test lama)
    # -------------------------------------------------------------------------
    
    def _get_or_create_customer(self, name=None):
        """Buat atau ambil customer test"""
        # Default menggunakan nama yang sama dengan test lama
        customer_name = name or "_Test Customer for Discount"
        if frappe.db.exists("Customer", customer_name):
            return frappe.get_doc("Customer", customer_name)
            
        customer = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": customer_name,
            "customer_type": "Company",
            "customer_group": "All Customer Groups",
            "territory": "All Territories"
        })
        customer.insert(ignore_permissions=True)
        return customer
    
    def _get_or_create_item(self, item_code=None, is_stock_item=0):
        """Buat atau ambil item test"""
        # Default menggunakan nama yang sama dengan test lama
        code = item_code or "_Test Item for Discount"
        if frappe.db.exists("Item", code):
            return frappe.get_doc("Item", code)
            
        item = frappe.get_doc({
            "doctype": "Item",
            "item_code": code,
            "item_name": code,
            "item_group": "All Item Groups",
            "stock_uom": "Nos",
            "is_stock_item": is_stock_item
        })
        item.insert(ignore_permissions=True)
        return item
    
    # -------------------------------------------------------------------------
    # HELPERS - Accounts (menggunakan suffix _TC yang sama dengan test lama)
    # -------------------------------------------------------------------------
    
    def _get_or_create_cash_account(self):
        """Ambil atau buat akun Cash untuk company"""
        account_name = "Cash - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name
            
        root_account = frappe.db.get_value("Account", {
            "company": self.company.name, 
            "account_type": "Cash", 
            "is_group": 1
        })
        if not root_account:
            root_account = frappe.db.get_value("Account", {
                "company": self.company.name, 
                "root_type": "Asset", 
                "is_group": 1
            }, "name")
            
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
        """Ambil atau buat akun Sales/Income"""
        account_name = "Sales - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name
            
        root_account = frappe.db.get_value("Account", {
            "company": self.company.name, 
            "account_type": "Income Account", 
            "is_group": 1
        })
        if not root_account:
            root_account = frappe.db.get_value("Account", {
                "company": self.company.name, 
                "root_type": "Income", 
                "is_group": 1
            }, "name")
            
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
    
    def _get_or_create_expense_account(self, account_type="Cost of Goods Sold"):
        """Ambil atau buat akun Expense/COGS"""
        account_name = f"{account_type} - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name
            
        root_account = frappe.db.get_value("Account", {
            "company": self.company.name, 
            "account_type": account_type, 
            "is_group": 1
        })
        if not root_account:
            root_account = frappe.db.get_value("Account", {
                "company": self.company.name, 
                "root_type": "Expense", 
                "is_group": 1
            }, "name")
            
        account = frappe.get_doc({
            "doctype": "Account",
            "account_name": account_type,
            "parent_account": root_account,
            "company": self.company.name,
            "root_type": "Expense",
            "account_type": account_type,
            "is_group": 0
        }).insert(ignore_permissions=True)
        return account.name
    
    def _get_or_create_cost_center(self):
        """Ambil atau buat Cost Center"""
        cost_center_name = "Main - _TC"
        if frappe.db.exists("Cost Center", cost_center_name):
            return cost_center_name
            
        root_cc = frappe.db.get_value("Cost Center", {
            "company": self.company.name, 
            "is_group": 1
        }, "name")
        
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
    
    def _get_or_create_warehouse(self, warehouse_name=None):
        """Ambil atau buat Warehouse"""
        # Default menggunakan nama yang sama dengan test lama
        wh_name = warehouse_name or "Test Warehouse Discount"
        if frappe.db.exists("Warehouse", wh_name):
            return wh_name
            
        warehouse = frappe.get_doc({
            "doctype": "Warehouse",
            "warehouse_name": wh_name,
            "company": self.company.name,
        }).insert(ignore_permissions=True)
        return warehouse.name
    
    # -------------------------------------------------------------------------
    # HELPERS - Payment & POS Profile (menggunakan nama yang sama dengan test lama)
    # -------------------------------------------------------------------------
    
    def _get_or_create_mode_of_payment(self, mop_name=None):
        """Buat Mode of Payment dengan default account"""
        # Default menggunakan nama yang sama dengan test lama
        name = mop_name or "Cash for Discount"
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
    
    def _get_or_create_pos_profile(self, include_taxes=False, taxes_template=None):
        """
        Buat POS Profile lengkap.
        """
        # Default menggunakan nama yang sama dengan test lama
        name = "_Test POS Profile for Discount"
        if frappe.db.exists("POS Profile", name):
            return frappe.get_doc("POS Profile", name)
            
        warehouse = self._get_or_create_warehouse()
        income_account = self._get_or_create_income_account()
        expense_account = self._get_or_create_expense_account()
        cost_center = self._get_or_create_cost_center()
        
        doc_dict = {
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
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "default": 1
            }],
            "applicable_for_users": [{
                "user": frappe.session.user
            }]
        }
        
        # Jika taxes_template disediakan, gunakan itu
        if include_taxes and taxes_template:
            doc_dict["taxes_and_charges"] = taxes_template
        else:
            # Default menggunakan template yang sama dengan test lama
            doc_dict["taxes_and_charges"] = self._create_test_taxes_template()
            
        pos_profile = frappe.get_doc(doc_dict)
        pos_profile.insert(ignore_permissions=True)
        return pos_profile
    
    def _get_or_create_branch(self, branch_name=None):
        """Ambil atau buat Branch"""
        # Default menggunakan nama yang sama dengan test lama
        b_name = branch_name or "_Test Branch"
        if frappe.db.exists("Branch", b_name):
            return b_name
            
        branch = frappe.get_doc({
            "doctype": "Branch",
            "branch": b_name
        })
        branch.insert(ignore_permissions=True)
        return branch.name
    
    # -------------------------------------------------------------------------
    # HELPERS - Discount Account & Taxes Template (menggunakan nama yang sama dengan test lama)
    # -------------------------------------------------------------------------
    
    def _get_or_create_discount_account(self):
        """Buat akun diskon (Expense)"""
        account_name = "Discount Allowed - _TC"
        if frappe.db.exists("Account", account_name):
            return account_name
            
        root_account = frappe.db.get_value("Account", {
            "company": self.company.name, 
            "root_type": "Expense", 
            "is_group": 1
        }, "name")
        
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
        """Buat Sales Taxes and Charges Template dengan baris Discount"""
        # Menggunakan nama yang sama dengan test lama (tanpa suffix company)
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
    
    # -------------------------------------------------------------------------
    # HELPERS - POS Opening Entry
    # -------------------------------------------------------------------------
    
    def _create_pos_opening_entry(self, pos_profile=None, branch=None):
        """Buat POS Opening Entry dengan branch"""
        profile = pos_profile or self.pos_profile.name
        branch_name = branch or self.branch
        
        existing = frappe.db.get_value("POS Opening Entry", {
            "pos_profile": profile,
            "docstatus": 1,
            "status": "Open"
        }, "name")
        
        if existing:
            return frappe.get_doc("POS Opening Entry", existing)
            
        opening_entry = frappe.get_doc({
            "doctype": "POS Opening Entry",
            "pos_profile": profile,
            "company": self.company.name,
            "branch": branch_name,
            "period_start_date": now_datetime(),
            "user": frappe.session.user,
            "balance_details": [{
                "mode_of_payment": self.mode_of_payment,
                "opening_amount": 0
            }]
        })
        opening_entry.insert(ignore_permissions=True)
        opening_entry.submit()
        return opening_entry
    
    # -------------------------------------------------------------------------
    # HELPERS - POS Invoice Creation (menggunakan nama yang sama dengan test lama)
    # -------------------------------------------------------------------------
    
    def _create_test_pos_invoice(self, qty=1, rate=100, customer=None, 
                                  items=None, payments=None, submit=False, **kwargs):
        """
        Helper untuk membuat POS Invoice dengan konfigurasi fleksibel.
        Menggunakan nama yang sama dengan test lama untuk compatibility.
        """
        total = 0
        invoice_items = []
        
        if items:
            invoice_items = items
            total = sum(item.get('qty', 0) * item.get('rate', 0) for item in items)
        else:
            total = qty * rate
            invoice_items = [{
                "item_code": self.item.name,
                "qty": qty,
                "rate": rate,
                "amount": total
            }]
            
        invoice_payments = payments or [{
            "mode_of_payment": self.mode_of_payment,
            "amount": total
        }]
        
        invoice_dict = {
            "doctype": "POS Invoice",
            "company": self.company.name,
            "customer": customer or self.customer.name,
            "posting_date": nowdate(),
            "posting_time": nowtime(),
            "pos_profile": self.pos_profile.name,
            "items": invoice_items,
            "payments": invoice_payments,
            "is_pos": 1
        }
        
        # Update dengan kwargs tambahan
        invoice_dict.update(kwargs)
        
        invoice = frappe.get_doc(invoice_dict)
        invoice.insert(ignore_permissions=True)
        
        if submit:
            invoice.submit()
            
        return invoice