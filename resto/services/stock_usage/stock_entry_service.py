"""StockEntryService — convert a submitted POS Consumption into a
Stock Entry (Material Issue).

Fixes Phase 1 audit Bug #5: legacy SE-creation path forgot to copy
`batch_no` onto the SE child rows, so Stock Ledger Entry posted with
NULL batch_no on batched items — silently corrupting per-batch balance.

This service inserts the SE as a Draft. The caller (UI or workflow)
decides whether to submit. Opt-in per consumption matches the
architecture decision recorded in the refactor plan.
"""

from typing import Dict

import frappe
from frappe.utils import flt


class StockEntryService:
    """Build Stock Entry from a submitted POS Consumption."""

    POS_CONSUMPTION_DOCTYPE = "POS Consumption"
    STOCK_ENTRY_DOCTYPE = "Stock Entry"

    def create_material_issue(self, pcn_name: str) -> str:
        """Create a Draft Stock Entry (Material Issue) from a submitted
        POS Consumption. Returns the SE name.

        Source warehouse comes from the POS Consumption header so all
        RM rows issue from the same location (typical kitchen flow).
        """
        pcn = frappe.get_doc(self.POS_CONSUMPTION_DOCTYPE, pcn_name)

        if getattr(pcn, "docstatus", 0) != 1:
            frappe.throw(
                f"POS Consumption {pcn_name} must be Submitted before "
                "creating a Stock Entry"
            )

        se = frappe.new_doc(self.STOCK_ENTRY_DOCTYPE)
        se.stock_entry_type = "Material Issue"
        se.company = getattr(pcn, "company", None)
        se.remarks = f"Auto-created from POS Consumption {pcn_name}"

        source_warehouse = getattr(pcn, "warehouse", None)
        posting_date = getattr(pcn, "posting_date", None)
        if posting_date:
            se.posting_date = posting_date

        for rm in (getattr(pcn, "rm_breakdown", None) or []):
            se.append("items", self._build_se_item_row(rm, source_warehouse))

        se.insert()
        return se.name

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_se_item_row(rm, source_warehouse) -> Dict:
        uom = getattr(rm, "uom", None)
        row: Dict = {
            "item_code": getattr(rm, "rm_item", None),
            "qty": flt(getattr(rm, "final_qty", 0)),
            "uom": uom,
            "stock_uom": uom,
            "conversion_factor": 1,
            "s_warehouse": source_warehouse,
        }
        if getattr(rm, "is_batched", 0):
            row["batch_no"] = getattr(rm, "batch_no", None)
        return row
