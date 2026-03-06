# apps/your_app/your_app/pos_receipt.py

from __future__ import annotations
import math
import tempfile
import frappe
from typing import List, Dict, Any
from frappe.utils import now_datetime
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import requests
import re
import os

# ========== Konstanta & Util ==========
LINE_WIDTH = 32
ITEM_HEIGHT_MULT = 2

ESC = b"\x1b"
GS  = b"\x1d"

# Font paths untuk CJK rendering
CJK_FONT_PATHS = [
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/arphic/uming.ttc',
]

LATIN_FONT_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    '/usr/share/fonts/truetype/freefont/FreeSans.ttf',
]

def _get_cjk_font_path():
    """Cari font CJK yang tersedia di sistem"""
    for path in CJK_FONT_PATHS:
        if os.path.exists(path):
            return path
    return None

def _get_latin_font_path():
    """Cari font Latin yang tersedia di sistem"""
    for path in LATIN_FONT_PATHS:
        if os.path.exists(path):
            return path
    return None

def _contains_cjk(text: str) -> bool:
    """Cek apakah teks mengandung karakter CJK"""
    if not text:
        return False
    for char in text:
        code = ord(char)
        if (0x4E00 <= code <= 0x9FFF) or \
           (0x3400 <= code <= 0x4DBF) or \
           (0x20000 <= code <= 0x2A6DF) or \
           (0x3000 <= code <= 0x303F):
            return True
    return False

