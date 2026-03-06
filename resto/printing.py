from __future__ import annotations
import math
import tempfile
import frappe
from typing import List, Dict, Any
from frappe.utils import now_datetime
from PIL import Image
from io import BytesIO
import requests
import re
import os

# ========== Konstanta & Util ==========
LINE_WIDTH = 32
ITEM_HEIGHT_MULT = 2

ESC = b"\x1b"
GS  = b"\x1d"

def _esc_init() -> bytes:
    return ESC + b'@'

def _esc_align_left() -> bytes:
    return ESC + b'a' + b'\x00'

def _esc_align_center() -> bytes:
    return ESC + b'a' + b'\x01'

def _esc_align_right() -> bytes:
    return ESC + b'a' + b'\x02'

def _esc_bold(on: bool) -> bytes:
    return ESC + b'E' + (b'\x01' if on else b'\x00')

def _esc_font_a() -> bytes:
    return ESC + b'M' + b'\x00'

def _esc_cut_full() -> bytes:
    return GS + b'V' + b'\x00'

def _esc_feed(n: int) -> bytes:
    n = max(0, min(n, 255))
    return ESC + b'd' + bytes([n])

def _esc_qr(data: str) -> bytes:
    store_pL = (len(data) + 3) & 0xFF
    store_pH = (len(data) + 3) >> 8
    cmds = b""
    cmds += GS + b'(' + b'k' + b'\x04\x00' + b'1A' + b'\x02\x00'
    cmds += GS + b'(' + b'k' + b'\x03\x00' + b'1C' + b'\x04'
    cmds += GS + b'(' + b'k' + b'\x03\x00' + b'1E' + b'\x31'
    cmds += GS + b'(' + b'k' + bytes([store_pL, store_pH]) + b'1P0' + data.encode('utf-8')
    cmds += GS + b'(' + b'k' + b'\x03\x00' + b'1Q' + b'\x30'
    return cmds

def _esc_char_size(width_mul: int = 0, height_mul: int = 0) -> bytes:
    w = max(0, min(7, int(width_mul)))
    h = max(0, min(7, int(height_mul)))
    return GS + b'!' + bytes([(w << 4) | h])

def _fmt_money(val: float, currency: str = "IDR") -> str:
    n = 0 if currency.upper() in ("IDR", "RP") else 2
    if n == 0:
        s = f"{int(round(val)):n}"
    else:
        s = f"{val:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    prefix = "Rp " if currency.upper() in ("IDR", "RP") else (currency.upper() + " ")
    return prefix + s

def _wrap_text(text: str, width: int) -> List[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], ""
    for w in words:
        if len(cur) + (1 if cur else 0) + len(w) <= width:
            cur = (cur + " " + w) if cur else w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def _fit(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"

def _line(char: str = "-") -> str:
    return char * LINE_WIDTH

def _format_line(left: str, right: str, width: int = LINE_WIDTH):
    left = str(left)
    right = str(right)
    space = width - len(left) - len(right)
    if space < 1:
        space = 1
    return f"{left}{' ' * space}{right}"

def _pad_lr(left: str, right: str, width: int) -> str:
    space = width - len(left) - len(right)
    if space < 1:
        return (left + " " + right)[0:width]
    return f"{left}{' ' * space}{right}"

def _contains_cjk(text: str) -> bool:
    if not text:
        return False
    for char in text:
        code = ord(char)
        if (0x4E00 <= code <= 0x9FFF) or \
           (0x3400 <= code <= 0x4DBF) or \
           (0x20000 <= code <= 0x2A6DF) or \
           (0xF900 <= code <= 0xFAFF):
            return True
    return False

def _safe_encode(text: str) -> bytes:
    if not text:
        return b""
    try:
        return text.encode('gb18030', 'ignore')
    except:
        try:
            return text.encode('utf-8', 'ignore')
        except:
            return text.encode('ascii', 'ignore')

def _esc_print_image(image_path):
    if image_path.startswith("/"):
        image_url = frappe.utils.get_url(image_path)
    else:
        image_url = image_path

    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content)).convert("L")

    max_width = 384
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)))

    image = image.point(lambda x: 0 if x < 128 else 255, '1')

    bytes_out = b""
    width_bytes = (image.width + 7) // 8

    for y in range(image.height):
        line = b""
        for x in range(0, image.width, 8):
            byte = 0
            for bit in range(8):
                if x + bit < image.width and image.getpixel((x + bit, y)) == 0:
                    byte |= (1 << (7 - bit))
            line += bytes([byte])
        bytes_out += b"\x1b*\x21" + bytes([width_bytes % 256, width_bytes // 256]) + line + b"\n"

    return _esc_align_center() + bytes_out + b"\n"

def cups_print_raw(raw_bytes: bytes, printer_name: str) -> int:
    try:
        import cups
        conn = cups.Connection()
        printers = conn.getPrinters()
        if printer_name not in printers:
            raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan di CUPS")

        if printer_name == "Kasir":
            open_drawer_command = b'\x1B\x70\x00\x19\xFA'
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(open_drawer_command)
                tmp_path_drawer = tmp.name
            conn.printFile(printer_name, tmp_path_drawer, "Open Drawer", {"raw": "true"})
            
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = tmp.name

        job_id = conn.printFile(printer_name, tmp_path, "POS_Receipt", {"raw": "true"})
        return job_id
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), f"CUPS Print Error: {printer_name}")
        raise

