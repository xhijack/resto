import frappe
from frappe import _
import json
from frappe.auth import LoginManager
from frappe.core.doctype.user.user import generate_keys

@frappe.whitelist()
def print_now():
    from resto.printing import pos_invoice_print_now
    return pos_invoice_print_now()

@frappe.whitelist(allow_guest=True)
def login_with_pin(pin):
    try:
        # 🔍 Cari user berdasarkan PIN
        user = frappe.db.get_value(
            "User",
            {"pincode": pin},
            ["name", "email", "username", "full_name"],
            as_dict=True
        )

        if not user:
            frappe.local.response["http_status_code"] = 404
            return {"status": "error", "message": "PIN Code not found"}

        # 🧹 Hapus semua session lama user ini (device lama akan logout otomatis)
        frappe.db.sql("DELETE FROM `tabSessions` WHERE user = %s", user.get("name"))

        # 🔐 Hapus API Key dan Secret lama
        frappe.db.set_value("User", user.get("name"), "api_key", None)
        frappe.db.set_value("User", user.get("name"), "api_secret", None)
        frappe.db.commit()  # Commit dulu agar benar-benar bersih

        # 🚪 Login baru pakai LoginManager
        login_manager = LoginManager()
        login_manager.user = user.get("name")
        login_manager.post_login()

        # 🔑 Buat API Key & Secret baru
        api_key, api_secret = generate_keys(user.get("name"))

        # 🧾 Response ke frontend
        frappe.response["message"] = {
            "status": "success",
            "message": "Authentication success",
            "sid": frappe.session.sid,  # ← ini penting untuk session
            "api_key": api_key,
            "api_secret": api_secret,
            "username": user.get("username"),
            "full_name": user.get("full_name"),
            "email": user.get("email"),
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

@frappe.whitelist(allow_guest=True)
def get_branch_list():
    data = frappe.get_all("Branch", fields=["name", "branch"])
    return data

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
def update_table_status(name, status, taken_by=None, pax=0, customer=None, type_customer=None, orders=None, checked=None):
    doc = frappe.get_doc("Table", name)

    if checked is not None:
        doc.checked = int(checked)

    doc.status = status
    doc.taken_by = taken_by or None
    doc.pax = int(pax) if pax else 0
    doc.customer = None if not customer else customer
    doc.type_customer = None if not type_customer else type_customer

    if isinstance(orders, str):
        try:
            orders = json.loads(orders)
        except Exception:
            frappe.log_error("Gagal parse orders JSON", orders)
            orders = []

    elif not isinstance(orders, list):
        orders = []

    doc.set("orders", [])

    if orders:
        for o in orders:
            invoice_name = o.get("invoice_name") if isinstance(o, dict) else o
            if invoice_name:
                doc.append("orders", {"invoice_name": invoice_name})

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "message": f"Table {doc.name} updated successfully", "checked": getattr(doc, "checked", None)}

