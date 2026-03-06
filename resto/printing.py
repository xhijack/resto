from __future__ import annotations
import math
import tempfile
import frappe
from typing import List, Dict, Any  # <-- TAMBAHKAN IMPORT INI
from frappe.utils import now_datetime
from PIL import Image
from io import BytesIO
import requests
import re
import os

# ========== Konstanta & Util ==========
LINE_WIDTH = 32           # ganti ke 42 jika printer 42 kolom
ITEM_HEIGHT_MULT = 2      # 2 = aman di banyak printer; coba 3 kalau masih kecil

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
    # Font A (normal). Untuk memperkecil, pakai Font B atau mode double-wide/height.
    return ESC + b'M' + b'\x00'

def _esc_cut_full() -> bytes:
    # GS V 0 (full cut) - umum didukung
    return GS + b'V' + b'\x00'

def _esc_cut_full_with_feed() -> bytes:
    # GS V 65 (Function B: full cut with feed) - jika printer mendukung (mis. Epson)
    return GS + b'V' + b'\x41'

def _esc_feed(n: int) -> bytes:
    # Feed n baris
    n = max(0, min(n, 255))
    return ESC + b'd' + bytes([n])

def _esc_qr(data: str) -> bytes:
    """
    ESC/POS QR (model umum)
    Model 2, ukuran 4, koreksi M
    """
    store_pL = (len(data) + 3) & 0xFF
    store_pH = (len(data) + 3) >> 8
    cmds = b""
    # Select model: 2
    cmds += GS + b'(' + b'k' + b'\x04\x00' + b'1A' + b'\x02\x00'
    # Set size: 4 (1..16)
    cmds += GS + b'(' + b'k' + b'\x03\x00' + b'1C' + b'\x04'
    # Set error correction: 48 + 1 (L=48,M=49,Q=50,H=51) -> M
    cmds += GS + b'(' + b'k' + b'\x03\x00' + b'1E' + b'\x31'
    # Store data
    cmds += GS + b'(' + b'k' + bytes([store_pL, store_pH]) + b'1P0' + data.encode('utf-8')
    # Print
    cmds += GS + b'(' + b'k' + b'\x03\x00' + b'1Q' + b'\x30'
    return cmds

def _esc_char_size(width_mul: int = 0, height_mul: int = 0) -> bytes:
    """Set character size via GS '!' n (0..7 multiplier -> 1x..8x)."""
    w = max(0, min(7, int(width_mul)))
    h = max(0, min(7, int(height_mul)))
    return GS + b'!' + bytes([(w << 4) | h])

def _esc_chinese_mode(on: bool = True) -> bytes:
    """
    Enable/disable Chinese character mode untuk printer yang support GB2312/GBK.
    Untuk Epson: FS & (enable), FS . (disable)
    """
    if on:
        # Enable Chinese mode (FS &)
        return b'\x1c\x26'
    else:
        # Disable Chinese mode (FS .)
        return b'\x1c\x2e'

def _esc_set_chinese_codepage() -> bytes:
    """
    Set codepage untuk Chinese characters.
    Untuk banyak printer thermal: ESC t n (select character code table)
    0x00 = PC437 (USA), 0x15 = WPC1252, 0x48 = UTF-8 (jika support)
    """
    # Coba set ke UTF-8 jika printer support, atau GB2312 (0x00 untuk default Chinese)
    # ESC t n - select character code table
    return ESC + b't' + b'\x00'  # Default, atau coba b'\x30' untuk Chinese

def _fmt_money(val: float, currency: str = "IDR") -> str:
    # Format IDR tanpa desimal
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
    """Potong ke 1 baris tepat (no wrap)."""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"

def _line(char: str = "-") -> str:
    return char * LINE_WIDTH  # tepat sepanjang kolom

def _format_line(left: str, right: str, width: int = LINE_WIDTH):
    """
    Format satu baris agar teks kiri dan kanan rata sesuai lebar kertas printer.
    Contoh hasil:
    'Subtotal:                           50,000'
    """
    left = str(left)
    right = str(right)

    # Hitung jumlah spasi di tengah
    space = width - len(left) - len(right)
    if space < 1:
        space = 1  # minimal 1 spasi biar gak nabrak

    return f"{left}{' ' * space}{right}"

