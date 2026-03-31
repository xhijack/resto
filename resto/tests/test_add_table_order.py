import frappe
import json
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.api import add_table_order

class TestAddTableOrder(RestoPOSTestBase):
    """Unit tests for add_table_order API"""

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

    # -------------------------------------------------------------------------
    # Test Cases
    # -------------------------------------------------------------------------

    def test_add_new_order_success(self):
        """Add a new order to an empty table"""
        # Initially no orders
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 0)
        self.assertEqual(table.status, "Kosong")

        # Call API to add an order
        result = add_table_order(self.table_name, {"invoice_name": self.invoice1.name})
        self.assertTrue(result["success"])
        self.assertIn("berhasil ditambahkan", result["message"])

        # Reload table and verify
        table.reload()
        self.assertEqual(len(table.orders), 1)
        self.assertEqual(table.orders[0].invoice_name, self.invoice1.name)
        # Status should become "Terisi"
        self.assertEqual(table.status, "Terisi")

    def test_add_order_to_already_occupied_table(self):
        """Add order to a table that already has orders"""
        # First add one order
        add_table_order(self.table_name, {"invoice_name": self.invoice1.name})
        # Now add second order
        result = add_table_order(self.table_name, {"invoice_name": self.invoice2.name})
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 2)
        # Status should stay "Terisi"
        self.assertEqual(table.status, "Terisi")

    def test_add_duplicate_order_fails(self):
        """Attempt to add the same invoice twice should return failure"""
        # Add first time
        add_table_order(self.table_name, {"invoice_name": self.invoice1.name})
        # Try to add again
        result = add_table_order(self.table_name, {"invoice_name": self.invoice1.name})
        self.assertFalse(result["success"])
        self.assertIn("sudah ada", result["message"])
        # Verify no duplicate added
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 1)

    def test_add_order_as_json_string(self):
        """Pass order as JSON string"""
        order_json = json.dumps({"invoice_name": self.invoice1.name})
        result = add_table_order(self.table_name, order_json)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 1)
        self.assertEqual(table.orders[0].invoice_name, self.invoice1.name)

    def test_add_order_with_extra_fields(self):
        """Order dict can contain extra fields, only invoice_name is extracted"""
        order = {
            "invoice_name": self.invoice1.name,
            "discount": 10,
            "notes": "Extra cheese"
        }
        result = add_table_order(self.table_name, order)
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 1)
        self.assertEqual(table.orders[0].invoice_name, self.invoice1.name)
        # Extra fields are not stored in orders child table
        self.assertNotIn("discount", table.orders[0].as_dict())

    def test_add_order_missing_table_name(self):
        """Missing table_name should raise exception"""
        with self.assertRaises(frappe.ValidationError) as cm:
            add_table_order("", {"invoice_name": self.invoice1.name})
        self.assertIn("wajib diisi", str(cm.exception))

    def test_add_order_missing_order(self):
        """Missing order parameter should raise exception"""
        with self.assertRaises(frappe.ValidationError) as cm:
            add_table_order(self.table_name, None)
        self.assertIn("wajib diisi", str(cm.exception))

    def test_add_order_missing_invoice_name(self):
        """Order dict missing invoice_name should raise exception"""
        with self.assertRaises(frappe.ValidationError) as cm:
            add_table_order(self.table_name, {"something": "else"})
        self.assertIn("invoice_name", str(cm.exception))

    def test_add_order_invalid_json_string(self):
        """Passing invalid JSON string should treat as plain string, using it as invoice_name."""
        # The function will fall back to {"invoice_name": order} for any string,
        # even invalid JSON. So it will add an order with that string as invoice_name.
        result = add_table_order(self.table_name, "{invalid json")
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 1)
        self.assertEqual(table.orders[0].invoice_name, "{invalid json")

    def test_add_order_non_existent_table(self):
        """Table name that doesn't exist should raise exception"""
        with self.assertRaises(frappe.DoesNotExistError):
            add_table_order("NonExistentTable123", {"invoice_name": self.invoice1.name})

    def test_add_order_preserves_existing_orders(self):
        """Adding new order should not remove existing ones"""
        # Add first order
        add_table_order(self.table_name, {"invoice_name": self.invoice1.name})
        # Add second order
        add_table_order(self.table_name, {"invoice_name": self.invoice2.name})
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(len(table.orders), 2)
        self.assertEqual(table.orders[0].invoice_name, self.invoice1.name)
        self.assertEqual(table.orders[1].invoice_name, self.invoice2.name)

    def test_add_order_when_table_status_not_kosong(self):
        """If table status is already Terisi, adding order does not change status"""
        # Set status to Terisi manually (without orders)
        frappe.db.set_value("Table", self.table_name, "status", "Terisi")
        frappe.db.commit()
        # Add order
        result = add_table_order(self.table_name, {"invoice_name": self.invoice1.name})
        self.assertTrue(result["success"])
        table = frappe.get_doc("Table", self.table_name)
        self.assertEqual(table.status, "Terisi")  # remains Terisi