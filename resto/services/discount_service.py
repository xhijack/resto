import frappe


class DiscountService:
    def remove_discount(self, pos_invoice):
        doc = frappe.get_doc("POS Invoice", pos_invoice)
        for tax in doc.taxes:
            if tax.description == "Discount":
                doc.remove(tax)
                doc.save()
                frappe.db.commit()
                return {"ok": True, "message": "Diskon berhasil dihapus", "pos_invoice": pos_invoice}
        return {"ok": False, "message": "Tidak ditemukan diskon untuk dihapus"}
