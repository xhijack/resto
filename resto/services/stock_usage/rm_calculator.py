"""RawMaterialCalculatorService — orchestrator.

Pipeline (per POS Daily Summary):
  load Daily Summary → fan out to all linked POS Closing Entries →
  extract invoice names per PCE → aggregate by sold item →
  resolve FG/BOM → explode RM → allocate batches (for batched RMs) →
  enrich with on-hand qty.

Scope unit: ONE POS Daily Summary, which already aggregates every PCE
that closed for one branch on one day. The orchestrator fans out across
the summary's `pos_transactions` child rows so a single load covers the
whole day's stock consumption — not just a single shift.

This is the only service in the stock-usage stack that composes the others.
Per-service responsibilities stay narrow; this one wires them together.
"""

from typing import Dict, List, Optional

import frappe
from frappe.utils import flt

from resto.services.stock_usage.pos_invoice_aggregator import PosInvoiceAggregatorService
from resto.services.stock_usage.bom_resolver import BomResolverService
from resto.services.stock_usage.batch_allocator import BatchAllocatorService


class RawMaterialCalculatorService:
    """Compose aggregator + bom + batch services into a POS Closing breakdown."""

    def __init__(self):
        self.aggregator = PosInvoiceAggregatorService()
        self.bom = BomResolverService()
        self.batch = BatchAllocatorService()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute_breakdown(self, daily_summary_name: str, warehouse: Optional[str] = None) -> Dict:
        """Return {"items": [...]} — one FG row per aggregated sold item
        across every PCE listed on the given POS Daily Summary.

        Each FG row carries `rm_items` (flat RM list) and `rm_tree` (hierarchical
        view). Batched RMs include `is_batched`, `batch_allocations`,
        `batch_partial`, and `batch_shortage_qty`.
        """
        if not daily_summary_name:
            return {"items": []}

        eds = frappe.get_doc("POS Daily Summary", daily_summary_name)
        pces = self._load_pces(eds)
        company = self._resolve_company(eds, pces)

        inv_names = self._collect_invoice_names(pces)
        if not inv_names:
            return {"items": []}

        agg = self.aggregator.aggregate_by_fg(inv_names, company)

        items: List[Dict] = []
        for sold_code, base in agg.items():
            qty = flt(base.get("qty"))
            if qty <= 0:
                continue

            fg = self.bom.resolve_fg(sold_code, company)
            fg_code = fg.get("item_code") or sold_code
            bom_no = fg.get("bom_no")
            selling_amount = flt(base.get("selling_amount"))

            rm_items = self._build_rm_rows(bom_no, qty, company, warehouse)
            rm_tree = self.bom.build_tree(bom_no, qty) if bom_no else []
            if rm_tree and warehouse:
                self._enrich_tree_actual_qty(rm_tree, warehouse)

            items.append({
                "item_code": fg_code,
                "item_name": fg.get("item_name") or base.get("item_name") or fg_code,
                "stock_uom": fg.get("stock_uom") or base.get("stock_uom"),
                "qty": qty,
                "bom_no": bom_no,
                "selling_amount": selling_amount,
                "selling_rate": (selling_amount / qty) if qty else 0,
                "rm_items": rm_items,
                "rm_tree": rm_tree,
                "actual_qty": self._on_hand(fg_code, warehouse),
                "resto_menu": base.get("resto_menu"),
                "category": base.get("category"),
            })

        return {"items": items}

    # ------------------------------------------------------------------
    # Daily-summary fan-out
    # ------------------------------------------------------------------

    @staticmethod
    def _load_pces(eds) -> List:
        """Load every PCE doc referenced by the Daily Summary's child rows."""
        rows = getattr(eds, "pos_transactions", None) or []
        pces: List = []
        for row in rows:
            pce_name = getattr(row, "pos_closing_entry", None)
            if not pce_name:
                continue
            pces.append(frappe.get_doc("POS Closing Entry", pce_name))
        return pces

    @staticmethod
    def _resolve_company(eds, pces: List) -> Optional[str]:
        """Prefer Branch.company on the Daily Summary; fall back to first PCE.

        POS Daily Summary stores `branch` (not `company` directly), so we look
        the company up via Branch. If that lookup is unavailable (test fixtures,
        legacy data), we fall through to the first PCE's company.
        """
        branch = getattr(eds, "branch", None)
        if branch:
            company = frappe.db.get_value("Branch", branch, "company")
            if company:
                return company
        for pce in pces:
            company = getattr(pce, "company", None)
            if company:
                return company
        return None

    def _collect_invoice_names(self, pces: List) -> List[str]:
        """Fan out aggregator.extract_invoice_names across all PCEs, dedupe."""
        combined: List[str] = []
        for pce in pces:
            combined.extend(self.aggregator.extract_invoice_names(pce))
        return list(dict.fromkeys(combined))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_rm_rows(
        self, bom_no: Optional[str], fg_qty: float,
        company: Optional[str], warehouse: Optional[str],
    ) -> List[Dict]:
        if not bom_no:
            return []

        rm_flat = self.bom.explode_bom_flat(bom_no, fg_qty, company)
        rows: List[Dict] = []
        for rm in rm_flat:
            row = dict(rm)
            rm_code = row.get("item_code")
            is_batched = self.batch.is_item_batched(rm_code) if rm_code else False
            row["is_batched"] = is_batched
            row["actual_qty"] = self._on_hand(rm_code, warehouse)

            if is_batched and warehouse:
                plan = self.batch.allocate_fifo(rm_code, warehouse, flt(row.get("qty")))
                row["batch_allocations"] = plan.get("allocations", [])
                row["batch_partial"] = plan.get("partial", False)
                row["batch_shortage_qty"] = flt(plan.get("shortage_qty", 0))
            else:
                row["batch_allocations"] = []
                row["batch_partial"] = False
                row["batch_shortage_qty"] = 0.0

            rows.append(row)
        return rows

    @staticmethod
    def _on_hand(item_code: Optional[str], warehouse: Optional[str]) -> float:
        if not item_code or not warehouse:
            return 0.0
        return flt(frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty",
        ) or 0)

    def _enrich_tree_actual_qty(self, nodes: List[Dict], warehouse: str) -> None:
        """Walk rm_tree in place and attach Bin actual_qty per node.

        Matches the legacy get_pos_breakdown output shape so the existing
        UI grid keeps rendering the on-hand column for every tree node.
        """
        for node in nodes:
            node["actual_qty"] = self._on_hand(node.get("item_code"), warehouse)
            children = node.get("children") or []
            if children:
                self._enrich_tree_actual_qty(children, warehouse)
