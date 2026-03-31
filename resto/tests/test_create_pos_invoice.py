# test_create_pos_invoice.py - TETAP SAMA

import frappe
from resto.tests.resto_pos_test_base import RestoPOSTestBase

# Import function under test
from resto.api import create_pos_invoice


class TestCreatePOSInvoice(RestoPOSTestBase):
    """Unit tests for create_pos_invoice API"""
    
    def setUp(self):
        """Setup spesifik untuk test pembuatan POS Invoice"""
        super().setUp()
        
        # Buat POS Opening Entry (wajib untuk membuat POS Invoice)
        self.pos_opening_entry = self._create_pos_opening_entry()
        
        # Setup tax templates untuk Dine In dan Take Away
        self.tax_template_dine_in = self._create_tax_template("Dengan Service")
        self.tax_template_take_away = self._create_tax_template("Tanpa Service")
        
        # Setup Resto Menu
        self.resto_menu = self._create_resto_menu()
        
        # Set default company di Global Defaults
        self._ensure_global_defaults()

        
        test_role = "System Manager"  # biasanya sudah ada di test user

        # Tambahkan permission agar test existing tetap jalan
        test_role = "System Manager"

        self._setup_permissions(test_role, [
            "Allow Create POS Invoice"
        ])


    def _setup_permissions(self, role, permissions):
        if isinstance(permissions, str):
            permissions = [permissions]

        settings = frappe.get_single("Resto Settings")

        # clear dulu biar gak duplicate
        settings.permissions = []

        for p in permissions:
            settings.append("permissions", {
                "role": role,
                "permission": p
            })

        settings.save(ignore_permissions=True)
    
    def _ensure_global_defaults(self):
        """Pastikan default company tersetting"""
        defaults = frappe.get_single("Global Defaults")
        if not defaults.default_company:
            defaults.default_company = self.company.name
            defaults.save()
    
    def _get_or_create_brand(self, brand_name=None):
        """Ambil atau buat Brand"""
        b_name = brand_name or f"_Test Brand Resto - {self.company.abbr}"
        if frappe.db.exists("Brand", b_name):
            return b_name
            
        brand = frappe.get_doc({
            "doctype": "Brand", 
            "brand": b_name
        })
        brand.insert(ignore_permissions=True)
        return b_name
    
    def _create_tax_template(self, title):
        """Buat Sales Taxes and Charges Template"""
        template_name = f"{title} - {self.company.abbr}"
        if frappe.db.exists("Sales Taxes and Charges Template", template_name):
            return frappe.get_doc("Sales Taxes and Charges Template", template_name)
            
        account_head = self._get_or_create_expense_account()
        
        template = frappe.get_doc({
            "doctype": "Sales Taxes and Charges Template",
            "title": title,
            "company": self.company.name,
            "taxes": [{
                "charge_type": "On Net Total",
                "account_head": account_head,
                "description": "Service Tax",
                "rate": 10,
                "included_in_print_rate": 0
            }]
        })
        template.insert(ignore_permissions=True)
        return template
    
    def _create_resto_menu(self):
        """Buat Resto Menu untuk test"""
        menu_code = "TM"
        title = "_Test Resto Menu"
        name = f"{menu_code}-{title}"
        
        if frappe.db.exists("Resto Menu", name):
            return frappe.get_doc("Resto Menu", name)
            
        brand = self._get_or_create_brand()
        
        menu = frappe.get_doc({
            "doctype": "Resto Menu",
            "title": title,
            "menu_code": menu_code,
            "sell_item": self.item.name,
            "brand": brand,
            "use_stock": 0
        })
        menu.insert(ignore_permissions=True)
        return menu
    
    # ========================================================================
    # TEST CASES
    # ========================================================================
    
    def test_create_pos_invoice_dine_in(self):
        """Test pembuatan invoice dengan order type Dine In"""
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Dine In",
            "items": [{
                "item_code": self.item.name,
                "qty": 2,
                "rate": 100,
                "resto_menu": self.item.name,
                "category": "Food",
                "status_kitchen": "Not Send"
            }],
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "amount": 200
            }]
        }
        
        result = create_pos_invoice(payload)
        self.assertEqual(result["status"], "success")
        
        pos_invoice = frappe.get_doc("POS Invoice", result["name"])
        self.assertEqual(pos_invoice.order_type, "Dine In")
        self.assertEqual(pos_invoice.taxes_and_charges, self.tax_template_dine_in.name)
        self.assertEqual(len(pos_invoice.items), 1)
        self.assertEqual(pos_invoice.items[0].qty, 2)
        self.assertEqual(pos_invoice.docstatus, 0)

    def test_create_pos_invoice_take_away(self):
        """Test pembuatan invoice dengan order type Take Away"""
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Take Away",
            "items": [{
                "item_code": self.item.name,
                "qty": 1,
                "rate": 150,
                "resto_menu": self.item.name
            }],
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "amount": 150
            }]
        }
        
        result = create_pos_invoice(payload)
        pos_invoice = frappe.get_doc("POS Invoice", result["name"])
        self.assertEqual(pos_invoice.order_type, "Take Away")
        self.assertEqual(pos_invoice.taxes_and_charges, self.tax_template_take_away.name)

    def test_create_pos_invoice_with_additional_items(self):
        """Test pembuatan invoice dengan additional items"""
        if not frappe.get_meta("POS Invoice").get_field("additional_items"):
            self.skipTest("additional_items field not found in POS Invoice")
            
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Dine In",
            "items": [{
                "item_code": self.item.name,
                "qty": 1,
                "rate": 100,
                "resto_menu": self.item.name
            }],
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "amount": 100
            }],
            "additional_items": [{
                "resto_menu": self.resto_menu.name,
                "add_on": "Extra cheese",
                "price": 20,
                "notes": "Add extra cheese"
            }]
        }
        
        result = create_pos_invoice(payload)
        pos_invoice = frappe.get_doc("POS Invoice", result["name"])
        self.assertEqual(len(pos_invoice.additional_items), 1)
        self.assertIn(self.resto_menu.title, pos_invoice.additional_items[0].item_name)
        self.assertEqual(pos_invoice.additional_items[0].price, 20)

    def test_create_pos_invoice_with_discount_params(self):
        """Test pembuatan invoice dengan parameter diskon"""
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Dine In",
            "items": [{
                "item_code": self.item.name,
                "qty": 1,
                "rate": 100,
                "resto_menu": self.item.name
            }],
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "amount": 100
            }],
            "discount_amount": 10,
            "discount_name": "Test Discount",
            "discount_for_bank": "Test Bank"
        }
        
        result = create_pos_invoice(payload)
        pos_invoice = frappe.get_doc("POS Invoice", result["name"])
        self.assertEqual(pos_invoice.discount_amount, 10)
        self.assertEqual(pos_invoice.discount_name, "Test Discount")
        self.assertEqual(pos_invoice.discount_for_bank, "Test Bank")

    def test_create_pos_invoice_queue(self):
        """Test pembuatan invoice dengan nomor antrian"""
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Take Away",
            "items": [{
                "item_code": self.item.name,
                "qty": 1,
                "rate": 100,
                "resto_menu": self.item.name
            }],
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "amount": 100
            }],
            "queue": "Q123"
        }
        
        result = create_pos_invoice(payload)
        pos_invoice = frappe.get_doc("POS Invoice", result["name"])
        self.assertEqual(pos_invoice.queue, "Q123")
    
    # ========================================================================
    # ERROR CASES
    # ========================================================================
    
    def test_create_pos_invoice_missing_customer(self):
        """Test error jika customer tidak disediakan"""
        payload = {
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Dine In",
            "items": [{"item_code": self.item.name, "qty": 1, "rate": 100}]
        }
        
        with self.assertRaises(frappe.ValidationError):
            create_pos_invoice(payload)

    def test_create_pos_invoice_missing_items(self):
        """Test error jika items kosong"""
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Dine In",
            "items": [],
            "payments": [{"mode_of_payment": self.mode_of_payment, "amount": 100}]
        }
        
        with self.assertRaises(Exception):
            create_pos_invoice(payload)

    def test_create_pos_invoice_invalid_order_type(self):
        """Test error jika order_type tidak valid"""
        payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": "Delivery",
            "items": [{
                "item_code": self.item.name,
                "qty": 1,
                "rate": 100,
                "resto_menu": self.item.name
            }],
            "payments": [{
                "mode_of_payment": self.mode_of_payment,
                "amount": 100
            }]
        }
        
        with self.assertRaises(frappe.ValidationError):
            create_pos_invoice(payload)

    