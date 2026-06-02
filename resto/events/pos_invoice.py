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
    # doc.net_total = sum(flt(i.net_amount) for i in doc.items)
    # doc.base_net_total = sum(flt(i.base_net_amount) for i in doc.items)

    # total_tax = 0
    # base_total_tax = 0

    # for tax in doc.taxes:
    #     if tax.charge_type == "On Net Total":
    #         tax.tax_amount = flt(doc.net_total * tax.rate / 100)
    #         tax.base_tax_amount = flt(doc.base_net_total * tax.rate / 100)
    #     tax.total = doc.net_total + tax.tax_amount
    #     tax.base_total = doc.base_net_total + tax.base_tax_amount
    #     total_tax += tax.tax_amount
    #     base_total_tax += tax.base_tax_amount

    # doc.total_taxes_and_charges = total_tax
    # doc.base_total_taxes_and_charges = base_total_tax

    # doc.grand_total = doc.net_total + total_tax - flt(doc.discount_amount)
    # doc.base_grand_total = doc.base_net_total + base_total_tax - flt(doc.base_discount_amount)
    # doc.rounded_total = flt(doc.grand_total, doc.precision("rounded_total"))
    # doc.base_rounded_total = flt(doc.base_grand_total, doc.precision("base_rounded_total"))

    # =====================
    # PAYMENT SYNC (ANTI PARTIAL)
    # =====================
    # if doc.is_pos:
    #     gt = flt(doc.rounded_total or doc.grand_total)
    #     doc.paid_amount = gt
    #     doc.base_paid_amount = gt
    #     for p in doc.payments:
    #         p.amount = gt
    #         p.base_amount = gt
    #     doc.outstanding_amount = 0

def block_partial_payment(doc, method):
    """Anti-partial guard untuk POS Invoice.
    Tolak submit kalau total paid < grand_total. Tolerance 1 rupiah untuk
    floating-point pembulatan (rounded_total bisa beda <1 dari grand_total).
    Cancel/amend tetap diizinkan — guard cuma di submit path."""
    if not doc.is_pos:
        return
    grand = flt(doc.rounded_total or doc.grand_total)
    paid = sum(flt(p.amount) for p in (doc.payments or []))
    if grand - paid > 1:
        frappe.throw(
            f"Pembayaran kurang dari total. Total: Rp{grand:,.0f}, "
            f"Dibayar: Rp{paid:,.0f}, Kurang: Rp{grand - paid:,.0f}.",
            title="Pembayaran Belum Lunas",
        )


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


def auto_cancel_fully_voided_draft(doc, method):
    """Cancel a Draft POS Invoice once every line is flagged Void Menu.

    Per-item void leaves the invoice Draft with grand_total=0. Nothing in the
    POS flow can then submit it, so the meja stays "Has Ordered" forever and
    end-shift inherits a phantom open order. We mirror what
    InvoiceService.void_pos_invoice does for whole-invoice voids: cancel the
    doc, drop it from Table.orders, and reset the meja to Kosong when no
    other orders remain.
    """
    if doc.docstatus != 0 or not getattr(doc, "is_pos", 0):
        return
    if not doc.items:
        return
    if any(getattr(it, "status_kitchen", "") != "Void Menu" for it in doc.items):
        return
    if doc.flags.get("auto_cancel_fully_voided"):
        return

    doc.flags.auto_cancel_fully_voided = True
    table_name = getattr(doc, "table", None)

    # Frappe state machine: docstatus 0 (Draft) tidak bisa langsung ke 2
    # (Cancelled). Submit dulu (0 → 1) lalu cancel (1 → 2). Aman untuk
    # fully-voided invoice: grand_total=0 lolos block_partial_payment,
    # tidak ada voucher, kitchen stock sudah di-rollback oleh
    # handle_kitchen_stock (before_save).
    doc.flags.ignore_permissions = True
    doc.submit()
    doc.cancel()

    if not table_name:
        return

    from resto.services.table_service import TableService

    svc = TableService()
    svc.remove_table_order(table_name, doc.name)

    table_doc = svc.repo.get_table(table_name)
    if not (table_doc.orders or []):
        svc.clear_table(table_name)