def cups_print_pdf_with_cut(pdf_bytes: bytes, printer_name: str) -> int:
    """
    Print PDF dengan auto-cut menggunakan CUPS options.
    """
    import cups
    import tempfile

    conn = cups.Connection()
    printers = conn.getPrinters()
    if printer_name not in printers:
        raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    # Options untuk thermal printer dengan auto-cut
    options = {
        'media': 'Custom.58x200mm',  # Custom size
        'fit-to-page': 'False',
        'print-scaling': 'none',
        'page-ranges': '1',  # Only print page 1
    }
    
    job_id = conn.printFile(printer_name, tmp_path, "Kitchen_Order", options)
    return job_id

def sanitize_kitchen_payload(items):
    blacklist = ["tambahan", "Tambahan", "TAMBAHAN"]
    clean_items = []
    for it in items:
        for field in ["add_ons", "quick_notes", "item_name"]:
            if it.get(field):
                val = it[field]
                for b in blacklist:
                    val = val.replace(b, "").strip()
                it[field] = val
        clean_items.append(it)
    return clean_items

# ========== Normalisasi POS Invoice ==========
def _collect_pos_invoice(name: str) -> Dict[str, Any]:
    doc = frappe.get_doc("POS Invoice", name).reload()

    currency = doc.get("currency") or "IDR"
    items = []

    for it in doc.get("items", []):
        item_code = it.get("item_code")
        standard_price = frappe.db.get_value(
            "Item Price",
            {"item_code": item_code, "price_list": "Standard Selling"},
            "price_list_rate"
        ) or it.get("rate") 

        items.append({
            "item_code": it.get("item_code"),
            "item_name": it.get("item_name") or it.get("item_code"),
            "resto_menu": it.get("resto_menu"),
            "qty": float(it.get("qty") or 0),
            "rate": float(standard_price or 0),
            "amount": float(it.get("amount") or 0),
            "uom": it.get("uom") or it.get("stock_uom"),
            "discount_percentage": float(it.get("discount_percentage") or 0),
            "discount_amount": float(it.get("discount_amount") or 0),
            "description": it.get("description") or "",
            "add_ons" : it.get("add_ons") or "",
            "quick_notes": it.get("quick_notes") or "",
            "status_kitchen": it.get("status_kitchen") or "",
            "is_checked": int(it.get("is_checked") or 0)
        })

    taxes = []
    for tx in doc.get("taxes", []):
        taxes.append({
            "description": tx.get("description") or "Tax",
            "amount": float(tx.get("tax_amount") or 0),
            "rate": int(tx.get("rate") or 0),
        })

    payments = []
    total_paid = 0.0
    for p in doc.get("payments", []):
        amt = float(p.get("amount") or 0)
        total_paid += amt
        payments.append({
            "mode_of_payment": p.get("mode_of_payment") or "Payment",
            "amount": amt,
        })

    branch_detail = {}
    if doc.get("branch"):
        try:
            branch_doc = frappe.get_doc("Branch", doc.get("branch"))
            branch_detail = branch_doc.as_dict()
        except frappe.DoesNotExistError:
            branch_detail = {}

    grand_total = float(doc.get("rounded_total") or doc.get("grand_total") or 0)
    change_amount = doc.get("change_amount")
    if change_amount is None:
        change_amount = max(0.0, total_paid - grand_total)

    return {
        "name": doc.get("name"),
        "posting_date": str(doc.get("posting_date") or ""),
        "posting_time": str(doc.get("posting_time") or ""),
        "branch": doc.get("branch") or "",
        "branch_detail": branch_detail, 
        "company": doc.get("company") or "",
        "customer": doc.get("customer") or "",
        "customer_name": doc.get("customer_name") or "",
        "order_type": doc.get("order_type") or "",
        "queue": doc.get("queue") or "",
        "currency": currency,
        "total": float(doc.get("total") or 0),
        "discount_amount": float(doc.get("discount_amount") or 0),
        "total_taxes_and_charges": float(doc.get("total_taxes_and_charges") or 0),
        "grand_total": float(doc.get("grand_total") or 0),
        "rounded_total": float(doc.get("rounded_total") or 0),
        "paid_amount": float(doc.get("paid_amount") or 0),
        "change_amount": float(change_amount or 0),
        "loyalty_points": doc.get("loyalty_points"),
        "loyalty_amount": float(doc.get("loyalty_amount") or 0),
        "remarks": (doc.get("remarks") or "").strip(),
        "items": items,
        "taxes": taxes,
        "payments": payments,
        "pos_profile": doc.get("pos_profile") or "",
        "doc": doc,
    }

