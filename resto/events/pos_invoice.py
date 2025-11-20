import frappe

def exclude_void_items_from_total(doc, method):
    total = 0
    net_total = 0
    base_net_total = 0

    for item in doc.items:
        if item.status_kitchen != "Void Menu":
            total += (item.amount or 0)
            net_total += (item.net_amount or 0)
            base_net_total += (item.base_net_amount or 0)

    # total sebelum diskon
    doc.total = total
    doc.base_total = total

    # total setelah diskon
    doc.net_total = net_total
    doc.base_net_total = base_net_total

    taxes = doc.total_taxes_and_charges or 0
    base_taxes = doc.base_total_taxes_and_charges or 0

    # ✔ grand total HARUS pakai net_total
    doc.grand_total = net_total + taxes
    doc.base_grand_total = base_net_total + base_taxes

    doc.rounded_total = frappe.utils.flt(doc.grand_total, doc.precision("rounded_total"))
    doc.base_rounded_total = frappe.utils.flt(doc.base_grand_total, doc.precision("base_rounded_total"))

    paid = sum([(p.amount or 0) for p in getattr(doc, "payments", [])])
    doc.outstanding_amount = doc.rounded_total - paid
