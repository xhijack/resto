import frappe
from frappe import _
import json
from frappe.auth import LoginManager
from frappe.core.doctype.user.user import generate_keys
from frappe.utils import flt, get_datetime, now_datetime

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
    from resto.repositories.menu_repository import MenuRepository
    return MenuRepository().get_all_branches()

@frappe.whitelist()
def get_all_branch_menu_with_children(branch=None):
    from resto.services.kitchen_service import KitchenService
    return KitchenService().get_all_branch_menu_with_children(branch=branch)

@frappe.whitelist(allow_guest=False)
def create_customer(name, mobile_no=None):
    from resto.repositories.customer_repository import CustomerRepository
    return CustomerRepository().create_customer(name, mobile_no=mobile_no)

@frappe.whitelist()
def update_table_status(name, status=None, taken_by=None, pax=None, customer=None, type_customer=None, orders=None, checked=None):
    from resto.services.table_service import TableService
    return TableService().update_table_status(
        name, status=status, taken_by=taken_by, pax=pax,
        customer=customer, type_customer=type_customer, orders=orders, checked=checked
    )

@frappe.whitelist()
def add_table_order(table_name, order):
    from resto.services.table_service import TableService
    return TableService().add_table_order(table_name, order)

@frappe.whitelist()
def get_select_options(doctype, fieldname):
    meta = frappe.get_meta(doctype)
    field = next((f for f in meta.fields if f.fieldname == fieldname and f.fieldtype == "Select"), None)

    if not field:
        frappe.throw(f"Field {fieldname} bukan Select di {doctype}")

    options = [opt for opt in (field.options or "").split("\n") if opt]

    return {"options": options}

def create_pos_invoice(payload):
    from resto.services.invoice_service import InvoiceService
    return InvoiceService().create_pos_invoice(payload)

def get_branch_menu_by_resto_menu(pos_name):
    from resto.services.kitchen_service import KitchenService
    return KitchenService().get_branch_menu_by_resto_menu(pos_name)

@frappe.whitelist()
def process_kitchen_printing(pos_invoice):
    frappe.enqueue(
        "resto.api._process_kitchen_printing_worker",
        queue="long",
        timeout=300,
        pos_invoice=pos_invoice
    )

    return True

def _process_kitchen_printing_worker(pos_invoice):
    from resto.services.kitchen_service import KitchenService
    KitchenService().process_kitchen_printing_worker(pos_invoice)

@frappe.whitelist()
def enqueue_checker_after_kitchen(pos_name: str, branch: str):
    from resto.services.printing_service import PrintingService
    return PrintingService().enqueue_checker_after_kitchen(pos_name, branch)

@frappe.whitelist()
def send_to_kitchen(payload, table_name=None, status=None, taken_by=None, pax=0,
                    customer=None, type_customer=None, orders=None, checked=None):
    from resto.services.kitchen_service import KitchenService
    return KitchenService().send_to_kitchen(
        payload=payload, table_name=table_name, status=status, taken_by=taken_by,
        pax=pax, customer=customer, type_customer=type_customer,
        orders=orders, checked=checked
    )

# TODO: grouping_items_to_kitchen_station — implement atau hapus jika tidak diperlukan
# def grouping_items_to_kitchen_station(branch, pos_name): ...

# TODO: send_to_ks_printing — pindahkan ke PrintingService jika KS Printing doctype diaktifkan
# def send_to_ks_printing(kitchen_station, pos_invoice, items): ...

def print_to_ks_now(pos_invoice):
    from resto.services.kitchen_service import KitchenService
    KitchenService().print_to_ks_now(pos_invoice)

@frappe.whitelist()
def get_branch_menu_for_kitchen_printing(pos_name: str):
    from resto.services.kitchen_service import KitchenService
    return KitchenService().get_branch_menu_for_kitchen_printing(pos_name)

@frappe.whitelist(allow_guest=True)
def get_all_tables_with_details():
    from resto.services.table_service import TableService
    return TableService().get_all_tables_with_details()

@frappe.whitelist()
def print_bill_now(invoice_name: str, branch: str, table_name=None,
                   status=None, taken_by=None, pax=0,
                   customer=None, type_customer=None, orders=None, checked=None):
    from resto.services.printing_service import PrintingService
    from resto.services.table_service import TableService
    return PrintingService().print_bill_now(
        invoice_name, branch, table_name=table_name, status=status,
        taken_by=taken_by, pax=pax, customer=customer,
        type_customer=type_customer, orders=orders, checked=checked,
        table_service=TableService() if table_name else None
    )

@frappe.whitelist()
def print_receipt_now(invoice_name: str, branch: str):
    from resto.services.printing_service import PrintingService
    return PrintingService().print_receipt_now(invoice_name, branch)



@frappe.whitelist()
def get_end_day_report():
    from resto.services.reporting_service import ReportingService
    return ReportingService().get_end_day_report()



@frappe.whitelist()
def get_end_day_report_v2(posting_date=None, outlet=None, do_print=False):
    from resto.services.reporting_service import ReportingService
    return ReportingService().get_end_day_report_v2(
        posting_date=posting_date, outlet=outlet, do_print=do_print
    )

@frappe.whitelist()
def end_shift(user=None, is_submit=True):
    from resto.services.reporting_service import ReportingService
    return ReportingService().end_shift(user=user, is_submit=is_submit)

