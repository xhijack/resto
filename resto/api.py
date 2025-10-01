import frappe
from frappe import _
import json

from resto.printing import pos_invoice_print_now

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

def create_pos_invoice(payload):
    """
    Fungsi reusable untuk membuat & submit POS Invoice.
    Return dict { status, name }
    """
    if isinstance(payload, str):
        payload = json.loads(payload)

    customer    = payload.get("customer")
    pos_profile = payload.get("pos_profile")
    items       = payload.get("items", [])
    payments    = payload.get("payments", [])
    queue       = payload.get("queue")

    pos_invoice = frappe.get_doc({
        "doctype": "POS Invoice",
        "customer": customer,
        "pos_profile": pos_profile,
        "company": frappe.db.get_single_value("Global Defaults", "default_company"),
        "items": [],
        "payments": [],
        "queue": queue,
    })

    for item in items:
        pos_invoice.append("items", {
            "item_code": item.get("item_code"),
            "qty": item.get("qty"),
            "rate": item.get("rate"),
            "resto_menu": item.get("resto_menu"),
            "category": item.get("category"),
            "status_kitchen": item.get("status_kitchen"),
            "add_ons": item.get("add_ons"),
            "quick_notes": item.get("quick_notes")
        })

    for pay in payments:
        pos_invoice.append("payments", {
            "mode_of_payment": pay.get("mode_of_payment"),
            "amount": pay.get("amount")
        })

    pos_invoice.insert(ignore_permissions=True)
    pos_invoice.save()

    return {
        "status": "success",
        "name": pos_invoice.name
    }

def get_branch_menu_by_resto_menu(pos_name):
    branch_results = []
    items = frappe.get_all(
        "POS Invoice Item",
        filters={"parent": pos_name},
        fields=["resto_menu"]
    )

    for it in items:
        resto_menu = it.get("resto_menu")
        if not resto_menu:
            continue

        branch_menus = frappe.get_all(
            "Branch Menu",
            filters={"menu_item": resto_menu},
            fields=["name","branch","menu_item"]
        )

        for bm in branch_menus:
            bm_doc = frappe.get_doc("Branch Menu", bm.name)
            kitchen_printers = []
            for ks in bm_doc.printers:
                if ks.printer_name:
                    kitchen_printers.append({
                        "station": ks.kitchen_station,
                        "printer_name": ks.printer_name
                    })

            branch_results.append({
                "resto_menu": resto_menu,
                "branch": bm.branch,
                "kitchen_printers": kitchen_printers
            })

    return branch_results

@frappe.whitelist()
def send_to_kitchen(payload):
    """
    1. Buat POS Invoice
    2. Cari Branch Menu per resto_menu
    """
    try:
        result = create_pos_invoice(payload)
        pos_name = result["name"]

        branch_data = get_branch_menu_by_resto_menu(pos_name)

        for branch in branch_data:
            for kp in branch["kitchen_printers"]:
                printer_name = kp["printer_name"]
                pos_invoice_print_now(pos_name, printer_name)

        return {
            "status": "success",
            "pos_invoice": pos_name,
            "branch_data": branch_data
        }



    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Send to Kitchen Error")
        return {
            "status": "error",
            "message": str(e)
        }
