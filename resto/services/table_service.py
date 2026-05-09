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
        """Atomic APPEND order ke Table.orders. Pakai row-level lock supaya
        2 thread bersamaan tidak saling overwrite (race condition)."""
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

        # Pakai get_table_for_update: combined lock + locking read.
        # Penting: read HARUS locking (FOR UPDATE) supaya dapat latest committed
        # data. Non-locking read di REPEATABLE READ akan return snapshot
        # transaksi → _original_modified stale → TimestampMismatchError.
        doc = self.repo.get_table_for_update(table_name)
        existing_invoices = {o.invoice_name for o in doc.orders}
        if invoice_name in existing_invoices:
            # Tetap commit untuk release lock walau no-op.
            frappe.db.commit()
            return {"success": False, "message": f"Invoice {invoice_name} sudah ada di Table {table_name}"}

        doc.append("orders", {"invoice_name": invoice_name})
        if doc.status == "Kosong":
            doc.status = "Terisi"

        # Skip optimistic timestamp check — kita pakai pessimistic lock
        # (SELECT ... FOR UPDATE), jadi check_if_latest jadi redundant DAN
        # bikin false-positive: kalau 2 thread keduanya sempat load doc
        # sebelum salah satu commit, optimistic check gagal walau lock-nya benar.
        doc.flags.ignore_version = True
        self.repo.save_table(doc)

        # Realtime push: notify subscribers (mobile devices) bahwa table ini
        # punya order baru. Pakai after_commit=True supaya event tidak terbang
        # sebelum DB commit (kalau transaksi rollback, tidak ada ghost event).
        # No room param → broadcast ke semua subscriber site (single-tenant).
        frappe.publish_realtime(
            "table_order_added",
            {
                "table_name": table_name,
                "invoice_name": invoice_name,
                "status": doc.status,
            },
            after_commit=True,
        )
        return {"success": True, "message": f"Order {invoice_name} berhasil ditambahkan ke Table {table_name}"}

    def remove_table_order(self, table_name, invoice_name):
        """Atomic REMOVE invoice dari Table.orders. Dipakai saat invoice
        di-pay-off / clear individual. Locking pattern sama dengan add."""
        if not table_name or not invoice_name:
            frappe.throw("Table name dan invoice_name wajib diisi.")

        doc = self.repo.get_table_for_update(table_name)
        before = len(doc.orders or [])
        new_orders = [
            {"invoice_name": o.invoice_name}
            for o in (doc.orders or [])
            if o.invoice_name and o.invoice_name != invoice_name
        ]
        if len(new_orders) == before:
            frappe.db.commit()
            return {"success": False, "message": f"Invoice {invoice_name} tidak ada di Table {table_name}"}

        doc.set("orders", new_orders)
        doc.flags.ignore_version = True
        self.repo.save_table(doc)

        frappe.publish_realtime(
            "table_order_removed",
            {"table_name": table_name, "invoice_name": invoice_name},
            after_commit=True,
        )
        return {"success": True, "message": f"Order {invoice_name} dihapus dari Table {table_name}"}

    def update_table_meta(self, name, status=None, taken_by=None, pax=None,
                          customer=None, type_customer=None, checked=None):
        """Update field metadata Table TANPA menyentuh orders. Dipakai oleh
        send_to_kitchen pasca-refactor: orders di-update via add_table_order
        atomic, meta lain via method ini.

        Status='Kosong' juga clear field operasional (taken_by/pax/customer/
        type_customer/checked) supaya konsisten dengan update_table_status.

        Pakai lock_table_for_update sama seperti add_table_order — tanpa lock,
        kalau add_table_order + update_table_meta dipanggil berurutan oleh 2
        thread, gap antar-call bikin TimestampMismatchError karena optimistic
        concurrency check Frappe (loaded.modified vs db.modified)."""
        if not name:
            frappe.throw("name wajib diisi.")

        doc = self.repo.get_table_for_update(name)

        if status == "Kosong":
            doc.status = "Kosong"
            doc.taken_by = ""
            doc.pax = 0
            doc.customer = ""
            doc.type_customer = ""
            doc.checked = 0
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

        doc.flags.ignore_version = True
        self.repo.save_table(doc)

        frappe.publish_realtime(
            "table_meta_updated",
            {
                "table_name": name,
                "status": doc.status,
                "pax": doc.pax,
                "customer": doc.customer,
                "type_customer": doc.type_customer,
                "taken_by": doc.taken_by,
            },
            after_commit=True,
        )
        return {
            "success": True,
            "message": f"Table {doc.name} meta updated",
            "checked": getattr(doc, "checked", None),
        }

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

    def get_merged_group_size(self, source_table):
        if not self.repo.table_exists(source_table):
            frappe.throw(f"Table '{source_table}' tidak ditemukan")

        doc = self.repo.get_table(source_table)
        invoice_names = list({o.invoice_name for o in (doc.orders or []) if o.invoice_name})
        if not invoice_names:
            return 1

        parents = frappe.get_all(
            "Table Order",
            filters={"invoice_name": ["in", invoice_names]},
            pluck="parent",
        )
        members = set(parents) | {source_table}
        return len(members)

    def move_merged_group(self, source_table, target_tables):
        if isinstance(target_tables, str):
            try:
                target_tables = json.loads(target_tables)
            except Exception:
                target_tables = [target_tables]

        if not isinstance(target_tables, list) or not target_tables:
            frappe.throw("target_tables wajib diisi (minimal 1 meja).")

        if not self.repo.table_exists(source_table):
            frappe.throw(f"Table '{source_table}' tidak ditemukan")

        source_doc = self.repo.get_table(source_table)
        invoice_names = list({o.invoice_name for o in (source_doc.orders or []) if o.invoice_name})
        if invoice_names:
            parents = frappe.get_all(
                "Table Order",
                filters={"invoice_name": ["in", invoice_names]},
                pluck="parent",
            )
            members = sorted(set(parents) | {source_table})
        else:
            members = [source_table]

        if len(target_tables) != len(members):
            frappe.throw(
                f"Tabel ini hasil gabung {len(members)} meja, target harus {len(members)} meja juga "
                f"(sekarang {len(target_tables)})."
            )

        member_set = set(members)
        for t in target_tables:
            if t in member_set:
                frappe.throw(f"Target '{t}' tidak boleh sama dengan meja sumber.")
            if not self.repo.table_exists(t):
                frappe.throw(f"Table '{t}' tidak ditemukan")
            tgt_doc = self.repo.get_table(t)
            if (tgt_doc.status or "Kosong") != "Kosong":
                frappe.throw(f"Table target '{t}' tidak kosong (status: {tgt_doc.status}).")

        for src, tgt in zip(members, list(target_tables)):
            src_doc = self.repo.get_table(src)
            tgt_doc = self.repo.get_table(tgt)

            tgt_doc.status = src_doc.status
            tgt_doc.taken_by = src_doc.taken_by
            tgt_doc.pax = src_doc.pax
            tgt_doc.customer = src_doc.customer
            tgt_doc.type_customer = src_doc.type_customer
            tgt_doc.checked = src_doc.checked
            tgt_doc.set(
                "orders",
                [{"invoice_name": o.invoice_name} for o in (src_doc.orders or []) if o.invoice_name],
            )

            src_doc.status = "Kosong"
            src_doc.taken_by = ""
            src_doc.pax = 0
            src_doc.customer = ""
            src_doc.type_customer = ""
            src_doc.checked = 0
            src_doc.set("orders", [])

            self.repo.save_table(tgt_doc)
            self.repo.save_table(src_doc)

        return {
            "ok": True,
            "moved_count": len(members),
            "message": f"Berhasil memindahkan {len(members)} meja",
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
