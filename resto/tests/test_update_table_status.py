import frappe
import json
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.api import update_table_status

class TestUpdateTable(RestoPOSTestBase):
    """Unit tests for update_table_status API"""

    def setUp(self):
        super().setUp()
        # Create a test table
        self.table_name = self._create_test_table()
        # Create some POS invoices to use as orders
        self.invoice1 = self._create_test_pos_invoice(submit=True)
        self.invoice2 = self._create_test_pos_invoice(qty=2, rate=200, submit=True)

    def tearDown(self):
        # Clean up test table if exists
        if frappe.db.exists("Table", self.table_name):
            frappe.delete_doc("Table", self.table_name, force=True)
        super().tearDown()

    def _create_test_table(self):
        """Create a Table document for testing."""
        table_id = f"_Test Table {frappe.generate_hash(length=5)}"
        table = frappe.new_doc("Table")
        # Set required fields
        table.table_name = table_id
        table.status = "Kosong"
        table.taken_by = ""
        table.pax = 0
        table.customer = ""
        table.type_customer = ""
        table.checked = 0
        table.orders = []
        table.insert(ignore_permissions=True)
        return table.name

    def test_update_table_to_empty(self):
        """Set table to 'Kosong' should reset all fields"""
        # Set some non-default values (using valid link values)
        frappe.db.set_value("Table", self.table_name, {
            "status": "Terisi",
            "taken_by": "Administrator",  # valid user
            "pax": 4,
            "customer": self.customer.name,  # valid customer
            "type_customer": "Corporate",   # allowed value
            "checked": 1
        })
        # Add an order
        table = frappe.get_doc("Table", self.table_name)
        table.append("orders", {"invoice_name": self.invoice1.name})
        table.save()

        # Call API with status="Kosong"
        result = update_table_status(self.table_name, status="Kosong")
        self.assertTrue(result["success"])
        self.assertIn("updated successfully", result["message"])

        # Reload table and verify reset
        table.reload()
        self.assertEqual(table.status, "Kosong")
        self.assertEqual(table.taken_by, "")
        self.assertEqual(table.pax, 0)
        self.assertEqual(table.customer, "")
        self.assertEqual(table.type_customer, "")
        self.assertEqual(table.checked, 0)
        self.assertEqual(len(table.orders), 0)

    def test_update_table_status_only(self):
        """Update only status field"""
        result = update_table_status(self.table_name, status="Terisi")
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(table.status, "Terisi")
        # Other fields should remain default
        self.assertEqual(table.taken_by, "")
        self.assertEqual(table.pax, 0)
        self.assertEqual(table.customer, "")
        self.assertEqual(table.type_customer, "")

    def test_update_table_multiple_fields(self):
        """Update taken_by, pax, customer, type_customer, checked"""
        result = update_table_status(
            self.table_name,
            taken_by="Administrator",  # valid user
            pax=2,
            customer=self.customer.name,  # valid customer
            type_customer="Corporate",   # allowed
            checked=1
        )
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(table.taken_by, "Administrator")
        self.assertEqual(table.pax, 2)
        self.assertEqual(table.customer, self.customer.name)
        self.assertEqual(table.type_customer, "Corporate")
        self.assertEqual(table.checked, 1)
        # Status remains default
        self.assertEqual(table.status, "Kosong")

    def test_update_table_add_orders(self):
        """Add orders to table using list of invoice names"""
        orders = [self.invoice1.name, self.invoice2.name]
        result = update_table_status(self.table_name, orders=orders)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        order_invoices = [d.invoice_name for d in table.orders]
        self.assertEqual(set(order_invoices), set(orders))

    def test_update_table_add_orders_duplicate(self):
        """Adding duplicate invoice names should not create duplicates"""
        # First add one invoice
        update_table_status(self.table_name, orders=[self.invoice1.name])
        # Now add both invoices (one duplicate)
        update_table_status(self.table_name, orders=[self.invoice1.name, self.invoice2.name])
        table = frappe.get_doc("Table", self.table_name)
        order_invoices = [d.invoice_name for d in table.orders]
        # Should contain only unique invoices
        self.assertEqual(set(order_invoices), {self.invoice1.name, self.invoice2.name})
        self.assertEqual(len(order_invoices), 2)

    def test_update_table_orders_as_json_string(self):
        """Pass orders as JSON string"""
        orders_json = json.dumps([self.invoice1.name, self.invoice2.name])
        result = update_table_status(self.table_name, orders=orders_json)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        order_invoices = [d.invoice_name for d in table.orders]
        self.assertEqual(set(order_invoices), {self.invoice1.name, self.invoice2.name})

    def test_update_table_orders_invalid_json(self):
        """Invalid JSON in orders should be ignored and logged"""
        # Set initial orders
        update_table_status(self.table_name, orders=[self.invoice1.name])
        # Pass invalid JSON string
        result = update_table_status(self.table_name, orders="{invalid json}")
        self.assertTrue(result["success"])  # Should not raise error
        table = frappe.get_doc("Table", self.table_name)
        # Orders should remain unchanged
        order_invoices = [d.invoice_name for d in table.orders]
        self.assertEqual(order_invoices, [self.invoice1.name])

    def test_update_table_orders_non_list(self):
        """Pass orders as non-list (e.g., dict) should be ignored"""
        update_table_status(self.table_name, orders=[self.invoice1.name])
        result = update_table_status(self.table_name, orders={"invoice_name": self.invoice2.name})
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        # Orders should remain unchanged (no new orders added)
        order_invoices = [d.invoice_name for d in table.orders]
        self.assertEqual(order_invoices, [self.invoice1.name])

    def test_update_table_partial_update(self):
        """Update only one field and ensure others unchanged"""
        # Set some initial values using valid links
        frappe.db.set_value("Table", self.table_name, {
            "taken_by": "Administrator",
            "pax": 1,
            "customer": self.customer.name,
            "type_customer": "Corporate"
        })
        # Update only pax
        result = update_table_status(self.table_name, pax=3)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(table.pax, 3)
        self.assertEqual(table.taken_by, "Administrator")
        self.assertEqual(table.customer, self.customer.name)
        self.assertEqual(table.type_customer, "Corporate")

    def test_update_table_checked_value(self):
        """Verify checked value is returned in response"""
        # Set checked=1 via API
        result1 = update_table_status(self.table_name, checked=1)
        self.assertEqual(result1.get("checked"), 1)
        # Update checked=0 via API
        result2 = update_table_status(self.table_name, checked=0)
        self.assertEqual(result2.get("checked"), 0)
        # Now set checked to 5 via direct DB update
        frappe.db.set_value("Table", self.table_name, "checked", 5)
        frappe.db.commit()
        # Call API with status update only, no checked param
        result3 = update_table_status(self.table_name, status="Terisi")
        # Should still return 5 because we didn't change checked
        self.assertEqual(result3.get("checked"), 5)

    def test_update_table_orders_with_dict_list(self):
        """Pass orders as list of dicts with invoice_name"""
        orders = [{"invoice_name": self.invoice1.name}, {"invoice_name": self.invoice2.name}]
        result = update_table_status(self.table_name, orders=orders)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        order_invoices = [d.invoice_name for d in table.orders]
        self.assertEqual(set(order_invoices), {self.invoice1.name, self.invoice2.name})

    def test_update_table_orders_mixed_types(self):
        """Pass orders with mixed types (string and dict)"""
        orders = [self.invoice1.name, {"invoice_name": self.invoice2.name}]
        result = update_table_status(self.table_name, orders=orders)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        order_invoices = [d.invoice_name for d in table.orders]
        self.assertEqual(set(order_invoices), {self.invoice1.name, self.invoice2.name})