# ========== KITCHEN PDF GENERATOR - COMPACT & PROPER CUT ==========
class KitchenPDFGenerator:
    """
    Generator PDF untuk Kitchen Receipt - compact dengan proper height calculation.
    Menggunakan 58mm width, minimal margin, dan exact height calculation.
    """
    
    def __init__(self):
        self.width_mm = 58
        self.margin_mm = 1.5  # Minimal margin
        self.usable_width = self.width_mm - (2 * self.margin_mm)
        
        # Register CJK fonts
        self.cjk_font = None
        self.latin_font = 'Helvetica-Bold'
        self._register_fonts()
    
    def _register_fonts(self):
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            font_paths = [
                ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 'WQYZen'),
                ('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 'WQYMicro'),
                ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 'NotoCJK'),
            ]
            
            for path, name in font_paths:
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont(name, path))
                        self.cjk_font = name
                        break
                    except:
                        continue
                        
        except ImportError:
            pass
    
    def _text_width(self, text: str, font_size: float, is_cjk: bool = False) -> float:
        """Estimate text width in mm"""
        char_width = 0.6 if is_cjk else 0.35  # mm per char at size 10
        return len(text) * char_width * (font_size / 10)
    
    def generate(self, station: str, table: str, date_str: str, by: str, order_type: str, items: List[Dict]) -> bytes:
        """
        Generate compact kitchen PDF dengan exact height.
        """
        from reportlab.lib.pagesizes import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        
        # Calculate exact height needed
        total_height = self._calculate_height(station, table, date_str, by, order_type, items)
        
        # Create PDF with exact size (PORTRAIT: height > width)
        page_size = (self.width_mm * mm, total_height * mm)
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        
        # Start from top with minimal margin
        y = total_height * mm - 2 * mm
        x = self.margin_mm * mm
        
        # STATION NAME - Center, Bold, Large
        c.setFont(self.latin_font, 13)
        c.drawCentredString(self.width_mm * mm / 2, y, station)
        y -= 5 * mm
        
        # INFO - Compact
        c.setFont(self.latin_font, 8)
        info_lines = [
            f"Tbl:{table}",
            f"{date_str}",
            f"By:{by}",
            f"Type:{order_type}",
        ]
        for line in info_lines:
            c.drawString(x, y, line)
            y -= 3 * mm
        
        # Separator
        y -= 1 * mm
        c.line(x, y, (self.width_mm - self.margin_mm) * mm, y)
        y -= 3 * mm
        
        # ITEMS
        for item in items:
            qty = item.get('qty', '')
            name = item.get('name', '')
            name_cn = item.get('name_cn', '')
            addons = item.get('addons', [])
            notes = item.get('notes', '')
            
            # Qty + Name (Bold, larger)
            c.setFont(self.latin_font, 10)
            main_text = f"{qty}x {name}"
            c.drawString(x, y, main_text)
            y -= 4 * mm
            
            # Chinese name (if exists)
            if name_cn and self.cjk_font:
                c.setFont(self.cjk_font, 11)
                c.drawString(x + 2 * mm, y, name_cn)
                y -= 4 * mm
            
            # Addons
            if addons:
                c.setFont(self.latin_font, 7)
                for addon in addons:
                    c.drawString(x + 2 * mm, y, f"+{addon}")
                    y -= 2.5 * mm
            
            # Notes
            if notes:
                c.setFont(self.latin_font, 7)
                c.drawString(x + 2 * mm, y, f"#{notes}")
                y -= 2.5 * mm
            
            # Spacer between items
            y -= 1.5 * mm
        
        # Bottom separator
        c.line(x, y, (self.width_mm - self.margin_mm) * mm, y)
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
    
    def _calculate_height(self, station, table, date_str, by, order_type, items) -> float:
        """Calculate exact height in mm"""
        height = 4  # Top margin + station
        
        # Info lines
        height += 4 * 3  # 4 lines * 3mm each
        
        # Separators and spacing
        height += 5
        
        # Items
        for item in items:
            height += 4  # Main line
            
            if item.get('name_cn'):
                height += 4  # Chinese line
            
            height += len(item.get('addons', [])) * 2.5
            if item.get('notes'):
                height += 2.5
            
            height += 1.5  # Spacer
        
        # Bottom
        height += 3
        
        return max(height, 40)

def build_kitchen_pdf(data: Dict[str, Any], station_name: str, items: List[Dict], created_by: str = None) -> bytes:
    """Build kitchen PDF dengan Chinese support."""
    
    # Get mandarin map
    resto_menus = list(set([i.get("resto_menu") for i in items if i.get("resto_menu")]))
    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {d.name: d.custom_mandarin_name for d in menu_data if d.custom_mandarin_name}
    
    # Build items
    pdf_items = []
    for it in items:
        qty = int(it.get('qty', 0)) if float(it.get('qty', 0)).is_integer() else it.get('qty', 0)
        item_name = it.get('item_name', '')
        resto_menu = it.get('resto_menu')
        mandarin_name = mandarin_map.get(resto_menu, '')
        
        # Parse addons
        addons = []
        add_ons_str = it.get('add_ons', '')
        if add_ons_str:
            for add in [a.strip() for a in add_ons_str.split(',') if a.strip()]:
                if '(' in add and ')':
                    name = add.rsplit('(', 1)[0].strip()
                else:
                    name = add
                addons.append(name)
        
        notes = it.get('quick_notes', '')
        
        pdf_items.append({
            'qty': qty,
            'name': item_name,
            'name_cn': mandarin_name,
            'addons': addons,
            'notes': notes
        })
    
    # Generate PDF
    table = get_table_names_from_pos_invoice(data["name"])
    date_str = f"{data['posting_date']} {data['posting_time'][:5]}"
    
    generator = KitchenPDFGenerator()
    return generator.generate(
        station=station_name,
        table=table,
        date_str=date_str,
        by=created_by or '',
        order_type=data['order_type'],
        items=pdf_items
    )

