import frappe
from frappe import _

@frappe.whitelist(allow_guest=True)
def login_with_pin(email, pin):
    try:
        user = frappe.db.get_value("User", {"email": email}, ["name", "pin_code"], as_dict=True)

        if not user:
            frappe.local.response["http_status_code"] = 404
            return {"status": "error", "message": "User not found"}
        
        if user.get("pin_code") == pin:
            frappe.local.login_manager.user = user.get("name")
            frappe.local.login_manager.post_login()
            return {"status": "success", "message": "Logged In"}
        else:
            frappe.local.response["http_status_code"] = 401
            return {"status": "error", "message": "Invalid PIN"}
    
    except Exception as e:
        frappe.log_error(message=frappe.get_traceback(), title="Login With PIN Failed")
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": frappe.utils.cstr(e)}

@frappe.whitelist(allow_guest=False)
def create_customer(name, mobile_no):
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": name,
        "customer_type": "Company",
        "mobile_no": mobile_no,
        "mobile_number": mobile_no
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc.as_dict()

import frappe

@frappe.whitelist()
def update_table_status(name, status, taken_by=None, pax=0, customer=None, type_customer=None, order=None):
    doc = frappe.get_doc("Table", name)

    doc.status = status
    doc.taken_by = taken_by or None
    doc.pax = int(pax) if pax else 0

    doc.customer = None if not customer else customer
    doc.type_customer = None if not type_customer else type_customer
    doc.order = None if not order else order

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "message": f"Table {doc.table_name} updated"}

@frappe.whitelist()
def get_select_options(doctype, fieldname):
    meta = frappe.get_meta(doctype)
    field = next((f for f in meta.fields if f.fieldname == fieldname and f.fieldtype == "Select"), None)

    if not field:
        frappe.throw(f"Field {fieldname} bukan Select di {doctype}")

    options = [opt for opt in (field.options or "").split("\n") if opt]

    return {"options": options}