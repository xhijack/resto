from typing import List, Dict, Union, Optional, Tuple
import frappe
from frappe.utils import flt, getdate, nowdate
from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict
import json
# ---------- Helpers ----------


# ---------- Resto Menu Mapping Helpers ----------

def _get_item_name_uom(item_code: str) -> Tuple[str, str]:
    """Get Item.item_name and stock_uom for convenience."""
    if not item_code:
        return ("", "")
    row = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom"], as_dict=True) or {}
    return (row.get("item_name") or "", row.get("stock_uom") or "")


def _get_menu_by_sell_item(sell_item_code: str) -> Optional[Dict]:
    """Return Resto Menu doc (as dict) matched by sell_item. If field `active` exists, require active=1."""
    if not sell_item_code:
        return None
    # Build filters dynamically based on schema
    filters = {"sell_item": sell_item_code}
    try:
        meta = frappe.get_meta("Resto Menu")
        if getattr(meta, "fields", None):
            if any(df.fieldname == "active" for df in meta.fields):
                filters["active"] = 1
    except Exception:
        pass

    menu_name = frappe.db.get_value("Resto Menu", filters, "name")
    if not menu_name:
        return None
    return frappe.db.get_value(
        "Resto Menu",
        menu_name,
        [
            "name",
            "sell_item",
            "recipe_item",
            "default_bom",
            "menu_category"
        ],
        as_dict=True,
    )


def _resolve_fg_and_bom_for_sale(sold_item_code: str, company: str) -> Tuple[str, str, str, Optional[str]]:
    """
    From a *sold* item (usually non-stock sell_item), resolve the *FG* item used for
    consumption posting and its BOM.
    Returns: (fg_item_code, fg_item_name, fg_uom, bom_no)
    - Prefer Resto Menu mapping (recipe_item + default_bom)
    - Fallback to using sold item itself and `_get_item_default_bom`.
    """
    menu = _get_menu_by_sell_item(sold_item_code)
    if menu and menu.get("recipe_item"):
        fg_code = menu["recipe_item"]
        fg_name, fg_uom = _get_item_name_uom(fg_code)
        bom_no = menu.get("default_bom") or _get_item_default_bom(fg_code, company)
        return fg_code, (fg_name or menu.get("menu_name") or fg_code), fg_uom, bom_no

    # Fallback: use sold item as FG
    fg_code = sold_item_code
    fg_name, fg_uom = _get_item_name_uom(fg_code)
    bom_no = _get_item_default_bom(fg_code, company)
    return fg_code, fg_name, fg_uom, bom_no


def _get_item_default_bom(item_code: str, company: str) -> Optional[str]:
    """
    Resolve default BOM for an item with these priorities:
    1) If there is an active Resto Menu where this item is the `recipe_item`, use its `default_bom`.
    2) Item's default BOM for the given company (is_default=1 & is_active=1)
    3) Latest active BOM for the item in the company
    """
    if not item_code:
        return None

    # 1) Resto Menu mapping (recipe_item -> default_bom)
    rm_filters = {"recipe_item": item_code}
    try:
        meta = frappe.get_meta("Resto Menu")
        if getattr(meta, "fields", None):
            if any(df.fieldname == "active" for df in meta.fields):
                rm_filters["active"] = 1
    except Exception:
        pass
    rm_bom = frappe.db.get_value("Resto Menu", rm_filters, "default_bom")
    if rm_bom:
        return rm_bom

    # 2) Item's default BOM
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

# ---------- POS Closing Entry Helpers ----------