def _pad_lr(left: str, right: str, width: int) -> str:
    # Satu baris: left ... right (rata kiri-kanan)
    space = width - len(left) - len(right)
    if space < 1:
        return (left + " " + right)[0:width]
    return f"{left}{' ' * space}{right}"

def _contains_cjk(text: str) -> bool:
    """Cek apakah teks mengandung karakter CJK (Chinese, Japanese, Korean)"""
    if not text:
        return False
    for char in text:
        code = ord(char)
        # CJK Unified Ideographs (Chinese characters)
        if (0x4E00 <= code <= 0x9FFF) or \
           (0x3400 <= code <= 0x4DBF) or \
           (0x20000 <= code <= 0x2A6DF) or \
           (0xF900 <= code <= 0xFAFF):  # CJK Compatibility Ideographs
            return True
    return False

def _safe_encode(text: str) -> bytes:
    """
    Encode text untuk printer thermal dengan support Chinese characters.
    Menggunakan GB18030 (support semua Chinese chars) atau UTF-8 dengan fallback.
    """
    if not text:
        return b""
    
    try:
        # Coba GB18030 dulu (support Chinese paling lengkap untuk printer China)
        return text.encode('gb18030', 'ignore')
    except:
        try:
            # Fallback ke UTF-8
            return text.encode('utf-8', 'ignore')
        except:
            # Last resort: ASCII dengan ignore
            return text.encode('ascii', 'ignore')

def _esc_print_image(image_path):
    """
    Convert logo ke ESC/POS format (bitmap)
    """
    # URL absolut jika path logo berupa /files/...
    if image_path.startswith("/"):
        image_url = frappe.utils.get_url(image_path)
    else:
        image_url = image_path

    # Ambil file gambar
    response = requests.get(image_url)
    image = Image.open(BytesIO(response.content)).convert("L")  # ubah ke grayscale

    # Resize agar muat di kertas 58mm (lebar sekitar 384 pixel)
    max_width = 384
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, int(image.height * ratio)))

    # Convert ke hitam putih
    image = image.point(lambda x: 0 if x < 128 else 255, '1')

    # Konversi ke byte ESC/POS
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

    # Reset align ke tengah
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
        "doc": doc,  # original doc kalau mau ambil field lain
    }