def _text_to_escpos_image(text: str, font_size: int = 24, max_width: int = 384) -> bytes:
    """
    Convert text (dengan CJK) ke image bitmap untuk ESC/POS printing
    Lebar 384 pixel = 58mm/80mm thermal printer
    """
    try:
        # Cari font
        font_path = _get_cjk_font_path() or _get_latin_font_path()
        if not font_path:
            # Fallback ke default font
            font = ImageFont.load_default()
        else:
            font = ImageFont.truetype(font_path, font_size)
        
        # Buat image sementara untuk ukur text
        temp_img = Image.new('1', (1, 1), 1)
        draw = ImageDraw.Draw(temp_img)
        
        # Get text size
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        
        # Jika terlalu lebar, wrap atau truncate
        if text_width > max_width:
            # Coba dengan font lebih kecil
            for size in [20, 18, 16]:
                try:
                    font = ImageFont.truetype(font_path, size)
                    bbox = draw.textbbox((0, 0), text, font=font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    if text_width <= max_width:
                        break
                except:
                    continue
        
        # Buat image final
        img_width = max_width
        img_height = text_height + 4  # Padding
        
        image = Image.new('1', (img_width, img_height), 1)  # 1 = white background
        draw = ImageDraw.Draw(image)
        
        # Center text
        x = (img_width - text_width) // 2
        y = 2
        draw.text((x, y), text, font=font, fill=0)  # 0 = black text
        
        # Convert ke ESC/POS bitmap
        return _image_to_escpos_bitmap(image)
        
    except Exception as e:
        frappe.logger("pos_print").error(f"Error converting text to image: {e}")
        # Fallback: return empty
        return b""

def _image_to_escpos_bitmap(image: Image.Image) -> bytes:
    """Convert PIL Image ke ESC/POS bitmap format"""
    # Convert ke 1-bit (monochrome)
    image = image.convert('1')
    
    width = image.width
    height = image.height
    
    # ESC/POS bitmap: GS v 0 (normal) atau GS 8 L (extended)
    # Kita gunakan GS v 0 untuk kompatibilitas lebih baik
    
    bytes_out = b""
    
    # Set line spacing to 0 untuk tight printing
    bytes_out += ESC + b'3' + b'\x00'
    
    width_bytes = (width + 7) // 8
    
    for y in range(height):
        # ESC * m n1 n2 - Print bit-image
        # m = 0 (8-dot single density), 1 (8-dot double density), 32 (24-dot), 33 (24-dot)
        # Kita gunakan mode 33 (24-dot double density) untuk kualitas lebih baik
        line_data = b""
        for x in range(0, width, 8):
            byte = 0
            for bit in range(8):
                if x + bit < width:
                    pixel = image.getpixel((x + bit, y))
                    # PIL 1-bit image: 0 = black, 255 = white
                    if pixel == 0:
                        byte |= (1 << (7 - bit))
            line_data += bytes([byte])
        
        # Print raster bit image: GS v 0 xL xH yL yH
        # atau ESC * m n1 n2 d1...dk
        bytes_out += ESC + b'*' + b'\x33' + bytes([width_bytes % 256, width_bytes // 256]) + line_data + b'\n'
    
    # Reset line spacing
    bytes_out += ESC + b'2'
    
    # Feed sedikit
    bytes_out += ESC + b'd' + b'\x01'
    
    return bytes_out

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

def _esc_cut_full_with_feed() -> bytes:
    return GS + b'V' + b'\x41'

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

def cups_print_pdf(pdf_bytes: bytes, printer_name: str) -> int:
    import cups
    import tempfile

    conn = cups.Connection()
    printers = conn.getPrinters()
    if printer_name not in printers:
        raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name

    job_id = conn.printFile(printer_name, tmp_path, "POS_Invoice", {})
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

# ========== HELPER: Print line dengan CJK support ==========
def _print_line_with_cjk(out: bytes, text: str, encoding: str = "ascii") -> bytes:
    """
    Print satu baris teks. Jika mengandung CJK, convert ke image.
    Jika tidak, gunakan raw ESC/POS text.
    """
    if _contains_cjk(text):
        # Convert ke image bitmap
        image_bytes = _text_to_escpos_image(text, font_size=22, max_width=384)
        return out + image_bytes
    else:
        # Gunakan text biasa
        if encoding == "ascii":
            return out + (text + "\n").encode("ascii", "ignore")
        else:
            return out + (text + "\n").encode("utf-8", "ignore")

# ========== Builder ESC/POS dengan CJK Support ==========
def build_escpos_from_pos_invoice(name: str, add_qr: bool = False, qr_data: str | None = None) -> bytes:
    data = _collect_pos_invoice(name)
    lines = _format_receipt_lines(data)

    out = b""
    out += _esc_init()
    out += _esc_font_a()
    out += _esc_align_left()
    out += _esc_bold(False)

    # Header bold tengah utk judul toko & nomor invoice
    if data["company"]:
        out += _esc_align_center() + _esc_bold(True)
        for h in _wrap_text(data["company"], LINE_WIDTH):
            out = _print_line_with_cjk(out, h)
        out += _esc_bold(False)

    title = f"POS INVOICE {data['name'] or ''}".strip()
    out += _esc_align_center() + _esc_bold(True)
    out = _print_line_with_cjk(out, title)
    out += _esc_bold(False)
    out += _esc_align_left()

    for ln in lines:
        out = _print_line_with_cjk(out, ln)

    # Tambah QR (opsional)
    if add_qr and qr_data:
        out += _esc_align_center()
        out += _esc_qr(qr_data)
        out += _esc_align_left()
        out += _esc_feed(1)

    # Feed bawah + cut
    out += _esc_feed(3) + _esc_cut_full()
    return out

# ========== CUPS RAW PRINT ==========
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
    out = b""
    out += _esc_init()
    out += _esc_font_a()
    out += _esc_char_size(0, 3)
    out += _esc_align_center() + _esc_bold(True)
    
    # KITCHEN ORDER - gunakan image jika ada CJK
    out = _print_line_with_cjk(out, station_name)
    out += _esc_bold(False) + _esc_align_left()

    out += (f"Invoice: {data['name']}\n").encode("ascii", "ignore")
    out += (f"Tanggal: {data['posting_date']} {data['posting_time']}\n").encode("ascii", "ignore")
    out += (f"Petugas: {created_by}\n").encode("ascii", "ignore")

    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out = _print_line_with_cjk(out, f"Table: {table_names}")
        out += _esc_bold(False)

    out += (f"Purpose : {data['order_type']}\n").encode("ascii", "ignore")

    out += _line("-").encode() + b"\n"
    
    # ===== PREPARE MANDARIN MAP =====
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
            if d.custom_mandarin_name
        }

    for it in items:
        qty_val = it.get("qty", 0)
        if isinstance(qty_val, float) and qty_val.is_integer():
            qty = int(qty_val)
        else:
            qty = qty_val

        item_name = it.get("item_name", "")
        resto_menu = it.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu) or ""
        print(f"Item: {item_name}, Mandarin: {mandarin_name}")

        # ===== ITEM UTAMA + MANDARIN =====
        if mandarin_name:
            line = f"{qty} x {item_name} ({mandarin_name})"
        else:
            line = f"{qty} x {item_name}"

        # Gunakan image printing untuk item dengan CJK
        for w in _wrap_text(line, LINE_WIDTH):
            out = _print_line_with_cjk(out, w)

        # ===== ADD ONS =====
        add_ons_str = it.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",") if a.strip()]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, _ = add.rsplit("(", 1)
                    name = name.strip()
                else:
                    name = add

                add_line = f"  {name}"
                for w in _wrap_text(add_line, LINE_WIDTH):
                    out = _print_line_with_cjk(out, w)

        # ===== NOTES =====
        notes = it.get("quick_notes", "")
        if notes:
            note_line = f"  # {notes}"
            for w in _wrap_text(note_line, LINE_WIDTH):
                out = _print_line_with_cjk(out, w)

        # Spasi antar item
        out += b"\n"

    out += _line("-").encode() + b"\n"
    out += _esc_char_size(0, 0)
    out += _esc_feed(3) + _esc_cut_full()
    return out

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
            raw_kitchen = build_kitchen_receipt(data, kprinter, items, created_by=full_name)
            kitchen_job = cups_print_raw(raw_kitchen, kprinter)
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

