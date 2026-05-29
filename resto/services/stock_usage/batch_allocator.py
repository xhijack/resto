"""BatchAllocatorService — FIFO batch allocation backed by Stock Ledger Entry.

Fixes Phase 1 audit Bug #1: legacy Bin lookup is NOT batch-aware. Bin only
reports per-(item, warehouse) qty; it cannot distinguish individual batches.
For batched items (Item.has_batch_no=1) we must aggregate per-batch from the
Stock Ledger Entry table (the actual source of truth for batch-level qty).

Strategy: oldest creation first (FIFO), skip expired batches, skip zero/negative
balances. Returns full allocation plan + partial flag when stock insufficient.
"""

from typing import Dict, List

import frappe
from frappe.utils import flt, getdate


class BatchAllocatorService:
    """Allocate a required qty across available batches FIFO."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_item_batched(self, item_code: str) -> bool:
        """True if Item has batch tracking enabled."""
        if not item_code:
            return False
        return bool(frappe.db.get_value("Item", item_code, "has_batch_no"))

    def get_available_batches(self, item_code: str, warehouse: str) -> List[Dict]:
        """Return active batches for (item, warehouse), oldest first, expired removed.

        Each entry: {batch_no, available_qty, expiry_date, creation}.
        available_qty is computed from Stock Ledger Entry, not Bin (Bug #1 fix).
        """
        if not item_code or not warehouse:
            return []

        batches = frappe.get_all(
            "Batch",
            filters={"item": item_code, "disabled": 0},
            fields=["name as batch_no", "creation", "expiry_date"],
            order_by="creation asc",
        )
        if not batches:
            return []

        batches_sorted = sorted(batches, key=lambda b: str(b.get("creation") or ""))
        batch_names = [b["batch_no"] for b in batches_sorted]
        sle_qty = self._batch_qty_from_sle(item_code, warehouse, batch_names)

        today = getdate(frappe.utils.nowdate())
        result: List[Dict] = []
        for b in batches_sorted:
            qty = flt(sle_qty.get(b["batch_no"], 0))
            if qty <= 0:
                continue

            expiry = b.get("expiry_date")
            if expiry and getdate(expiry) < today:
                continue

            result.append({
                "batch_no": b["batch_no"],
                "available_qty": qty,
                "expiry_date": expiry,
                "creation": b.get("creation"),
            })
        return result

    def allocate_fifo(self, item_code: str, warehouse: str, required_qty: float) -> Dict:
        """Walk batches FIFO until required_qty satisfied.

        Returns:
            allocations: [{batch_no, allocated_qty, expiry_date}, ...]
            partial: True when total available < required
            shortage_qty: 0 when full allocation, else remaining unmet qty
        """
        required = flt(required_qty)
        batches = self.get_available_batches(item_code, warehouse)

        allocations: List[Dict] = []
        remaining = required
        for b in batches:
            if remaining <= 0:
                break
            avail = flt(b.get("available_qty"))
            take = min(avail, remaining)
            if take <= 0:
                continue
            allocations.append({
                "batch_no": b["batch_no"],
                "allocated_qty": take,
                "expiry_date": b.get("expiry_date"),
            })
            remaining -= take

        partial = remaining > 0
        return {
            "allocations": allocations,
            "partial": partial,
            "shortage_qty": flt(remaining) if partial else 0.0,
        }

    def validate_allocation(
        self, item_code: str, warehouse: str,
        batch_no: str, required_qty: float,
    ) -> Dict:
        """Check whether a specific batch can fulfill required_qty.

        Used at POS Consumption submit-time to guard against over-allocation
        when the user picked a batch manually.
        """
        required = flt(required_qty)
        if not batch_no:
            return {
                "valid": False,
                "shortage_qty": required,
                "message": f"Batch is required for {item_code}",
            }

        target = next(
            (b for b in self.get_available_batches(item_code, warehouse)
             if b["batch_no"] == batch_no),
            None,
        )
        if not target:
            return {
                "valid": False,
                "shortage_qty": required,
                "message": f"Batch {batch_no} not available for {item_code} in {warehouse}",
            }

        avail = flt(target.get("available_qty"))
        if avail >= required:
            return {"valid": True, "shortage_qty": 0.0, "message": ""}

        return {
            "valid": False,
            "shortage_qty": required - avail,
            "message": f"Batch {batch_no} has only {avail} {item_code} (need {required})",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _batch_qty_from_sle(
        item_code: str, warehouse: str, batch_names: List[str]
    ) -> Dict[str, float]:
        """SUM(actual_qty) grouped by batch_no from Stock Ledger Entry.

        Bin is per-(item, warehouse), so it would conflate batch quantities.
        SLE is the only place that tracks per-batch movement.
        """
        if not batch_names:
            return {}

        placeholders = ", ".join(["%s"] * len(batch_names))
        rows = frappe.db.sql(
            f"""
            SELECT batch_no, SUM(actual_qty) AS qty
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s
              AND warehouse = %s
              AND batch_no IN ({placeholders})
              AND is_cancelled = 0
            GROUP BY batch_no
            """,
            [item_code, warehouse, *batch_names],
        ) or []
        return {row[0]: flt(row[1]) for row in rows}
