import frappe
from frappe.utils import flt
from resto.resto_sopwer.doctype.resto_menu.resto_menu import (
    consume_resto_menu_stock,
    rollback_resto_menu_stock
)

def exclude_void_items_from_total(doc, method):
    """
    PRODUCTION SAFE VERSION
    - Void item tidak masuk accounting
    - Snapshot harga void aman
    - Diskon hanya di header
    - Tax engine tetap dipakai (tidak override manual)
    - Accounting tetap balance
    - POS anti partial payment
    """

    has_void = False

    # ======================================================
    # 1️⃣ VOID ITEM LOCK
    # ======================================================
    for item in doc.items:

        if item.status_kitchen == "Void Menu":
            has_void = True

            # Snapshot hanya sekali
            if not flt(item.void_amount) and not flt(item.void_rate):

                branch_rate = frappe.db.get_value(
                    "Branch Menu",
                    {
                        "branch": doc.branch,
                        "sell_item": item.item_code,
                        "enabled": 1
                    },
                    "rate"
                )

                if branch_rate is None:
                    frappe.throw(
                        f"Harga Branch Menu tidak ditemukan untuk item {item.item_code}"
                    )

                branch_rate = flt(branch_rate)
                amount = branch_rate * flt(item.qty)

                item.void_qty = item.qty
                item.void_rate = branch_rate
                item.void_amount = amount
                item.void_net_amount = amount

            # Nolkan agar tidak masuk accounting
            item.price_list_rate = 0
            item.rate = 0
            item.net_rate = 0
            item.amount = 0
            item.net_amount = 0

            item.base_price_list_rate = 0
            item.base_rate = 0
            item.base_net_rate = 0
            item.base_amount = 0
            item.base_net_amount = 0

            item.discount_percentage = 0
            item.discount_amount = 0
            item.distributed_discount_amount = 0
            item.pricing_rules = ""

    # ======================================================
    # 2️⃣ HEADER SAFETY
    # ======================================================
    if has_void:
        doc.ignore_pricing_rule = 1

    # Paksa diskon hanya di header
    doc.apply_discount_on = "Net Total"

    # Jangan izinkan diskon distribusi ke item
    for item in doc.items:
        item.distributed_discount_amount = 0

    # ======================================================
    # 3️⃣ HITUNG SUBTOTAL DARI NON VOID
    # ======================================================
    subtotal = sum(flt(i.amount) for i in doc.items)
    # doc.net_total = subtotal
    # doc.base_net_total = subtotal

    # ======================================================
    # 4️⃣ BIARKAN ERPNext HITUNG TAX & DISCOUNT
    # ======================================================
    # doc.calculate_taxes_and_totals()

    # ======================================================
    # 5️⃣ PAYMENT SYNC (ANTI PARTIAL PAYMENT POS)
    # ======================================================
    if doc.is_pos:
        gt = flt(doc.rounded_total or doc.grand_total)

        doc.paid_amount = gt
        doc.base_paid_amount = gt

        for p in doc.payments:
            p.amount = gt
            p.base_amount = gt

        doc.outstanding_amount = 0
        gt = flt(doc.rounded_total or doc.grand_total)

        doc.paid_amount = gt
        doc.base_paid_amount = gt

        for p in doc.payments:
            p.amount = gt
            p.base_amount = gt

        doc.outstanding_amount = 0

def lock_void_value_after_submit(doc, method):
    for item in doc.items:
        if item.status_kitchen == "Void Menu":
            # kalau masih 0, restore dari snapshot terakhir
            if not flt(item.void_amount) and flt(item.void_rate) and flt(item.void_qty):
                item.db_set("void_amount", item.void_rate * item.void_qty)

def handle_kitchen_stock(doc, method):
    if not doc.is_pos:
        return

    for row in doc.items:
        if not row.resto_menu:
            continue

        # 🚚 SEND TO KITCHEN → CONSUME
        if (
            row.status_kitchen == "Already Send To Kitchen"
            and not row.kitchen_stock_consumed
        ):
            consume_resto_menu_stock(row.resto_menu, row.qty)
            row.kitchen_stock_consumed = 1

        # ❌ VOID MENU → ROLLBACK
        elif (
            row.status_kitchen == "Void Menu"
            and row.kitchen_stock_consumed
        ):
            rollback_resto_menu_stock(row.resto_menu, row.qty)
            row.kitchen_stock_consumed = 0

def rollback_kitchen_stock_on_cancel(doc, method):
    if not doc.is_pos:
        return

    for row in doc.items:
        if row.kitchen_stock_consumed and row.resto_menu:
            rollback_resto_menu_stock(row.resto_menu, row.qty)
            row.kitchen_stock_consumed = 0
