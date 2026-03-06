# apps/your_app/your_app/pos_receipt.py

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
LINE_WIDTH = 32           # ganti ke 42 jika printer 42 kolom
ITEM_HEIGHT_MULT = 2      # 2 = aman di banyak printer; coba 3 kalau masih kecil

# Konstanta untuk CJK width calculation
CJK_WIDTH = 2  # Karakter CJK dianggap 2 karakter latin
ASCII_WIDTH = 1

ESC = b"\x1b"
GS  = b"\x1d"

# Font paths untuk CJK - sesuaikan dengan sistem Anda
CJK_FONT_PATHS = [
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
]

LATIN_FONT_PATHS = [
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
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

def _get_char_width(char: str) -> int:
    """Hitung lebar karakter: CJK=2, Latin=1"""
    try:
        # Cek apakah karakter CJK
        if '\u4e00' <= char <= '\u9fff' or \
           '\u3400' <= char <= '\u4dbf' or \
           '\u3000' <= char <= '\u303f' or \
           '\uff00' <= char <= '\uffef':
            return CJK_WIDTH
        # East Asian Wide characters
        import unicodedata
        if unicodedata.east_asian_width(char) in ('F', 'W'):
            return CJK_WIDTH
        return ASCII_WIDTH
    except:
        return ASCII_WIDTH

def _calculate_display_width(text: str) -> int:
    """Hitung total lebar display string (CJK=2, Latin=1)"""
    return sum(_get_char_width(c) for c in text)

def _truncate_to_width(text: str, max_width: int, suffix: str = "...") -> str:
    """Truncate text berdasarkan display width, bukan len()"""
    if _calculate_display_width(text) <= max_width:
        return text
    
    current_width = 0
    result = []
    for char in text:
        char_width = _get_char_width(char)
        if current_width + char_width > max_width - _calculate_display_width(suffix):
            return "".join(result) + suffix
        result.append(char)
        current_width += char_width
    return "".join(result)

def _wrap_text_cjk(text: str, width: int) -> List[str]:
    """Wrap text dengan support CJK (karakter CJK = 2 width)"""
    if not text or not text.strip():
        return [""]
    
    words = []
    current_word = ""
    current_width = 0
    
    # Split by whitespace tapi pertahankan CJK characters
    for char in text:
        if char.isspace():
            if current_word:
                words.append((current_word, current_width))
                current_word = ""
                current_width = 0
            words.append((char, _get_char_width(char)))
        else:
            char_w = _get_char_width(char)
            # Jika CJK, treat sebagai word tersendiri
            if char_w == CJK_WIDTH:
                if current_word:
                    words.append((current_word, current_width))
                words.append((char, char_w))
                current_word = ""
                current_width = 0
            else:
                current_word += char
                current_width += char_w
    
    if current_word:
        words.append((current_word, current_width))
    
    lines = []
    current_line = ""
    current_line_width = 0
    
    for word, word_width in words:
        if word.isspace():
            # Whitespace: tambahkan jika tidak di awal line
            if current_line:
                current_line += word
                current_line_width += word_width
        else:
            # Cek apakah muat
            space_needed = 1 if current_line and not current_line.endswith(" ") else 0
            if current_line_width + space_needed + word_width <= width:
                if space_needed and not current_line.endswith(" "):
                    current_line += " "
                    current_line_width += 1
                current_line += word
                current_line_width += word_width
            else:
                # Line baru
                if current_line:
                    lines.append(current_line)
                current_line = word
                current_line_width = word_width
    
    if current_line:
        lines.append(current_line)
    
    return lines if lines else [""]

def _pad_lr_cjk(left: str, right: str, width: int) -> str:
    """Pad left-right dengan support CJK"""
    left_width = _calculate_display_width(left)
    right_width = _calculate_display_width(right)
    
    space = width - left_width - right_width
    if space < 1:
        # Jika terlalu panjang, truncate kiri
        if left_width > width - right_width - 3:
            left = _truncate_to_width(left, width - right_width - 3) + "..."
            left_width = _calculate_display_width(left)
            space = width - left_width - right_width
        if space < 1:
            space = 1
    
    return f"{left}{' ' * space}{right}"

def _fit_cjk(text: str, width: int) -> str:
    """Fit text ke width dengan support CJK"""
    if _calculate_display_width(text) <= width:
        return text
    if width <= 3:
        return _truncate_to_width(text, width)
    return _truncate_to_width(text, width, "...")

def _esc_init() -> bytes:
    # Initialize printer
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
    """Legacy wrapper - gunakan _wrap_text_cjk untuk CJK"""
    # Cek apakah ada karakter CJK
    if any(_get_char_width(c) == CJK_WIDTH for c in text):
        return _wrap_text_cjk(text, width)
    
    # Fallback ke original logic untuk pure ASCII
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
    """Potong ke 1 baris tepat (no wrap) - dengan support CJK."""
    if _calculate_display_width(text) <= width:
        return text
    return _fit_cjk(text, width)

def _line(char: str = "-") -> str:
    return char * LINE_WIDTH

def _format_line(left: str, right: str, width: int = LINE_WIDTH):
    """Format satu baris dengan support CJK"""
    return _pad_lr_cjk(str(left), str(right), width)

def _pad_lr(left: str, right: str, width: int) -> str:
    """Wrapper untuk backward compatibility"""
    return _pad_lr_cjk(left, right, width)

def _esc_print_image(image_path):
    """Convert logo ke ESC/POS format (bitmap)"""
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
    """Print PDF menggunakan CUPS"""
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

def cups_print_raw(raw_bytes: bytes, printer_name: str) -> int:
    """Print raw ESC/POS bytes menggunakan CUPS"""
    try:
        import cups
        conn = cups.Connection()
        printers = conn.getPrinters()
        if printer_name not in printers:
            raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan di CUPS")

        if printer_name == "Kasir":
            # Kirim perintah buka laci
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

# ========== PDF Builder untuk CJK Support ==========
def _create_receipt_pdf(content_items, width_mm=75, output_path=None):
    """
    Membuat PDF receipt dengan support CJK menggunakan ReportLab
    Berdasarkan code pertama yang berhasil
    """
    try:
        from reportlab.lib.pagesizes import mm
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.colors import HexColor
    except ImportError:
        raise ImportError("Install reportlab: pip install reportlab")

    if output_path is None:
        output_path = tempfile.mktemp(suffix='.pdf')

    # Register fonts
    cjk_font_path = _get_cjk_font_path()
    latin_font_path = _get_latin_font_path()
    
    registered_fonts = {}
    
    if cjk_font_path:
        try:
            pdfmetrics.registerFont(TTFont("CJKFont", cjk_font_path))
            registered_fonts['cjk'] = "CJKFont"
            print(f"✓ Registered CJK font: {cjk_font_path}")
        except Exception as e:
            print(f"✗ Failed to register CJK font: {e}")
    
    if latin_font_path:
        try:
            pdfmetrics.registerFont(TTFont("LatinFont", latin_font_path))
            registered_fonts['latin'] = "LatinFont"
        except Exception as e:
            print(f"✗ Failed to register Latin font: {e}")
    
    if not registered_fonts:
        raise Exception("Tidak ada font yang berhasil diregister!")

    # Setup canvas
    page_width = width_mm * mm
    # Hitung tinggi dinamis
    line_height = 4.5 * mm  # Tinggi per baris
    header_height = 20 * mm
    footer_height = 15 * mm
    total_height = header_height + (len(content_items) * line_height) + footer_height
    page_height = max(total_height, 80 * mm)  # Minimum 80mm

    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    
    y_position = page_height - 5 * mm  # Margin atas
    
    cjk_font = registered_fonts.get('cjk', registered_fonts.get('latin'))
    latin_font = registered_fonts.get('latin', registered_fonts.get('cjk'))
    
    # Header
    c.setFont(cjk_font, 12)
    c.setFillColor(HexColor('#000000'))
    
    # Cek apakah ada CJK di header
    header_text = "POS INVOICE"
    test_font = cjk_font if any('\u4e00' <= ch <= '\u9fff' for ch in header_text) else latin_font
    c.setFont(test_font, 12)
    c.drawCentredString(page_width/2, y_position, header_text)
    y_position -= 6 * mm
    
    # Garis pemisah
    c.line(5*mm, y_position, page_width-5*mm, y_position)
    y_position -= 4 * mm
    
    # Konten
    for item in content_items:
        text = item.get('text', '')
        is_cjk = item.get('is_cjk', False)
        font_size = item.get('size', 9)
        bold = item.get('bold', False)
        align = item.get('align', 'left')
        
        # Pilih font
        if is_cjk or any('\u4e00' <= ch <= '\u9fff' for ch in text):
            font = cjk_font
            # Kurangi size untuk CJK agar muat
            font_size = min(font_size, 10)
        else:
            font = latin_font
            
        c.setFont(font, font_size)
        
        # Alignment
        if align == 'center':
            c.drawCentredString(page_width/2, y_position, text)
        elif align == 'right':
            c.drawRightString(page_width-5*mm, y_position, text)
        else:
            c.drawString(5*mm, y_position, text)
        
        y_position -= line_height
        
        if y_position < 10 * mm:
            break
    
    # Footer
    y_position -= 3 * mm
    c.line(5*mm, y_position, page_width-5*mm, y_position)
    y_position -= 5 * mm
    
    c.setFont(cjk_font, 9)
    c.drawCentredString(page_width/2, y_position, "谢谢光临！")
    y_position -= 4 * mm
    c.setFont(latin_font, 8)
    c.drawCentredString(page_width/2, y_position, "Thank You!")
    
    c.save()
    return output_path

def _contains_cjk(text):
    """Cek apakah teks mengandung karakter CJK"""
    if not text:
        return False
    for char in text:
        code = ord(char)
        if (0x4E00 <= code <= 0x9FFF) or \
           (0x3400 <= code <= 0x4DBF) or \
           (0x20000 <= code <= 0x2A6DF):
            return True
    return False

# ========== Normalisasi POS Invoice ==========
def _collect_pos_invoice(name: str) -> Dict[str, Any]:
    """Ambil POS Invoice + items/payments/taxes lewat frappe.get_doc."""
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

# ========== Builder PDF untuk Bill dengan CJK ==========
def build_escpos_bill(name: str) -> bytes:
    """
    Build PDF receipt dengan support CJK (Mandarin, dll)
    Menggunakan ReportLab seperti code pertama yang berhasil
    """
    data = _collect_pos_invoice(name)
    
    # Prepare content items untuk PDF builder
    content_items = []
    cur = data["currency"]
    
    # Header
    if data["company"]:
        content_items.append({
            'text': data["company"],
            'is_cjk': _contains_cjk(data["company"]),
            'size': 11,
            'bold': True,
            'align': 'center'
        })
    
    # Invoice number
    content_items.append({
        'text': f"POS INVOICE {data['name']}",
        'is_cjk': False,
        'size': 10,
        'bold': True,
        'align': 'center'
    })
    
    # Separator line (simulated with text)
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Date
    content_items.append({
        'text': f"Tanggal: {data['posting_date']} {data['posting_time']}",
        'is_cjk': _contains_cjk(f"Tanggal: {data['posting_date']}"),
        'size': 9,
        'align': 'left'
    })
    
    # Customer
    if data["customer_name"]:
        content_items.append({
            'text': f"Customer: {data['customer_name']}",
            'is_cjk': _contains_cjk(data["customer_name"]),
            'size': 9,
            'align': 'left'
        })
    
    # Table
    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        content_items.append({
            'text': f"Table: {table_names}",
            'is_cjk': False,
            'size': 9,
            'bold': True,
            'align': 'left'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Items dengan Mandarin names
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
        mandarin_map = {
            d.name: d.get("custom_mandarin_name") 
            for d in menu_data 
            if d.get("custom_mandarin_name")
        }
    
    for item in data["items"]:
        item_name = item.get("item_name", "")
        qty = int(item.get("qty", 0))
        amount = float(item.get("amount", 0))
        resto_menu = item.get("resto_menu")
        
        # Tambahkan Mandarin name jika ada
        mandarin_name = mandarin_map.get(resto_menu, "")
        if mandarin_name:
            display_name = f"{item_name} ({mandarin_name})"
        else:
            display_name = item_name
        
        # Item name (dengan CJK support)
        content_items.append({
            'text': display_name,
            'is_cjk': _contains_cjk(display_name),
            'size': 9,
            'align': 'left'
        })
        
        # Qty x Rate = Amount
        line_text = f"{qty} x {_fmt_money(item.get('rate', 0), cur)}".ljust(20) + \
                   _fmt_money(amount, cur).rjust(12)
        content_items.append({
            'text': line_text,
            'is_cjk': False,
            'size': 9,
            'align': 'left'
        })
        
        # Add-ons
        add_ons = item.get("add_ons", "")
        if add_ons:
            for add in add_ons.split(","):
                if add.strip():
                    content_items.append({
                        'text': f"  + {add.strip()}",
                        'is_cjk': _contains_cjk(add),
                        'size': 8,
                        'align': 'left'
                    })
        
        # Notes
        notes = item.get("quick_notes", "")
        if notes:
            content_items.append({
                'text': f"  # {notes}",
                'is_cjk': _contains_cjk(notes),
                'size': 8,
                'align': 'left'
            })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Totals
    content_items.append({
        'text': f"Subtotal: {_fmt_money(data['total'], cur)}",
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    if data.get("discount_amount", 0) > 0:
        content_items.append({
            'text': f"Diskon: -{_fmt_money(data['discount_amount'], cur)}",
            'is_cjk': _contains_cjk("Diskon"),
            'size': 9,
            'align': 'left'
        })
    
    for tax in data.get("taxes", []):
        content_items.append({
            'text': f"{tax['description']}: {_fmt_money(tax['amount'], cur)}",
            'is_cjk': _contains_cjk(tax['description']),
            'size': 9,
            'align': 'left'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Grand Total
    content_items.append({
        'text': f"Grand Total: {_fmt_money(data.get('rounded_total') or data.get('grand_total', 0), cur)}",
        'is_cjk': _contains_cjk("Grand Total"),
        'size': 10,
        'bold': True,
        'align': 'left'
    })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Payments
    for pay in data.get("payments", []):
        content_items.append({
            'text': f"{pay['mode_of_payment']}: {_fmt_money(pay['amount'], cur)}",
            'is_cjk': _contains_cjk(pay['mode_of_payment']),
            'size': 9,
            'align': 'left'
        })
    
    # Change
    change = data.get("change_amount", 0)
    if change:
        content_items.append({
            'text': f"Change: {_fmt_money(change, cur)}",
            'is_cjk': _contains_cjk("Change"),
            'size': 9,
            'align': 'left'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Queue number untuk Take Away
    order_type = (data.get("order_type") or "").lower()
    if order_type in ["take away", "takeaway"] and data.get("queue"):
        content_items.append({
            'text': "Your Queue Number:",
            'is_cjk': False,
            'size': 10,
            'bold': True,
            'align': 'center'
        })
        content_items.append({
            'text': str(data["queue"]),
            'is_cjk': False,
            'size': 24,
            'bold': True,
            'align': 'center'
        })
    
    # Footer
    content_items.append({
        'text': "谢谢光临！",
        'is_cjk': True,
        'size': 10,
        'align': 'center'
    })
    content_items.append({
        'text': "Thank You!",
        'is_cjk': False,
        'size': 9,
        'align': 'center'
    })
    
    # Generate PDF
    pdf_path = _create_receipt_pdf(content_items, width_mm=75)
    
    # Read PDF bytes
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    # Cleanup temp file
    try:
        os.remove(pdf_path)
    except:
        pass
    
    return pdf_bytes

def _enqueue_bill_worker(name: str, printer_name: str):
    pdf = build_escpos_bill(name)
    job_id = cups_print_pdf(pdf, printer_name)

    frappe.logger("pos_print").info({
        "invoice": name,
        "printer": printer_name,
        "job_id": job_id,
        "type": "bill"
    })

    return job_id

# ========== Kitchen Receipt dengan CJK Support ==========
def build_kitchen_receipt(data: Dict[str, Any], station_name: str, items: List[Dict], created_by: None) -> bytes:
    """
    Build kitchen receipt PDF dengan CJK support
    """
    content_items = []
    
    # Header
    content_items.append({
        'text': station_name,
        'is_cjk': _contains_cjk(station_name),
        'size': 14,
        'bold': True,
        'align': 'center'
    })
    
    content_items.append({
        'text': f"Invoice: {data['name']}",
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': f"Tanggal: {data['posting_date']} {data['posting_time']}",
        'is_cjk': _contains_cjk("Tanggal"),
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': f"Petugas: {created_by}",
        'is_cjk': _contains_cjk(created_by) if created_by else False,
        'size': 9,
        'align': 'left'
    })
    
    # Table
    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        content_items.append({
            'text': f"Table: {table_names}",
            'is_cjk': False,
            'size': 10,
            'bold': True,
            'align': 'left'
        })
    
    content_items.append({
        'text': f"Purpose: {data['order_type']}",
        'is_cjk': _contains_cjk(data.get("order_type", "")),
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Mandarin mapping
    resto_menus = list(set([
        i.get("resto_menu") for i in items if i.get("resto_menu")
    ]))
    
    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {
            d.name: d.get("custom_mandarin_name")
            for d in menu_data if d.get("custom_mandarin_name")
        }
    
    # Items
    for it in items:
        qty = int(it.get("qty", 0)) if float(it.get("qty", 0)).is_integer() else it.get("qty", 0)
        item_name = it.get("item_name", "")
        resto_menu = it.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu, "")
        
        if mandarin_name:
            display_line = f"{qty} x {item_name} ({mandarin_name})"
        else:
            display_line = f"{qty} x {item_name}"
        
        # Item utama - BESAR & BOLD
        content_items.append({
            'text': display_line,
            'is_cjk': _contains_cjk(display_line),
            'size': 14,  # Besar untuk kitchen
            'bold': True,
            'align': 'left'
        })
        
        # Add-ons
        add_ons = it.get("add_ons", "")
        if add_ons:
            for add in add_ons.split(","):
                if add.strip():
                    # Parse "Nama (harga)"
                    add_text = add.strip()
                    if "(" in add_text and ")" in add_text:
                        name, _ = add_text.rsplit("(", 1)
                        add_text = name.strip()
                    
                    content_items.append({
                        'text': f"  + {add_text}",
                        'is_cjk': _contains_cjk(add_text),
                        'size': 10,
                        'align': 'left'
                    })
        
        # Notes
        notes = it.get("quick_notes", "")
        if notes:
            content_items.append({
                'text': f"  # {notes}",
                'is_cjk': _contains_cjk(notes),
                'size': 10,
                'align': 'left'
            })
        
        # Spacer
        content_items.append({
            'text': "",
            'is_cjk': False,
            'size': 4,
            'align': 'left'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Generate PDF (80mm untuk kitchen)
    pdf_path = _create_receipt_pdf(content_items, width_mm=80)
    
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    try:
        os.remove(pdf_path)
    except:
        pass
    
    return pdf_bytes

# ========== Checker Receipt dengan CJK ==========
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

    content_items = []
    
    # Header
    content_items.append({
        'text': "CHECKER",
        'is_cjk': False,
        'size': 14,
        'bold': True,
        'align': 'center'
    })
    
    company = data.get("company", "")
    branch = data.get("branch", "")
    if company or branch:
        header = f"{company}" + (f" - {branch}" if branch else "")
        content_items.append({
            'text': header,
            'is_cjk': _contains_cjk(header),
            'size': 10,
            'align': 'center'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Info
    table_names = get_table_names_from_pos_invoice(data["name"])
    content_items.append({
        'text': f"No Meja: {table_names}",
        'is_cjk': _contains_cjk("No Meja"),
        'size': 10,
        'bold': True,
        'align': 'left'
    })
    
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")
    content_items.append({
        'text': f"Date: {print_time}",
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': f"Purpose: {data.get('order_type', '')}",
        'is_cjk': _contains_cjk(data.get("order_type", "")),
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': f"Waiter: {get_waiter_name(data['name'])}",
        'is_cjk': _contains_cjk(get_waiter_name(data['name'])),
        'size': 9,
        'align': 'left'
    })
    
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        content_items.append({
            'text': f"Pax: {int(pax)}",
            'is_cjk': False,
            'size': 10,
            'bold': True,
            'align': 'left'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Mandarin mapping
    resto_menus = list(set([
        i.get("resto_menu") for i in items if i.get("resto_menu")
    ]))
    
    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {
            d.name: d.get("custom_mandarin_name")
            for d in menu_data if d.get("custom_mandarin_name")
        }
    
    # Items
    for item in items:
        qty = item.get("qty", 0)
        if isinstance(qty, float) and qty.is_integer():
            qty = int(qty)
        
        item_name = item.get("item_name", "")
        resto_menu = item.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu, "")
        
        if mandarin_name:
            display_line = f"{qty}x {item_name} ({mandarin_name})"
        else:
            display_line = f"{qty}x {item_name}"
        
        content_items.append({
            'text': display_line,
            'is_cjk': _contains_cjk(display_line),
            'size': 11,
            'bold': True,
            'align': 'left'
        })
        
        # Add-ons
        add_ons = item.get("add_ons", "")
        if add_ons:
            for add in add_ons.split(","):
                if add.strip():
                    content_items.append({
                        'text': f"     {add.strip()}",
                        'is_cjk': _contains_cjk(add),
                        'size': 9,
                        'align': 'left'
                    })
        
        # Notes
        notes = item.get("quick_notes", "")
        if notes:
            content_items.append({
                'text': f"     # {notes}",
                'is_cjk': _contains_cjk(notes),
                'size': 9,
                'align': 'left'
            })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Queue number untuk Take Away
    order_type = (data.get("order_type") or "").lower()
    if order_type in ["take away", "takeaway"] and data.get("queue"):
        content_items.append({
            'text': "Your Queue Number:",
            'is_cjk': False,
            'size': 10,
            'bold': True,
            'align': 'center'
        })
        content_items.append({
            'text': str(data["queue"]),
            'is_cjk': False,
            'size': 20,
            'bold': True,
            'align': 'center'
        })
    
    # Generate PDF
    pdf_path = _create_receipt_pdf(content_items, width_mm=75)
    
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    try:
        os.remove(pdf_path)
    except:
        pass
    
    return pdf_bytes

def _enqueue_checker_worker(name: str, printer_name: str):
    pdf = build_escpos_checker(name)

    if not pdf:
        frappe.logger("pos_print").info({
            "invoice": name,
            "message": "Tidak ada item baru untuk di-print ke checker"
        })
        return None

    job_id = cups_print_pdf(pdf, printer_name)

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

# ========== Kitchen Receipt from Payload dengan CJK ==========
def build_kitchen_receipt_from_payload(entry: Dict[str, Any], title_prefix: str = "") -> bytes:
    current_user = frappe.session.user
    full_name = frappe.db.get_value("User", current_user, "full_name")

    station = entry.get("kitchen_station", "Kitchen") or "-"
    inv = entry.get("pos_invoice", "-")
    tdate = entry.get("transaction_date") or frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    items = entry.get("items", [])
    
    content_items = []
    
    # Header
    content_items.append({
        'text': station,
        'is_cjk': _contains_cjk(station),
        'size': 16,
        'bold': True,
        'align': 'center'
    })
    
    content_items.append({
        'text': f"Invoice: {inv}",
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': f"Tanggal: {tdate}",
        'is_cjk': _contains_cjk("Tanggal"),
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': f"Petugas: {full_name}",
        'is_cjk': _contains_cjk(full_name) if full_name else False,
        'size': 9,
        'align': 'left'
    })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Mandarin mapping
    resto_menus = list(set([
        i.get("resto_menu") for i in items if i.get("resto_menu")
    ]))
    
    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {
            d.name: d.get("custom_mandarin_name")
            for d in menu_data if d.get("custom_mandarin_name")
        }
    
    # Items
    for it in items:
        qty = it.get("qty", 0)
        if isinstance(qty, float) and qty.is_integer():
            qty = int(qty)
        
        item_name = it.get("item_name", "") or it.get("short_name", "") or it.get("resto_menu", "-")
        mandarin_name = mandarin_map.get(it.get("resto_menu"), "")
        
        if mandarin_name:
            display_line = f"{qty} x {item_name} ({mandarin_name})"
        else:
            display_line = f"{qty} x {item_name}"
        
        # BESAR untuk kitchen
        content_items.append({
            'text': display_line,
            'is_cjk': _contains_cjk(display_line),
            'size': 16,  # Besar untuk mudah dibaca kitchen
            'bold': True,
            'align': 'left'
        })
        
        # Add-ons
        add_ons = it.get("add_ons", "")
        if add_ons:
            for add in add_ons.split(","):
                if add.strip():
                    # Parse harga
                    add_text = add.strip()
                    if "(" in add_text and ")" in add_text:
                        name, _ = add_text.rsplit("(", 1)
                        add_text = name.strip()
                    
                    content_items.append({
                        'text': f"  {add_text}",
                        'is_cjk': _contains_cjk(add_text),
                        'size': 11,
                        'align': 'left'
                    })
        
        # Notes
        notes = it.get("quick_notes", "")
        if notes:
            content_items.append({
                'text': f"  # {notes}",
                'is_cjk': _contains_cjk(notes),
                'size': 11,
                'align': 'left'
            })
        
        # Spacer
        content_items.append({
            'text': "",
            'is_cjk': False,
            'size': 3,
            'align': 'left'
        })
    
    content_items.append({
        'text': "-" * 32,
        'is_cjk': False,
        'size': 9,
        'align': 'left'
    })
    
    # Generate PDF (80mm untuk kitchen)
    pdf_path = _create_receipt_pdf(content_items, width_mm=80)
    
    with open(pdf_path, 'rb') as f:
        pdf_bytes = f.read()
    
    try:
        os.remove(pdf_path)
    except:
        pass
    
    return pdf_bytes

# ========== Receipt Printer (Raw ESC/POS untuk non-CJK) ==========
def build_escpos_receipt(name: str) -> bytes:
    """
    Fallback ke raw ESC/POS untuk printer yang tidak support PDF
    TAPI dengan CJK yang di-convert ke image (jika diperlukan)
    """
    data = _collect_pos_invoice(name)
    
    # Cek apakah ada CJK content
    has_cjk = any(_contains_cjk(str(v)) for v in [
        data.get("company", ""),
        data.get("customer_name", ""),
    ] + [it.get("item_name", "") for it in data.get("items", [])])
    
    # Jika ada CJK, gunakan PDF approach
    if has_cjk:
        return build_escpos_bill(name)  # Return PDF bytes
    
    # Jika tidak ada CJK, gunakan raw ESC/POS (original logic)
    items = data.get("items", [])
    payments = data.get("payments", [])
    taxes = data.get("taxes", [])

    company = data.get("company") or ""
    order_type = data.get("order_type") or ""
    customer = data.get("customer_name") or data.get("customer") or ""
    total = data.get("total", 0)
    grand_total = data.get("grand_total", 0)
    change = data.get("change_amount", 0)
    
    separator = "-" * LINE_WIDTH

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # Header
    out += _esc_align_center() + _esc_bold(True)
    if company:
        out += (company + "\n").encode("ascii", "ignore")
    out += _esc_bold(False)
    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")

    # Info
    out += (f"No : {data['name']}\n").encode("ascii", "ignore")
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")

    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += (f"Table: {table_names}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (separator + "\n").encode("ascii", "ignore")

    # Items
    for item in items:
        item_name = item.get("item_name", "")
        qty = int(item.get("qty", 0))
        rate = item.get("rate", 0)
        amount = rate * qty

        out += (f"{item_name}\n").encode("ascii", "ignore")
        line = f"{qty}x @{format_number(rate)}".ljust(LINE_WIDTH - 12) + f"{format_number(amount).rjust(12)}"
        out += (line + "\n").encode("ascii", "ignore")

    # Totals
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_bold(True)
    out += (_format_line("Grand Total:", format_number(grand_total)) + "\n").encode("ascii", "ignore")
    out += _esc_bold(False)

    # Payments
    for pay in payments:
        mop = pay.get("mode_of_payment") or "-"
        amt = pay.get("amount") or 0
        out += (f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n").encode("ascii", "ignore")

    if change:
        out += (f"Change:".rjust(LINE_WIDTH - 12) + f"{format_number(change).rjust(12)}\n").encode("ascii", "ignore")

    # Footer
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_align_center()
    out += b"Thank You!\n"

    # Queue
    if (order_type or "").lower() in ["take away", "takeaway"] and data.get("queue"):
        out += _esc_feed(2)
        out += _esc_align_center()
        out += _esc_bold(True)
        out += b"Queue Number:\n"
        out += _esc_bold(False)
        out += b"\x1b!\x38"  # Double size
        out += f"{data['queue']}\n".encode("ascii", "ignore")
        out += b"\x1b!\x00"
        out += _esc_feed(2)

    out += _esc_feed(8) + _esc_cut_full()
    return out

def _enqueue_receipt_worker(name: str, printer_name: str):
    raw = build_escpos_receipt(name)
    job_id = cups_print_pdf(raw, printer_name) if raw[:4] == b'%PDF' else cups_print_raw(raw, printer_name)

    frappe.logger("pos_print").info({
        "invoice": name,
        "printer": printer_name,
        "job_id": job_id,
        "type": "receipt"
    })

    return job_id

# ========== API Functions ==========
@frappe.whitelist()
def pos_invoice_print_now(name: str, printer_name: str, add_qr: int = 0, qr_data: str | None = None) -> dict:
    try:
        data = _collect_pos_invoice(name)
        doc = frappe.get_doc("POS Invoice", name)

        full_name = frappe.db.get_value("User", doc.owner, "full_name")

        results = []

        # Bill print (PDF dengan CJK support)
        pdf = build_escpos_bill(name)
        job_id = cups_print_pdf(pdf, printer_name)
        results.append({"printer": printer_name, "job_id": job_id, "type": "bill"})

        # Kitchen prints
        kitchen_groups: Dict[str, List[Dict]] = {}
        for it in data["items"]:
            for printer in get_item_printers(it):
                kitchen_groups.setdefault(printer, []).append(it)

        for kprinter, items in kitchen_groups.items():
            kitchen_pdf = build_kitchen_receipt(data, kprinter, items, created_by=full_name)
            kitchen_job = cups_print_pdf(kitchen_pdf, kprinter)
            results.append({"printer": kprinter, "job_id": kitchen_job, "type": "kitchen"})

        frappe.msgprint(f"POS Invoice {name} terkirim ke {len(results)} printer")
        return {"ok": True, "jobs": results}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "POS Invoice Print Error")
        frappe.throw(f"Gagal print invoice {name}: {str(e)}")

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
            station = entry.get("kitchen_station", "")
            printer_name = entry.get("printer_name", "") or station
            if not station:
                raise ValueError("Setiap entry wajib memiliki 'kitchen_station'")
            if not printer_name:
                raise ValueError("Setiap entry wajib memiliki 'printer_name'")

            if printer_name not in printers:
                raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan di CUPS")

            entry.setdefault("pos_invoice", "")
            entry.setdefault("transaction_date", frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"))
            entry.setdefault("items", [])
            
            pdf = build_kitchen_receipt_from_payload(entry)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(pdf)
                tmp_path = tmp.name

            job_id = conn.printFile(printer_name, tmp_path, f"KITCHEN_{station}", {})
            results.append({
                "station": station,
                "printer": printer_name,
                "job_id": job_id,
                "pos_invoice": entry.get("pos_invoice", ""),
            })

        frappe.msgprint(f"{len(results)} kitchen ticket dikirim ke printer")
        return {"ok": True, "jobs": results}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Kitchen Print Error (from payload)")
        frappe.throw(f"Gagal print kitchen: {str(e)}")

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
    pdf = build_escpos_bill(name)
    job_id = cups_print_pdf(pdf, printer_name)
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

# ========== Preview Functions ==========
@frappe.whitelist(allow_guest=True)
def preview_receipt(name: str):
    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    pdf_bytes = build_escpos_bill(name)
    
    # Convert PDF ke text representation untuk preview
    text = "[PDF Receipt dengan CJK Support]\n\n"
    
    # Decode untuk preview (extract text dari PDF tidak mudah, jadi kita buat summary)
    data = _collect_pos_invoice(name)
    
    lines = []
    lines.append(f"Company: {data.get('company', '')}")
    lines.append(f"Invoice: {data.get('name', '')}")
    lines.append(f"Date: {data.get('posting_date', '')} {data.get('posting_time', '')}")
    lines.append(f"Customer: {data.get('customer_name', '')}")
    lines.append("-" * 40)
    
    for item in data.get("items", []):
        lines.append(f"{item.get('qty', 0)} x {item.get('item_name', '')}")
        if item.get("add_ons"):
            lines.append(f"   + {item.get('add_ons')}")
        if item.get("quick_notes"):
            lines.append(f"   # {item.get('quick_notes')}")
    
    lines.append("-" * 40)
    lines.append(f"Total: {data.get('grand_total', 0)}")
    
    text += "\n".join(lines)

    return {
        "preview": text,
        "invoice": name,
        "timestamp": now_datetime(),
        "pdf_size": len(pdf_bytes)
    }
    
@frappe.whitelist(allow_guest=True)
def preview_checker(name: str):
    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    pdf_bytes = build_escpos_checker(name)
    
    if not pdf_bytes:
        return {
            "preview": "Tidak ada item baru untuk checker",
            "invoice": name,
            "timestamp": now_datetime()
        }

    text = "[PDF Checker dengan CJK Support]\n\n"
    
    data = _collect_pos_invoice(name)
    lines = []
    lines.append("CHECKER")
    lines.append(f"Table: {get_table_names_from_pos_invoice(name)}")
    lines.append("-" * 40)
    
    # Get unchecked items only
    items = [
        item for item in data.get("items", [])
        if int(item.get("is_checked") or 0) == 0
        and item.get("status_kitchen") == "Already Send To Kitchen"
    ]
    
    for item in items:
        lines.append(f"{item.get('qty', 0)}x {item.get('item_name', '')}")
        if item.get("add_ons"):
            lines.append(f"   {item.get('add_ons')}")
        if item.get("quick_notes"):
            lines.append(f"   # {item.get('quick_notes')}")
    
    text += "\n".join(lines)

    return {
        "preview": text,
        "invoice": name,
        "timestamp": now_datetime(),
        "pdf_size": len(pdf_bytes)
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

    pdf_bytes = build_kitchen_receipt_from_payload(entry)

    text = "[PDF Kitchen dengan CJK Support]\n\n"
    text += f"Station: {entry['kitchen_station']}\n"
    text += f"Invoice: {entry['pos_invoice']}\n"
    text += "-" * 40 + "\n"
    
    for it in entry["items"]:
        text += f"{it.get('qty', 0)} x {it.get('resto_menu', '')}\n"
        if it.get("add_ons"):
            text += f"   + {it.get('add_ons')}\n"
        if it.get("quick_notes"):
            text += f"   # {it.get('quick_notes')}\n"

    return {
        "preview": text.strip(),
        "invoice": invoice_name,
        "timestamp": now_datetime(),
        "pdf_size": len(pdf_bytes)
    }