# ========== Formatter Teks ke Baris ==========
def _format_receipt_lines(data: Dict[str, Any]) -> List[str]:
    cur = data["currency"]
    lines: List[str] = []

    # Header Toko (Company)
    if data["company"]:
        for h in _wrap_text(data["company"], LINE_WIDTH):
            lines.append(h.center(LINE_WIDTH))
    title = f"POS INVOICE {data['name'] or ''}".strip()
    lines.append(title.center(LINE_WIDTH))
    lines.append(_line("-"))

    # Tanggal, Kasir (jika mau tambah owner, ambil dari doc.owner atau submitter)
    lines.append(_pad_lr(f"Tanggal", f"{data['posting_date']} {data['posting_time']}", LINE_WIDTH))
    if data["customer_name"]:
        lines.append(_pad_lr("Customer", data["customer_name"], LINE_WIDTH))
    lines.append(_line("-"))

    # Items
    for it in data["items"]:
        name = it["item_name"] or it["item_code"] or "-"
        for w in _wrap_text(name, LINE_WIDTH):
            lines.append(w)
        qty_rate = f"{int(it['qty']) if it['qty'].is_integer() else it['qty']} x {_fmt_money(it['rate'], cur)}"
        amount = _fmt_money(it["amount"], cur)
        lines.append(_pad_lr("  " + qty_rate, amount, LINE_WIDTH))
        if it.get("discount_amount") or it.get("discount_percentage"):
            dsc = it.get("discount_amount") or 0
            dpc = it.get("discount_percentage") or 0
            info = f"  Diskon {dpc:.0f}%"
            if dsc:
                info += f" ({_fmt_money(dsc, cur)})"
            lines.append(_pad_lr(info, "", LINE_WIDTH))

    lines.append(_line("-"))

    # Subtotal / Discount / Taxes
    lines.append(_pad_lr("Subtotal", _fmt_money(data["total"], cur), LINE_WIDTH))
    if data.get("discount_amount", 0) > 0:
        lines.append(_pad_lr("Diskon", "-" + _fmt_money(data["discount_amount"], cur), LINE_WIDTH))

    if data["taxes"]:
        for tx in data["taxes"]:
            desc = tx["description"] or "Tax"
            amt  = tx["amount"] or 0.0
            lines.append(_pad_lr(desc, _fmt_money(amt, cur), LINE_WIDTH))

    gt = data.get("rounded_total") or data.get("grand_total") or 0
    if data.get("rounded_total") and abs(data["rounded_total"] - data["grand_total"]) >= 0.5:
        lines.append(_pad_lr("Grand Total", _fmt_money(data["grand_total"], cur), LINE_WIDTH))
        lines.append(_pad_lr("Rounded", _fmt_money(data["rounded_total"], cur), LINE_WIDTH))
    else:
        lines.append(_pad_lr("Grand Total", _fmt_money(gt, cur), LINE_WIDTH))

    lines.append(_line("-"))

    # Payments
    paid_sum = 0.0
    for p in data["payments"]:
        paid_sum += p["amount"]
        lines.append(_pad_lr(p["mode_of_payment"], _fmt_money(p["amount"], cur), LINE_WIDTH))

    lines.append(_pad_lr("Jumlah Bayar", _fmt_money(paid_sum, cur), LINE_WIDTH))
    change = data.get("change_amount", max(0.0, paid_sum - gt))
    lines.append(_pad_lr("Kembalian", _fmt_money(change, cur), LINE_WIDTH))

    # Loyalty (opsional)
    if (data.get("loyalty_points") or 0) > 0:
        lines.append(_pad_lr("Loyalty Pts", str(data["loyalty_points"]), LINE_WIDTH))
    if (data.get("loyalty_amount") or 0) > 0:
        lines.append(_pad_lr("Loyalty Amt", _fmt_money(data["loyalty_amount"], cur), LINE_WIDTH))

    lines.append(_line("-"))

    # Footer
    if data.get("remarks"):
        for w in _wrap_text(data["remarks"], LINE_WIDTH):
            lines.append(w)
    lines.append("Terima kasih & selamat berbelanja!".center(LINE_WIDTH))
    lines.append(" ".center(LINE_WIDTH))

    return lines

