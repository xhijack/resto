import frappe

def validate_discount_on_pos_invoice(doc, method):
    if doc.discount_amount and doc.discount_amount > 0:
        if not doc.discount_account:
            frappe.throw("Please set Discount Account to apply discount on POS Invoice")