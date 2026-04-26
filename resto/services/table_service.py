import json
import frappe
from resto.repositories.table_repository import TableRepository


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
                if isinstance(orders, str):
                    try:
                        orders = json.loads(orders)
                    except Exception:
                        frappe.log_error("Gagal parse orders JSON", orders)
                        orders = []

                if not isinstance(orders, list):
                    orders = []

                existing_invoices = {d.invoice_name for d in doc.orders}
                for o in orders:
                    invoice_name = o.get("invoice_name") if isinstance(o, dict) else o
                    if invoice_name and invoice_name not in existing_invoices:
                        doc.append("orders", {"invoice_name": invoice_name})

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

    def get_all_tables_with_details(self):
        tables = self.repo.get_all_tables()
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
                "checked": t.checked,
                "orders": [{"invoice_name": o.invoice_name} for o in doc.orders],
            })
        return result
