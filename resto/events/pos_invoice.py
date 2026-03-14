import frappe
from frappe.utils import flt
from resto.resto_sopwer.doctype.resto_menu.resto_menu import (
    consume_resto_menu_stock,
    rollback_resto_menu_stock
)

def exclude_void_items_from_total(doc, method):
    """
    FINAL – HARD LOCK VERSION
    - Void Menu tidak masuk accounting
    - Rate asli disimpan ke void_*
    - Diskon hanya di header
    - Item NON-VOID tidak berubah net_amount
    - Tax tetap benar
    - POS anti partial payment
    """

    has_void = False

    # =====================
    # VOID ITEM LOCK
    # =====================
    for item in doc.items:
        if item.status_kitchen == "Void Menu":
            has_void = True

            if not flt(item.void_amount) and not flt(item.void_rate):
                # 🔥 Ambil rate dari Branch Menu (khusus void)
                branch_rate = frappe.db.get_value(
                    "Branch Menu",
                    {"branch": doc.branch, "sell_item": item.item_code, "enabled": 1},
                    "rate"
                )

                if branch_rate is None:
                    frappe.throw(f"Harga Branch Menu tidak ditemukan untuk item {item.item_code}")

                branch_rate = flt(branch_rate)
                amount = branch_rate * flt(item.qty)

                # 🔒 SNAPSHOT VOID
                item.void_qty = item.qty
                item.void_rate = item.rate
                item.void_amount = item.amount
                item.void_net_amount = item.net_amount
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

    # =====================
    # HEADER SAFETY
    # =====================
    if has_void:
        doc.ignore_pricing_rule = 1
        doc.apply_discount_on = "Net Total"

    # =====================
    # TAX ENGINE (ERPNext)
    # =====================
    for tax in doc.taxes:
        tax.dont_recompute_tax = 0

    doc.calculate_taxes_and_totals()

    # =====================
    # 🔒 HARD OVERRIDE ITEM NON-VOID
    # =====================
    for item in doc.items:
        if item.status_kitchen != "Void Menu":
            item.distributed_discount_amount = 0
            item.discount_amount = 0
            item.discount_percentage = 0

            item.net_rate = item.rate
            item.net_amount = item.amount
            item.base_net_rate = item.base_rate
            item.base_net_amount = item.base_amount

    # =====================
    # RECALC TOTAL MANUAL
    # =====================
    doc.net_total = sum(flt(i.net_amount) for i in doc.items)
    doc.base_net_total = sum(flt(i.base_net_amount) for i in doc.items)

    total_tax = 0
    base_total_tax = 0

    for tax in doc.taxes:
        if tax.charge_type == "On Net Total":
            tax.tax_amount = flt(doc.net_total * tax.rate / 100)
            tax.base_tax_amount = flt(doc.base_net_total * tax.rate / 100)
        tax.total = doc.net_total + tax.tax_amount
        tax.base_total = doc.base_net_total + tax.base_tax_amount
        total_tax += tax.tax_amount
        base_total_tax += tax.base_tax_amount

    doc.total_taxes_and_charges = total_tax
    doc.base_total_taxes_and_charges = base_total_tax

    doc.grand_total = doc.net_total + total_tax - flt(doc.discount_amount)
    doc.base_grand_total = doc.base_net_total + base_total_tax - flt(doc.base_discount_amount)
    doc.rounded_total = flt(doc.grand_total, doc.precision("rounded_total"))
    doc.base_rounded_total = flt(doc.base_grand_total, doc.precision("base_rounded_total"))

    # =====================
    # PAYMENT SYNC (ANTI PARTIAL)
    # =====================
    if doc.is_pos:
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
            if not flt(item.void_amount) and flt(item.void_rate) and flt(item.void_qty):
                item.db_set("void_amount", item.void_rate * item.void_qty)

def handle_kitchen_stock(doc, method):
    if not doc.is_pos:
        return
    for row in doc.items:
        if not row.resto_menu:
            continue
        if row.status_kitchen == "Already Send To Kitchen" and not row.kitchen_stock_consumed:
            consume_resto_menu_stock(row.resto_menu, row.qty)
            row.kitchen_stock_consumed = 1
        elif row.status_kitchen == "Void Menu" and row.kitchen_stock_consumed:
            rollback_resto_menu_stock(row.resto_menu, row.qty)
            row.kitchen_stock_consumed = 0

def rollback_kitchen_stock_on_cancel(doc, method):
    if not doc.is_pos:
        return
    for row in doc.items:
        if row.kitchen_stock_consumed and row.resto_menu:
            rollback_resto_menu_stock(row.resto_menu, row.qty)
            row.kitchen_stock_consumed = 0


def validate_discount_account(doc, method):
    # cek apakah ada discount
    if not doc.apply_discount_on:
        return

    charge_type = None
    tax_rate = 0
    tax_amount = 0

    # CASE 1: Discount Percentage
    if doc.additional_discount_percentage > 0:
        charge_type = "On Net Total"
        tax_rate = -abs(doc.additional_discount_percentage)

    # CASE 2: Discount Amount
    elif doc.discount_amount:
        charge_type = "Actual"
        tax_amount = -abs(doc.discount_amount)

    else:
        return

    # reset discount bawaan ERPNext
    doc.apply_discount_on = None
    doc.additional_discount_percentage = 0
    doc.discount_amount = 0

    # cek apakah sudah ada baris discount
    discount_row = None
    for tax in doc.taxes:
        if tax.description == "Discount":
            discount_row = tax
            break

    if discount_row:
        discount_row.charge_type = charge_type
        discount_row.rate = tax_rate
        discount_row.tax_amount = tax_amount
    else:
        doc.append("taxes", {
            "charge_type": charge_type,
            "account_head": "4-40100 - Diskon Penjualan - M",  # ganti sesuai chart of account
            "description": "Discount",
            "rate": tax_rate,
            "tax_amount": tax_amount
        })

def validate_on_submit(doc, method):
    if doc.status == "Paid":
        from resto.api import update_table_status
        if doc.is_pos and not doc.payments:
            frappe.throw("Payment is required for POS Invoice")

        tos = frappe.get_all("Table Order", filters={"invoice_name": doc.name}, fields=["name", "parent"])
        for to in tos:
            update_table_status(to['parent'], "Kosong")