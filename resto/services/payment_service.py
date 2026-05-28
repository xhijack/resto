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
        # bersihkan baris payments existing di DRAFT, pasang set baru, submit.
        # Boleh split methods (e.g. Cash 800rb + Mandiri 200rb).
        # Boleh over-payment ASAL ada cash mode yang cukup untuk kembalian
        # (kembalian wajib cash, tidak boleh refund kartu).
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
            # Preserve voucher_code untuk Voucher mode of payment — kalau di-drop,
            # before_submit hook validate_voucher_payments akan throw "Voucher
            # payment row requires voucher_code" walaupun mobile sudah kirim.
            row = {"mode_of_payment": mode, "amount": amt}
            if p.get("voucher_code"):
                row["voucher_code"] = p.get("voucher_code")
            normalized.append(row)

        total_paid = sum(p["amount"] for p in normalized)

        doc = frappe.get_doc("POS Invoice", pos_invoice)
        grand = flt(doc.rounded_total or doc.grand_total)
        if grand - total_paid > 1:
            frappe.throw(
                f"Pembayaran kurang dari total. Total: Rp{grand:,.0f}, "
                f"Dibayar: Rp{total_paid:,.0f}, Kurang: Rp{grand - total_paid:,.0f}.",
                title="Pembayaran Belum Lunas",
            )

        change = max(0.0, total_paid - grand)
        if change > 1:
            cash_total = sum(
                p["amount"] for p in normalized
                if self._is_cash_mode(p["mode_of_payment"])
            )
            if cash_total + 1 < change:
                frappe.throw(
                    f"Kembalian Rp{change:,.0f} tidak bisa diberikan: "
                    f"pembayaran tunai hanya Rp{cash_total:,.0f}. "
                    f"Tambahkan pembayaran Cash yang menutupi kembalian.",
                    title="Kembalian Tidak Bisa Diberikan",
                )

        doc.set("payments", [])
        for p in normalized:
            doc.append("payments", p)

        if change > 0:
            doc.change_amount = change

        doc.submit()
        clear_table_merged(pos_invoice)
        frappe.db.commit()
        return {
            "ok": True,
            "message": "Pembayaran berhasil",
            "pos_invoice": pos_invoice,
            "total_paid": total_paid,
            "change_amount": change,
        }

    @staticmethod
    def _is_cash_mode(mode_of_payment):
        # Cash type Mode of Payment ditandai field `type == "Cash"` di doctype
        # bawaan ERPNext. Aman: pakai .type, bukan match nama (yang bisa
        # "Cash"/"Tunai"/dll).
        if not mode_of_payment:
            return False
        return frappe.db.get_value("Mode of Payment", mode_of_payment, "type") == "Cash"
