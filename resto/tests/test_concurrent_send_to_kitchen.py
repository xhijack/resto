"""Regression guard: concurrent send_to_kitchen ke meja yang sama.

Pre-fix behavior:
    backend send_to_kitchen menerima orders snapshot dari frontend lalu REPLACE
    seluruh table.orders via update_table_status(orders=). 2 thread bersamaan
    membaca state lama → last-writer-wins → invoice 1 thread overwrite yang lain
    → orphan POS Invoice (sudah dibuat di DB tapi tidak ter-link ke meja).

Post-fix behavior:
    send_to_kitchen pakai add_table_order atomic dengan SELECT ... FOR UPDATE
    row-lock di TableRepository.lock_table_for_update. Read-modify-save atomik
    per thread → kedua invoice masuk ke table.orders, no orphan.

Test ini akan FAIL kalau seseorang revert ke pattern REPLACE — itulah inti
regression guard.

Catatan: test commit ke DB beneran (FrappeTestCase savepoint tidak cukup karena
worker thread pakai connection berbeda). tearDown cleanup table.orders + invoice
yang dibuat agar test idempotent.
"""

import threading
import frappe
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.kitchen_service import KitchenService

CONCURRENT_TABLE = "_TestConcT1"


class TestConcurrentSendToKitchen(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self._cleanup_state()
        if not frappe.db.exists("Table", CONCURRENT_TABLE):
            frappe.get_doc({
                "doctype": "Table",
                "table_name": CONCURRENT_TABLE,
                "branch": self.branch,
            }).insert(ignore_permissions=True)
        else:
            t = frappe.get_doc("Table", CONCURRENT_TABLE)
            t.set("orders", [])
            t.status = "Kosong"
            t.save(ignore_permissions=True)
        frappe.db.commit()

    def tearDown(self):
        self._cleanup_state()
        super().tearDown()

    def _cleanup_state(self):
        if frappe.db.exists("Table", CONCURRENT_TABLE):
            t = frappe.get_doc("Table", CONCURRENT_TABLE)
            invoices_to_delete = [o.invoice_name for o in (t.orders or [])]
            t.set("orders", [])
            t.status = "Kosong"
            try:
                t.save(ignore_permissions=True)
            except Exception:
                pass
            for name in invoices_to_delete:
                try:
                    frappe.delete_doc(
                        "POS Invoice", name, force=1, ignore_permissions=True
                    )
                except Exception:
                    pass
            frappe.db.commit()

    def test_concurrent_send_to_kitchen_no_orphan(self):
        """2 thread bersamaan kirim invoice berbeda ke meja yang sama →
        kedua invoice harus masuk ke table.orders + masing-masing punya
        field `table` set (no overwrite, no orphan)."""
        site = frappe.local.site
        results, errors = [], []
        results_lock = threading.Lock()

        # Snapshot fixtures dari main thread — worker thread punya koneksi
        # sendiri jadi ngk bisa baca self.foo dari objek di thread lain.
        customer_name = self.customer.name
        item_code = self.item.name
        pos_profile_name = self.pos_profile.name
        branch_name = self.branch
        mode_of_payment = self.mode_of_payment

        # Barrier supaya kedua thread benar-benar mulai bersamaan (maksimalkan
        # window race condition kalau lock tidak bekerja).
        start_barrier = threading.Barrier(2)

        def worker(idx):
            try:
                frappe.connect(site=site)
                start_barrier.wait(timeout=5)
                payload = {
                    "customer": customer_name,
                    "pos_profile": pos_profile_name,
                    "branch": branch_name,
                    "order_type": None,
                    "items": [{"item_code": item_code, "qty": 1, "rate": 100}],
                    "payments": [{"mode_of_payment": mode_of_payment, "amount": 100}],
                }
                result = KitchenService().send_to_kitchen(
                    payload=payload,
                    table_name=CONCURRENT_TABLE,
                    status="Terisi",
                )
                with results_lock:
                    results.append(result)
            except Exception as e:
                with results_lock:
                    errors.append((idx, repr(e)))
            finally:
                try:
                    frappe.destroy()
                except Exception:
                    pass

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(errors, [], f"Worker thread errors: {errors}")
        self.assertEqual(len(results), 2, f"Expected 2 results, got: {results}")

        # Refresh main thread connection — Table doc di main thread cache stale.
        frappe.db.commit()
        table_doc = frappe.get_doc("Table", CONCURRENT_TABLE)
        invoice_names = sorted({o.invoice_name for o in (table_doc.orders or [])})

        self.assertEqual(
            len(invoice_names), 2,
            f"Race condition: expected 2 distinct invoices in table.orders, "
            f"got {invoice_names}. Result invoices: "
            f"{[r.get('pos_invoice') for r in results]}"
        )

        # Verifikasi kedua invoice ter-link ke meja via custom field — bukan
        # cuma via Table Order child row. Kalau salah satu hilang, itu orphan.
        for name in invoice_names:
            linked_table = frappe.db.get_value("POS Invoice", name, "table")
            self.assertEqual(
                linked_table, CONCURRENT_TABLE,
                f"Invoice {name} field `table` = {linked_table!r}, "
                f"expected {CONCURRENT_TABLE!r} (orphan invoice!)"
            )