def _append_wrapped(out: bytes, text: str, indent: int = 0) -> bytes:
    pad = " " * indent if indent > 0 else ""
    for w in _wrap_text(text, LINE_WIDTH - indent):
        out += (pad + w + "\n").encode("ascii", "ignore")
    return out

def build_kitchen_receipt_from_payload(entry: Dict[str, Any], title_prefix: str = "") -> bytes:
    current_user = frappe.session.user
    full_name = frappe.db.get_value("User", current_user, "full_name")

    station = _safe_str(entry.get("kitchen_station")) or "-"
    inv = _safe_str(entry.get("pos_invoice")) or "-"
    tdate = _safe_str(entry.get("transaction_date")) or frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    items = entry.get("items") or []
    
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
            if d.custom_mandarin_name
        }

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # HEADER
    out += _esc_align_center() + _esc_bold(True)
    out = _print_line_with_cjk(out, station)
    out += _esc_bold(False) + _esc_align_left()

    out += (f"Invoice : {inv}\n").encode("ascii", "ignore")
    out += (f"Tanggal : {tdate}\n").encode("ascii", "ignore")
    out += (f"Petugas : {full_name}\n").encode("ascii", "ignore")
    
    out += (_line("-") + "\n").encode("ascii", "ignore")

    # ITEMS
    for it in items:
        qty_s = _fmt_qty(it.get("qty") or 0)
        item_name = _safe_str(it.get("item_name"))
        short_name = _safe_str(it.get("short_name"))
        menu_name = _safe_str(it.get("resto_menu"))
        add_ons = _safe_str(it.get("add_ons"))
        qnotes = _safe_str(it.get("quick_notes"))
        
        title = item_name or short_name or menu_name or "-"
        mandarin_name = mandarin_map.get(it.get("resto_menu")) or ""
        if mandarin_name:
            display_line = f"{qty_s} x {title} ({mandarin_name})"
        else:
            display_line = f"{qty_s} x {title}"

        # Besarkan tinggi
        out += _esc_char_size(0, ITEM_HEIGHT_MULT) + _esc_bold(True)
        big_line = _fit(display_line, LINE_WIDTH)
        out = _print_line_with_cjk(out, big_line)
        out += _esc_bold(False) + _esc_char_size(0, 0)
        
        add_ons_str = it.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",")]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, price = add.rsplit("(", 1)
                    price = price.replace(")", "").strip()
                    name = name.strip()
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12)
                    out = _print_line_with_cjk(out, add_line)
    
        notes = it.get("quick_notes", "")
        if notes:
            out = _print_line_with_cjk(out, f"  # {notes}")

        out += b"\n"

    out += (_line("-") + "\n").encode("ascii", "ignore")
    out += _esc_feed(5)
    out += _esc_cut_full()

    return out

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
            
            raw = build_kitchen_receipt_from_payload(entry)

            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name

            job_id = conn.printFile(printer_name, tmp_path, f"KITCHEN_{station}", {"raw": "true"})
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