# ========== Builder ESC/POS ==========
def build_escpos_from_pos_invoice(name: str, add_qr: bool = False, qr_data: str | None = None) -> bytes:
    data = _collect_pos_invoice(name)
    lines = _format_receipt_lines(data)

    out = b""
    out += _esc_init()
    out += _esc_font_a()
    out += _esc_align_left()
    out += _esc_bold(False)

    if data["company"]:
        out += _esc_align_center() + _esc_bold(True)
        for h in _wrap_text(data["company"], LINE_WIDTH):
            out += _safe_encode(h + "\n")
        out += _esc_bold(False)

    title = f"POS INVOICE {data['name'] or ''}".strip()
    out += _esc_align_center() + _esc_bold(True) + _safe_encode(title + "\n") + _esc_bold(False)
    out += _esc_align_left()

    for ln in lines:
        out += _safe_encode(ln + "\n")

    if add_qr and qr_data:
        out += _esc_align_center()
        out += _esc_qr(qr_data)
        out += _esc_align_left()
        out += _esc_feed(1)

    out += _esc_feed(3) + _esc_cut_full()
    return out

def get_item_printers(item: Dict) -> List[str]:
    branch_menu = item.get("resto_menu")
    if not branch_menu:
        return []
    doc = frappe.get_doc("Branch Menu", branch_menu)
    printers = []
    for ks in doc.get("printers") or []:
        if ks.get("printer_name"):
            printers.append(ks["printer_name"])
    return printers

def build_kitchen_receipt(data: Dict[str, Any], station_name: str, items: List[Dict], created_by: None) -> bytes:
    """Build kitchen receipt menggunakan PDF dengan Chinese support."""
    return build_kitchen_pdf(data, station_name, items, created_by)

# ========== API: cetak sekarang (sync) ==========
@frappe.whitelist()
def pos_invoice_print_now(name: str, printer_name: str, add_qr: int = 0, qr_data: str | None = None) -> dict:
    try:
        data = _collect_pos_invoice(name)
        doc = frappe.get_doc("POS Invoice", name)

        full_name = frappe.db.get_value("User", doc.owner, "full_name")

        results = []

        raw = build_escpos_from_pos_invoice(name, bool(int(add_qr)), qr_data)
        job_id = cups_print_raw(raw, printer_name)
        results.append({"printer": printer_name, "job_id": job_id, "type": "bill"})

        kitchen_groups: Dict[str, List[Dict]] = {}
        for it in data["items"]:
            for printer in get_item_printers(it):
                kitchen_groups.setdefault(printer, []).append(it)

        for kprinter, items in kitchen_groups.items():
            # Kitchen pakai PDF dengan Chinese support
            pdf_bytes = build_kitchen_receipt(data, kprinter, items, created_by=full_name)
            # Print dengan auto-cut option
            kitchen_job = cups_print_pdf_with_cut(pdf_bytes, kprinter)
            results.append({"printer": kprinter, "job_id": kitchen_job, "type": "kitchen"})

        frappe.msgprint(f"POS Invoice {name} terkirim ke {len(results)} printer")
        return {"ok": True, "jobs": results}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "POS Invoice Print Error")
        frappe.throw(f"Gagal print invoice {name}: {str(e)}")

# ========== Kitchen: builder dari payload kustom ==========
def _fmt_qty(val: float | int) -> str:
    try:
        f = float(val)
        return str(int(f)) if f.is_integer() else str(f)
    except Exception:
        return str(val)

def _safe_str(v) -> str:
    return (v or "").strip()

def build_kitchen_receipt_from_payload(entry: Dict[str, Any], title_prefix: str = "") -> bytes:
    """Build kitchen receipt dari payload menggunakan PDF."""
    current_user = frappe.session.user
    full_name = frappe.db.get_value("User", current_user, "full_name")

    station = _safe_str(entry.get("kitchen_station")) or "-"
    inv = _safe_str(entry.get("pos_invoice")) or "-"
    tdate = _safe_str(entry.get("transaction_date")) or frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    items = entry.get("items") or []
    
    # Mandarin mapping
    resto_menus = list(set([i.get("resto_menu") for i in items if i.get("resto_menu")]))
    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {d.name: d.custom_mandarin_name for d in menu_data if d.custom_mandarin_name}
    
    # Build items
    pdf_items = []
    for it in items:
        qty_s = _fmt_qty(it.get("qty") or 0)
        item_name = _safe_str(it.get("item_name"))
        short_name = _safe_str(it.get("short_name"))
        menu_name = _safe_str(it.get("resto_menu"))
        
        title = item_name or short_name or menu_name or "-"
        mandarin_name = mandarin_map.get(it.get("resto_menu")) or ""
        
        # Parse addons
        addons = []
        add_ons_str = it.get("add_ons", "")
        if add_ons_str:
            for add in [a.strip() for a in add_ons_str.split(",")]:
                if "(" in add and ")":
                    name = add.rsplit("(", 1)[0].strip()
                else:
                    name = add
                addons.append(name)
        
        notes = it.get("quick_notes", "")
        
        pdf_items.append({
            'qty': qty_s,
            'name': title,
            'name_cn': mandarin_name,
            'addons': addons,
            'notes': notes
        })
    
    # Generate PDF
    table = get_table_names_from_pos_invoice(inv)
    
    generator = KitchenPDFGenerator()
    return generator.generate(
        station=station,
        table=table,
        date_str=tdate,
        by=full_name,
        order_type="Kitchen",
        items=pdf_items
    )

