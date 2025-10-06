import frappe
from frappe import _
import json

from resto.printing import pos_invoice_print_now

@frappe.whitelist(allow_guest=True)
def login_with_pin(email, pin):
    try:
        user = frappe.db.get_value(
            "User",
            {"email": email},
            ["name", "pin_code", "username", "full_name"],
            as_dict=True
        )
        if not user:
            frappe.local.response["http_status_code"] = 404
            return {"status": "error", "message": "User not found"}

        if user.get("pin_code") != pin:
            frappe.local.response["http_status_code"] = 401
            return {"status": "error", "message": "Invalid PIN"}

        # 🧹 Hapus semua session lama user ini (device lama ketendang)
        frappe.db.sql("DELETE FROM `tabSessions` WHERE user = %s", user.get("name"))

        # 🗝️ Hapus credential lama
        frappe.db.set_value("User", user.get("name"), "api_key", None)
        frappe.db.set_value("User", user.get("name"), "api_secret", None)

        # 🔐 Login baru
        login_manager = frappe.auth.LoginManager()
        login_manager.user = user.get("name")
        login_manager.post_login()

        # 🔑 Generate API key baru
        api_key, api_secret = generate_keys(user.get("name"))

        frappe.response["message"] = {
            "status": "success",
            "message": "Authentication success",
            "sid": frappe.session.sid,
            "api_key": api_key,
            "api_secret": api_secret,
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "email": email,
        }

        frappe.db.commit()

        return frappe.response["message"]

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Login With PIN Failed")
        frappe.local.response["http_status_code"] = 500
        return {"status": "error", "message": frappe.utils.cstr(e)}

