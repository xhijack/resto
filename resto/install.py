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
            "fieldtype": "Table",
            "insert_after": "resto_menu",
            "options": "Quick Notes",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "add_ons", "dt": "POS Invoice Item"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice Item",
            "fieldname": "add_ons",
            "label": "Add Ons",
            "fieldtype": "Table",
            "insert_after": "resto_menu",
            "options": "Menu Add Ons",
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {'fieldname': "pin_code", "dt": "User"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "User",
            "fieldname": "pin_code",
            "label": "PIN Code",
            "fieldtype": "Data",
            "length": 6,
            "insert_after": "username"
        }).insert(ignore_permissions=True)

    if not frappe.db.exists("Custom Field", {"fieldname": "status_kitchen", "dt": "POS Invoice"}):
        frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "POS Invoice",
            "fieldname": "status_kitchen",
            "label": "Status Kitchen",
            "fieldtype": "Select",
            "options": "\nBelum Dikirim\nDikirim ke Dapur\nSelesai",
            "insert_after": "pos_profile",
        }).insert(ignore_permissions=True)