# ========== API: print kitchen dari payload ==========
@frappe.whitelist()
def kitchen_print_from_payload(payload, title_prefix: str = "") -> dict:
    import json
    import cups
    try:
        if isinstance(payload, list):
            entries = payload
        elif isinstance(payload, dict):
            entries = [payload]
        elif isinstance(payload, (bytes, bytearray)):
            obj = json.loads(payload.decode())
            entries = obj if isinstance(obj, list) else [obj]
        elif isinstance(payload, str):
            obj = json.loads(payload or "[]")
            entries = obj if isinstance(obj, list) else [obj]
        else:
            raise TypeError(f"payload bertipe {type(payload).__name__} tidak didukung")

        conn = cups.Connection()
        printers = conn.getPrinters()

        results = []
        for entry in entries:
            station = _safe_str(entry.get("kitchen_station"))
            printer_name = _safe_str(entry.get("printer_name")) or station
            if not station:
                raise ValueError("Setiap entry wajib memiliki 'kitchen_station'")
            if not printer_name:
                raise ValueError("Setiap entry wajib memiliki 'printer_name'")

            if printer_name not in printers:
                raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan di CUPS")

            entry.setdefault("pos_invoice", "")
            entry.setdefault("transaction_date", frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"))
            entry.setdefault("items", [])
            
            # Generate PDF
            pdf_bytes = build_kitchen_receipt_from_payload(entry)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf_bytes)
                tmp_path = tmp.name
            
            # Print dengan auto-cut
            options = {
                'media': 'Custom.58x200mm',
                'fit-to-page': 'False',
                'print-scaling': 'none',
            }
            job_id = conn.printFile(printer_name, tmp_path, f"K_{station}", options)
            results.append({
                "station": station,
                "printer": printer_name,
                "job_id": job_id,
                "pos_invoice": _safe_str(entry.get("pos_invoice")),
            })

        frappe.msgprint(f"{len(results)} kitchen ticket dikirim ke printer")
        return {"ok": True, "jobs": results}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Kitchen Print Error (from payload)")
        frappe.throw(f"Gagal print kitchen: {str(e)}")

# ========== API: masuk antrian (async) ==========
@frappe.whitelist()
def pos_invoice_print_enqueue(name: str, printer_name: str, add_qr: int = 0, qr_data: str | None = None) -> dict:
    frappe.enqueue(
        "resto.printing._enqueue_worker",
        queue="long",
        job_name=f"print_pos_invoice_{name}",
        name=name,
        printer_name=printer_name,
        add_qr=bool(int(add_qr)),
        qr_data=qr_data,
    )
    return {"queued": True, "name": name, "printer": printer_name}

def _enqueue_worker(name: str, printer_name: str, add_qr: bool, qr_data: str | None):
    raw = build_escpos_from_pos_invoice(name, add_qr, qr_data)
    job_id = cups_print_raw(raw, printer_name)
    frappe.logger("pos_print").info({"invoice": name, "printer": printer_name, "job_id": job_id})

def format_number(val) -> str:
    try:
        return f"{float(val):,.0f}".replace(",", ".")
    except Exception:
        return str(val or 0)

def get_table_names_from_pos_invoice(pos_invoice_name: str) -> str:
    tables = frappe.get_all(
        "Table Order",
        filters={"invoice_name": pos_invoice_name},
        fields=["parent"],
        distinct=True
    )
    return ", ".join([t["parent"] for t in tables])

def get_total_pax_from_pos_invoice(pos_invoice_name: str) -> int:
    table_orders = frappe.get_all(
        "Table Order",
        filters={"invoice_name": pos_invoice_name},
        fields=["parent"]
    )
    total_pax = 0
    for t in table_orders:
        pax = frappe.db.get_value("Table", t["parent"], "pax") or 0
        total_pax += pax
    return total_pax

def get_waiter_name(pos_invoice_name: str) -> str:
    invoice = frappe.get_doc("POS Invoice", pos_invoice_name)
    owner = invoice.owner
    user = frappe.get_doc("User", owner)
    return user.full_name or owner  

def get_cashier_name(pos_invoice_name: str) -> str:
    invoice = frappe.get_doc("POS Invoice", pos_invoice_name)
    pos_profile_name = invoice.pos_profile
    pos_profile = frappe.get_doc("POS Profile", pos_profile_name)

    opening_entries = frappe.get_all(
        "POS Opening Entry",
        filters={
            "pos_profile": pos_profile.name,
            "status": "Open",
            "docstatus": 1
        },
        fields=["user", "name"],
        order_by="creation desc",
        limit_page_length=1
    )

    if opening_entries:
        opening_user = opening_entries[0].user
        user_doc = frappe.get_doc("User", opening_user)
        return user_doc.full_name or opening_user

    owner_user_doc = frappe.get_doc("User", invoice.owner)
    return owner_user_doc.full_name or invoice.owner

