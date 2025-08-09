from typing import List, Dict, Union, Optional, Tuple
import frappe
from frappe.utils import flt, getdate, nowdate
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict

# ---------- Helpers ----------

def _get_item_default_bom(item_code: str, company: str) -> Optional[str]:
    bom = frappe.db.get_value(
        "BOM",
        {"item": item_code, "is_default": 1, "is_active": 1, "company": company},
        "name",
    )
    if not bom:
        bom = frappe.db.get_value(
            "BOM",
            {"item": item_code, "is_active": 1, "company": company},
            "name",
            order_by="modified desc",
        )
    return bom

def _get_item_unit_cost(item_code: str) -> float:
    """Unit Cost preference: valuation_rate → last_purchase_rate → standard_rate."""
    if not item_code:
        return 0.0
    vals = frappe.db.get_value(
        "Item",
        item_code,
        ["valuation_rate", "last_purchase_rate", "standard_rate"],
        as_dict=True,
    ) or {}
    return flt(vals.get("valuation_rate") or vals.get("last_purchase_rate") or vals.get("standard_rate") or 0)

def _get_item_selling_rate(item_code: str, price_list: Optional[str]) -> float:
    """Ambil selling rate dari Item Price (Selling) jika ada."""
    if not item_code:
        return 0.0
    filters = {"item_code": item_code, "selling": 1}
    if price_list:
        filters["price_list"] = price_list
    price = frappe.db.get_value("Item Price", filters, "price_list_rate")
    if price is None and price_list:
        price = frappe.db.get_value("Item Price", {"item_code": item_code, "selling": 1}, "price_list_rate")
    return flt(price or 0)

def _norm(v) -> str:
    """Normalize any scalar-ish input to clean string."""
    if v is None:
        return ""
    if isinstance(v, (int, float)):
        return frappe.as_unicode(v).strip()
    if isinstance(v, str):
        return frappe.as_unicode(v).strip()
    if isinstance(v, dict):
        for k in ("value", "name", "item_code", "warehouse", "label", "content", "html"):
            if k in v and isinstance(v[k], (str, int, float)):
                return frappe.as_unicode(v[k]).strip()
    return frappe.as_unicode(v).strip()

# ---------- BOM Tree Builder ----------

def _build_bom_tree(bom_no: str, fg_qty: float) -> List[Dict]:
    """
    Build tree dari BOM secara rekursif.
    - fg_qty: kuantitas FG di SO; akan men-scale qty komponen mengikuti BOM.quantity.
    Return: list node: [{item_code, item_name, stock_uom, qty, unit_cost, cost, children:[...]}]
    """
    if not bom_no or not fg_qty:
        return []

    doc = frappe.get_doc("BOM", bom_no)
    base_qty = flt(doc.quantity) or 1.0
    scale = flt(fg_qty) / base_qty

    nodes: List[Dict] = []
    for bi in doc.items:
        code = bi.item_code
        if not code:
            continue
        uom = bi.uom or bi.get("stock_uom")
        req_qty = flt(bi.qty) * scale
        unit_cost = _get_item_unit_cost(code)
        children = _build_bom_tree(bi.bom_no, req_qty) if getattr(bi, "bom_no", None) else []
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

# ---------- Public API ----------

@frappe.whitelist()
def get_so_breakdown(sales_order: str, company: str) -> Dict[str, List[Dict]]:
    so = frappe.get_doc("Sales Order", sales_order)
    selling_price_list = getattr(so, "selling_price_list", None)

    out_items: List[Dict] = []

    for it in so.items:
        bom_no = it.get("bom_no") or it.get("bom") or _get_item_default_bom(it.item_code, company)
        selling_rate = flt(it.get("rate")) or _get_item_selling_rate(it.item_code, selling_price_list)
        selling_amount = selling_rate * flt(it.get("qty") or 0)

        # Flat list (untuk grid)
        rm_list: List[Dict] = []
        if bom_no and it.qty:
            bom_items = get_bom_items_as_dict(
                bom=bom_no, company=company, qty=flt(it.qty), fetch_exploded=1
            )
            for bi in bom_items.values():
                code = bi.get("item_code")
                if not code:
                    continue
                uom = bi.get("stock_uom") or bi.get("uom")
                req = flt(bi.get("qty") or 0)
                unit_cost = _get_item_unit_cost(code)
                rm_list.append({
                    "item_code": code,
                    "item_name": bi.get("item_name"),
                    "stock_uom": uom,
                    "required_qty": req,
                    "unit_cost": unit_cost,
                    "cost": unit_cost * req,
                })

        # Tree (untuk tampilan hierarchical)
        rm_tree: List[Dict] = _build_bom_tree(bom_no, flt(it.qty)) if (bom_no and it.qty) else []

        out_items.append({
            "so_item_name": it.name,
            "item_code": it.item_code,
            "item_name": it.item_name,
            "qty": flt(it.qty),
            "stock_uom": it.stock_uom,
            "bom_no": bom_no,
            "selling_rate": selling_rate,
            "selling_amount": selling_amount,
            "rm_items": rm_list,
            "rm_tree": rm_tree,
        })

    return {"items": out_items}

