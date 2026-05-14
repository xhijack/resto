import json
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

    def pay_invoice(self, pos_invoice, payments):
        # Atomic full-pay: terima list payments [{mode_of_payment, amount}, ...],
        # bersihkan baris payments existing di DRAFT (kalau ada residu dari create_pos_invoice
        # payload atau attempt sebelumnya), pasang set baru, validasi sum == grand,
        # submit dalam 1 transaksi. Boleh split methods (e.g. Cash 800rb + Mandiri 200rb)
        # tapi tidak boleh under-payment.
        if isinstance(payments, str):
            try:
                payments = json.loads(payments)
            except Exception:
                frappe.throw("payments tidak valid JSON")
        if not isinstance(payments, list) or not payments:
            frappe.throw("payments harus list dan tidak boleh kosong",
                         title="Payload Tidak Valid")

        normalized = []
        for p in payments:
            mode = (p.get("mode_of_payment") or "").strip()
            amt = flt(p.get("amount") or 0)
            if not mode:
                frappe.throw("mode_of_payment wajib di setiap row payments")
            if amt <= 0:
                frappe.throw(f"amount untuk {mode} harus > 0")
            normalized.append({"mode_of_payment": mode, "amount": amt})

        total_paid = sum(p["amount"] for p in normalized)

        doc = frappe.get_doc("POS Invoice", pos_invoice)
        grand = flt(doc.rounded_total or doc.grand_total)
        if abs(grand - total_paid) > 1:
            frappe.throw(
                f"Total pembayaran harus sama dengan total invoice. "
                f"Total: Rp{grand:,.0f}, Dibayar: Rp{total_paid:,.0f}, "
                f"Selisih: Rp{abs(grand - total_paid):,.0f}.",
                title="Pembayaran Tidak Sesuai",
            )

        doc.set("payments", [])
        for p in normalized:
            doc.append("payments", p)

        doc.submit()
        clear_table_merged(pos_invoice)
        frappe.db.commit()
        return {
            "ok": True,
            "message": "Pembayaran berhasil",
            "pos_invoice": pos_invoice,
            "total_paid": total_paid,
        }
