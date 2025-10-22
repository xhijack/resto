import frappe

def exclude_void_items_from_total(doc, method):
    """Exclude items dengan status_kitchen = 'Void Menu' dari total"""
    total = 0
    net_total = 0
    base_net_total = 0

    for item in doc.items:
        if item.status_kitchen != "Void Menu":
            total += (item.amount or 0)
            net_total += (item.net_amount or 0)
            base_net_total += (item.base_net_amount or 0)

    doc.total = total
    doc.base_total = total
    doc.net_total = net_total
    doc.base_net_total = base_net_total
    doc.grand_total = total
    doc.base_grand_total = total
    doc.rounded_total = frappe.utils.flt(total, doc.precision("rounded_total"))
    doc.base_rounded_total = frappe.utils.flt(total, doc.precision("base_rounded_total"))

    paid = sum([(p.amount or 0) for p in getattr(doc, "payments", [])])
    doc.outstanding_amount = doc.rounded_total - paid