def build_escpos_bill(name: str) -> bytes:
    import frappe
    from frappe.utils.pdf import get_pdf
    from frappe.utils import now_datetime

    data = _collect_pos_invoice(name)
    LINE_WIDTH = 32

    def money(val):
        return f"{int(round(val or 0)):,.0f}".replace(",", ".")

    resto_menus = list(set([
        i.get("resto_menu") for i in data.get("items", [])
        if i.get("resto_menu")
    ]))

    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {d.name: d.get("custom_mandarin_name") for d in menu_data if d.get("custom_mandarin_name")}

    def wrap_text(text, width=LINE_WIDTH):
        if not text:
            return [""]
        words = str(text).split()
        lines, current = [], ""
        for w in words:
            if len(current) + len(w) + 1 <= width:
                current = f"{current} {w}".strip()
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)
        return lines

    def format_line(left, right):
        space = LINE_WIDTH - len(str(left)) - len(str(right))
        return f"{left}{' ' * max(space, 1)}{right}"

    items_html = ""
    for item in data.get("items", []):
        qty = int(item.get("qty") or 0)
        name_item = item.get("item_name") or ""
        amount = float(item.get("amount") or 0)
        resto_menu = item.get("resto_menu")
        mandarin = mandarin_map.get(resto_menu) or ""
        display_name = f"{name_item} ({mandarin})" if mandarin else name_item

        for line in wrap_text(f"{qty} x {display_name}"):
            items_html += f"<tr><td colspan='2'>{line}</td></tr>"

        items_html += f"<tr><td style='padding-left:8px;'>{format_line('', money(amount))}</td></tr>"

        for add in (item.get("add_ons") or "").split(","):
            if add.strip():
                items_html += f"<tr><td style='padding-left:8px;'>+ {add.strip()}</td></tr>"

        if item.get("quick_notes"):
            items_html += f"<tr><td style='padding-left:8px;'># {item['quick_notes']}</td></tr>"

    taxes_html = ""
    for tax in data.get("taxes", []):
        taxes_html += f"<tr><td>{tax.get('description','')}</td><td style='text-align:right;'>{money(tax.get('amount',0))}</td></tr>"

    payments_html = ""
    for pay in data.get("payments", []):
        payments_html += f"<tr><td>{pay.get('mode_of_payment','')}</td><td style='text-align:right;'>{money(pay.get('amount',0))}</td></tr>"

    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")
    company = data.get("company") or ""
    customer = data.get("customer_name") or data.get("customer") or ""
    order_type = data.get("order_type") or ""
    queue_no = data.get("queue") or ""
    total_qty = sum(int(item.get("qty",0)) for item in data.get("items", []))

    html = f"""
    <html>
    <head>
    <meta charset="utf-8">
    <style>
    @page {{ size: 58mm 300mm; margin:4mm; }}
    body {{ font-family:"DejaVu Sans Mono", monospace; font-size:10px; line-height:1.2; width:58mm; }}
    table {{ width:100%; border-collapse: collapse; table-layout: fixed; }}
    td {{ padding:0; vertical-align: top; }}
    .center {{ text-align:center; }}
    .right {{ text-align:right; }}
    hr {{ border-top:1px dashed black; border-bottom:none; margin:4px 0; }}
    </style>
    </head>
    <body>
    <div class='center'><b>{company}</b><br>{print_time}<br>Invoice: {data.get('name')}</div>
    <hr>
    <table>{items_html}</table>
    <hr>
    <table>
    <tr><td>Subtotal</td><td class='right'>{money(data.get('total',0))}</td></tr>
    {taxes_html}
    <tr><td><b>Grand Total</b></td><td class='right'><b>{money(data.get('grand_total',0))}</b></td></tr>
    </table>
    <hr>
    <table>{payments_html}</table>
    <br>
    <div class='center'>Terima kasih!<br>Selamat menikmati hidangan Anda!</div>
    """

    if order_type.lower() in ["take away","takeaway"] and queue_no:
        html += f"<br><div class='center'><b>Your Queue Number: {queue_no}</b></div>"

    html += "</body></html>"

    return get_pdf(html)

def _enqueue_bill_worker(name: str, printer_name: str):
    import cups
    pdf = build_escpos_bill(name)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf)
        tmp_path = tmp.name
    
    conn = cups.Connection()
    job_id = conn.printFile(printer_name, tmp_path, "Bill", {})

    frappe.logger("pos_print").info({
        "invoice": name,
        "printer": printer_name,
        "job_id": job_id,
        "type": "bill"
    })

    return job_id