def _extract_pos_invoices_from_pce(pce_doc) -> List[str]:
    """
    Try to extract Sales Invoice / POS Invoice names from a POS Closing Entry document.
    Compatible with multiple ERPNext versions/child-table schemas.
    Returns a list of invoice names.
    """
    invs: List[str] = []
    if not pce_doc:
        return invs

    # 1) Look through child tables for likely link fields
    try:
        for tf in (pce_doc.meta.get_table_fields() or []):
            for ch in (pce_doc.get(tf.fieldname) or []):
                for key in ("sales_invoice", "invoice", "pos_invoice", "si_name", "name"):
                    val = ch.get(key)
                    if isinstance(val, str) and val:
                        invs.append(val)
    except Exception:
        pass

    invs = [x for x in invs if isinstance(x, str) and x]

    # 2) Keep only those that exist as Sales Invoice or POS Invoice
    filtered: List[str] = []
    for x in invs:
        if frappe.db.exists("Sales Invoice", x) or frappe.db.exists("POS Invoice", x):
            filtered.append(x)

    # 3) If nothing found, fallback by date range and flags
    if not filtered:
        try:
            start = getattr(pce_doc, "period_start_date", None) or getattr(pce_doc, "start_date", None)
            end   = getattr(pce_doc, "period_end_date", None) or getattr(pce_doc, "end_date", None)
            pos_profile = getattr(pce_doc, "pos_profile", None)
            filters = {"docstatus": 1, "is_pos": 1}
            if start and end:
                filters["posting_date"] = ["between", [getdate(start), getdate(end)]]
            if pos_profile:
                filters["pos_profile"] = pos_profile
            if getattr(pce_doc, "company", None):
                filters["company"] = pce_doc.company
            # Sales Invoices covering POS
            filtered = [r.name for r in frappe.get_all("Sales Invoice", filters=filters, pluck="name")]
        except Exception:
            pass

    return list(dict.fromkeys(filtered))  # de-dup while keeping order

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
        # Resolve FG & BOM using Resto Menu mapping if applicable
        fg_code, fg_name, fg_uom, bom_no = _resolve_fg_and_bom_for_sale(it.item_code, company)

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
            "item_code": fg_code,
            "item_name": fg_name or it.item_name,
            "qty": flt(it.qty),
            "stock_uom": fg_uom or it.stock_uom,
            "bom_no": bom_no,
            "selling_rate": selling_rate,
            "selling_amount": selling_amount,
            "rm_items": rm_list,
            "rm_tree": rm_tree,
        })

    return {"items": out_items}


# ---------- POS Closing Entry Public API ----------