# ========== MULTILINGUAL PDF GENERATOR ==========
class MultilingualReceiptGenerator:
    """
    Generator PDF untuk receipt dengan support Chinese (Mandarin) characters.
    Menggunakan ReportLab untuk generate PDF yang bisa diprint ke printer thermal.
    """
    
    def __init__(self, page_width_mm=75):
        self.page_width_mm = page_width_mm
        self.margin_mm = 3  # margin kiri/kanan dalam mm
        
        # Register fonts CJK
        self.font_paths = {
            'wqy-zenhei': '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
            'wqy-microhei': '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
            'noto-sans-cjk': '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
            'noto-sans-cjk-sc': '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
            'dejavu': '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            'liberation': '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        }
        
        self.registered_fonts = {}
        self._register_fonts()
        
    def _register_fonts(self):
        """Register fonts yang tersedia di sistem"""
        try:
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            
            for font_name, font_path in self.font_paths.items():
                if os.path.exists(font_path):
                    try:
                        register_name = f"Font_{font_name}"
                        pdfmetrics.registerFont(TTFont(register_name, font_path))
                        self.registered_fonts[font_name] = register_name
                    except Exception as e:
                        frappe.logger().debug(f"Failed to register font {font_name}: {e}")
                        
        except ImportError:
            frappe.throw("ReportLab tidak terinstall. Install dengan: pip install reportlab")
    
    def _get_cjk_font(self):
        """Get font CJK yang tersedia"""
        for font_key in ['wqy-zenhei', 'noto-sans-cjk', 'noto-sans-cjk-sc', 'wqy-microhei']:
            if font_key in self.registered_fonts:
                return self.registered_fonts[font_key]
        return None
    
    def _get_latin_font(self):
        """Get font Latin yang tersedia"""
        for font_key in ['dejavu', 'liberation']:
            if font_key in self.registered_fonts:
                return self.registered_fonts[font_key]
        # Fallback ke default Helvetica jika tidak ada
        return 'Helvetica'
    
    def _contains_cjk(self, text: str) -> bool:
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
    
    def create_receipt_pdf(self, content_lines: List[Dict], title: str = "Receipt") -> bytes:
        """
        Create PDF receipt dari list of content lines.
        
        Args:
            content_lines: List of dict dengan keys:
                - text: string content
                - size: font size (default 9)
                - bold: boolean
                - align: 'left', 'center', 'right'
                - is_cjk: auto-detected if not provided
        """
        from reportlab.lib.pagesizes import mm
        from reportlab.pdfgen import canvas
        from reportlab.lib.colors import HexColor
        
        cjk_font = self._get_cjk_font()
        latin_font = self._get_latin_font()
        
        if not cjk_font:
            frappe.logger().warning("Font CJK tidak ditemukan, Chinese characters mungkin tidak tampil")
        
        # Hitung tinggi yang dibutuhkan
        total_height_mm = self._calculate_height(content_lines)
        
        # Buat PDF
        page_size = (self.page_width_mm * mm, total_height_mm * mm)
        
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=page_size)
        
        width = self.page_width_mm * mm
        y_pos = total_height_mm * mm - (3 * mm)  # Start dari atas dengan margin
        
        for line in content_lines:
            text = line.get('text', '')
            size = line.get('size', 9)
            bold = line.get('bold', False)
            align = line.get('align', 'left')
            is_cjk = line.get('is_cjk', self._contains_cjk(text))
            
            # Pilih font
            if is_cjk and cjk_font:
                font = cjk_font
                size = min(size, 11)  # Kurangi size untuk CJK
            else:
                font = latin_font
            
            c.setFont(font, size)
            
            # Hitung posisi X berdasarkan alignment
            if align == 'center':
                c.drawCentredString(width / 2, y_pos, text)
            elif align == 'right':
                c.drawRightString(width - (self.margin_mm * mm), y_pos, text)
            else:
                c.drawString(self.margin_mm * mm, y_pos, text)
            
            # Move down
            line_height = size * 0.35  # mm per point
            y_pos -= (line_height + 1) * mm
        
        c.save()
        buffer.seek(0)
        return buffer.getvalue()
    
    def _calculate_height(self, content_lines: List[Dict]) -> float:
        """Hitung tinggi total yang dibutuhkan dalam mm"""
        height = 10  # Margin atas/bawah
        
        for line in content_lines:
            size = line.get('size', 9)
            is_cjk = line.get('is_cjk', False)
            text = line.get('text', '')
            
            if is_cjk:
                size = min(size, 11)
            
            # Estimasi tinggi per baris
            line_height = size * 0.35
            height += line_height + 1
        
        return max(height, 50)  # Minimum 50mm

def build_multilingual_kitchen_pdf(data: Dict[str, Any], station_name: str, items: List[Dict], created_by: str = None) -> bytes:
    """
    Build kitchen receipt sebagai PDF dengan support Chinese characters.
    """
    generator = MultilingualReceiptGenerator(page_width_mm=75)
    
    content_lines = []
    
    # Header
    content_lines.append({'text': station_name, 'size': 14, 'bold': True, 'align': 'center', 'is_cjk': False})
    content_lines.append({'text': '', 'size': 4})  # Spacer
    
    # Info
    content_lines.append({'text': f"Invoice: {data['name']}", 'size': 9, 'align': 'left'})
    content_lines.append({'text': f"Tanggal: {data['posting_date']} {data['posting_time']}", 'size': 9})
    if created_by:
        content_lines.append({'text': f"Petugas: {created_by}", 'size': 9})
    
    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        content_lines.append({'text': f"Table: {table_names}", 'size': 10, 'bold': True})
    
    content_lines.append({'text': f"Purpose: {data['order_type']}", 'size': 9})
    content_lines.append({'text': '-' * 32, 'size': 9})
    
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
    
    # Items
    for it in items:
        qty = int(it.get('qty', 0)) if float(it.get('qty', 0)).is_integer() else it.get('qty', 0)
        item_name = it.get('item_name', '')
        resto_menu = it.get('resto_menu')
        mandarin_name = mandarin_map.get(resto_menu, '')
        
        # Main item line dengan Chinese
        if mandarin_name:
            display_text = f"{qty} x {item_name} ({mandarin_name})"
            is_cjk = True
        else:
            display_text = f"{qty} x {item_name}"
            is_cjk = False
        
        content_lines.append({
            'text': display_text,
            'size': 11,
            'bold': True,
            'is_cjk': is_cjk
        })
        
        # Add-ons
        add_ons = it.get('add_ons', '')
        if add_ons:
            for add in [a.strip() for a in add_ons.split(',') if a.strip()]:
                if '(' in add and ')' in add:
                    name = add.rsplit('(', 1)[0].strip()
                else:
                    name = add
                content_lines.append({
                    'text': f"  {name}",
                    'size': 9,
                    'is_cjk': _contains_cjk(name)
                })
        
        # Notes
        notes = it.get('quick_notes', '')
        if notes:
            content_lines.append({
                'text': f"  # {notes}",
                'size': 9,
                'is_cjk': _contains_cjk(notes)
            })
        
        content_lines.append({'text': '', 'size': 3})  # Spacer antar item
    
    content_lines.append({'text': '-' * 32, 'size': 9})
    
    return generator.create_receipt_pdf(content_lines, title=f"Kitchen_{station_name}")