def build_escpos_receipt(name: str) -> bytes:
    data = _collect_pos_invoice(name)

    items = data.get("items", [])
    payments = data.get("payments", [])
    taxes = data.get("taxes", [])

    company = data.get("company") or ""
    order_type = data.get("order_type") or ""
    customer = data.get("customer_name") or data.get("customer") or ""
    total = data.get("total", 0)
    discount = data.get("discount_amount", 0)
    tax_total = data.get("total_taxes_and_charges", 0)
    grand_total = data.get("grand_total", 0)
    paid = data.get("paid_amount", 0)
    change = data.get("change_amount", 0)
    queue_no = data.get("queue") or ""
    branch = data.get("branch") or ""
    branch_detail = data.get("branch_detail") or {}

    address1 = branch_detail.get("address_line1") or ""
    address2 = branch_detail.get("address_line2") or ""
    city = branch_detail.get("city") or ""
    pincode = branch_detail.get("pincode") or ""
    phone = branch_detail.get("phone") or ""
    
    address1 = address2 = city = pincode = phone = ""

    if company:
        addr_links = frappe.get_all(
            "Dynamic Link",
            filters={"link_doctype": "Company", "link_name": company},
            fields=["parent"],
            order_by="creation asc"
        )

        if addr_links:
            address_doc = frappe.get_doc("Address", addr_links[0].parent)
            address1 = address_doc.address_line1 or ""
            address2 = address_doc.address_line2 or ""
            city = address_doc.city or ""
            pincode = address_doc.pincode or ""
            phone = address_doc.phone or ""

    total_qty = sum(int(item.get("qty", 0)) for item in items)
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")

    separator = "-" * LINE_WIDTH

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    logo = frappe.db.get_value("Company", company, "custom_company_logo") or frappe.db.get_value("Company", company, "company_logo")
    out += _esc_align_center() + _esc_bold(True)

    company_city_line = f"{company} {city}".strip()
    if company_city_line:
        out += _safe_encode(company_city_line + "\n")

    if address1:
        out += _safe_encode(address1 + "\n")
    if address2:
        out += _safe_encode(address2 + "\n")
    if phone:
        out += _safe_encode(f"Tlp. {phone}\n")

    out += _esc_bold(False)
    out += _esc_align_left()
    out += _safe_encode(separator + "\n")

    out += _safe_encode(f"No : {data['name']}\n")
    out += _safe_encode(f"Date : {print_time}\n")

    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += _safe_encode(f"Table: {table_names}\n")
        out += _esc_bold(False)

    out += _safe_encode(f"Purpose : {order_type}\n")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += _safe_encode(f"Pax : {pax_int}\n")
        out += _esc_bold(False)

    cashier_name = get_cashier_name(data["name"])
    out += _safe_encode(f"Cashier : {cashier_name}\n")

    if customer:
        out += _safe_encode(f"Customer: {customer}\n")

    out += _safe_encode(separator + "\n")

    for item in items:
        item_name = item.get("item_name", "")
        qty = int(item.get("qty", 0))
        rate = item.get("rate", 0)
        amount = rate * qty

        out += _safe_encode(f"{item_name}\n")
        line = f"{qty}x @{format_number(rate)}".ljust(LINE_WIDTH - 12) + f"{format_number(amount).rjust(12)}"
        out += _safe_encode(line + "\n")

        add_ons_str = item.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",")]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, price = add.rsplit("(", 1)
                    price = price.replace(")", "").strip()
                    name = name.strip()
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12) + f"{format_number(float(price)).rjust(12)}"
                    out += _safe_encode(add_line + "\n")

        notes = item.get("quick_notes", "")
        if notes:
            out += _safe_encode(f"  # {notes}\n")

    out += _safe_encode(separator + "\n")
    out += _safe_encode(f"{total_qty} items\n")

    sc_amount = 0
    tax_amount = 0

    for tax in taxes:
        tax_name = tax.get("description", "")
        amount = tax.get("amount", 0)

        if "Pendapatan Service" in tax_name:
            sc_amount += amount
        elif "VAT" in tax_name:
            tax_amount += amount

    if sc_amount:
        out += _safe_encode(_format_line("Sc:", format_number(sc_amount)) + "\n")

    out += _safe_encode(_format_line("Subtotal:", format_number(total)) + "\n")

    if tax_amount:
        out += _safe_encode(_format_line("Tax:", format_number(tax_amount)) + "\n")
    
    out += _safe_encode(separator + "\n")
    out += _esc_bold(True)
    out += _safe_encode(_format_line("Grand Total:", format_number(grand_total)) + "\n")
    out += _esc_bold(False)
    
    for pay in payments:
        mop = pay.get("mode_of_payment") or "-"
        amt = pay.get("amount") or 0
        out += _safe_encode(f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n")

    if change:
        out += _safe_encode(f"Change:".rjust(LINE_WIDTH - 12) + f"{format_number(change).rjust(12)}\n")

    out += _safe_encode(separator + "\n")
    out += _esc_align_center()
    out += _safe_encode("Terima kasih!\n")
    out += _safe_encode("Selamat menikmati hidangan Anda!\n")

    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += _safe_encode("Your Queue Number:\n")
            out += _esc_bold(False)

            out += _esc_align_center()
            out += b"\x1b!\x38"
            out += _safe_encode(f"{queue_no}\n")
            out += b"\x1b!\x00"
            out += _esc_feed(2)

    out += _esc_feed(8) + _esc_cut_full()
    return out

def _enqueue_receipt_worker(name: str, printer_name: str):
    raw = build_escpos_receipt(name)
    job_id = cups_print_raw(raw, printer_name)

    frappe.logger("pos_print").info({
        "invoice": name,
        "printer": printer_name,
        "job_id": job_id,
        "type": "receipt"
    })

    return job_id

# ========== CHECKER RECEIPT DENGAN CHINESE SUPPORT ==========
def build_escpos_checker(name: str) -> bytes:
    """
    Build CHECKER receipt dengan support Chinese characters.
    Format: Item Name di baris 1, Chinese name di baris 2 (newline).
    """
    data = _collect_pos_invoice(name)

    items = sanitize_kitchen_payload([
        item for item in data.get("items", [])
        if int(item.get("is_checked") or 0) == 0
        and item.get("status_kitchen") == "Already Send To Kitchen"
    ])
    
    if not items:
        frappe.logger("pos_print").info({
            "invoice": name,
            "message": "Semua item sudah di-print ke checker"
        })
        return b""

    company = data.get("company") or ""
    order_type = data.get("order_type") or ""
    branch = data.get("branch") or ""

    total_qty = sum(int(item.get("qty", 0)) for item in items)
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")
    
    # PREPARE MANDARIN MAP
    resto_menus = list(set([
        i.get("resto_menu")
        for i in items
        if i.get("resto_menu")
    ]))

    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {
            d.name: d.custom_mandarin_name
            for d in menu_data
        }

    separator = "-" * LINE_WIDTH

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # HEADER
    out += _esc_align_center() + _esc_bold(True)
    out += _safe_encode("CHECKER\n")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out += _safe_encode(header_line + "\n")

    out += _esc_bold(False)
    out += _esc_align_left()
    out += _safe_encode(separator + "\n")
    
    table_names = get_table_names_from_pos_invoice(data["name"])

    # INFO
    out += _safe_encode(f"No Meja : {table_names}\n")
    out += _safe_encode(f"Date : {print_time}\n")
    out += _safe_encode(f"Purpose : {order_type}\n")
    out += _safe_encode(f"Waiter : {get_waiter_name(data['name'])}\n")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += _safe_encode(f"Pax : {pax_int}\n")
        out += _esc_bold(False)

    out += _safe_encode(separator + "\n")

    # ITEMS DENGAN CHINESE - FORMAT BARIS TERPISAH
    for item in items:
        item_name = (item.get("item_name") or "").strip()
        qty = item.get("qty") or 1
        resto_menu = item.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu) or ""

        # Format qty
        if isinstance(qty, (int, float)):
            qty_str = f"{int(qty)}x"
        else:
            qty_str = f"{qty}x"

        # BARIS 1: Qty + Item Name (Latin, BOLD, Double Height)
        out += _esc_bold(True)
        out += _esc_char_size(0, 1)  # Double height
        line1 = f"{qty_str} {item_name}"
        out += _safe_encode(line1 + "\n")
        out += _esc_char_size(0, 0)
        out += _esc_bold(False)

        # BARIS 2: Chinese name (if exists)
        if mandarin_name:
            out += _safe_encode(f"  {mandarin_name}\n")

        # ADD ONS
        add_ons_str = item.get("add_ons") or ""
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",") if a.strip()]
            for add in add_ons_list:
                add_line = f"  + {add}"
                out += _safe_encode(add_line + "\n")

        # QUICK NOTES
        notes = (item.get("quick_notes") or "").strip()
        if notes:
            note_line = f"  # {notes}"
            out += _safe_encode(note_line + "\n")
        
        # Minimal spacer
        out += _safe_encode("\n")

    # TOTAL QTY
    out += _safe_encode(separator + "\n")
    out += _safe_encode(f"{total_qty} items\n")

    # QUEUE NUMBER (Take Away)
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += _safe_encode("Your Queue Number:\n")
            out += _esc_bold(False)

            out += _esc_align_center()
            out += b"\x1b!\x38"
            out += _safe_encode(f"{queue_no}\n")
            out += b"\x1b!\x00"
            out += _esc_feed(2)

    # Feed minimal + CUT
    out += _esc_feed(3)
    out += _esc_cut_full()  # AUTO CUT!
    
    return out