@frappe.whitelist()
def get_pos_breakdown(pos_closing_entry: str, company: str, warehouse: str = None) -> Dict[str, List[Dict]]:
    """
    Build aggregated FG list from all POS invoices within a POS Closing Entry, then derive
    RM breakdown from the default/selected BOM per FG item.
    Returns a shape compatible with the frontend: 
    { items: [ 
        { item_code, item_name, qty, stock_uom, bom_no, selling_rate, selling_amount, 
          rm_items: [...], rm_tree: [...], actual_qty } 
      ] }
    """
    if not pos_closing_entry:
        frappe.throw("POS Closing Entry is required")

    pce = frappe.get_doc("POS Closing Entry", pos_closing_entry)

    # 1) Collect invoice names (Sales Invoice or POS Invoice)
    inv_names = _extract_pos_invoices_from_pce(pce)
    if not inv_names:
        return {"items": []}

    # 2) Aggregate by item_code across all invoices
    agg: Dict[str, Dict] = {}

    def _add_row(code: str, name: str, uom: str, qty: float, amount: float, resto_menu: str, category: str):
        if not code:
            return
        row = agg.setdefault(code, {
            "item_code": code,
            "item_name": name,
            "resto_menu": resto_menu,
            "category": category,
            "stock_uom": uom,
            "qty": 0.0,
            "selling_amount": 0.0,
            "bom_no": None,
        })
        row["qty"] += flt(qty)
        row["selling_amount"] += flt(amount)
        if not row.get("item_name") and name:
            row["item_name"] = name
        if not row.get("resto_menu") and resto_menu:
            row["resto_menu"] = resto_menu
        if not row.get("stock_uom") and uom:
            row["stock_uom"] = uom
        if not row.get("category") and category:
            row["category"] = category

    # Prefer Sales Invoice (modern POS), fallback to POS Invoice
    for inv in inv_names:
        if frappe.db.exists("Sales Invoice", inv):
            si = frappe.get_doc("Sales Invoice", inv)
            for it in (si.items or []):
                fg_code, fg_name, fg_uom, bom_no = _resolve_fg_and_bom_for_sale(it.item_code, pce.company or company)
                resto_menu = getattr(it, "resto_menu", None)
                category = getattr(it, "category", None)

                _add_row(fg_code, fg_name, fg_uom, it.qty, flt(it.net_amount or it.amount or 0), resto_menu, category)
        elif frappe.db.exists("POS Invoice", inv):
            pi = frappe.get_doc("POS Invoice", inv)
            for it in (pi.items or []):
                fg_code, fg_name, fg_uom, bom_no = _resolve_fg_and_bom_for_sale(it.item_code, pce.company or company)
                resto_menu = getattr(it, "resto_menu", None)
                category = getattr(it, "category", None)

                _add_row(fg_code, fg_name, fg_uom, it.qty, flt(it.net_amount or it.amount or 0), resto_menu, category)

    out_items: List[Dict] = []
    for code, base in agg.items():
        qty = flt(base.get("qty") or 0)
        if qty <= 0:
            continue
        amount = flt(base.get("selling_amount") or 0)
        selling_rate = (amount / qty) if qty else 0

        # Resolve BOM for the FG code (recipe_item) or fallback
        bom_no = _get_item_default_bom(code, company)

        # Flat list for grid
        rm_list: List[Dict] = []
        if bom_no and qty:
            bom_items = get_bom_items_as_dict(bom=bom_no, company=company, qty=qty, fetch_exploded=1)
            for bi in bom_items.values():
                ic = bi.get("item_code")
                if not ic:
                    continue
                uom = bi.get("stock_uom") or bi.get("uom")
                req = flt(bi.get("qty") or 0)
                unit_cost = _get_item_unit_cost(ic)

                # === Ambil actual qty dari Bin ===
                actual_qty = 0
                if warehouse:
                    actual_qty = frappe.db.get_value(
                        "Bin",
                        {"item_code": ic, "warehouse": warehouse},
                        "actual_qty"
                    ) or 0

                rm_list.append({
                    "item_code": ic,
                    "item_name": bi.get("item_name"),
                    "stock_uom": uom,
                    "required_qty": req,
                    "unit_cost": unit_cost,
                    "cost": unit_cost * req,
                    "actual_qty": actual_qty,
                })

        # Build rm_tree + inject actual_qty
        rm_tree: List[Dict] = []
        if bom_no and qty:
            rm_tree = _build_bom_tree(bom_no, qty)

            def enrich_tree(tree_nodes):
                for node in tree_nodes:
                    ic = node.get("item_code")
                    if ic and warehouse:
                        node["actual_qty"] = frappe.db.get_value(
                            "Bin",
                            {"item_code": ic, "warehouse": warehouse},
                            "actual_qty"
                        ) or 0
                    else:
                        node["actual_qty"] = 0
                    # recursive kalau ada children
                    if node.get("children"):
                        enrich_tree(node["children"])

            enrich_tree(rm_tree)

        # === Ambil actual qty untuk FG item juga ===
        fg_actual_qty = 0
        if warehouse:
            fg_actual_qty = frappe.db.get_value(
                "Bin",
                {"item_code": code, "warehouse": warehouse},
                "actual_qty"
            ) or 0

        out_items.append({
            "item_code": code,
            "item_name": base.get("item_name"),
            "resto_menu": base.get("resto_menu"),
            "category": base.get("category"),
            "qty": qty,
            "stock_uom": base.get("stock_uom"),
            "bom_no": bom_no,
            "selling_rate": selling_rate,
            "selling_amount": amount,
            "rm_items": rm_list,
            "rm_tree": rm_tree,
            "actual_qty": fg_actual_qty,   # stok per warehouse untuk FG
        })

    return {"items": out_items}