# ========== BILL PRINT dengan CJK ==========
def build_escpos_bill(name: str) -> bytes:
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
    
    # Ambil alamat utama Company
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
    
    # ===== PREPARE MANDARIN MAP =====
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

    # ===== HEADER =====
    out += _esc_align_center() + _esc_bold(True)

    company_city_line = f"{company} {city}".strip()
    if company_city_line:
        out = _print_line_with_cjk(out, company_city_line)

    if address1:
        out = _print_line_with_cjk(out, address1)
    if address2:
        out = _print_line_with_cjk(out, address2)
    if phone:
        out = _print_line_with_cjk(out, f"Tlp. {phone}")

    out += _esc_bold(False)
    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")

    # ===== INFORMASI INVOICE =====
    out += (f"No : {data['name']}\n").encode("ascii", "ignore")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")

    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out = _print_line_with_cjk(out, f"Table: {table_names}")
        out += _esc_bold(False)

    out += (f"Purpose : {order_type}\n").encode("ascii", "ignore")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out = _print_line_with_cjk(out, f"Pax : {pax_int}")
        out += _esc_bold(False)

    cashier_name = get_cashier_name(data["name"])
    out = _print_line_with_cjk(out, f"Cashier : {cashier_name}")

    if customer:
        out = _print_line_with_cjk(out, f"Customer: {customer}")

    out += (separator + "\n").encode("ascii", "ignore")

    # ===== ITEMS =====
    for item in items:
        item_name = (item.get("item_name") or "").strip()
        qty = int(item.get("qty") or 0)
        rate = float(item.get("rate") or 0)
        amount = qty * rate
        resto_menu = item.get("resto_menu")

        mandarin_name = mandarin_map.get(resto_menu) or ""

        # ===== NAMA ITEM =====
        if mandarin_name:
            display_name = f"{item_name} ({mandarin_name})"
        else:
            display_name = item_name

        # Gunakan image printing untuk nama item (karena bisa ada CJK)
        out = _print_line_with_cjk(out, display_name)

        # ===== BARIS HARGA =====
        left_part = f"{qty}x @{format_number(rate)}"
        right_part = format_number(amount)
        line = left_part.ljust(LINE_WIDTH - 12) + right_part.rjust(12)
        out += (line + "\n").encode("ascii", "ignore")

        # ===== ADD ONS =====
        add_ons_str = item.get("add_ons") or ""
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",") if a.strip()]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, price = add.rsplit("(", 1)
                    price = price.replace(")", "").strip()
                    name = name.strip()
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12) + format_number(float(price)).rjust(12)
                    out = _print_line_with_cjk(out, add_line)
                else:
                    out = _print_line_with_cjk(out, f"  {add}")

        # ===== NOTES =====
        notes = (item.get("quick_notes") or "").strip()
        if notes:
            out = _print_line_with_cjk(out, f"  # {notes}")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== TOTALS =====
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
        out += (_format_line("Sc:", format_number(sc_amount)) + "\n").encode("ascii", "ignore")

    out += (_format_line("Subtotal:", format_number(total)) + "\n").encode("ascii", "ignore")

    if tax_amount:
        out += (_format_line("Tax:", format_number(tax_amount)) + "\n").encode("ascii", "ignore")
    
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_bold(True)
    out += (_format_line("Grand Total:", format_number(grand_total)) + "\n").encode("ascii", "ignore")
    out += _esc_bold(False)

    # ===== FOOTER =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_align_center()
    out = _print_line_with_cjk(out, "Terima kasih!")
    out = _print_line_with_cjk(out, "Selamat menikmati hidangan Anda!")

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out = _print_line_with_cjk(out, "Your Queue Number:")
            out += _esc_bold(False)
            out += b"\x1b!\x38"
            out += f"{queue_no}\n".encode("ascii", "ignore")
            out += b"\x1b!\x00"
            out += _esc_feed(2)

    out += _esc_feed(8) + _esc_cut_full()
    return out

