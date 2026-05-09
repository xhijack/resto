import json
import frappe
from resto.repositories.table_repository import TableRepository
from resto.repositories.invoice_repository import InvoiceRepository
from resto.services.invoice_service import InvoiceService


class TableService:
    def __init__(self, repo=None):
        self.repo = repo or TableRepository()

    def update_table_status(self, name, status=None, taken_by=None, pax=None,
                            customer=None, type_customer=None, orders=None, checked=None):
        doc = self.repo.get_table(name)

        if status == "Kosong":
            doc.status = "Kosong"
            doc.taken_by = ""
            doc.pax = 0
            doc.customer = ""
            doc.type_customer = ""
            doc.checked = 0
            doc.orders = []
        else:
            if checked is not None:
                doc.checked = int(checked)
            if status is not None:
                doc.status = status
            if taken_by is not None:
                doc.taken_by = taken_by
            if pax is not None:
                doc.pax = int(pax)
            if customer is not None:
                doc.customer = customer
            if type_customer is not None:
                doc.type_customer = type_customer
            if orders is not None:
                parsed_orders = orders
                if isinstance(parsed_orders, str):
                    try:
                        parsed_orders = json.loads(parsed_orders)
                    except Exception:
                        frappe.log_error("Gagal parse orders JSON", orders)
                        parsed_orders = None  # invalid → skip update orders

                # REPLACE semantic: payload = state baru orders. Dedupe by invoice_name.
                # Sebelumnya append-only — bug: caller yang mau hapus 1 invoice (mis.
                # MoveItemModal saat source table punya >1 invoice) tidak bisa, karena
                # invoice yang dihilangkan dari payload tetap ada di DB → LinkExistsError
                # saat delete invoice tsb.
                # Input invalid (non-list / parse gagal) → JANGAN sentuh orders, biar
                # caller yang corrupt payload-nya tidak accidentally clear semua.
                if isinstance(parsed_orders, list):
                    seen = set()
                    new_orders = []
                    for o in parsed_orders:
                        invoice_name = o.get("invoice_name") if isinstance(o, dict) else o
                        if invoice_name and invoice_name not in seen:
                            seen.add(invoice_name)
                            new_orders.append({"invoice_name": invoice_name})
                    doc.set("orders", new_orders)

        self.repo.save_table(doc)
        return {
            "success": True,
            "message": f"Table {doc.name} updated successfully",
            "checked": getattr(doc, "checked", None)
        }

    def add_table_order(self, table_name, order):
        if not table_name or not order:
            frappe.throw("Table name dan order wajib diisi.")

        if isinstance(order, str):
            try:
                order = json.loads(order)
            except Exception:
                order = {"invoice_name": order}

        invoice_name = order.get("invoice_name") if isinstance(order, dict) else None
        if not invoice_name:
            frappe.throw("Field 'invoice_name' wajib ada di order.")

        doc = self.repo.get_table(table_name)
        existing_invoices = {o.invoice_name for o in doc.orders}
        if invoice_name in existing_invoices:
            return {"success": False, "message": f"Invoice {invoice_name} sudah ada di Table {table_name}"}

        doc.append("orders", {"invoice_name": invoice_name})
        if doc.status == "Kosong":
            doc.status = "Terisi"

        self.repo.save_table(doc)
        return {"success": True, "message": f"Order {invoice_name} berhasil ditambahkan ke Table {table_name}"}

    def clear_table(self, table_name):
        doc = self.repo.get_table(table_name)
        doc.orders = []
        doc.customer = None
        doc.taken_by = None
        doc.status = "Kosong"
        doc.type_customer = None
        self.repo.save_table(doc)

    def clear_table_merged(self, pos_invoice):
        tables = self.repo.get_tables_for_invoice(pos_invoice)
        for table in tables:
            if table:
                self.clear_table(table)

    def merge_table(self, pos_invoice, source_table=None, target_table=None):
        if not source_table:
            frappe.throw("source_table wajib diisi")
        if not target_table:
            frappe.throw("target_table wajib diisi")

        if not self.repo.table_exists(source_table):
            frappe.throw(f"Table '{source_table}' tidak ditemukan")

        if not self.repo.invoice_exists(pos_invoice):
            frappe.throw(f"POS Invoice '{pos_invoice}' tidak ditemukan")

        inv_repo = InvoiceRepository()
        source_invoice = inv_repo.get_invoice(pos_invoice)
        if source_invoice.docstatus == 1:
            frappe.throw(f"POS Invoice '{pos_invoice}' sudah disubmit dan tidak dapat di-merge")

        invoice_service = InvoiceService(repo=inv_repo)

        for tbl in target_table:
            if tbl == source_table:
                continue
            if not self.repo.table_exists(tbl):
                continue

            target_table_doc = self.repo.get_table(tbl)
            target_orders = target_table_doc.get("orders", [])
            for order in target_orders:
                invoice_service.move_items_from_invoice(order.invoice_name, pos_invoice)
                order.invoice_name = pos_invoice
            if target_orders:
                self.repo.save_table(target_table_doc)

        invoice_service.delete_merge_invoice(pos_invoice)
        return {
            "ok": True,
            "message": f"Berhasil menggabungkan {len(target_table)} meja ke {source_table}"
        }

    def get_all_tables_with_details(self):
        tables = self.repo.get_all_tables()
        taken_by_emails = [t.taken_by for t in tables if t.taken_by]
        full_name_map = self.repo.get_user_full_names(taken_by_emails)

        result = []
        for t in tables:
            doc = self.repo.get_table(t.name)
            result.append({
                "id": t.name,
                "name": t.table_name,
                "status": t.status or "Kosong",
                "type": t.table_type,
                "zone": t.zone,
                "customer": t.customer or None,
                "pax": t.pax or 0,
                "typeCustomer": t.type_customer or None,
                "floor": t.floor or "1",
                "takenBy": t.taken_by or None,
                "takenByName": full_name_map.get(t.taken_by) if t.taken_by else None,
                "checked": t.checked,
                "orders": [{"invoice_name": o.invoice_name} for o in doc.orders],
            })
        return result
