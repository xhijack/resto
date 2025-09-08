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