@frappe.whitelist()
def get_discounts_with_options():
    from resto.repositories.discount_repository import DiscountRepository
    return DiscountRepository().get_discounts_with_options()

@frappe.whitelist()
def get_select_options(doctype, fieldname):
    """
    Mengambil pilihan dari field Select
    """
    if not doctype or not fieldname:
        frappe.throw(_("doctype dan fieldname wajib diisi"))

    meta = frappe.get_meta(doctype)
    field = meta.get_field(fieldname)
    if not field:
        frappe.throw(_("Field {0} tidak ditemukan di {1}").format(fieldname, doctype))

    options = field.options
    if options:
        options_list = [o.strip() for o in options.split("\n") if o.strip()]
    else:
        options_list = []

    return options_list

@frappe.whitelist()
def get_active_pos_profile_for_user(user):
    from resto.services.pos_service import POSService
    return POSService().get_active_pos_profile_for_user(user)

import frappe

@frappe.whitelist()
def get_active_pos_opening():
    from resto.services.pos_service import POSService
    return POSService().get_active_pos_opening(frappe.session.user)

@frappe.whitelist()
def check_pos_status_for_user(user=None):
    from resto.services.pos_service import POSService
    user = user or frappe.session.user
    return POSService().check_pos_status_for_user(user)

@frappe.whitelist()
def open_pos(user=None, pos_profile=None, opening_balance=0, branch=None):

    user = user or frappe.session.user

    # Ambil POS Profile
    if not pos_profile:
        pos_profile_list = frappe.get_all(
            "POS Profile User",
            filters={"user": user},
            pluck="parent",
            limit=1
        )
        if not pos_profile_list:
            frappe.throw("POS Profile untuk user ini tidak ditemukan")
        pos_profile = pos_profile_list[0]

    # Ambil branch
    if not branch:
        branch = frappe.db.get_value("POS Profile", pos_profile, "branch")

    if not branch:
        frappe.throw("Branch tidak ditemukan untuk POS Profile ini")

    opening = frappe.get_doc({
        "doctype": "POS Opening Entry",
        "pos_profile": pos_profile,
        "user": user,
        "branch": branch,
        "status": "Open",
        "period_start_date": now_datetime(),
        "opening_balance": opening_balance
    })

    opening.append("balance_details", {
        "mode_of_payment": "Cash",
        "opening_amount": opening_balance
    })

    opening.insert(ignore_permissions=True)
    opening.submit()

    return {
        "name": opening.name,
        "pos_profile": pos_profile,
        "branch": branch
    }

@frappe.whitelist(allow_guest=True)
def get_company_name():
    from resto.repositories.menu_repository import MenuRepository
    return MenuRepository().get_company_name()

@frappe.whitelist()
def print_void_item(pos_invoice: str):
    from resto.services.printing_service import PrintingService
    return PrintingService().print_void_item(pos_invoice)


@frappe.whitelist()
def move_table(pos_invoice):
    # TODO: implementasi move_table
    pass

@frappe.whitelist()
def merge_table(pos_invoice, source_table, target_table=None):
    if isinstance(target_table, str):
        try:
            target_table = json.loads(target_table)
        except Exception:
            target_table = [target_table]
    from resto.services.table_service import TableService
    return TableService().merge_table(pos_invoice, source_table=source_table, target_table=target_table)

def move_items_from_invoice(source_invoice_name, target_invoice_name):
    from resto.services.invoice_service import InvoiceService
    InvoiceService().move_items_from_invoice(source_invoice_name, target_invoice_name)


@frappe.whitelist()
def move_item(pos_invoice):
    # TODO: implementasi move_item (pindah item antar invoice)
    pass

@frappe.whitelist()
def split_bill(pos_invoice):
    # TODO: implementasi split_bill (pecah invoice menjadi beberapa)
    pass

@frappe.whitelist()
def remove_item(pos_invoice, item_code, qty):
    # TODO: implementasi remove_item dengan status VOID MENU di InvoiceService
    pass

@frappe.whitelist()
def apply_discount(pos_invoice=None, discount_percentage=0, discount_amount=0, discount_name=None, discount_for_bank=None, user=None):
    from resto.services.invoice_service import InvoiceService
    return InvoiceService().apply_discount(
        pos_invoice=pos_invoice,
        discount_percentage=discount_percentage,
        discount_amount=discount_amount,
        discount_name=discount_name,
        discount_for_bank=discount_for_bank,
        user=user
    )
        
@frappe.whitelist()
def remove_discount(pos_invoice):
    from resto.services.discount_service import DiscountService
    return DiscountService().remove_discount(pos_invoice)

@frappe.whitelist()
def create_payment(pos_invoice, amount, mode_of_payment):
    from resto.services.payment_service import PaymentService
    return PaymentService().create_payment(pos_invoice, amount, mode_of_payment)

def clear_table_merged(pos_invoice):
    from resto.services.table_service import TableService
    TableService().clear_table_merged(pos_invoice)

def delete_merge_invoice(pos_invoice):
    from resto.services.invoice_service import InvoiceService
    InvoiceService().delete_merge_invoice(pos_invoice)

def clear_table(table_name):
    from resto.services.table_service import TableService
    TableService().clear_table(table_name)