@frappe.whitelist()
def create_stock_entry_from_pos_usage(
    pos_closing_entry: str,
    company: str,
    posting_date: Optional[str] = None,
    stock_entry_type: str = "Material Issue",
    source_warehouse: Optional[str] = None,
    target_warehouse: Optional[str] = None,
    remarks: Optional[str] = None,
    items: Union[List[Dict], str, None] = None,
) -> str:
    """
    Create & submit Stock Entry from edited RM payload, linked to a POS Closing Entry context.
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
    se.remarks = (remarks or "") + f"\nGenerated from Stock Usage Tool for POS Closing Entry {pos_closing_entry}"

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
            # No Sales Order link in POS variant
            "description": row.get("remarks") or row.get("item_name") or "",
        })

    if not se.items:
        frappe.throw("No valid items after validation.")

    se.insert()
    se.submit()
    return se.name


# ---------- POS Consumption API ----------

@frappe.whitelist()
def create_pos_consumption(
    pos_closing: str,
    company: str,
    warehouse: str,
    notes: Optional[str] = None,
    menu_summaries: Union[List[Dict], str, None] = None,
    rm_breakdown: Union[List[Dict], str, None] = None,
):
    """
    Create a POS Consumption document capturing menu-level HPP and consolidated RM usage
    instead of immediately posting a Stock Entry.

    Expected payloads:
      menu_summaries: [
        { "menu": <Resto Menu name or empty>, "sell_item": <Item>, "qty_sold": float,
          "sales_amount": float, "rm_value_total": float, "margin_amount": float,
          "category": <str or Link>, "raw_material_breakdown": list }
      ]
      rm_breakdown: [
        { "rm_item": <Item>, "uom": <UOM>, "planned_qty": float,
          "adj_qty": float, "final_qty": float, "valuation_rate_snapshot": float }
      ]
    """
    # Normalize json inputs
    if isinstance(menu_summaries, str):
        try:
            menu_summaries = frappe.parse_json(menu_summaries)
        except Exception:
            menu_summaries = []
    if isinstance(rm_breakdown, str):
        try:
            rm_breakdown = frappe.parse_json(rm_breakdown)
        except Exception:
            rm_breakdown = []

    pce = frappe.get_doc("POS Closing Entry", pos_closing)

    # Auto fields from closing
    closing_start = getattr(pce, "period_start_date", None) or getattr(pce, "start_date", None)
    closing_end   = getattr(pce, "period_end_date", None) or getattr(pce, "end_date", None)
    if not company:
        company = getattr(pce, "company", None)

    doc = frappe.new_doc("POS Consumption")
    doc.pos_closing = pce.name
    doc.company = company
    doc.warehouse = warehouse
    doc.closing_start = closing_start
    doc.closing_end = closing_end
    doc.status = "Draft"
    if notes:
        doc.notes = notes

    # Resolve child table fieldnames dynamically by options
    menu_ct = None
    rm_ct = None
    for tf in (doc.meta.get_table_fields() or []):
        if tf.options == "POS Consumption Menu":
            menu_ct = tf.fieldname
        elif tf.options == "POS Consumption RM":
            rm_ct = tf.fieldname
    if not menu_ct or not rm_ct:
        # Fallback to conventional names
        menu_ct = menu_ct or "menu_summary"
        rm_ct = rm_ct or "rm_breakdown"

    # Append Menu Summary
    for ms in (menu_summaries or []):
        doc.append(menu_ct, {
            "menu": ms.get("menu"),
            "sell_item": ms.get("sell_item"),
            "qty_sold": flt(ms.get("qty_sold")),
            "sales_amount": flt(ms.get("sales_amount")),
            "rm_value_total": flt(ms.get("rm_value_total")),
            "margin_amount": flt(ms.get("margin_amount")),
            "category": ms.get("category"),
            "raw_material_breakdown": json.dumps(ms.get("raw_material_breakdown") or []),
        })

    # Append RM Breakdown
    for rm in (rm_breakdown or []):
        # take snapshot if not provided
        val_rate = rm.get("valuation_rate_snapshot")
        if val_rate in (None, "") and rm.get("rm_item"):
            val_rate = _get_item_unit_cost(rm.get("rm_item"))
        doc.append(rm_ct, {
            "rm_item": rm.get("rm_item"),
            "uom": rm.get("uom"),
            "planned_qty": flt(rm.get("planned_qty")),
            "actual_qty": flt(rm.get("actual_qty")),
            "diff_qty": flt(rm.get("diff_qty")),
            "valuation_rate_snapshot": flt(val_rate or 0),
        })

    frappe.log_error(f"Company: {company}, Warehouse: {warehouse}", "POS Consumption Debug")
    print(f"Company: {company}, Warehouse: {warehouse}")


    doc.insert()

    doc.submit()

    return doc.name

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