@frappe.whitelist()
def add_table_order(table_name, order):
    """Tambah order baru ke Table tanpa menghapus orders lama"""
    import json

    if not table_name or not order:
        frappe.throw("Table name dan order wajib diisi.")

    # Ambil dokumen Table
    doc = frappe.get_doc("Table", table_name)

    # Pastikan order bisa dibaca (bisa dikirim sebagai dict atau JSON string)
    if isinstance(order, str):
        try:
            order = json.loads(order)
        except Exception:
            order = {"invoice_name": order}

    invoice_name = order.get("invoice_name")
    if not invoice_name:
        frappe.throw("Field 'invoice_name' wajib ada di order.")

    # Cek apakah invoice_name sudah ada
    existing_invoices = {o.invoice_name for o in doc.orders}
    if invoice_name in existing_invoices:
        return {"success": False, "message": f"Invoice {invoice_name} sudah ada di Table {table_name}"}

    # Tambahkan order baru
    doc.append("orders", {"invoice_name": invoice_name})

    # Ubah status jadi 'Terisi' jika sebelumnya kosong
    if doc.status == "Kosong":
        doc.status = "Terisi"

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"success": True, "message": f"Order {invoice_name} berhasil ditambahkan ke Table {table_name}"}

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

    customer         = payload.get("customer")
    pos_profile      = payload.get("pos_profile")
    branch      = payload.get("branch")
    items            = payload.get("items", [])
    payments         = payload.get("payments", [])
    queue            = payload.get("queue")
    additional_items = payload.get("additional_items", [])
    order_type       = payload.get("order_type")

    # Buat dokumen POS Invoice baru
    pos_invoice = frappe.get_doc({
        "doctype": "POS Invoice",
        "customer": customer,
        "pos_profile": pos_profile,
        "order_type": order_type,
        "branch": branch,
        "company": frappe.db.get_single_value("Global Defaults", "default_company"),
        "items": [],
        "payments": [],
        "queue": queue,
        "additional_items": [],   # ✅ gunakan fieldname yang sesuai
    })

    # Tambahkan item utama
    for item in items:
        pos_invoice.append("items", {
            "item_code": item.get("item_code"),
            "qty": item.get("qty"),
            "rate": item.get("rate"),
            "resto_menu": item.get("resto_menu"),
            "category": item.get("category"),
            "status_kitchen": item.get("status_kitchen"),
            "add_ons": item.get("add_ons"),  # tetap string field di item
            "quick_notes": item.get("quick_notes"),
        })

    # Tambahkan pembayaran
    for pay in payments:
        pos_invoice.append("payments", {
            "mode_of_payment": pay.get("mode_of_payment"),
            "amount": pay.get("amount")
        })

    # ✅ Tambahkan child table Additional Items
    if frappe.get_meta("POS Invoice").get_field("additional_items"):
        for add in additional_items:
            pos_invoice.append("additional_items", {
                "item_name": add.get("item_name"),
                "add_on": add.get("add_on"),
                "price": add.get("price"),
                "notes": add.get("notes"),
            })
    else:
        frappe.log_error("Field 'additional_items' tidak ditemukan di POS Invoice",
                         "Create POS Invoice Error")

    # Simpan dokumen
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
    2. Print ke kitchen station (optional — error tidak batalkan invoice)
    """
    try:
        result = create_pos_invoice(payload)
        pos_name = result["name"]

        try:
            print_to_ks_now(pos_name)
            printing_status = "Printing berhasil"
        except Exception as print_err:
            frappe.log_error(frappe.get_traceback(), f"Printing Error for POS {pos_name}")
            printing_status = f"Printing gagal: {str(print_err)}"

        return {
            "status": "success",
            "pos_invoice": pos_name,
            "message": f"POS Invoice {pos_name} created. {printing_status}"
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Send to Kitchen - Invoice Creation Error")
        frappe.throw(
            title="POS Invoice Creation Error",
            msg=str(e)
        )

# def print_bill(pos_name, printer_name) :

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

@frappe.whitelist(allow_guest=True)
def get_all_tables_with_details():
    tables = frappe.get_all(
        "Table",
        fields=[
            "name",
            "table_name",
            "status",
            "table_type",
            "zone",
            "customer",
            "pax",
            "type_customer",
            "floor",
            "taken_by",
            "order",
        ],
        order_by="table_name asc"
    )

    result = []
    for t in tables:
        doc = frappe.get_doc("Table", t.name)
        result.append({
            "id": t.name,
            "name": t.table_name,
            "status": t.status or "Kosong",
            "type": t.table_type,
            "zone": t.zone,
            "customer": t.customer or None,
            "pax": t.pax or 0,
            "typeCustomer": t.type_customer or None,
            "floor": t.floor or "1",
            "takenBy": t.taken_by or None,
            "order": t.order or None,
            "orders": [
                {"invoice_name": o.invoice_name} for o in doc.orders
            ],
        })

    return result

@frappe.whitelist()
def print_bill_now(invoice_name: str, branch: str):
    from resto.printing import _enqueue_bill_worker
    import frappe

    try:
        printer = frappe.db.get_value(
            "Printer Settings",
            {"branch": branch},
            "printer_bill_name"
        )

        if not printer:
            frappe.throw(f"Tidak ditemukan printer untuk branch {branch}")

        # Enqueue print job
        job_id = _enqueue_bill_worker(invoice_name, printer)
        frappe.msgprint(f"Invoice {invoice_name} dikirim ke printer {printer}")
        return {"ok": True, "job_id": job_id}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Print Bill Error")
        frappe.throw(f"Gagal print bill {invoice_name}: {str(e)}")

@frappe.whitelist()
def print_receipt_now(invoice_name: str, branch: str):
    from resto.printing import _enqueue_receipt_worker
    import frappe

    try:
        printer = frappe.db.get_value(
            "Printer Settings",
            {"branch": branch},
            "printer_receipt_name"
        )

        if not printer:
            frappe.throw(f"Tidak ditemukan printer untuk branch {branch}")

        # Enqueue print job
        job_id = _enqueue_receipt_worker(invoice_name, printer)
        frappe.msgprint(f"Invoice {invoice_name} dikirim ke printer {printer}")
        return {"ok": True, "job_id": job_id}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Print Receipt Error")
        frappe.throw(f"Gagal print Receipt {invoice_name}: {str(e)}")
