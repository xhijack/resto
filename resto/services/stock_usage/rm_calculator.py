"""RawMaterialCalculatorService — orchestrator.

Replaces the inline pipeline inside legacy `get_pos_breakdown`:
extract invoices → aggregate by sold item → resolve FG/BOM → explode RM →
allocate batches (for batched RMs) → enrich with on-hand qty.

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

    def compute_breakdown(self, pce_name: str, warehouse: Optional[str] = None) -> Dict:
        """Return {"items": [...]} — one FG row per aggregated sold item.

        Each FG row carries `rm_items` (flat RM list) and `rm_tree` (hierarchical
        view). Batched RMs include `is_batched`, `batch_allocations`,
        `batch_partial`, and `batch_shortage_qty`.
        """
        if not pce_name:
            return {"items": []}

        pce = frappe.get_doc("POS Closing Entry", pce_name)
        company = getattr(pce, "company", None)

        inv_names = self.aggregator.extract_invoice_names(pce)
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