def _enqueue_checker_worker(name: str, printer_name: str):
    raw = build_escpos_checker(name)

    if not raw:
        frappe.logger("pos_print").info({
            "invoice": name,
            "message": "Tidak ada item baru untuk di-print ke checker"
        })
        return None

    job_id = cups_print_raw(raw, printer_name)

    items_to_update = frappe.db.get_all(
        "POS Invoice Item",
        filters={"parent": name, "is_checked": 0},
        pluck="name"
    )

    if items_to_update:
        for item_name in items_to_update:
            frappe.db.set_value("POS Invoice Item", item_name, "is_checked", 1)

        frappe.db.commit()
        frappe.logger("pos_print").info({
            "invoice": name,
            "updated_items": len(items_to_update),
            "message": "Update is_checked = 1 untuk item yang sudah di-print"
        })

    frappe.logger("pos_print").info({
        "invoice": name,
        "printer": printer_name,
        "job_id": job_id,
        "type": "checker"
    })

    return job_id

@frappe.whitelist(allow_guest=True)
def preview_receipt(name: str):
    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    receipt_bytes = build_escpos_bill(name)
    text = receipt_bytes.decode("utf-8", "ignore")
    text = re.sub(r'[\x00-\x09\x0B-\x1F\x7F-\x9F]', '', text)

    return {
        "preview": text,
        "invoice": name,
        "timestamp": now_datetime()
    }
    
@frappe.whitelist(allow_guest=True)
def preview_checker(name: str):
    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    receipt_bytes = build_escpos_checker(name)
    text = receipt_bytes.decode("utf-8", "ignore")
    text = re.sub(r'[\x00-\x09\x0B-\x1F\x7F-\x9F]', '', text)

    return {
        "preview": text,
        "invoice": name,
        "timestamp": now_datetime()
    }

@frappe.whitelist(allow_guest=True)
def preview_kitchen_receipt_simple(invoice_name: str):
    import re
    from frappe.utils import now_datetime

    if not frappe.db.exists("POS Invoice", invoice_name):
        return {"error": f"POS Invoice {invoice_name} tidak ditemukan"}

    doc = frappe.get_doc("POS Invoice", invoice_name)

    entry = {
        "kitchen_station": doc.branch or "Kitchen",
        "pos_invoice": doc.name,
        "transaction_date": f"{doc.posting_date} {doc.posting_time}",
        "items": []
    }

    for it in doc.items:
        entry["items"].append({
            "resto_menu": it.get("resto_menu") or it.get("item_name"),
            "short_name": it.get("item_name"),
            "qty": it.get("qty"),
            "add_ons": it.get("add_ons"),
            "quick_notes": it.get("quick_notes")
        })

    receipt_bytes = build_kitchen_receipt_from_payload(entry)
    text = receipt_bytes.decode("utf-8", "ignore")
    text = re.sub(r'[\x00-\x09\x0B-\x1F\x7F-\x9F]', '', text)

    return {
        "preview": text.strip(),
        "invoice": invoice_name,
        "timestamp": now_datetime()
    }