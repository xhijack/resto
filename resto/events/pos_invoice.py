import frappe
from frappe.utils import flt

def exclude_void_items_from_total(doc, method):
    """
    - Void Menu dikeluarkan dari perhitungan
    - TAX dihitung ulang dari net_total baru
    - Payment POS disinkronkan ke grand_total
    """

    # HITUNG ITEM (NON VOID)
    total = net_total = base_total = base_net_total = 0

    for item in doc.items:
        if item.status_kitchen != "Void Menu":
            total += flt(item.amount)
            net_total += flt(item.net_amount)
            base_total += flt(item.base_amount)
            base_net_total += flt(item.base_net_amount)

    doc.total = total
    doc.base_total = base_total
    doc.net_total = net_total
    doc.base_net_total = base_net_total

    # HITUNG ULANG TAX
    total_taxes = base_total_taxes = 0

    for tax in doc.taxes:
        # reset nilai lama
        tax.tax_amount = 0
        tax.tax_amount_after_discount_amount = 0
        tax.base_tax_amount = 0
        tax.base_tax_amount_after_discount_amount = 0

        if tax.charge_type == "On Net Total":
            tax.tax_amount = flt(net_total * tax.rate / 100)
            tax.tax_amount_after_discount_amount = tax.tax_amount
            tax.base_tax_amount = flt(base_net_total * tax.rate / 100)
            tax.base_tax_amount_after_discount_amount = tax.base_tax_amount

        total_taxes += tax.tax_amount
        base_total_taxes += tax.base_tax_amount

        # update running total (penting untuk print format ERPNext)
        tax.total = net_total + total_taxes
        tax.base_total = base_net_total + base_total_taxes

    doc.total_taxes_and_charges = total_taxes
    doc.base_total_taxes_and_charges = base_total_taxes

    # GRAND TOTAL
    doc.grand_total = net_total + total_taxes
    doc.base_grand_total = base_net_total + base_total_taxes

    doc.rounded_total = flt(
        doc.grand_total, doc.precision("rounded_total")
    )
    doc.base_rounded_total = flt(
        doc.base_grand_total, doc.precision("base_rounded_total")
    )

    # POS PAYMENT SYNC
    if doc.is_pos and doc.payments:
        total_paid = 0

        if len(doc.payments) == 1:
            doc.payments[0].amount = doc.rounded_total
            doc.payments[0].base_amount = doc.base_rounded_total
            total_paid = doc.rounded_total
        else:
            current_total = sum(flt(p.amount) for p in doc.payments)
            if current_total:
                ratio = doc.rounded_total / current_total
                for p in doc.payments:
                    p.amount = flt(p.amount * ratio, 2)
                    p.base_amount = flt(p.base_amount * ratio, 2)
                    total_paid += p.amount

        doc.paid_amount = total_paid
        doc.base_paid_amount = total_paid

    # OUTSTANDING
    doc.outstanding_amount = flt(doc.grand_total - doc.paid_amount)
    if doc.outstanding_amount < 0:
        doc.outstanding_amount = 0
