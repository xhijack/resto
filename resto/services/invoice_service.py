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
        table = payload.get("table")

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
            "type_customer": type_customer,
            "table": table,
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

        # Cari account_head dari template — pakai template yang doc benar-benar pakai
        template_name = doc.taxes_and_charges or pos_profile.taxes_and_charges
        if not template_name:
            frappe.throw(
                "Tax template tidak ditemukan di POS Invoice maupun di POS Profile. "
                "Set 'taxes_and_charges' di salah satunya."
            )
        tax_template = self.repo.get_tax_template(template_name)
        account_head = next(
            (t.account_head for t in tax_template.taxes if t.description == "Discount"),
            None
        )
        if not account_head:
            frappe.throw(
                f"Row 'Discount' tidak ditemukan di template pajak '{template_name}'. "
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

    def delete_merge_invoice(self, pos_invoice):
        for doc in self.repo.get_merged_invoices(pos_invoice):
            doc.delete()

    def list_paid_invoices_for_table(self, table_name):
        return self.repo.list_paid_invoices_for_table(table_name)

    def list_paid_invoices(self, posting_date=None, branch=None, table_name=None):
        return self.repo.list_paid_invoices(
            posting_date=posting_date,
            branch=branch,
            table_name=table_name,
        )

    def void_pos_invoice(self, invoice_name):
        # Cancel POS Invoice + cleanup table.orders kalau invoice ter-link ke meja.
        # Pakai TableService.remove_table_order yang sudah row-locked → race-safe
        # vs. add_table_order/remove_table_order paralel dari device lain.
        from resto.services.table_service import TableService
        doc = frappe.get_doc("POS Invoice", invoice_name)
        table_name = doc.get("table")
        doc.cancel()
        if table_name:
            TableService().remove_table_order(table_name, invoice_name)
        return {"success": True, "name": invoice_name, "table": table_name}

    SKIP_FIELDS = {"name", "parent", "parenttype", "parentfield", "idx"}

    def split_invoice(self, source_name, items):
        """Pisah subset item dari source invoice ke invoice baru.

        items: list of {"item_row_name": str, "qty": number}.
        - source row qty di-reduce (atau di-hapus kalau habis)
        - new invoice copy header source (customer, pos_profile, branch, taxes_and_charges)
          + item rows yang diminta (rate, status_kitchen, dst tetap)
        - Throws kalau source jadi kosong (mustahil split semua) atau qty invalid.

        Return: new invoice name.
        """
        if isinstance(items, str):
            items = json.loads(items)
        if not items:
            frappe.throw("items wajib diisi.")

        source = self.repo.get_invoice(source_name)
        if source.docstatus == 1:
            frappe.throw(f"POS Invoice '{source_name}' sudah disubmit, tidak bisa di-split.")

        # Map: row_name → (source_item, requested_qty)
        requested = {}
        for entry in items:
            row_name = entry.get("item_row_name")
            qty = entry.get("qty")
            if not row_name or qty is None:
                frappe.throw("Setiap item butuh 'item_row_name' dan 'qty'.")
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                frappe.throw(f"qty '{qty}' tidak valid (harus angka).")
            if qty <= 0:
                frappe.throw(f"qty harus > 0 untuk row {row_name}.")
            requested[row_name] = qty

        source_rows_by_name = {it.name: it for it in source.get("items", [])}
        for row_name, qty in requested.items():
            if row_name not in source_rows_by_name:
                frappe.throw(f"Item row '{row_name}' tidak ada di invoice {source_name}.")
            src_qty = float(source_rows_by_name[row_name].qty or 0)
            if qty > src_qty:
                frappe.throw(
                    f"Split qty {qty} > qty source ({src_qty}) untuk row {row_name}."
                )

        # Cegah split habis — minimal 1 row tersisa di source.
        remaining_total = sum(
            float(it.qty or 0) - requested.get(it.name, 0)
            for it in source.get("items", [])
        )
        if remaining_total <= 0:
            frappe.throw(
                "Split akan mengosongkan invoice sumber. Pakai 'Pindah Meja' kalau "
                "memang mau pindahkan semua item."
            )

        # Subtotal proporsi untuk distribusi diskon absolut (Actual tax row
        # description="Discount"). Hitung sebelum mutasi items.
        split_subtotal = 0.0
        source_subtotal = 0.0
        for it in source.get("items", []):
            rate = float(it.get("rate") or 0)
            src_qty = float(it.qty or 0)
            source_subtotal += rate * src_qty
            split_qty = requested.get(it.name)
            if split_qty:
                split_subtotal += rate * float(split_qty)
        share = (split_subtotal / source_subtotal) if source_subtotal > 0 else 0

        # Build new invoice — copy header source termasuk discount metadata.
        new_invoice = frappe.get_doc({
            "doctype": "POS Invoice",
            "customer": source.customer,
            "pos_profile": source.pos_profile,
            "order_type": source.order_type,
            "branch": getattr(source, "branch", None),
            "company": source.company,
            "taxes_and_charges": getattr(source, "taxes_and_charges", None),
            "apply_discount_on": getattr(source, "apply_discount_on", None) or "Net Total",
            "discount_name": getattr(source, "discount_name", None) or "",
            "discount_for_bank": getattr(source, "discount_for_bank", None) or "",
            "ordered_by": frappe.session.user,
            "items": [],
        })

        # Copy tax rows. Untuk row "Discount" Actual (absolut): scale tax_amount
        # by share. Untuk "On Net Total" (%): biarkan rate apa adanya — %
        # invariant terhadap subtotal.
        for tax in source.get("taxes", []):
            tax_amount = 0
            if (tax.description or "").lower() == "discount" and tax.charge_type == "Actual":
                src_amt = float(tax.tax_amount or 0)
                tax_amount = round(src_amt * share, 2)
            new_invoice.append("taxes", {
                "charge_type": tax.charge_type,
                "account_head": tax.account_head,
                "rate": tax.rate,
                "tax_amount": tax_amount,
                "description": tax.description,
            })

        # Move qty: build new rows + reduce/remove source rows.
        kept_source_items = []
        for it in source.get("items", []):
            split_qty = requested.get(it.name)
            src_qty = float(it.qty or 0)

            if split_qty:
                fields = it.meta.get_fieldnames_with_value()
                row = {f: it.get(f) for f in fields if f not in self.SKIP_FIELDS}
                row["qty"] = split_qty
                new_invoice.append("items", row)

                remaining = src_qty - split_qty
                if remaining > 0:
                    it.qty = remaining
                    kept_source_items.append(it)
                # else: drop row dari source (tidak append ke kept)
            else:
                kept_source_items.append(it)

        source.set("items", kept_source_items)

        # Scale source's Actual "Discount" tax_amount by (1 - share) supaya
        # total nominal diskon kedua invoice tetap sama dengan source asli.
        # Untuk % "On Net Total" Discount row: biarkan — rate invariant.
        remaining_share = 1 - share
        for tax in source.get("taxes", []):
            if (tax.description or "").lower() == "discount" and tax.charge_type == "Actual":
                src_amt = float(tax.tax_amount or 0)
                tax.tax_amount = round(src_amt * remaining_share, 2)

        # Clear row_id pada tax rows yang bukan referencing (sama trick di
        # move_items_from_invoice untuk hindari ValidationError dari template).
        for tax in new_invoice.get("taxes", []):
            if tax.charge_type not in ("On Previous Row Amount", "On Previous Row Total"):
                tax.row_id = None
        for tax in source.get("taxes", []):
            if tax.charge_type not in ("On Previous Row Amount", "On Previous Row Total"):
                tax.row_id = None

        new_invoice.insert(ignore_permissions=True)
        source.save()
        frappe.db.commit()
        return new_invoice.name

    def move_invoice_items(self, source_name, target_name, items):
        """Pindah subset item dari source invoice ke target invoice yang sudah ada.

        items: list of {"item_row_name": str, "qty": number}.
        Beda dari split_invoice (target = invoice baru) dan move_items_from_invoice
        (target sudah ada tapi pindah SEMUA item). Ini partial-to-existing.

        - source row qty di-reduce (atau di-hapus kalau habis)
        - target append row baru dengan field-field copy dari source
        - Throws kalau source kosong setelah move (pakai move_table sekalian).
        """
        if isinstance(items, str):
            items = json.loads(items)
        if not items:
            frappe.throw("items wajib diisi.")
        if source_name == target_name:
            frappe.throw("Source dan target invoice tidak boleh sama.")

        source = self.repo.get_invoice(source_name)
        target = self.repo.get_invoice(target_name)
        if source.docstatus == 1:
            frappe.throw(f"POS Invoice '{source_name}' sudah disubmit, tidak bisa di-pindah.")
        if target.docstatus == 1:
            frappe.throw(f"POS Invoice '{target_name}' sudah disubmit, tidak bisa di-pindah.")

        requested = {}
        for entry in items:
            row_name = entry.get("item_row_name")
            qty = entry.get("qty")
            if not row_name or qty is None:
                frappe.throw("Setiap item butuh 'item_row_name' dan 'qty'.")
            try:
                qty = float(qty)
            except (TypeError, ValueError):
                frappe.throw(f"qty '{qty}' tidak valid (harus angka).")
            if qty <= 0:
                frappe.throw(f"qty harus > 0 untuk row {row_name}.")
            requested[row_name] = qty

        source_rows_by_name = {it.name: it for it in source.get("items", [])}
        for row_name, qty in requested.items():
            if row_name not in source_rows_by_name:
                frappe.throw(f"Item row '{row_name}' tidak ada di invoice {source_name}.")
            src_qty = float(source_rows_by_name[row_name].qty or 0)
            if qty > src_qty:
                frappe.throw(
                    f"Move qty {qty} > qty source ({src_qty}) untuk row {row_name}."
                )

        remaining_total = sum(
            float(it.qty or 0) - requested.get(it.name, 0)
            for it in source.get("items", [])
        )
        if remaining_total <= 0:
            frappe.throw(
                "Move akan mengosongkan invoice sumber. Pakai 'Gabung Meja' kalau "
                "memang mau pindahkan semua item."
            )

        kept_source_items = []
        for it in source.get("items", []):
            move_qty = requested.get(it.name)
            src_qty = float(it.qty or 0)

            if move_qty:
                fields = it.meta.get_fieldnames_with_value()
                row = {f: it.get(f) for f in fields if f not in self.SKIP_FIELDS}
                row["qty"] = move_qty
                target.append("items", row)

                remaining = src_qty - move_qty
                if remaining > 0:
                    it.qty = remaining
                    kept_source_items.append(it)
            else:
                kept_source_items.append(it)

        source.set("items", kept_source_items)

        for tax in target.get("taxes", []):
            if tax.charge_type not in ("On Previous Row Amount", "On Previous Row Total"):
                tax.row_id = None
        for tax in source.get("taxes", []):
            if tax.charge_type not in ("On Previous Row Amount", "On Previous Row Total"):
                tax.row_id = None

        target.save()
        source.save()
        frappe.db.commit()
        return {"ok": True, "source": source_name, "target": target_name}

    def move_items_from_invoice(self, source_name, target_name):
        source = self.repo.get_invoice(source_name)
        target = self.repo.get_invoice(target_name)

        for item in source.get("items"):
            fields = item.meta.get_fieldnames_with_value()
            row = {f: item.get(f) for f in fields if f not in self.SKIP_FIELDS}
            target.append("items", row)

        # Use set_value to avoid triggering full validate() on source — the invoice
        # may have tax rows with row_id set for non-row-reference charge types, which
        # causes ValidationError in calculate_taxes_and_totals when save() runs.
        frappe.db.set_value("POS Invoice", source_name, {
            "is_merged": 1,
            "merge_invoice": target_name,
        })

        # Repoint semua Table Order row yang masih link ke source ke target.
        # Tanpa ini, kasus chained merge bikin delete_merge_invoice() throw
        # LinkExistsError karena tabel-tabel yang sebelumnya merged ke source
        # masih punya Table Order row → source. Caller (merge_table) cuma
        # repoint child rows dari `target_table` arg, bukan absorbed sub-tree.
        frappe.db.sql(
            """
            UPDATE `tabTable Order`
            SET invoice_name = %s
            WHERE invoice_name = %s
            """,
            (target_name, source_name),
        )

        # Clear row_id from tax rows that don't depend on a previous row before saving
        # target, to avoid the same ValidationError (same fix used in apply_discount).
        for tax in target.get("taxes", []):
            if tax.charge_type not in ("On Previous Row Amount", "On Previous Row Total"):
                tax.row_id = None

        target.save()
        frappe.db.commit()
