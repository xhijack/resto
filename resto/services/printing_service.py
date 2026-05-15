import json
import frappe
from resto.repositories.printing_repository import PrintingRepository

try:
    from resto.printing import (
        _enqueue_bill_worker, _enqueue_check_worker, _enqueue_receipt_worker,
        _enqueue_checker_worker, build_void_item_receipt, cups_print_raw,
        get_printer_state, build_test_print_payload,
    )
except Exception:
    _enqueue_bill_worker = None
    _enqueue_check_worker = None
    _enqueue_receipt_worker = None
    _enqueue_checker_worker = None
    build_void_item_receipt = None
    cups_print_raw = None
    get_printer_state = None
    build_test_print_payload = None


class PrintingService:
    def __init__(self, repo=None):
        self.repo = repo or PrintingRepository()

    # ------------------------------------------------------------------
    # print_bill_now
    # ------------------------------------------------------------------

    def _update_status_for_invoice_tables(self, invoice_name, table_name, table_service,
                                          taken_by, pax, customer, type_customer,
                                          orders, checked):
        if not (table_name and table_service is not None):
            return

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

        related = table_service.repo.get_tables_for_invoice(invoice_name) or []
        targets = list(related)
        if table_name and table_name not in targets:
            targets.insert(0, table_name)

        for tname in targets:
            table_service.update_table_status(
                name=tname,
                status="Print Bill",
                taken_by=taken_by,
                pax=pax,
                customer=customer,
                type_customer=type_customer,
                orders=orders,
                checked=checked,
            )

    def print_bill_now(self, invoice_name, branch, table_name=None,
                       status=None, taken_by=None, pax=0, customer=None,
                       type_customer=None, orders=None, checked=None,
                       table_service=None):
        printer = self.repo.get_bill_printer(branch)
        if not printer:
            frappe.throw(f"Tidak ditemukan printer untuk branch {branch}")

        self._update_status_for_invoice_tables(
            invoice_name, table_name, table_service,
            taken_by, pax, customer, type_customer, orders, checked,
        )

        job_id = _enqueue_bill_worker(invoice_name, printer)
        frappe.msgprint(f"Invoice {invoice_name} dikirim ke printer {printer}")
        return {"ok": True, "job_id": job_id}

    # ------------------------------------------------------------------
    # print_check_now
    # ------------------------------------------------------------------

    def print_check_now(self, invoice_name, branch, table_name=None,
                        status=None, taken_by=None, pax=0, customer=None,
                        type_customer=None, orders=None, checked=None,
                        table_service=None):
        printer = self.repo.get_bill_printer(branch)
        if not printer:
            frappe.throw(f"Tidak ditemukan printer untuk branch {branch}")

        self._update_status_for_invoice_tables(
            invoice_name, table_name, table_service,
            taken_by, pax, customer, type_customer, orders, checked,
        )

        job_id = _enqueue_check_worker(invoice_name, printer)
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

        self._print_void_to_other_stations(
            pos_invoice, items_to_print, branch, void_printer=printer_name
        )

        for it in items_to_print:
            self.repo.mark_void_printed(it["name"])

        frappe.logger("pos_print").info({
            "invoice": pos_invoice,
            "printer": printer_name,
            "job_id": job_id,
            "items_printed": len(items_to_print)
        })

        return {"ok": True, "job_id": job_id, "items_printed": len(items_to_print)}

    # ------------------------------------------------------------------
    # list_printers_with_status
    # ------------------------------------------------------------------

    def list_printers_with_status(self):
        """Return Kitchen Station list dengan status pycups (online/offline).

        Bila CUPS tidak tersedia (daemon down / pycups missing), tetap return
        list Kitchen Station dengan state="cups_unavailable" supaya UI tidak crash.

        Probe TCP di get_printer_state bersifat blocking per printer (~1.5s
        timeout untuk yang offline). Tanpa parallelisasi, N printer offline =
        N × 1.5s. Pakai ThreadPoolExecutor dengan max 8 worker — cukup untuk
        deployment khas (1–6 station per branch).
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        stations = frappe.get_all(
            "Kitchen Station",
            fields=["name", "printer_name", "description"],
        )

        try:
            import cups
            cups.Connection()  # validasi daemon hidup; worker buat conn sendiri
        except Exception:
            return [
                {
                    "name": s["name"],
                    "printer_name": s.get("printer_name") or "",
                    "label": s.get("description") or s["name"],
                    "is_online": False,
                    "state": "cups_unavailable",
                }
                for s in stations
            ]

        def _resolve(s):
            entry = {
                "name": s["name"],
                "printer_name": s.get("printer_name") or "",
                "label": s.get("description") or s["name"],
                "is_online": False,
                "state": "not_found",
            }
            if not entry["printer_name"]:
                return entry
            try:
                info = get_printer_state(entry["printer_name"])
                entry["is_online"] = info["is_online"]
                entry["state"] = info["state"]
            except frappe.ValidationError:
                pass  # state stays "not_found"
            return entry

        if not stations:
            return []

        max_workers = min(8, len(stations))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_resolve, s) for s in stations]
            results = [f.result() for f in as_completed(futures)]

        name_order = {s["name"]: i for i, s in enumerate(stations)}
        results.sort(key=lambda e: name_order.get(e["name"], 10**9))
        return results

    # ------------------------------------------------------------------
    # test_print
    # ------------------------------------------------------------------

    def test_print(self, printer_name: str):
        if not printer_name:
            frappe.throw("printer_name wajib diisi")

        # Pre-check status: CUPS akan accept job (assign job_id) meskipun
        # printer fisik mati — job duduk di queue sampai printer hidup. Tanpa
        # pre-check, test print "sukses" padahal printer mati → user bingung.
        try:
            status = get_printer_state(printer_name)
        except frappe.ValidationError:
            raise  # propagate (printer tidak terdaftar di CUPS)
        except Exception:
            # CUPS daemon down / pycups tidak ada — jangan submit
            frappe.throw(f"Tidak bisa cek status printer '{printer_name}' di CUPS")

        if not status.get("is_online"):
            reasons = status.get("state_reasons") or []
            reason_hint = f" (alasan: {', '.join(reasons)})" if reasons else ""
            frappe.throw(
                f"Printer '{printer_name}' sedang offline / tidak siap{reason_hint}. "
                f"Cek apakah printer menyala dan terhubung."
            )

        raw = build_test_print_payload(printer_name)
        job_id = cups_print_raw(raw, printer_name)
        frappe.logger("pos_print").info({
            "printer": printer_name,
            "job_id": job_id,
            "type": "test_print",
        })
        return {"ok": True, "job_id": job_id, "printer": printer_name}

    def enqueue_checker_after_kitchen(self, pos_name, branch):
        try:
            printer = self.repo.get_checker_printer(branch)
            if not printer:
                frappe.throw(f"Tidak ditemukan printer checker default untuk branch {branch}")

            job_id = _enqueue_checker_worker(pos_name, printer)
            frappe.logger().info(
                f"Enqueue Checker: {pos_name} (printer={printer}, job_id={job_id})"
            )
            return job_id
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Enqueue Checker Error for {pos_name}")
            return None

    def _print_void_to_other_stations(self, pos_invoice, items_to_print, branch, void_printer=None):
        # Bug v1.2.14: dulu loop `for item: for printer: print(items_to_print, printer)`
        # → kalau 2 item routed ke printer yang sama (mis: 2 minuman ke BAR),
        # BAR dapat receipt 2x dengan full items. Kasus jelas pasca merge table.
        # Fix: group items by printer dulu, lalu print 1x per printer dengan
        # hanya items yang relevan ke printer itu.
        #
        # Bug v1.2.17 (Issue #4): kalau void_printer == kitchen station printer
        # (mis. default void = BAR, dan item route ke BAR), BAR dicetak 2x:
        # 1x dari top-level print_void_item (full items), 1x dari sini (items
        # yang route ke BAR). Fix: skip printer kalau == void_printer; top-level
        # sudah cover printer itu dengan full items_to_print.
        printer_to_items = {}
        for item in items_to_print:
            for printer_name in self.repo.get_branch_menu_printers_for_item(
                item["item_code"], branch
            ):
                if printer_name == void_printer:
                    continue
                printer_to_items.setdefault(printer_name, []).append(item)

        for printer_name, items_for_printer in printer_to_items.items():
            raw = build_void_item_receipt(pos_invoice, items_for_printer, printer_name)
            cups_print_raw(raw, printer_name)
