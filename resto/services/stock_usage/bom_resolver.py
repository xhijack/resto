"""BomResolverService — resolve FG item + BOM tree dari sold item.

Replaces legacy helpers di stock_usage_tool.py:
- _resolve_fg_and_bom_for_sale
- _get_item_default_bom
- _build_bom_tree
- _get_item_unit_cost (sebagian)

Major improvements over legacy:
- Per-instance BOM tree cache → no N+1 saat multi-call (Phase 1 audit)
- Returns dict (bukan tuple) untuk extensibility
- Type-hinted untuk readability
"""

from typing import Dict, List, Optional

import frappe
from frappe.utils import flt
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict


class BomResolverService:
    """Resolve FG + BOM dari sold item. Pakai cache untuk avoid redundant BOM fetches."""

    def __init__(self):
        # Per-instance cache: {bom_no: (bom_doc, base_quantity)}
        # Reset setiap request lifecycle — safe untuk multi-request server
        self._bom_doc_cache: Dict[str, tuple] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve_fg(self, sold_item_code: str, company: str) -> Dict:
        """Resolve FG item code + name + uom + bom dari sold item.

        Priority:
        1. Resto Menu mapping (recipe_item + default_bom)
        2. Fallback: sold_item as FG + default BOM via Item

        Returns dict: {item_code, item_name, stock_uom, bom_no}
        bom_no bisa None kalau tidak ditemukan dimanapun.
        """
        menu = self._get_menu_by_sell_item(sold_item_code)

        if menu and menu.get("recipe_item"):
            fg_code = menu["recipe_item"]
            fg_name, fg_uom = self._get_item_name_uom(fg_code)
            bom_no = menu.get("default_bom") or self._get_item_default_bom(fg_code, company)
            return {
                "item_code": fg_code,
                "item_name": fg_name or fg_code,
                "stock_uom": fg_uom,
                "bom_no": bom_no,
            }

        # Fallback path
        fg_code = sold_item_code
        fg_name, fg_uom = self._get_item_name_uom(fg_code)
        bom_no = self._get_item_default_bom(fg_code, company)
        return {
            "item_code": fg_code,
            "item_name": fg_name or fg_code,
            "stock_uom": fg_uom,
            "bom_no": bom_no,
        }

    def explode_bom_flat(self, bom_no: str, qty: float, company: str) -> List[Dict]:
        """Explode BOM → flat list of RM dengan quantities scaled to fg_qty.

        Pakai ERPNext native get_bom_items_as_dict (sudah handle multi-level explode).
        Plus enrich with unit_cost dari Item valuation_rate priority.
        """
        if not bom_no or not qty:
            return []

        bom_items = get_bom_items_as_dict(
            bom=bom_no, company=company, qty=flt(qty), fetch_exploded=1,
        )

        rm_list: List[Dict] = []
        for bi in bom_items.values():
            code = bi.get("item_code") if isinstance(bi, dict) else getattr(bi, "item_code", None)
            if not code:
                continue
            item_name = bi.get("item_name") if isinstance(bi, dict) else getattr(bi, "item_name", None)
            stock_uom = (
                bi.get("stock_uom") or bi.get("uom") if isinstance(bi, dict)
                else (getattr(bi, "stock_uom", None) or getattr(bi, "uom", None))
            )
            req_qty = flt(bi.get("qty") if isinstance(bi, dict) else getattr(bi, "qty", 0))
            unit_cost = self._get_item_unit_cost(code)
            rm_list.append({
                "item_code": code,
                "item_name": item_name,
                "stock_uom": stock_uom,
                "qty": req_qty,
                "required_qty": req_qty,
                "unit_cost": unit_cost,
                "cost": unit_cost * req_qty,
            })
        return rm_list

    def build_tree(self, bom_no: str, fg_qty: float) -> List[Dict]:
        """Build BOM tree recursively. Cache BOM docs to fix N+1.

        Returns list of node dicts: {item_code, item_name, stock_uom, qty,
        unit_cost, cost, children: [...]}
        """
        if not bom_no or not fg_qty:
            return []

        doc, base_qty = self._get_bom_doc_cached(bom_no)
        scale = flt(fg_qty) / (base_qty or 1.0)

        nodes: List[Dict] = []
        for bi in doc.items:
            code = bi.item_code
            if not code:
                continue
            uom = getattr(bi, "uom", None) or getattr(bi, "stock_uom", None)
            req_qty = flt(bi.qty) * scale
            unit_cost = self._get_item_unit_cost(code)
            children = (
                self.build_tree(bi.bom_no, req_qty)
                if getattr(bi, "bom_no", None) else []
            )
            nodes.append({
                "item_code": code,
                "item_name": bi.item_name,
                "stock_uom": uom,
                "qty": req_qty,
                "unit_cost": unit_cost,
                "cost": unit_cost * req_qty,
                "children": children,
            })
        return nodes

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_bom_doc_cached(self, bom_no: str) -> tuple:
        """Cache BOM doc + base_quantity per-instance. Fixes N+1 di legacy
        _build_bom_tree yang call get_doc per recursion level."""
        if bom_no not in self._bom_doc_cache:
            doc = frappe.get_doc("BOM", bom_no)
            base_qty = flt(doc.quantity) or 1.0
            self._bom_doc_cache[bom_no] = (doc, base_qty)
        return self._bom_doc_cache[bom_no]

    @staticmethod
    def _get_item_name_uom(item_code: str) -> tuple:
        if not item_code:
            return ("", "")
        row = frappe.db.get_value(
            "Item", item_code, ["item_name", "stock_uom"], as_dict=True,
        ) or {}
        return (row.get("item_name") or "", row.get("stock_uom") or "")

    @staticmethod
    def _get_menu_by_sell_item(sell_item_code: str) -> Optional[Dict]:
        """Return Resto Menu dict (or None) untuk sell_item. Filter active=1 kalau field ada."""
        if not sell_item_code:
            return None
        filters = {"sell_item": sell_item_code}
        try:
            meta = frappe.get_meta("Resto Menu")
            if getattr(meta, "fields", None):
                if any(getattr(df, "fieldname", None) == "active" for df in meta.fields):
                    filters["active"] = 1
        except Exception:
            pass

        menu_name = frappe.db.get_value("Resto Menu", filters, "name")
        if not menu_name:
            return None
        return frappe.db.get_value(
            "Resto Menu",
            menu_name,
            ["name", "sell_item", "recipe_item", "default_bom", "menu_category"],
            as_dict=True,
        )

    def _get_item_default_bom(self, item_code: str, company: str) -> Optional[str]:
        """Resolve default BOM untuk item. Priority:
        1) Resto Menu (recipe_item -> default_bom)
        2) Item is_default BOM untuk company
        3) Latest active BOM untuk item+company
        """
        if not item_code:
            return None

        # 1) Resto Menu mapping
        rm_filters = {"recipe_item": item_code}
        try:
            meta = frappe.get_meta("Resto Menu")
            if getattr(meta, "fields", None):
                if any(getattr(df, "fieldname", None) == "active" for df in meta.fields):
                    rm_filters["active"] = 1
        except Exception:
            pass
        rm_bom = frappe.db.get_value("Resto Menu", rm_filters, "default_bom")
        if rm_bom:
            return rm_bom

        # 2) Default active BOM
        bom = frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_default": 1, "is_active": 1, "company": company},
            "name",
        )
        if bom:
            return bom

        # 3) Latest active BOM
        return frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_active": 1, "company": company},
            "name",
            order_by="modified desc",
        )

    @staticmethod
    def _get_item_unit_cost(item_code: str) -> float:
        """Unit cost priority: valuation_rate → last_purchase_rate → standard_rate."""
        if not item_code:
            return 0.0
        vals = frappe.db.get_value(
            "Item",
            item_code,
            ["valuation_rate", "last_purchase_rate", "standard_rate"],
            as_dict=True,
        ) or {}
        return flt(
            vals.get("valuation_rate")
            or vals.get("last_purchase_rate")
            or vals.get("standard_rate")
            or 0
        )
