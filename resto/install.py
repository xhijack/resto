import frappe

def after_migrate():
    if not frappe.db.exists("DocType", "POS Invoice Item"):
        frappe.logger().warning("POS Invoice Item DocType not found. Skipping custom fields creation.")
        return

    if not frappe.db.exists("Custom Field", {'fieldname': "resto_menu", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "resto_menu",
            "label": "Resto Menu",
            "fieldtype": "Link",
            "options": "Resto Menu",
            "insert_after": "item_name",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "category", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "category",
            "label": "Category",
            "fieldtype": "Data",
            "insert_after": "resto_menu",
            "fetch_from": "resto_menu.menu_category",
            "read_only": 1,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "quick_notes", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "quick_notes",
            "label": "Quick Notes",
            "fieldtype": "Small Text",
            "insert_after": "resto_menu",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "add_ons", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "add_ons",
            "label": "Add Ons",
            "fieldtype": "Small Text",
            "insert_after": "quick_notes",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "is_checked", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "is_checked",
            "label": "Is Checked (Printed)",
            "fieldtype": "Check",
            "insert_after":"add_ons",
            "default": 0,
        }).insert(ignore_permissions=True)

    # if not frappe.db.exists("Custom Field", {"fieldname": "pin_code", "dt": "User"}):
    #     frappe.get_doc({
    #         "doctype": "Custom Field",
    #         "dt": "User",
    #         "fieldname": "pin_code",
    #         "label": "PIN Code",
    #         "fieldtype": "Data",
    #         "unique": 1,
    #         "length": 6,
    #         "insert_after": "username",
    #         "description": "Masukkan 6 digit PIN unik untuk login"
    #     }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {"fieldname": "pincode", "dt": "User"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "User",
            "fieldname": "pincode",
            "label": "PIN Code",
            "fieldtype": "Data",
            "unique": 1,
            "length": 6,
            "insert_after": "username",
            "description": "Masukkan 6 digit PIN unik untuk login"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "status_kitchen", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "status_kitchen",
            "label": "Status Kitchen",
            "fieldtype": "Select",
            "insert_after": "item_code",
            "options": "\nNot Send\nAlready Send To Kitchen\nVoid Menu",
        }).insert(ignore_permissions=True)
    
    if not frappe.db.exists("Custom Field", {'fieldname': 'void_qty', 'dt': 'POS Invoice Item'}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "void_qty",
            "label": "Void QTY",
            "fieldtype": "Float",
            "insert_after": "stock_uom",
            "read_only": 1,
            "allow_on_submit": 1,
            "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': 'void_rate', 'dt': 'POS Invoice Item'}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "void_rate",
            "label": "Void Rate",
            "fieldtype": "Currency",
            "insert_after": "item_tax_template",
            "read_only": 1,
            "allow_on_submit": 1,
            "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': 'void_amount', 'dt': 'POS Invoice Item'}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "void_amount",
            "label": "Void Amount",
            "fieldtype": "Currency",
            "insert_after": "void_rate",
            "read_only": 1,
            "allow_on_submit": 1,
            "depends_on": "eval:doc.status_kitchen == 'Void Menu'"
        }).insert(ignore_permissions=True)
    
    if not frappe.db.exists("Custom Field", {'fieldname': 'kitchen_stock_consumed', 'dt': 'POS Invoice Item'}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "kitchen_stock_consumed",
            "label": "Kitchen Stock Consumed",
            "fieldtype": "Check",
            "insert_after": "stock_uom",
            "read_only": 1,
            "hidden": 1,
            "default": 0
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': 'queue', 'dt': 'POS Invoice'}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "queue",
            "label": "Queue",
            "fieldtype": "Data",
            "insert_after": "status_kitchen"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "branch", "dt": "POS Invoice"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "branch",
            "label": "Branch",
            "fieldtype": "Link",
            "options": "Branch",
            "insert_after": "due_date",
        }).insert(ignore_permissions=True)
    
    if not frappe.db.exists("Custom Field", {'fieldname': "additional_items", "dt": "POS Invoice"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "additional_items",
            "label": "Additional Items",
            "fieldtype": "Table",
            "options": "Additional Items",  
            "insert_after": "items",
        }).insert(ignore_permissions=True)
    
    if not frappe.db.exists("Custom Field", {'fieldname': "order_type", "dt": "POS Invoice"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "order_type",
            "label": "Order Type",
            "fieldtype": "Select",
            "options": "Dine In\nTake Away",
            "insert_after": "branch",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "address", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "address",
            "label": "Address",
            "fieldtype": "Link",
            "options": "Address",
            "insert_after": "branch",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "address_line1", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "address_line1",
            "label": "Adress Line 1",
            "fieldtype": "Data",
            "insert_after": "address",
            "fetch_from": "address.address_line1",
            "read_only": 1,
        }).insert(ignore_permissions=True)
    
    if not frappe.db.exists("Custom Field", {'fieldname': "address_line2", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "address_line2",
            "label": "Adress Line 2",
            "fieldtype": "Data",
            "insert_after": "address_line1",
            "fetch_from": "address.address_line2",
            "read_only": 1,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "city", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "city",
            "label": "City",
            "fieldtype": "Data",
            "insert_after": "address_line2",
            "fetch_from": "address.city",
            "read_only": 1,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "state", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "state",
            "label": "State/Province",
            "fieldtype": "Data",
            "insert_after": "city",
            "fetch_from": "address.state",
            "read_only": 1,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "pincode", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "pincode",
            "label": "Postal Code",
            "fieldtype": "Data",
            "insert_after": "state",
            "fetch_from": "address.pincode",
            "read_only": 1,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "phone", "dt": "Branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Branch",
            "fieldname": "phone",
            "label": "Phone",
            "fieldtype": "Data",
            "insert_after": "pincode",
            "fetch_from": "address.phone",
            "read_only": 1,
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {"dt": "Company", "fieldname": "custom_company_logo"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Company",
            "fieldname": "custom_company_logo",
            "label": "Company Logo",
            "fieldtype": "Attach Image",
            "insert_after": "company_name"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "discount_for_bank"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "discount_for_bank",
            "label": "Discount For Bank",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "base_discount_amount"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {"dt": "POS Invoice", "fieldname": "discount_name"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "discount_name",
            "label": "Discount Name",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "base_discount_amount"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {"dt": "POS Closing Entry", "fieldname": "end_day_processed"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Closing Entry",
            "fieldname": "end_day_processed",
            "label": "End Day Processed",
            "fieldtype": "Check",
            "default": 0,
            "read_only": 1,
            "allow_on_submit": 1,
            "insert_after": "period_end_date"
        }).insert(ignore_permissions=True)
        
    if not frappe.db.exists("Custom Field", {"dt": "POS Opening Entry", "fieldname": "branch"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Opening Entry",
            "fieldname": "branch",
            "label": "Branch",
            "fieldtype": "Link",
            "options": "Branch",
            "reqd": 1,
            "insert_after": "user"
        }).insert(ignore_permissions=True)