import frappe
from frappe.utils import flt
from resto.api import clear_table_merged


class PaymentService:
    def create_payment(self, pos_invoice, amount, mode_of_payment):
        doc = frappe.get_doc("POS Invoice", pos_invoice)
        existing_paid = sum(flt(p.amount) for p in (doc.payments or []))
        new_total = existing_paid + flt(amount)
        grand = flt(doc.rounded_total or doc.grand_total)
        # Tolerance 1 rupiah untuk pembulatan (rounded_total bisa beda <1 dari
        # grand_total). Defense-in-depth: before_submit hook POS Invoice juga
        # reject under-payment; di sini error message lebih informatif untuk
        # caller endpoint legacy.
        if grand - new_total > 1:
            frappe.throw(
                f"Pembayaran kurang dari total. Total: Rp{grand:,.0f}, "
                f"Dibayar: Rp{new_total:,.0f}, Kurang: Rp{grand - new_total:,.0f}.",
                title="Pembayaran Belum Lunas",
            )
        doc.append("payments", {
            "mode_of_payment": mode_of_payment,
            "amount": amount
        })
        doc.submit()
        clear_table_merged(pos_invoice)
        frappe.db.commit()
        return {"ok": True, "message": "Pembayaran berhasil ditambahkan", "pos_invoice": pos_invoice}
