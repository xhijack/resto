"""PosConsumptionService — Draft + Submit workflow for POS Consumption.

Fixes Phase 1 audit Bug #6: legacy code called `doc.submit()` directly
without `doc.save()` first. That bypasses validate_save lifecycle hooks
and produces inconsistent state when validation fails after a partial
write. The new flow is explicit: create Draft → user reviews → Submit.
"""

from typing import Dict

import frappe
from frappe.utils import flt

from resto.services.stock_usage.batch_allocator import BatchAllocatorService


def _get_item_unit_cost(item_code: str) -> float:
    """Snapshot rate priority: valuation → last_purchase → standard."""
    if not item_code:
        return 0.0
    vals = frappe.db.get_value(
        "Item", item_code,
        ["valuation_rate", "last_purchase_rate", "standard_rate"],
        as_dict=True,
    ) or {}
    return flt(
        vals.get("valuation_rate")
        or vals.get("last_purchase_rate")
        or vals.get("standard_rate")
        or 0
    )


class PosConsumptionService:
    """Lifecycle ownership for POS Consumption docs."""

    DOCTYPE = "POS Consumption"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_draft(self, payload: Dict) -> str:
        """Insert as Draft (docstatus=0). NEVER submit here.

        Snapshots valuation_rate per RM at draft time so cost reporting
        stays stable even when Item.valuation_rate updates later.
        """
        doc = frappe.new_doc(self.DOCTYPE)
        doc.pos_daily_summary = payload.get("pos_daily_summary")
        doc.company = payload.get("company")
        doc.warehouse = payload.get("warehouse")
        if payload.get("posting_date"):
            doc.posting_date = payload.get("posting_date")
        if payload.get("remarks"):
            doc.remarks = payload.get("remarks")

        for menu in (payload.get("menu_summaries") or []):
            doc.append("menu_summaries", dict(menu))

        for rm in (payload.get("rm_breakdown") or []):
            row = dict(rm)
            if not row.get("valuation_rate_snapshot"):
                row["valuation_rate_snapshot"] = _get_item_unit_cost(row.get("rm_item"))
            doc.append("rm_breakdown", row)

        doc.insert()
        return doc.name

    def submit_consumption(self, name: str) -> None:
        """Validate batch availability, then submit. Only Draft → Submitted.

        Re-submitting an already-submitted doc is rejected (the user should
        amend or create a new doc — submitted state is the audit trail).
        """
        doc = frappe.get_doc(self.DOCTYPE, name)
        if getattr(doc, "docstatus", 0) != 0:
            frappe.throw(
                f"POS Consumption {name} is not a Draft and cannot be re-submitted"
            )

        batch_service = BatchAllocatorService()
        warehouse = getattr(doc, "warehouse", None)

        for rm in (getattr(doc, "rm_breakdown", None) or []):
            if not getattr(rm, "is_batched", 0):
                continue

            result = batch_service.validate_allocation(
                getattr(rm, "rm_item", None),
                warehouse,
                getattr(rm, "batch_no", None),
                flt(getattr(rm, "final_qty", 0)),
            )
            if not result.get("valid"):
                frappe.throw(
                    result.get("message")
                    or f"Batch insufficient for {getattr(rm, 'rm_item', '')}"
                )

        doc.submit()
