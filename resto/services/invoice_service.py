import json
import frappe
from resto.repositories.invoice_repository import InvoiceRepository

VALID_ORDER_TYPES = {"Dine In", "Take Away"}
ORDER_TYPE_TEMPLATE = {
    "Dine In": "Dengan Service",
    "Take Away": "Tanpa Service",
}


class InvoiceService:
    def __init__(self, repo=None):
        self.repo = repo or InvoiceRepository()

    # ------------------------------------------------------------------
    # create_pos_invoice
    # ------------------------------------------------------------------

    def create_pos_invoice(self, payload):
        if isinstance(payload, str):
            payload = json.loads(payload)

        customer = payload.get("customer")
        pos_profile = payload.get("pos_profile")
        branch = payload.get("branch")
        items = payload.get("items", [])
        payments = payload.get("payments", [])
        queue = payload.get("queue")
        additional_items = payload.get("additional_items", [])
        order_type = payload.get("order_type")
        discount_amount = payload.get("discount_amount")
        discount_for_bank = payload.get("discount_for_bank") or ""
        discount_name = payload.get("discount_name") or ""
        additional_discount_percentage = payload.get("additional_discount_percentage")
        pax = payload.get("pax")
        type_customer = payload.get("type_customer")

        # --- Validasi wajib ---
        if not customer:
            frappe.throw("customer wajib diisi")
        if not pos_profile:
            frappe.throw("pos_profile wajib diisi")
        if not items:
            frappe.throw("items tidak boleh kosong")
        if order_type is not None and order_type not in VALID_ORDER_TYPES:
            frappe.throw(f"order_type tidak valid: '{order_type}'. Harus Dine In atau Take Away")

        # --- Tax template ---
        company = self.repo.get_default_company()
        tax_template_name = None
        taxes = []

        if order_type:
            template_title = ORDER_TYPE_TEMPLATE[order_type]
            tax_template_name = self.repo.get_tax_template_name(template_title)
            if not tax_template_name:
                frappe.throw(f"Sales Taxes and Charges Template '{template_title}' tidak ditemukan")
            template = self.repo.get_tax_template(tax_template_name)
            for t in template.taxes:
                taxes.append({
                    "charge_type": t.charge_type,
                    "account_head": t.account_head,
                    "rate": t.rate,
                    "tax_amount": 0,
                    "description": t.description
                })

        # --- Buat doc ---
        pos_invoice = frappe.get_doc({
            "doctype": "POS Invoice",
            "customer": customer,
            "pos_profile": pos_profile,
            "order_type": order_type,
            "branch": branch,
            "company": company,
            "items": [],
            "payments": [],
            "queue": queue,
            "additional_items": [],
            "taxes_and_charges": tax_template_name,
            "apply_discount_on": "Net Total",
            "additional_discount_percentage": additional_discount_percentage,
            "discount_amount": discount_amount,
            "discount_for_bank": discount_for_bank,
            "discount_name": discount_name,
            "ordered_by": frappe.session.user,
            "pax": pax,
            "type_customer": type_customer
        })

        for item in items:
            pos_invoice.append("items", {
                "item_code": item.get("item_code"),
                "qty": item.get("qty"),
                "rate": item.get("rate"),
                "resto_menu": item.get("resto_menu"),
                "category": item.get("category"),
                "status_kitchen": item.get("status_kitchen"),
                "add_ons": item.get("add_ons"),
                "quick_notes": item.get("quick_notes"),
                "waiter": item.get("waiter"),
                "is_checked": item.get("is_checked"),
                "is_print_kitchen": item.get("is_print_kitchen")
            })

        for pay in payments:
            pos_invoice.append("payments", {
                "mode_of_payment": pay.get("mode_of_payment"),
                "amount": pay.get("amount")
            })

        if self.repo.has_additional_items_field():
            for add in additional_items:
                resto_menu_name = add.get("resto_menu")
                resto_menu_doc_name = self.repo.find_resto_menu(resto_menu_name)
                if not resto_menu_doc_name:
                    frappe.throw(f"Resto Menu '{resto_menu_name}' tidak ditemukan")
                resto_menu_doc = self.repo.get_resto_menu(resto_menu_doc_name)
                combined_name = f"{resto_menu_doc.menu_code}-{resto_menu_doc.title}"
                pos_invoice.append("additional_items", {
                    "item_name": combined_name,
                    "add_on": add.get("add_on"),
                    "price": add.get("price"),
                    "notes": add.get("notes"),
                })
        else:
            frappe.log_error("Field 'additional_items' tidak ditemukan di POS Invoice", "Create POS Invoice")

        pos_invoice.insert(ignore_permissions=True)
        return {"status": "success", "name": pos_invoice.name}

    # ------------------------------------------------------------------
    # apply_discount
    # ------------------------------------------------------------------

    def apply_discount(self, pos_invoice=None, discount_percentage=0,
                       discount_amount=0, discount_name=None, discount_for_bank=None, user=None):
        if not pos_invoice:
            return {"ok": False, "message": "Skip discount: pos_invoice kosong", "skipped": True}

        if not self.repo.invoice_exists(pos_invoice):
            return {"ok": False, "message": f"POS Invoice {pos_invoice} tidak ditemukan", "skipped": True}

        # Bug fix: user param harus prioritas atas session
        user = user or frappe.session.user

        discount_percentage = float(discount_percentage or 0)
        discount_amount = float(discount_amount or 0)

        # Validasi nilai negatif
        if discount_percentage < 0:
            frappe.throw("discount_percentage tidak boleh negatif")
        if discount_amount < 0:
            frappe.throw("discount_amount tidak boleh negatif")

        doc = self.repo.get_invoice(pos_invoice)
        active_profile = self.repo.get_active_profile_for_user(user)
        pos_profile = self.repo.get_pos_profile(active_profile["pos_profile"])

        if not doc.taxes_and_charges:
            doc.taxes_and_charges = pos_profile.taxes_and_charges
            doc.set_taxes()

        # Tentukan charge_type
        if discount_percentage > 0:
            charge_type = "On Net Total"
            tax_rate = -abs(discount_percentage)
            tax_amount = 0
        elif discount_amount > 0:
            charge_type = "Actual"
            tax_rate = 0
            tax_amount = -abs(discount_amount)
        else:
            charge_type = "Actual"
            tax_rate = 0
            tax_amount = 0

        # Cari account_head dari template
        tax_template = self.repo.get_tax_template(pos_profile.taxes_and_charges)
        account_head = next(
            (t.account_head for t in tax_template.taxes if t.description == "Discount"),
            None
        )
        if not account_head:
            frappe.throw(
                f"Row 'Discount' tidak ditemukan di template pajak '{pos_profile.taxes_and_charges}'. "
                "Tambahkan row dengan description 'Discount' di template tersebut."
            )

        # Update atau append row Discount
        discount_row = next((t for t in doc.taxes if t.description == "Discount"), None)
        if discount_row:
            discount_row.charge_type = charge_type
            discount_row.rate = tax_rate
            discount_row.tax_amount = tax_amount
        else:
            doc.append("taxes", {
                "description": "Discount",
                "charge_type": charge_type,
                "account_head": account_head,
                "rate": tax_rate,
                "tax_amount": tax_amount
            })

        # Fix row reference error
        for tax in doc.taxes:
            if tax.charge_type not in ["On Previous Row Amount", "On Previous Row Total"]:
                tax.row_id = None

        doc.calculate_taxes_and_totals()
        doc.discount_name = discount_name
        doc.discount_for_bank = discount_for_bank
        self.repo.save_invoice(doc)

        return {"ok": True, "message": "Diskon berhasil diterapkan", "pos_invoice": pos_invoice}

    # ------------------------------------------------------------------
    # move_items_from_invoice
    # ------------------------------------------------------------------

    SKIP_FIELDS = {"name", "parent", "parenttype", "parentfield", "idx"}

    def move_items_from_invoice(self, source_name, target_name):
        source = self.repo.get_invoice(source_name)
        target = self.repo.get_invoice(target_name)

        for item in source.get("items"):
            fields = item.meta.get_fieldnames_with_value()
            row = {f: item.get(f) for f in fields if f not in self.SKIP_FIELDS}
            target.append("items", row)

        source.is_merged = 1
        source.merge_invoice = target_name

        source.save()
        target.save()
        frappe.db.commit()
