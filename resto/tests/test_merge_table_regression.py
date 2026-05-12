"""Integration regression test untuk Issue #6 — merge table bikin meja kedua
orphan: invoice di Table Order tidak bisa dibuka, item hilang dari UI meja kedua.

Konteks user report (APK v1.2.17 + backend 9890bfb):
- Gabung 2 meja → buka meja 1: items terlihat (OK).
- Buka meja 2: kosong / tidak ada items.
- DB: meja 2 punya Table Order dengan invoice_name yang tidak bisa dibuka.
- Sebelumnya sudah pernah solved — regresi karena update terbaru.

Test ini PAKAI REAL DB (bukan mock) supaya menangkap regresi yang mock tidak bisa:
- Frappe doc.save() interplay dengan SQL UPDATE langsung di tabTable Order.
- delete_merge_invoice() membersihkan invoice yang salah.
- Stale child rows yang tidak ter-update saat save_table().

Run:
    /opt/anaconda3/envs/env/bin/bench --site resto.integration_test run-tests \\
        --app resto --module resto.tests.test_merge_table_regression
"""

import frappe
from frappe.utils import nowdate, nowtime
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.table_service import TableService


class TestMergeTableRegression(RestoPOSTestBase):
    """Real-DB regression test untuk merge_table.

    Skenario inti: 2 meja, masing-masing punya 1 draft POS Invoice + 1 Table Order
    row pointing ke invoice tersebut. Setelah merge, kedua meja harus point ke
    kept invoice (tidak orphan), kept invoice harus exists dan punya items
    gabungan dari kedua sumber.
    """

    def setUp(self):
        super().setUp()
        self._ensure_zone_and_floor()
        self.table_a = self._make_table("TBL-REGR-A")
        self.table_b = self._make_table("TBL-REGR-B")

    def tearDown(self):
        # Hapus residu agar test idempotent.
        for tbl in ("TBL-REGR-A", "TBL-REGR-B"):
            if frappe.db.exists("Table", tbl):
                doc = frappe.get_doc("Table", tbl)
                doc.orders = []
                doc.save(ignore_permissions=True)
                doc.delete(ignore_permissions=True, force=True)
        # POS Invoices: cleanup draft yang dibuat test ini.
        for inv in frappe.get_all(
            "POS Invoice",
            filters={"customer": self.customer.name, "docstatus": 0},
            pluck="name",
        ):
            try:
                frappe.delete_doc("POS Invoice", inv, force=True, ignore_permissions=True)
            except Exception:
                pass
        frappe.db.commit()
        super().tearDown()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_zone_and_floor(self):
        if not frappe.db.exists("Table Zone", "_Test Zone Regr"):
            frappe.get_doc({
                "doctype": "Table Zone",
                "name_zone": "_Test Zone Regr",
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Table Floor", "_Test Floor Regr"):
            frappe.get_doc({
                "doctype": "Table Floor",
                "name_floor": "_Test Floor Regr",
            }).insert(ignore_permissions=True)

    def _make_table(self, table_name):
        if frappe.db.exists("Table", table_name):
            doc = frappe.get_doc("Table", table_name)
            doc.orders = []
            doc.status = "Kosong"
            doc.save(ignore_permissions=True)
            return doc
        return frappe.get_doc({
            "doctype": "Table",
            "table_name": table_name,
            "zone": "_Test Zone Regr",
            "floor": "_Test Floor Regr",
            "status": "Kosong",
            "table_type": "4",
        }).insert(ignore_permissions=True)

    def _make_draft_invoice(self, item_rate, item_qty=1):
        inv = self._create_test_pos_invoice(qty=item_qty, rate=item_rate, submit=False)
        return inv

    def _attach_invoice_to_table(self, table_doc, invoice_name, taken_by=None):
        table_doc.status = "Has Taken"
        table_doc.taken_by = taken_by or frappe.session.user
        table_doc.pax = 2
        table_doc.append("orders", {"invoice_name": invoice_name})
        table_doc.save(ignore_permissions=True)
        frappe.db.commit()
        return table_doc

    # ------------------------------------------------------------------
    # Regression tests
    # ------------------------------------------------------------------

    def test_meja_kedua_tetap_point_ke_kept_invoice_setelah_merge(self):
        """Inti bug Issue #6.

        Setelah merge meja A + meja B (B di-absorb ke A), meja B masih harus
        punya Table Order dengan invoice_name = kept_invoice (= A's invoice).
        Kalau ini fail → meja B di UI mobile akan tampak kosong / orphan.
        """
        inv_a = self._make_draft_invoice(item_rate=100, item_qty=2)
        inv_b = self._make_draft_invoice(item_rate=50, item_qty=3)

        self._attach_invoice_to_table(self.table_a, inv_a.name)
        self._attach_invoice_to_table(self.table_b, inv_b.name)

        TableService().merge_table(
            pos_invoice=inv_a.name,
            source_table=self.table_a.name,
            target_table=[self.table_b.name],
        )

        # Reload dari DB (jangan pakai in-memory snapshot)
        reloaded_b = frappe.get_doc("Table", self.table_b.name)
        b_invoice_refs = [o.invoice_name for o in (reloaded_b.orders or [])]
        self.assertIn(
            inv_a.name, b_invoice_refs,
            f"Meja B (absorbed) harus punya Table Order pointing ke kept invoice "
            f"{inv_a.name}, tapi malah: {b_invoice_refs}",
        )
        self.assertNotIn(
            inv_b.name, b_invoice_refs,
            f"Meja B tidak boleh punya reference ke source invoice {inv_b.name} "
            f"yang sudah di-merge/delete.",
        )

    def test_kept_invoice_masih_exists_setelah_merge(self):
        """Kept invoice (yang jadi target merge) tidak boleh ter-delete."""
        inv_a = self._make_draft_invoice(item_rate=100, item_qty=2)
        inv_b = self._make_draft_invoice(item_rate=50, item_qty=3)

        self._attach_invoice_to_table(self.table_a, inv_a.name)
        self._attach_invoice_to_table(self.table_b, inv_b.name)

        TableService().merge_table(
            pos_invoice=inv_a.name,
            source_table=self.table_a.name,
            target_table=[self.table_b.name],
        )

        self.assertTrue(
            frappe.db.exists("POS Invoice", inv_a.name),
            f"Kept invoice {inv_a.name} hilang setelah merge — bug critical.",
        )

    def test_source_invoice_terhapus_setelah_merge(self):
        """Source invoice (yang di-absorb) harus ter-delete oleh delete_merge_invoice."""
        inv_a = self._make_draft_invoice(item_rate=100, item_qty=2)
        inv_b = self._make_draft_invoice(item_rate=50, item_qty=3)

        self._attach_invoice_to_table(self.table_a, inv_a.name)
        self._attach_invoice_to_table(self.table_b, inv_b.name)

        TableService().merge_table(
            pos_invoice=inv_a.name,
            source_table=self.table_a.name,
            target_table=[self.table_b.name],
        )

        self.assertFalse(
            frappe.db.exists("POS Invoice", inv_b.name),
            f"Source invoice {inv_b.name} harus dihapus setelah merge.",
        )

    def test_kept_invoice_punya_items_dari_kedua_sumber(self):
        """Items dari meja A (qty 2) + meja B (qty 3) total qty 5 di kept invoice."""
        inv_a = self._make_draft_invoice(item_rate=100, item_qty=2)
        inv_b = self._make_draft_invoice(item_rate=50, item_qty=3)

        self._attach_invoice_to_table(self.table_a, inv_a.name)
        self._attach_invoice_to_table(self.table_b, inv_b.name)

        TableService().merge_table(
            pos_invoice=inv_a.name,
            source_table=self.table_a.name,
            target_table=[self.table_b.name],
        )

        reloaded = frappe.get_doc("POS Invoice", inv_a.name)
        total_qty = sum(int(it.qty) for it in reloaded.items)
        self.assertEqual(
            total_qty, 5,
            f"Kept invoice harus punya total qty 5 (2 dari A + 3 dari B), "
            f"actual: {total_qty}",
        )

    def test_meja_a_juga_tetap_point_ke_kept_invoice(self):
        """Source table (TBL-A) juga harus tetap punya orders[].invoice_name = inv_a."""
        inv_a = self._make_draft_invoice(item_rate=100, item_qty=2)
        inv_b = self._make_draft_invoice(item_rate=50, item_qty=3)

        self._attach_invoice_to_table(self.table_a, inv_a.name)
        self._attach_invoice_to_table(self.table_b, inv_b.name)

        TableService().merge_table(
            pos_invoice=inv_a.name,
            source_table=self.table_a.name,
            target_table=[self.table_b.name],
        )

        reloaded_a = frappe.get_doc("Table", self.table_a.name)
        a_refs = [o.invoice_name for o in (reloaded_a.orders or [])]
        self.assertIn(inv_a.name, a_refs)

    def test_mobile_style_fetch_invoice_dari_meja_b_succeeds(self):
        """End-to-end: dari sisi mobile, ambil meja B, baca orders[0].invoice_name,
        lalu frappe.get_doc — harus succeed dan return kept invoice's data."""
        inv_a = self._make_draft_invoice(item_rate=100, item_qty=2)
        inv_b = self._make_draft_invoice(item_rate=50, item_qty=3)

        self._attach_invoice_to_table(self.table_a, inv_a.name)
        self._attach_invoice_to_table(self.table_b, inv_b.name)

        TableService().merge_table(
            pos_invoice=inv_a.name,
            source_table=self.table_a.name,
            target_table=[self.table_b.name],
        )

        reloaded_b = frappe.get_doc("Table", self.table_b.name)
        self.assertTrue(reloaded_b.orders, "Meja B tidak boleh kehilangan orders array")
        ref_invoice = reloaded_b.orders[0].invoice_name
        # Ini adalah simulasi mobile mencoba membuka invoice dari meja kedua.
        fetched = frappe.get_doc("POS Invoice", ref_invoice)
        self.assertEqual(fetched.name, inv_a.name)
