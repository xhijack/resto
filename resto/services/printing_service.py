import json
import frappe
from resto.repositories.printing_repository import PrintingRepository

try:
    from resto.printing import _enqueue_bill_worker, _enqueue_receipt_worker
    from resto.printing import build_void_item_receipt, cups_print_raw
except Exception:
    _enqueue_bill_worker = None
    _enqueue_receipt_worker = None
    build_void_item_receipt = None
    cups_print_raw = None


class PrintingService:
    def __init__(self, repo=None):
        self.repo = repo or PrintingRepository()

    # ------------------------------------------------------------------
    # print_bill_now
    # ------------------------------------------------------------------

    def print_bill_now(self, invoice_name, branch, table_name=None,
                       status=None, taken_by=None, pax=0, customer=None,
                       type_customer=None, orders=None, checked=None,
                       table_service=None):
        printer = self.repo.get_bill_printer(branch)
        if not printer:
            frappe.throw(f"Tidak ditemukan printer untuk branch {branch}")

        if table_name and table_service is not None:
            if orders is None:
                orders = []
            elif isinstance(orders, str):
                try:
                    orders = json.loads(orders)
                except Exception:
                    frappe.log_error("Gagal parse orders JSON", orders)
                    orders = []
            if not isinstance(orders, list):
                orders = []

            table_service.update_table_status(
                name=table_name,
                status="Print Bill",
                taken_by=taken_by,
                pax=pax,
                customer=customer,
                type_customer=type_customer,
                orders=orders,
                checked=checked
            )

        job_id = _enqueue_bill_worker(invoice_name, printer)
        frappe.msgprint(f"Invoice {invoice_name} dikirim ke printer {printer}")
        return {"ok": True, "job_id": job_id}

    # ------------------------------------------------------------------
    # print_receipt_now
    # ------------------------------------------------------------------

    def print_receipt_now(self, invoice_name, branch):
        printer = self.repo.get_receipt_printer(branch)
        if not printer:
            frappe.throw(f"Tidak ditemukan printer untuk branch {branch}")

        job_id = _enqueue_receipt_worker(invoice_name, printer)
        frappe.msgprint(f"Invoice {invoice_name} dikirim ke printer {printer}")
        return {"ok": True, "job_id": job_id}

    # ------------------------------------------------------------------
    # print_void_item
    # ------------------------------------------------------------------

    def print_void_item(self, pos_invoice):
        items_to_print = self.repo.get_void_items_to_print(pos_invoice)

        if not items_to_print:
            frappe.logger("pos_print").info(
                f"Void Menu: tidak ada item baru untuk dicetak pada invoice {pos_invoice}"
            )
            return {"ok": True, "message": "Tidak ada item baru untuk dicetak"}

        branch = self.repo.get_invoice_branch(pos_invoice)
        printer_name = self.repo.get_void_printer(branch)
        if not printer_name:
            frappe.throw(f"Tidak ditemukan void printer untuk branch {branch}")

        raw = build_void_item_receipt(pos_invoice, items_to_print, printer_name)
        job_id = cups_print_raw(raw, printer_name)

        self._print_void_to_other_stations(pos_invoice, items_to_print, branch)

        for it in items_to_print:
            self.repo.mark_void_printed(it["name"])

        frappe.logger("pos_print").info({
            "invoice": pos_invoice,
            "printer": printer_name,
            "job_id": job_id,
            "items_printed": len(items_to_print)
        })

        return {"ok": True, "job_id": job_id, "items_printed": len(items_to_print)}

    def _print_void_to_other_stations(self, pos_invoice, items_to_print, branch):
        for item in items_to_print:
            for printer_name in self.repo.get_branch_menu_printers_for_item(
                item["item_code"], branch
            ):
                raw = build_void_item_receipt(pos_invoice, items_to_print)
                cups_print_raw(raw, printer_name)