@frappe.whitelist()
def get_available_qty(item_code: str, warehouse: str) -> float:
    """Qty tersedia saat ini di gudang (read-only; tidak bikin Bin baru)."""
    if not item_code or not warehouse:
        return 0.0
    qty = frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")
    return flt(qty or 0)

@frappe.whitelist()
def get_availability_bulk(rows: Union[List[Dict], str]) -> Dict[str, float]:
    """
    Input list of dicts: [{item_code: 'ITM-001', warehouse: 'Stores - M'}, ...]
    Kembalikan peta: {'ITM-001::Stores - M': 12.0, ...}
    """
    pairs: List[Tuple[str, str]] = []

    if isinstance(rows, str):
        try:
            rows = frappe.parse_json(rows)
        except Exception:
            rows = []

    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict):
                ic = _norm(r.get("item_code"))
                wh = _norm(r.get("warehouse"))
                if ic and wh:
                    pairs.append((ic, wh))
            elif isinstance(r, (list, tuple)):
                ic = _norm(r[0]) if len(r) >= 1 else ""
                wh = _norm(r[1]) if len(r) >= 2 else (_norm(r[5]) if len(r) >= 6 else "")
                if ic and wh:
                    pairs.append((ic, wh))

    pairs = list({(ic, wh) for (ic, wh) in pairs})

    out: Dict[str, float] = {}
    if not pairs:
        return out

    items = list({p[0] for p in pairs})
    whs   = list({p[1] for p in pairs})
    if not items or not whs:
        return out

    bins = frappe.get_all(
        "Bin",
        filters={"item_code": ["in", items], "warehouse": ["in", whs]},
        fields=["item_code", "warehouse", "actual_qty"],
    )
    for b in bins:
        out[f"{b.item_code}::{b.warehouse}"] = flt(b.actual_qty or 0)

    for it, wh in pairs:
        out.setdefault(f"{it}::{wh}", 0.0)

    return out

@frappe.whitelist()
def get_unit_cost(item_code: str) -> float:
    """Expose unit cost untuk 1 item (dipanggil saat user ganti item di grid)."""
    return _get_item_unit_cost(item_code)

@frappe.whitelist()
def get_unit_cost_bulk(item_codes: Union[List[str], str]) -> Dict[str, float]:
    """Bulk unit cost untuk banyak item_code: { item_code: unit_cost }"""
    if isinstance(item_codes, str):
        try:
            item_codes = frappe.parse_json(item_codes)
        except Exception:
            item_codes = []
    out: Dict[str, float] = {}
    unique = list({c for c in (item_codes or []) if c})
    if not unique:
        return out
    rows = frappe.get_all("Item", filters={"name": ["in", unique]},
                          fields=["name", "valuation_rate", "last_purchase_rate", "standard_rate"])
    for r in rows:
        out[r["name"]] = flt(r.get("valuation_rate") or r.get("last_purchase_rate") or r.get("standard_rate") or 0)
    return out

@frappe.whitelist()
def create_stock_entry_from_usage(
    sales_order: str,
    company: str,
    posting_date: Optional[str] = None,
    stock_entry_type: str = "Material Issue",
    source_warehouse: Optional[str] = None,
    target_warehouse: Optional[str] = None,
    remarks: Optional[str] = None,
    items: Union[List[Dict], str, None] = None,
) -> str:
    """
    Buat & submit Stock Entry dari payload RM yang sudah diedit user.
    items: [{ item_code, qty, stock_uom, warehouse, remarks, ... }]
    """
    if isinstance(items, str):
        try:
            items = frappe.parse_json(items)
        except Exception:
            items = []

    if not items:
        frappe.throw("No items to create Stock Entry.")
    if not source_warehouse:
        frappe.throw("Source Warehouse is required.")

    posting_date = posting_date or nowdate()

    se = frappe.new_doc("Stock Entry")
    se.company = company
    se.stock_entry_type = stock_entry_type
    se.posting_date = getdate(posting_date)
    se.set_posting_time = 1
    se.remarks = (remarks or "") + f"\nGenerated from Stock Usage Tool for SO {sales_order}"

    for row in items:
        qty = flt(row.get("qty"))
        if qty <= 0:
            continue

        s_wh = row.get("warehouse") or source_warehouse
        t_wh = None
        if stock_entry_type in ("Material Transfer", "Material Receipt"):
            t_wh = target_warehouse

        se.append("items", {
            "item_code": row.get("item_code"),
            "qty": qty,
            "uom": row.get("stock_uom"),
            "stock_uom": row.get("stock_uom"),
            "conversion_factor": 1,
            "s_warehouse": s_wh if stock_entry_type in ("Material Issue", "Material Transfer") else None,
            "t_warehouse": t_wh if stock_entry_type in ("Material Transfer", "Material Receipt") else None,
            "allow_zero_valuation_rate": 1,
            "sales_order": sales_order,
            "description": row.get("remarks") or row.get("item_name") or "",
        })

    if not se.items:
        frappe.throw("No valid items after validation.")

    se.insert()
    se.submit()
    return se.name