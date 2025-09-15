import frappe

def after_migrate(): 
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