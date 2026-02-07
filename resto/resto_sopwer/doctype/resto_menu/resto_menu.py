# Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc


class RestoMenu(Document):
    pass
	

def consume_resto_menu_stock(resto_menu, qty):
    menu = frappe.get_doc("Resto Menu", resto_menu)

    if not menu.use_stock:
        return

    used = menu.stock_used or 0
    limit = menu.stock_limit or 0

    if used + qty > limit:
        frappe.throw(
            f"Menu {menu.title} sudah SOLD OUT",
            frappe.ValidationError
        )

    menu.stock_used = used + qty

    if menu.stock_used >= limit:
        menu.is_sold_out = 1

    menu.save(ignore_permissions=True)
    
def rollback_resto_menu_stock(resto_menu, qty):
    menu = frappe.get_doc("Resto Menu", resto_menu)

    if not menu.use_stock:
        return

    menu.stock_used = max((menu.stock_used or 0) - qty, 0)

    if menu.stock_used < menu.stock_limit:
        menu.is_sold_out = 0

    menu.save(ignore_permissions=True)


@frappe.whitelist()
def get_resto_menu_stock(resto_menu):
    menu = frappe.get_doc("Resto Menu", resto_menu)

    if menu.use_stock and menu.is_sold_out:
        return {
            "qty": -1,
            "sold_out": True
        }

    remaining = (
        (menu.stock_limit or 0) - (menu.stock_used or 0)
        if menu.use_stock else None
    )

    return {
        "sold_out": False,
        "remaining": remaining
    }

@frappe.whitelist()
def make_branch_menu(source_name, branch=None, price_list=None, rate=0):
    """
    Duplikasi Resto Menu -> Branch Menu (termasuk child).
    Set juga field branch & price_list jika diisi dari dialog.
    """
    def _postprocess(source, target):
        if branch:
            # sesuaikan dengan nama field sebenarnya di Branch Menu
            target.branch = branch
        if price_list:
            # sesuaikan dengan nama field sebenarnya di Branch Menu
            target.price_list = price_list
        
        target.rate = rate

    mapping = {
        "Printers": {
            "doctype": "Branch Menu Printer",
        },
        "Resto Menu": {
            "doctype": "Branch Menu",
            # "field_map": {"field_di_resto": "field_di_branch"},  # jika perlu
        },
        "Menu Add Ons": {
            "doctype": "Menu Add Ons",  # ganti jika child doctype di Branch Menu berbeda
            # "field_map": {"item": "item", "price": "price"},
        },
    }

    doc = get_mapped_doc(
        "Resto Menu",
        source_name,
        mapping,
        target_doc=None,
        postprocess=_postprocess,
        ignore_permissions=False,   # set True jika memang mau bypass
    )

    doc.insert()
    frappe.db.commit()
    return doc.name

def reset_daily_resto_stock():
    """
    Reset stock_used, is_sold_out, stock_limit, dan uncheck use_stock untuk semua Resto Menu yang pakai stok.
    """
    menus = frappe.get_all("Resto Menu", filters={"use_stock": 1}, fields=["name"])
    
    for m in menus:
        menu_doc = frappe.get_doc("Resto Menu", m.name)
        menu_doc.use_stock = 0
        menu_doc.stock_limit = 0
        menu_doc.stock_used = 0
        menu_doc.is_sold_out = 0
        menu_doc.save(ignore_permissions=True)
    
    frappe.clear_cache(doctype="Resto Menu")
    frappe.log_error("Daily stock reset executed", "Resto Menu Stock Reset")
