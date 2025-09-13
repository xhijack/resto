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

@frappe.whitelist(allow_guest=True)
def update_table_status(table_name, status, taken_by=None):
    if not table_name:
        frappe.throw("table_name wajib diisi")

    doc = frappe.get_doc("Table", table_name)
    doc.status = status
    doc.taken_by = taken_by
    doc.save(ignore_permissions=True)

    frappe.db.commit()
    return {"success": True, "table": doc}