# ========== Builder ESC/POS ==========
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
            out += _safe_encode(h + "\n")
        out += _esc_bold(False)

    title = f"POS INVOICE {data['name'] or ''}".strip()
    out += _esc_align_center() + _esc_bold(True) + _safe_encode(title + "\n") + _esc_bold(False)
    out += _esc_align_left()

    for ln in lines:
        out += _safe_encode(ln + "\n")

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
    """
    Build kitchen receipt - sekarang menggunakan PDF untuk support Chinese.
    """
    # Gunakan PDF generator untuk support Chinese characters
    pdf_bytes = build_multilingual_kitchen_pdf(data, station_name, items, created_by)
    return pdf_bytes

# ========== API: cetak sekarang (sync) ==========
@frappe.whitelist()
def pos_invoice_print_now(name: str, printer_name: str, add_qr: int = 0, qr_data: str | None = None) -> dict:
    try:
        
        data = _collect_pos_invoice(name)
        doc = frappe.get_doc("POS Invoice", name)

        full_name = frappe.db.get_value(
            "User",
            doc.owner,
            "full_name"
        )

        results = []

        raw = build_escpos_from_pos_invoice(name, bool(int(add_qr)), qr_data)
        job_id = cups_print_raw(raw, printer_name)
        results.append({"printer": printer_name, "job_id": job_id, "type": "bill"})

        kitchen_groups: Dict[str, List[Dict]] = {}
        for it in data["items"]:
            for printer in get_item_printers(it):
                kitchen_groups.setdefault(printer, []).append(it)

        for kprinter, items in kitchen_groups.items():
            # Sekarang kitchen receipt adalah PDF, print menggunakan cups_print_pdf
            raw_kitchen = build_kitchen_receipt(data, kprinter, items, created_by=full_name)
            kitchen_job = cups_print_pdf(raw_kitchen, kprinter)
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
        out += _safe_encode(pad + w + "\n")
    return out

def build_kitchen_receipt_from_payload(entry: Dict[str, Any], title_prefix: str = "") -> bytes:
    """
    Build kitchen receipt dari payload sebagai PDF untuk support Chinese.
    """
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
    
    # Build content untuk PDF
    generator = MultilingualReceiptGenerator(page_width_mm=75)
    content_lines = []
    
    # Header
    content_lines.append({'text': station, 'size': 14, 'bold': True, 'align': 'center'})
    content_lines.append({'text': '', 'size': 4})
    
    table_name = get_table_names_from_pos_invoice(inv)
    content_lines.append({'text': f"No Meja: {table_name}", 'size': 10})
    content_lines.append({'text': f"Tanggal: {tdate}", 'size': 9})
    content_lines.append({'text': f"Petugas: {full_name}", 'size': 9})
    content_lines.append({'text': '-' * 32, 'size': 9})
    
    # Items
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
            is_cjk = True
        else:
            display_line = f"{qty_s} x {title}"
            is_cjk = False
        
        content_lines.append({
            'text': display_line,
            'size': 12,
            'bold': True,
            'is_cjk': is_cjk
        })
        
        # Add-ons
        add_ons_str = it.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",")]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name = add.rsplit("(", 1)[0].strip()
                else:
                    name = add
                content_lines.append({
                    'text': f"  {name}",
                    'size': 9,
                    'is_cjk': _contains_cjk(name)
                })
        
        # Notes
        notes = it.get("quick_notes", "")
        if notes:
            content_lines.append({
                'text': f"  # {notes}",
                'size': 9,
                'is_cjk': _contains_cjk(notes)
            })
        
        content_lines.append({'text': '', 'size': 3})
    
    content_lines.append({'text': '-' * 32, 'size': 9})
    
    return generator.create_receipt_pdf(content_lines, title=f"Kitchen_{station}")

