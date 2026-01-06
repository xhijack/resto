import frappe
from frappe.utils import flt

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
                item.void_qty = item.qty
                item.void_rate = item.rate
                item.void_amount = item.amount
                item.void_net_amount = item.net_amount

            # KUNCI TOTAL VOID
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
        doc.apply_discount_on = "Grand Total"

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
            # 🚫 diskon TIDAK boleh masuk item
            item.distributed_discount_amount = 0
            item.discount_amount = 0
            item.discount_percentage = 0

            # 🔒 kembalikan nilai asli
            item.net_rate = item.rate
            item.net_amount = item.amount
            item.base_net_rate = item.base_rate
            item.base_net_amount = item.base_amount

    # =====================
    # RECALC TOTAL MANUAL (AMAN)
    # =====================
    doc.net_total = sum(flt(i.net_amount) for i in doc.items)
    doc.base_net_total = sum(flt(i.base_net_amount) for i in doc.items)

    # TAX dihitung dari net_total
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
            # kalau masih 0, restore dari snapshot terakhir
            if not flt(item.void_amount) and flt(item.void_rate) and flt(item.void_qty):
                item.db_set("void_amount", item.void_rate * item.void_qty)
