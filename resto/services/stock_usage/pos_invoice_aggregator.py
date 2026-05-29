"""PosInvoiceAggregatorService — extract POS invoice names from a POS Closing
Entry and aggregate sold items across them.

Major improvements over the legacy inline loop in get_pos_breakdown:
- Bulk get_all on child tables (parent IN [...]) instead of get_doc per invoice
  (Phase 1 audit: N+1 across SI/PI fetches)
- Strict net_amount: throw early instead of silent fallback to amount=0
- Voucher items skipped at source (Bug: voucher rows leaked into RM calc)
- Dedup invoices appearing in both Sales Invoice and POS Invoice tables
  (prefer Sales Invoice — modern POS submits there)
"""

from typing import Dict, List

import frappe
from frappe.utils import flt, getdate


class PosInvoiceAggregatorService:
    """Pure data layer: invoice names → aggregated rows by sold item_code.

    FG resolution (recipe_item lookup via Resto Menu) is delegated to the
    orchestrator (RawMaterialCalculatorService) so this stays bound to one
    responsibility.
    """

    INVOICE_NAME_KEYS = (
        "sales_invoice",
        "invoice",
        "pos_invoice",
        "si_name",
        "name",
    )

    ITEM_FIELDS = [
        "item_code",
        "item_name",
        "stock_uom",
        "qty",
        "net_amount",
        "amount",
        "is_voucher_item",
        "resto_menu",
        "category",
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract_invoice_names(self, pce) -> List[str]:
        """Return list of invoice names from a POS Closing Entry document.

        Strategy:
        1. Walk every child table for known invoice-reference fields
        2. Keep only names that exist as Sales Invoice or POS Invoice
        3. Fallback: query by PCE date range + pos_profile + company
        """
        if not pce:
            return []

        candidates: List[str] = []
        try:
            table_fields = pce.meta.get_table_fields() or []
        except Exception:
            table_fields = []

        for tf in table_fields:
            try:
                rows = pce.get(tf.fieldname) or []
            except Exception:
                continue
            for ch in rows:
                for key in self.INVOICE_NAME_KEYS:
                    val = ch.get(key)
                    if isinstance(val, str) and val:
                        candidates.append(val)

        candidates = [x for x in candidates if isinstance(x, str) and x]

        filtered = [
            x for x in candidates
            if frappe.db.exists("Sales Invoice", x)
            or frappe.db.exists("POS Invoice", x)
        ]

        if not filtered:
            filtered = self._fallback_by_date_range(pce)

        return list(dict.fromkeys(filtered))

    def aggregate_by_fg(self, invoice_names: List[str], company: str) -> Dict[str, Dict]:
        """Aggregate invoice items by sold item_code.

        - Bulk-fetches Sales Invoice Item + POS Invoice Item by parent IN […]
        - Dedups invoices in both tables (prefer Sales Invoice)
        - Skips items flagged is_voucher_item=1
        - Throws if any non-voucher row has net_amount=None (strict mode)

        Returns {item_code: {item_code, item_name, stock_uom, resto_menu,
                              category, qty, selling_amount}}
        """
        if not invoice_names:
            return {}

        unique = list(dict.fromkeys(invoice_names))

        si_invs = [n for n in unique if frappe.db.exists("Sales Invoice", n)]
        si_set = set(si_invs)
        pi_invs = [
            n for n in unique
            if n not in si_set and frappe.db.exists("POS Invoice", n)
        ]

        rows: List[Dict] = []
        if si_invs:
            rows.extend(self._fetch_items("Sales Invoice Item", si_invs))
        if pi_invs:
            rows.extend(self._fetch_items("POS Invoice Item", pi_invs))

        agg: Dict[str, Dict] = {}
        for r in rows:
            if r.get("is_voucher_item"):
                continue

            code = r.get("item_code")
            if not code:
                continue

            if r.get("net_amount") is None:
                frappe.throw(
                    f"net_amount missing on invoice item {code}. "
                    "Submit invoice with net amounts before running Stock Usage."
                )

            row = agg.setdefault(code, {
                "item_code": code,
                "item_name": r.get("item_name"),
                "stock_uom": r.get("stock_uom"),
                "resto_menu": r.get("resto_menu"),
                "category": r.get("category"),
                "qty": 0.0,
                "selling_amount": 0.0,
            })
            row["qty"] += flt(r.get("qty"))
            row["selling_amount"] += flt(r.get("net_amount"))

            if not row.get("item_name") and r.get("item_name"):
                row["item_name"] = r.get("item_name")
            if not row.get("stock_uom") and r.get("stock_uom"):
                row["stock_uom"] = r.get("stock_uom")
            if not row.get("resto_menu") and r.get("resto_menu"):
                row["resto_menu"] = r.get("resto_menu")
            if not row.get("category") and r.get("category"):
                row["category"] = r.get("category")

        return agg

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fetch_items(self, doctype: str, parent_names: List[str]) -> List[Dict]:
        return frappe.get_all(
            doctype,
            filters={"parent": ["in", parent_names], "docstatus": 1},
            fields=self.ITEM_FIELDS,
        )

    @staticmethod
    def _fallback_by_date_range(pce) -> List[str]:
        start = getattr(pce, "period_start_date", None) or getattr(pce, "start_date", None)
        end = getattr(pce, "period_end_date", None) or getattr(pce, "end_date", None)
        pos_profile = getattr(pce, "pos_profile", None)
        company = getattr(pce, "company", None)

        filters: Dict = {"docstatus": 1, "is_pos": 1}
        if start and end:
            filters["posting_date"] = ["between", [getdate(start), getdate(end)]]
        if pos_profile:
            filters["pos_profile"] = pos_profile
        if company:
            filters["company"] = company

        rows = frappe.get_all("Sales Invoice", filters=filters, fields=["name"])
        return [r.name if hasattr(r, "name") else r.get("name") for r in rows]