def _enqueue_bill_worker(name: str, printer_name: str):
    raw = build_escpos_bill(name)
    job_id = cups_print_raw(raw, printer_name)

    frappe.logger("pos_print").info({
        "invoice": name,
        "printer": printer_name,
        "job_id": job_id,
        "type": "bill"
    })

    return job_id

# ========== RECEIPT PRINT ==========
def build_escpos_receipt(name: str) -> bytes:
    # Sama dengan bill untuk sekarang, bisa disesuaikan
    return build_escpos_bill(name)

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

# ========== CHECKER PRINT ==========
def build_escpos_checker(name: str) -> bytes:
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

    total_qty = sum(int(item.get("qty", 0)) for item in items)
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")
    
    # ===== PREPARE MANDARIN MAP =====
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

    # ===== HEADER =====
    out += _esc_align_center() + _esc_bold(True)
    out = _print_line_with_cjk(out, "CHECKER")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out = _print_line_with_cjk(out, header_line)

    out += _esc_bold(False)
    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")
    
    table_names = get_table_names_from_pos_invoice(data["name"])

    out = _print_line_with_cjk(out, f"No Meja : {table_names}")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")
    out += (f"Purpose : {order_type}\n").encode("ascii", "ignore")
    out = _print_line_with_cjk(out, f"Waiter : {get_waiter_name(data['name'])}")
    
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out = _print_line_with_cjk(out, f"Pax : {pax_int}")
        out += _esc_bold(False)

    out += (separator + "\n").encode("ascii", "ignore")

    # ===== ITEMS =====
    for item in items:
        item_name = (item.get("item_name") or "").strip()
        qty = item.get("qty") or 1
        resto_menu = item.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu) or ""

        if isinstance(qty, (int, float)):
            qty_str = f"{int(qty)}x"
        else:
            qty_str = f"{qty}x"

        if mandarin_name:
            full_item_name = f"{item_name} ({mandarin_name})"
        else:
            full_item_name = item_name

        line = f"{qty_str.ljust(5)}{full_item_name}"
        out = _print_line_with_cjk(out, line)

        # ===== ADD ONS =====
        add_ons_str = item.get("add_ons") or ""
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",") if a.strip()]
            for add in add_ons_list:
                out = _print_line_with_cjk(out, " " * 7 + add)

        # ===== QUICK NOTES =====
        notes = (item.get("quick_notes") or "").strip()
        if notes:
            out = _print_line_with_cjk(out, " " * 7 + f"# {notes}")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out = _print_line_with_cjk(out, "Your Queue Number:")
            out += _esc_bold(False)
            out += b"\x1b!\x38"
            out += f"{queue_no}\n".encode("ascii", "ignore")
            out += b"\x1b!\x00"
            out += _esc_feed(2)

    out += _esc_feed(8) + _esc_cut_full()
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

# ========== PREVIEW FUNCTIONS ==========
@frappe.whitelist(allow_guest=True)
def preview_receipt(name: str):
    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    receipt_bytes = build_escpos_bill(name)

    # Untuk preview, kita decode yang bisa saja
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