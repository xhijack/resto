import frappe
from resto.api import clear_table_merged


class PaymentService:
    def create_payment(self, pos_invoice, amount, mode_of_payment):
        doc = frappe.get_doc("POS Invoice", pos_invoice)
        doc.append("payments", {
            "mode_of_payment": mode_of_payment,
            "amount": amount
        })
        doc.submit()
        clear_table_merged(pos_invoice)
        frappe.db.commit()
        return {"ok": True, "message": "Pembayaran berhasil ditambahkan", "pos_invoice": pos_invoice}