def generate_keys(user):
    user_details = frappe.get_doc("User", user)
    api_secret = frappe.generate_hash(length=30)  # random baru tiap login

    # Kalau belum punya API key, buat baru
    if not user_details.api_key:
        api_key = frappe.generate_hash(length=15)
        user_details.api_key = api_key
    else:
        api_key = user_details.api_key

    # Simpan API secret baru (menendang token lama)
    user_details.api_secret = api_secret
    user_details.save(ignore_permissions=True)

    return api_key, api_secret

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

        # grouped = grouping_items_to_kitchen_station("", pos_name)
        # for kitchen_station, items in grouped.items():
            # send_to_ks_printing(kitchen_station, pos_name, items)

        branch_data = get_branch_menu_by_resto_menu(pos_name)

        for branch in branch_data:
            for kp in branch.get("kitchen_printers", []):
                printer_name = kp.get("printer_name")
                frappe.log(f"Sending to printer {printer_name} for POS {pos_name}")
                if not printer_name:
                    raise Exception("Printer name tidak ditemukan di kitchen_printers")
                pos_invoice_print_now(pos_name, printer_name)

        return {
            "status": "success",
            "pos_invoice": pos_name,
            "branch_data": branch_data
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Send to Kitchen Error")

        frappe.throw(
            title="Send to Kitchen Error",
            msg=str(e)
        )

def grouping_items_to_kitchen_station(branch, pos_name):
    """
    ***UNUSED***

    Grouping items by kitchen_station di POS Invoice Item.
    Return dict { kitchen_station: [items] }
    """
    items = frappe.get_all(
        "POS Invoice Item",
        filters={"parent": pos_name},
        fields=["item_code", "qty", "rate", "resto_menu", "category", "status_kitchen", "add_ons", "quick_notes"]
    )

    grouped = {}
    for item in items:
        branch_menu = frappe.get_doc("Branch Menu", filters={"branch": branch, "menu_item": item.get("resto_menu")})
        for ks in branch_menu.printers:
            kitchen_station = ks.printer_name
            if kitchen_station not in grouped:
                grouped[kitchen_station] = []
            grouped[kitchen_station].append(item)
    return grouped
        

def send_to_ks_printing(kitchen_station, pos_invoice, items):
    doc = frappe.new_doc("KS Printing")
    doc.kitchen_station = kitchen_station
    doc.pos_invoice = pos_invoice
    for item in items:
        doc.append("items", {
            "menu_item": item.get("resto_menu"),
            "qty": item.get("qty"),
            "add_ons": item.get("add_ons"),
            "quick_notes": item.get("quick_notes")
        })
    return doc.insert(ignore_permissions=True)

def print_to_ks_now(pos_invoice):
    from resto.printing import kitchen_print_from_payload
    for item in get_branch_menu_for_kitchen_printing(pos_invoice):
        ksp = send_to_ks_printing(item.get("kitchen_station"), pos_invoice, item.get("items", []))
        payload = {
            "kitchen_station": ksp.kitchen_station,
            "printer_name": ksp.printer_name,
            "pos_invoice": pos_invoice,
            "items": item.get("items", [])
        }
        kitchen_print_from_payload(payload)

@frappe.whitelist()
def get_branch_menu_for_kitchen_printing(pos_name: str):
    """
    Return list of tickets grouped by kitchen_station:
    [
      {
        "kitchen_station": "HOTKITCHEN",
        "pos_invoice": "POSINVOICE00001",
        "items": [
          {
            "resto_menu": "Nasi Goreng Spesial",
            "short_name": "NGS",
            "qty": 2,
            "quick_notes": "Tanpa Sambel",
            "add_ons": "Extra Kerupuk"
          }
        ]
      },
      ...
    ]
    """
    # Ambil branch dari POS Invoice agar pencarian Branch Menu relevan
    branch = frappe.db.get_value("POS Invoice", pos_name, "branch")

    # Ambil item dari POS Invoice Item (asumsi ada custom fields quick_notes & add_ons)
    pos_items = frappe.get_all(
        "POS Invoice Item",
        filters={"parent": pos_name},
        fields=["name", "resto_menu", "qty", "quick_notes", "add_ons"]
    )

    if not pos_items:
        return []

    # Group hasil per kitchen_station
    tickets_by_station = {}  # station -> list[items]
    short_name_cache = {}    # resto_menu -> short_name

    for it in pos_items:
        resto_menu = it.get("resto_menu")
        if not resto_menu:
            continue

        # Ambil short_name dari Resto Menu (cache biar hemat query)
        if resto_menu not in short_name_cache:
            short_name_cache[resto_menu] = frappe.db.get_value(
                "Resto Menu", resto_menu, "short_name"
            ) or ""

        # Cari Branch Menu yang sesuai resto_menu (dan branch jika tersedia)
        bm_filters = {"menu_item": resto_menu}
        if branch:
            bm_filters["branch"] = branch

        branch_menus = frappe.get_all(
            "Branch Menu",
            filters=bm_filters,
            fields=["name"]
        )

        if not branch_menus:
            # Jika tidak ada Branch Menu yang cocok, skip item ini
            # (atau bisa diarahkan ke station default jika ada requirement)
            continue

        # Kumpulkan station yang punya printer aktif (deduplicate)
        stations = set()
        for bm in branch_menus:
            bm_doc = frappe.get_doc("Branch Menu", bm.name)
            for ks in (bm_doc.printers or []):
                # Hanya station yang benar-benar punya printer_name
                if getattr(ks, "printer_name", None):
                    stations.add(getattr(ks, "kitchen_station", None))

        # Tambahkan item ini ke setiap station terkait
        for station in stations:
            if not station:
                continue

            tickets_by_station.setdefault(station, []).append({
                "resto_menu": resto_menu,
                "short_name": short_name_cache.get(resto_menu, ""),
                "qty": it.get("qty") or 0,
                "quick_notes": it.get("quick_notes") or "",
                "add_ons": it.get("add_ons") or "",
            })

    # Susun output list dengan field pos_invoice
    result = []
    for station, items in tickets_by_station.items():
        if not items:
            continue
        result.append({
            "kitchen_station": station,
            "pos_invoice": pos_name,
            "items": items
        })

    # (Opsional) urutkan biar stabil
    result.sort(key=lambda x: x["kitchen_station"] or "")
    return result