# ========== API: print kitchen dari payload (menerima dict/list atau string JSON) ==========
@frappe.whitelist()
def kitchen_print_from_payload(payload, title_prefix: str = "") -> dict:
    """
    payload: dict (single) / list (multi) / str (JSON)
    """
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
            
            # Print PDF
            job_id = conn.printFile(printer_name, tmp_path, f"KITCHEN_{station}", {})
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
    # Simpan log sederhana (opsional)
    frappe.logger("pos_print").info({"invoice": name, "printer": printer_name, "job_id": job_id})

def format_number(val) -> str:
    try:
        return f"{float(val):,.0f}".replace(",", ".")
    except Exception:
        return str(val or 0)

# function print bill

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
    # Ambil POS Invoice
    invoice = frappe.get_doc("POS Invoice", pos_invoice_name)
    
    # Ambil POS Profile dari invoice
    pos_profile_name = invoice.pos_profile
    pos_profile = frappe.get_doc("POS Profile", pos_profile_name)

    # Cari POS Opening Entry yang masih "Open" untuk POS Profile ini
    opening_entries = frappe.get_all(
        "POS Opening Entry",
        filters={
            "pos_profile": pos_profile.name,
            "status": "Open",  # Hanya yang sedang aktif
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

    # fallback: jika tidak ada POS Opening Entry aktif, pakai owner invoice
    owner_user_doc = frappe.get_doc("User", invoice.owner)
    return owner_user_doc.full_name or invoice.owner

def build_escpos_bill(name: str) -> bytes:
    """
    Return PDF bytes (thermal-like layout simulation) keeping all original data and layout
    """
    import frappe
    from frappe.utils.pdf import get_pdf
    from frappe.utils import now_datetime

    data = _collect_pos_invoice(name)

    LINE_WIDTH = 32

    def money(val):
        return f"{int(round(val or 0)):,.0f}".replace(",", ".")

    # ===============================
    # Mandarin Mapping
    # ===============================
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

    # ===============================
    # Text Helper
    # ===============================
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

    # ===============================
    # Items HTML
    # ===============================
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

        # Add-ons
        for add in (item.get("add_ons") or "").split(","):
            if add.strip():
                items_html += f"<tr><td style='padding-left:8px;'>+ {add.strip()}</td></tr>"

        # Notes
        if item.get("quick_notes"):
            items_html += f"<tr><td style='padding-left:8px;'># {item['quick_notes']}</td></tr>"

    # ===============================
    # Taxes HTML
    # ===============================
    taxes_html = ""
    for tax in data.get("taxes", []):
        taxes_html += f"<tr><td>{tax.get('description','')}</td><td style='text-align:right;'>{money(tax.get('amount',0))}</td></tr>"

    # ===============================
    # Payments HTML
    # ===============================
    payments_html = ""
    for pay in data.get("payments", []):
        payments_html += f"<tr><td>{pay.get('mode_of_payment','')}</td><td style='text-align:right;'>{money(pay.get('amount',0))}</td></tr>"

    # ===============================
    # Other info
    # ===============================
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")
    company = data.get("company") or ""
    customer = data.get("customer_name") or data.get("customer") or ""
    order_type = data.get("order_type") or ""
    queue_no = data.get("queue") or ""
    total_qty = sum(int(item.get("qty",0)) for item in data.get("items", []))

    # ===============================
    # HTML Template
    # ===============================
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

    # Queue number for take away
    if order_type.lower() in ["take away","takeaway"] and queue_no:
        html += f"<br><div class='center'><b>Your Queue Number: {queue_no}</b></div>"

    html += "</body></html>"

    return get_pdf(html)

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

    # Hitung total qty semua items
    total_qty = sum(int(item.get("qty", 0)) for item in items)

    # Format waktu cetak
    print_time = now_datetime().strftime("%d/%m/%Y %H:%M")

    separator = "-" * LINE_WIDTH

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # ===== HEADER =====
    logo = frappe.db.get_value("Company", company, "custom_company_logo") or frappe.db.get_value("Company", company, "company_logo")
    out += _esc_align_center() + _esc_bold(True)

    # Nama company + city
    company_city_line = f"{company} {city}".strip()
    if company_city_line:
        out += _safe_encode(company_city_line + "\n")

    # Alamat lengkap
    if address1:
        out += _safe_encode(address1 + "\n")
    if address2:
        out += _safe_encode(address2 + "\n")
    if phone:
        out += _safe_encode(f"Tlp. {phone}\n")

    out += _esc_bold(False)
    out += _esc_align_left()
    out += _safe_encode(separator + "\n")

    # ===== INFORMASI INVOICE =====
    out += _safe_encode(f"No : {data['name']}\n")
    out += _safe_encode(f"Date : {print_time}\n")

    # Nama table
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


    # Nama kasir
    cashier_name = get_cashier_name(data["name"])
    out += _safe_encode(f"Cashier : {cashier_name}\n")

    # Customer
    if customer:
        out += _safe_encode(f"Customer: {customer}\n")

    out += _safe_encode(separator + "\n")

    # ===== ITEMS =====
    for item in items:
        item_name = item.get("item_name", "")
        qty = int(item.get("qty", 0))
        rate = item.get("rate", 0)
        amount = rate * qty

        # Item utama
        out += _safe_encode(f"{item_name}\n")
        line = f"{qty}x @{format_number(rate)}".ljust(LINE_WIDTH - 12) + f"{format_number(amount).rjust(12)}"
        out += _safe_encode(line + "\n")

        # Add-ons
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

        # Notes
        notes = item.get("quick_notes", "")
        if notes:
            out += _safe_encode(f"  # {notes}\n")

    # ===== TOTAL QTY =====
    out += _safe_encode(separator + "\n")
    out += _safe_encode(f"{total_qty} items\n")

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

    # 1️⃣ Print SC dulu
    if sc_amount:
        out += _safe_encode(_format_line("Sc:", format_number(sc_amount)) + "\n")

    # 2️⃣ Lalu Subtotal
    out += _safe_encode(_format_line("Subtotal:", format_number(total)) + "\n")

    # 3️⃣ Lalu Tax
    if tax_amount:
        out += _safe_encode(_format_line("Tax:", format_number(tax_amount)) + "\n")
    
    out += _safe_encode(separator + "\n")
    out += _esc_bold(True)
    out += _safe_encode(_format_line("Grand Total:", format_number(grand_total)) + "\n")
    out += _esc_bold(False)
    
    # ===== PAYMENT =====
    for pay in payments:
        mop = pay.get("mode_of_payment") or "-"
        amt = pay.get("amount") or 0
        out += _safe_encode(f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n")

    if change:
        out += _safe_encode(f"Change:".rjust(LINE_WIDTH - 12) + f"{format_number(change).rjust(12)}\n")

    # ===== FOOTER =====
    out += _safe_encode(separator + "\n")
    out += _esc_align_center()
    out += _safe_encode("Terima kasih!\n")
    out += _safe_encode("Selamat menikmati hidangan Anda!\n")

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += _safe_encode("Your Queue Number:\n")
            out += _esc_bold(False)

            # --- Font besar + center untuk nomor antrian ---
            out += _esc_align_center()          # pastikan tetap di tengah
            out += b"\x1b!\x38"                 # ESC ! 56 → double height & width
            out += _safe_encode(f"{queue_no}\n")
            out += b"\x1b!\x00"                 # reset font ke normal
            out += _esc_feed(2)


    # Feed bawah + cut
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

    address1 = branch_detail.get("address_line1") or ""
    address2 = branch_detail.get("address_line2") or ""
    city = branch_detail.get("city") or ""
    pincode = branch_detail.get("pincode") or ""
    phone = branch_detail.get("phone") or ""
    
    # Hitung total qty semua items
    total_qty = sum(int(item.get("qty", 0)) for item in items)

    # Format waktu cetak
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
    out += _safe_encode("CHECKER\n")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out += _safe_encode(header_line + "\n")

    out += _esc_bold(False)

    out += _esc_align_left()
    out += _safe_encode(separator + "\n")
    
    # Nama table
    table_names = get_table_names_from_pos_invoice(data["name"])

    # ===== INFORMASI INVOICE =====
    # out += _safe_encode(f"No : {data['name']}\n")
    out += _safe_encode(f"No Meja : {table_names}\n")
    out += _safe_encode(f"Date : {print_time}\n")
    out += _safe_encode(f"Purpose : {order_type}\n")
    out += _safe_encode(f"Waiter : {get_waiter_name(data['name'])}\n")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += _safe_encode(f"Pax : {pax_int}")
        out += _esc_bold(False)

    out += _safe_encode(separator + "\n")

    # ===== ITEMS =====
    for item in items:
        item_name = (item.get("item_name") or "").strip()
        qty = item.get("qty") or 1
        resto_menu = item.get("resto_menu")
        # print("MANDARIN MAP:", mandarin_map)
        # Ambil dari mandarin_map (SUDAH di-query di atas)
        mandarin_name = mandarin_map.get(resto_menu) or ""

        # Format qty
        if isinstance(qty, (int, float)):
            qty_str = f"{int(qty)}x"
        else:
            qty_str = f"{qty}x"

        # Gabungkan dalam 1 baris
        if mandarin_name:
            full_item_name = f"{item_name} ({mandarin_name})"
        else:
            full_item_name = item_name

        line = f"{qty_str.ljust(5)}{full_item_name}"
        out += _safe_encode(line + "\n")

        # ===== ADD ONS =====
        add_ons_str = item.get("add_ons") or ""
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",") if a.strip()]
            for add in add_ons_list:
                out += _safe_encode(" " * 7 + add + "\n")

        # ===== QUICK NOTES =====
        notes = (item.get("quick_notes") or "").strip()
        if notes:
            out += _safe_encode(" " * 7 + f"# {notes}\n")

    # ===== TOTAL QTY =====
    out += _safe_encode(separator + "\n")
    out += _safe_encode(f"{total_qty} items\n")

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += _safe_encode("Your Queue Number:\n")
            out += _esc_bold(False)

            # --- Font besar + center untuk nomor antrian ---
            out += _esc_align_center()          # pastikan tetap di tengah
            out += b"\x1b!\x38"                 # ESC ! 56 → double height & width
            out += _safe_encode(f"{queue_no}\n")
            out += b"\x1b!\x00"                 # reset font ke normal
            out += _esc_feed(2)


    # Feed bawah + cut
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

@frappe.whitelist(allow_guest=True)
def preview_receipt(name: str):

    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    receipt_bytes = build_escpos_bill(name)

    text = receipt_bytes.decode("utf-8", "ignore")

    # Hapus control ESC/POS TANPA hapus newline
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

    # Hapus control ESC/POS TANPA hapus newline
    text = re.sub(r'[\x00-\x09\x0B-\x1F\x7F-\x9F]', '', text)

    return {
        "preview": text,
        "invoice": name,
        "timestamp": now_datetime()
    }

@frappe.whitelist(allow_guest=True)
def preview_kitchen_receipt_simple(invoice_name: str):
    """
    Preview kitchen receipt via GET hanya dengan invoice_name.
    """

    import re
    from frappe.utils import now_datetime

    # ===== VALIDASI =====
    if not frappe.db.exists("POS Invoice", invoice_name):
        return {"error": f"POS Invoice {invoice_name} tidak ditemukan"}

    doc = frappe.get_doc("POS Invoice", invoice_name)

    # ===== SIAPKAN ENTRY SESUAI FORMAT build_kitchen_receipt_from_payload =====
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

    # ===== BUILD RECEIPT (TANPA KITCHEN ORDER) =====
    receipt_bytes = build_kitchen_receipt_from_payload(entry)

    # ===== CONVERT KE TEXT =====
    text = receipt_bytes.decode("utf-8", "ignore")
    text = re.sub(r'[\x00-\x09\x0B-\x1F\x7F-\x9F]', '', text)

    return {
        "preview": text.strip(),
        "invoice": invoice_name,
        "timestamp": now_datetime()
    }