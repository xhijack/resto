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


# ========== Normalisasi POS Invoice ==========
def _collect_pos_invoice(name: str) -> Dict[str, Any]:
    """Ambil POS Invoice + items/payments/taxes lewat frappe.get_doc."""
    doc = frappe.get_doc("POS Invoice", name)

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
            "qty": float(it.get("qty") or 0),
            "rate": float(standard_price or 0),
            "amount": float(it.get("amount") or 0),
            "uom": it.get("uom") or it.get("stock_uom"),
            "discount_percentage": float(it.get("discount_percentage") or 0),
            "discount_amount": float(it.get("discount_amount") or 0),
            "description": it.get("description") or "",
            "add_ons" : it.get("add_ons") or "",
            "quick_notes": it.get("quick_notes") or "",
            "is_checked": it.get("is_checked") or ""
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
            out += (h + "\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    title = f"POS INVOICE {data['name'] or ''}".strip()
    out += _esc_align_center() + _esc_bold(True) + (title + "\n").encode("ascii", "ignore") + _esc_bold(False)
    out += _esc_align_left()

    for ln in lines:
        out += (ln + "\n").encode("ascii", "ignore")

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
    out += _esc_align_center() + _esc_bold(True)
    out += (f"KITCHEN ORDER - {station_name}\n").encode("ascii", "ignore")
    out += _esc_bold(False) + _esc_align_left()

    out += (f"Invoice: {data['name']}\n").encode("ascii", "ignore")
    out += (f"Tanggal: {data['posting_date']} {data['posting_time']}\n").encode("ascii", "ignore")
    out += (f"Petugas: {created_by}\n").encode("ascii", "ignore")

    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += (f"Table: {table_names}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (f"Purpose : {data['order_type']}\n").encode("ascii", "ignore")

    out += _line("-").encode() + b"\n"

    for it in items:
        qty = int(it["qty"]) if it["qty"].is_integer() else it["qty"]
        line = f"{qty} x {it['item_name']}"

        add_ons_str = it.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",")]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, price = add.rsplit("(", 1)
                    price = price.replace(")", "").strip()
                    name = name.strip()
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12)
                    out += (add_line + "\n").encode("ascii", "ignore")


        # Notes
        notes = it.get("quick_notes", "")
        if notes:
            out += (f"  # {notes}\n").encode("ascii", "ignore")


        for w in _wrap_text(line, LINE_WIDTH):
            out += (w + "\n").encode("ascii", "ignore")

    out += _line("-").encode() + b"\n"
    out += _esc_feed(3) + _esc_cut_full()
    return out

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
            raw_kitchen = build_kitchen_receipt(data, kprinter, items,created_by=full_name)
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

def build_kitchen_receipt_from_payload(entry: Dict[str, Any], title_prefix: str = "KITCHEN ORDER") -> bytes:
    """
    entry:
      {
        "kitchen_station": "HOT KITCHEN",
        "printer_name": "HOTKITCHEN",
        "pos_invoice": "POSINVOICE00001",
        "transaction_date": "2025-10-10 15:23:00",
        "items": [
          {
            "resto_menu": "Nasi Goreng Spesial",
            "short_name": "NGS",
            "qty": 2,
            "quick_notes": "Tanpa Sambel",
            "add_ons": "Extra Kerupuk"
          }
        ]
      }
    """
    current_user = frappe.session.user

    full_name = frappe.db.get_value(
        "User",
        current_user,
        "full_name"
    )

    station = _safe_str(entry.get("kitchen_station")) or "-"
    inv     = _safe_str(entry.get("pos_invoice")) or "-"
    tdate   = _safe_str(entry.get("transaction_date")) or frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    items   = entry.get("items") or []

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # HEADER (tanpa garis/feed di atas)
    out += _esc_align_center() + _esc_bold(True)
    out += (f"{title_prefix} - {station}\n").encode("ascii", "ignore")
    out += _esc_bold(False) + _esc_align_left()

    out += (f"Invoice : {inv}\n").encode("ascii", "ignore")
    out += (f"Tanggal : {tdate}\n").encode("ascii", "ignore")
    out += (f"Petugas : {full_name}\n").encode("ascii", "ignore")
    
    out += (_line("-") + "\n").encode("ascii", "ignore")

    # ITEMS (height besar, width normal -> 1 baris; truncate bila kepanjangan)
    for it in items:
        qty_s      = _fmt_qty(it.get("qty") or 0)
        short_name = _safe_str(it.get("short_name"))
        menu_name  = _safe_str(it.get("resto_menu"))
        add_ons    = _safe_str(it.get("add_ons"))
        qnotes     = _safe_str(it.get("quick_notes"))

        title = short_name or menu_name or "-"

        # Besarkan tinggi saja agar tidak pecah kolom
        out += _esc_char_size(0, ITEM_HEIGHT_MULT) + _esc_bold(True)
        big_line = _fit(f"{qty_s} x {title}", LINE_WIDTH)
        out += (big_line + "\n").encode("ascii", "ignore")
        out += _esc_bold(False) + _esc_char_size(0, 0)

        # Sub-informasi normal (opsional, 1 baris)
        if short_name and menu_name and menu_name != short_name:
            out += (f"  Menu : {_fit(menu_name, LINE_WIDTH-8)}\n").encode("ascii", "ignore")
        
        add_ons_str = it.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",")]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, price = add.rsplit("(", 1)
                    price = price.replace(")", "").strip()
                    name = name.strip()
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12)
                    out += (add_line + "\n").encode("ascii", "ignore")
    
        # Notes
        notes = it.get("quick_notes", "")
        if notes:
            out += (f"  # {notes}\n").encode("ascii", "ignore")

        out += b"\n"  # spacer

    out += (_line("-") + "\n").encode("ascii", "ignore")

    # ==== FEED TAMBAHAN sebelum cut supaya tidak "kepotong cepat" ====
    out += _esc_feed(5)        # atur 4-7 sesuai perilaku printermu

    # Cut: pilih salah satu—kebanyakan _esc_cut_full() sudah cukup
    out += _esc_cut_full()
    # Kalau printer mendukung cut-with-feed, ini alternatif yang rapi:
    # out += _esc_cut_full_with_feed()

    return out

# ========== API: print kitchen dari payload (menerima dict/list atau string JSON) ==========
@frappe.whitelist()
def kitchen_print_from_payload(payload, title_prefix: str = "KITCHEN ORDER") -> dict:
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

            raw = build_kitchen_receipt_from_payload(entry, title_prefix=title_prefix)

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
    # Simpan log sederhana (opsional)
    frappe.logger("pos_print").info({"invoice": name, "printer": printer_name, "job_id": job_id})

def format_number(val) -> str:
    try:
        return f"{float(val):,.0f}".replace(",", ".")
    except Exception:
        return str(val or 0)

# function print bill

def get_table_names_from_pos_invoice(pos_invoice_name: str) -> str:
    table_orders = frappe.get_all(
        "Table Order",
        filters={"invoice_name": pos_invoice_name},
        fields=["parent"] 
    )

    table_names = ", ".join([t["parent"] for t in table_orders])
    return table_names

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
    out += _esc_align_center() + _esc_bold(True)

    # Nama company + city
    company_city_line = f"{company} {city}".strip()
    if company_city_line:
        out += (company_city_line + "\n").encode("ascii", "ignore")

    # Alamat lengkap
    if address1:
        out += (address1 + "\n").encode("ascii", "ignore")
    if address2:
        out += (address2 + "\n").encode("ascii", "ignore")
    if phone:
        out += (f"Tlp. {phone}\n").encode("ascii", "ignore")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out += (header_line + "\n").encode("ascii", "ignore")

    out += _esc_bold(False)

    # Alamat branch
    # if address1 or address2 or city or pincode or phone:
    #     out += _esc_align_center()
    #     if address1:
    #         out += (f"{address1}\n").encode("ascii", "ignore")
    #     if address2:
    #         out += (f"{address2}\n").encode("ascii", "ignore")
    #     if city or pincode:
    #         out += (f"{city} - {pincode}\n").encode("ascii", "ignore")
    #     if phone:
    #         out += (f"Phone: {phone}\n").encode("ascii", "ignore")


    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")

    # ===== INFORMASI INVOICE =====
    out += (f"No : {data['name']}\n").encode("ascii", "ignore")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")

    # Nama table
    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += (f"Table: {table_names}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (f"Purpose : {order_type}\n").encode("ascii", "ignore")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += (f"Pax : {pax_int}\n").encode("ascii", "ignore")
        out += _esc_bold(False)


    # Nama kasir
    cashier_name = get_cashier_name(data["name"])
    out += (f"Cashier : {cashier_name}\n").encode("ascii", "ignore")

    # Customer
    if customer:
        out += (f"Customer: {customer}\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")

    # ===== ITEMS =====
    for item in items:
        item_name = item.get("item_name", "")
        qty = int(item.get("qty", 0))
        rate = item.get("rate", 0)
        amount = rate * qty

        # Item utama
        out += (f"{item_name}\n").encode("ascii", "ignore")
        line = f"{qty}x @{format_number(rate)}".ljust(LINE_WIDTH - 12) + f"{format_number(amount).rjust(12)}"
        out += (line + "\n").encode("ascii", "ignore")

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
                    out += (add_line + "\n").encode("ascii", "ignore")

        # Notes
        notes = item.get("quick_notes", "")
        if notes:
            out += (f"  # {notes}\n").encode("ascii", "ignore")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== TOTALS =====
    out += (_format_line("Subtotal:", format_number(total)) + "\n").encode("ascii", "ignore")

    for tax in taxes:
        tax_name = tax.get("description", "Tax")
        if "Pendapatan Service" in tax_name:
            tax_name = "Sc"
        elif "VAT" in tax_name:
            tax_name = "Tax"
        tax_amount = tax.get("amount", 0)
        # potong nama pajak agar tidak kepanjangan
        if len(tax_name) > 20:
            tax_name = tax_name[:20]
        out += (_format_line(tax_name, format_number(tax_amount)) + "\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_bold(True)
    out += (_format_line("Grand Total:", format_number(grand_total)) + "\n").encode("ascii", "ignore")
    out += _esc_bold(False)


    # ===== PAYMENT =====
    # for pay in payments:
    #     mop = pay.get("mode_of_payment") or "-"
    #     amt = pay.get("amount") or 0
    #     out += (f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n").encode("ascii", "ignore")

    # if change:
    #     out += (f"Change:".rjust(LINE_WIDTH - 12) + f"{format_number(change).rjust(12)}\n").encode("ascii", "ignore")

    # ===== FOOTER =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_align_center()
    out += b"Terima kasih!\n"
    out += b"Selamat menikmati hidangan Anda!\n"

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += b"Your Queue Number:\n"
            out += _esc_bold(False)

            # --- Font besar + center untuk nomor antrian ---
            out += _esc_align_center()          # pastikan tetap di tengah
            out += b"\x1b!\x38"                 # ESC ! 56 → double height & width
            out += f"{queue_no}\n".encode("ascii", "ignore")
            out += b"\x1b!\x00"                 # reset font ke normal
            out += _esc_feed(2)


    # Feed bawah + cut
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

    # if logo:
    #     try:
    #         out += _esc_print_image(logo)  
    #         out += b"\n"
    #     except Exception as e:
    #         frappe.log_error(f"❌ Gagal cetak logo company {company}: {str(e)}", "Print Receipt Error")

    # ===== HEADER =====
    out += _esc_align_center() + _esc_bold(True)

    # Nama company + city
    company_city_line = f"{company} {city}".strip()
    if company_city_line:
        out += (company_city_line + "\n").encode("ascii", "ignore")

    # Alamat lengkap
    if address1:
        out += (address1 + "\n").encode("ascii", "ignore")
    if address2:
        out += (address2 + "\n").encode("ascii", "ignore")
    if phone:
        out += (f"Tlp. {phone}\n").encode("ascii", "ignore")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out += (header_line + "\n").encode("ascii", "ignore")

    out += _esc_bold(False)

    # Alamat branch
    # if address1 or address2 or city or pincode or phone:
    #     out += _esc_align_center()
    #     if address1:
    #         out += (f"{address1}\n").encode("ascii", "ignore")
    #     if address2:
    #         out += (f"{address2}\n").encode("ascii", "ignore")
    #     if city or pincode:
    #         out += (f"{city} - {pincode}\n").encode("ascii", "ignore")
    #     if phone:
    #         out += (f"Phone: {phone}\n").encode("ascii", "ignore")


    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")

    # ===== INFORMASI INVOICE =====
    out += (f"No : {data['name']}\n").encode("ascii", "ignore")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")

    # Nama table
    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += (f"Table: {table_names}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (f"Purpose : {order_type}\n").encode("ascii", "ignore")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += (f"Pax : {pax_int}\n").encode("ascii", "ignore")
        out += _esc_bold(False)


    # Nama kasir
    cashier_name = get_cashier_name(data["name"])
    out += (f"Cashier : {cashier_name}\n").encode("ascii", "ignore")

    # Customer
    if customer:
        out += (f"Customer: {customer}\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")

    # ===== ITEMS =====
    for item in items:
        item_name = item.get("item_name", "")
        qty = int(item.get("qty", 0))
        rate = item.get("rate", 0)
        amount = rate * qty

        # Item utama
        out += (f"{item_name}\n").encode("ascii", "ignore")
        line = f"{qty}x @{format_number(rate)}".ljust(LINE_WIDTH - 12) + f"{format_number(amount).rjust(12)}"
        out += (line + "\n").encode("ascii", "ignore")

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
                    out += (add_line + "\n").encode("ascii", "ignore")

        # Notes
        notes = item.get("quick_notes", "")
        if notes:
            out += (f"  # {notes}\n").encode("ascii", "ignore")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== TOTALS =====
    out += (_format_line("Subtotal:", format_number(total)) + "\n").encode("ascii", "ignore")

    for tax in taxes:
        tax_name = tax.get("description", "Tax")
        if "Pendapatan Service" in tax_name:
            tax_name = "Sc"
        elif "VAT" in tax_name:
            tax_name = "Tax"
        tax_amount = tax.get("amount", 0)
        # potong nama pajak agar tidak kepanjangan
        if len(tax_name) > 20:
            tax_name = tax_name[:20]
        out += (_format_line(tax_name, format_number(tax_amount)) + "\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_bold(True)
    out += (_format_line("Grand Total:", format_number(grand_total)) + "\n").encode("ascii", "ignore")
    out += _esc_bold(False)
    
    # ===== PAYMENT =====
    for pay in payments:
        mop = pay.get("mode_of_payment") or "-"
        amt = pay.get("amount") or 0
        out += (f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n").encode("ascii", "ignore")

    if change:
        out += (f"Change:".rjust(LINE_WIDTH - 12) + f"{format_number(change).rjust(12)}\n").encode("ascii", "ignore")

    # ===== FOOTER =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_align_center()
    out += b"Terima kasih!\n"
    out += b"Selamat menikmati hidangan Anda!\n"

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += b"Your Queue Number:\n"
            out += _esc_bold(False)

            # --- Font besar + center untuk nomor antrian ---
            out += _esc_align_center()          # pastikan tetap di tengah
            out += b"\x1b!\x38"                 # ESC ! 56 → double height & width
            out += f"{queue_no}\n".encode("ascii", "ignore")
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

    items = [item for item in data.get("items", []) if not item.get("is_checked")]
    
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

    separator = "-" * LINE_WIDTH

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # ===== HEADER =====
    out += _esc_align_center() + _esc_bold(True)
    out += (f"CHECKER\n").encode("ascii", "ignore")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out += (header_line + "\n").encode("ascii", "ignore")

    out += _esc_bold(False)

    # Alamat branch
    # if address1 or address2 or city or pincode or phone:
    #     out += _esc_align_center()
    #     if address1:
    #         out += (f"{address1}\n").encode("ascii", "ignore")
    #     if address2:
    #         out += (f"{address2}\n").encode("ascii", "ignore")
    #     if city or pincode:
    #         out += (f"{city} - {pincode}\n").encode("ascii", "ignore")
    #     if phone:
    #         out += (f"Phone: {phone}\n").encode("ascii", "ignore")


    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")

    # ===== INFORMASI INVOICE =====
    out += (f"No : {data['name']}\n").encode("ascii", "ignore")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")

    # Nama table
    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += (f"Table: {table_names}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (f"Purpose : {order_type}\n").encode("ascii", "ignore")
    out += (f"Waiter : {get_waiter_name(data['name'])}\n").encode("ascii", "ignore")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += (f"Pax : {pax_int}\n").encode("ascii", "ignore")
        out += _esc_bold(False)


    # Nama kasir
    # cashier_name = get_cashier_name(data["name"])
    # out += (f"Cashier : {cashier_name}\n").encode("ascii", "ignore")

    # Customer
    # if customer:
    #     out += (f"Customer: {customer}\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")

    # ===== ITEMS =====
    for item in items:
        item_name = item.get("item_name", "")
        qty = item.get("qty", 1)

        left = item_name.strip()
        right = str(int(qty)) if isinstance(qty, (int, float)) and qty == int(qty) else str(qty)

        space = LINE_WIDTH - len(left) - len(right)
        if space < 1:
            space = 1
        line = f"{left}{' ' * space}{right}"
        out += (line + "\n").encode("ascii", "ignore")

        add_ons_str = item.get("add_ons", "")
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",")]
            for add in add_ons_list:
                if "(" in add and ")" in add:
                    name, price = add.rsplit("(", 1)
                    price = price.replace(")", "").strip()
                    name = name.strip()
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12)
                    out += (add_line + "\n").encode("ascii", "ignore")
    
        # Notes
        notes = item.get("quick_notes", "")
        if notes:
            out += (f"  # {notes}\n").encode("ascii", "ignore")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== TOTALS =====
    # out += (f"{'Subtotal:'.rjust(LINE_WIDTH - 12)}{format_number(total).rjust(12)}\n").encode("ascii", "ignore")

    # Tambahan biaya seperti service charge, pajak, dll
    # service_charge = next((t["amount"] for t in taxes if "service" in t["description"].lower()), 0)
    # if service_charge:
    #     out += (f"{'Service Charge:'.rjust(LINE_WIDTH - 12)}{format_number(service_charge).rjust(12)}\n").encode("ascii", "ignore")

    # if tax_total:
    #     out += (f"{'Tax:'.rjust(LINE_WIDTH - 12)}{format_number(tax_total).rjust(12)}\n").encode("ascii", "ignore")

    # out += (separator + "\n").encode("ascii", "ignore")
    # out += _esc_bold(True)
    # out += (f"{'Grand Total:'.rjust(LINE_WIDTH - 12)}{format_number(grand_total).rjust(12)}\n").encode("ascii", "ignore")
    # out += _esc_bold(False)

    # ===== PAYMENT =====
    # for pay in payments:
    #     mop = pay.get("mode_of_payment") or "-"
    #     amt = pay.get("amount") or 0
    #     out += (f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n").encode("ascii", "ignore")

    # if change:
    #     out += (f"Change:".rjust(LINE_WIDTH - 12) + f"{format_number(change).rjust(12)}\n").encode("ascii", "ignore")

    # ===== FOOTER =====
    # out += (separator + "\n").encode("ascii", "ignore")
    # out += _esc_align_center()
    # out += b"Terima kasih!\n"
    # out += b"Selamat menikmati hidangan Anda!\n"

    # ===== QUEUE NUMBER (Take Away) =====
    order_type_value = (order_type or "").lower()
    if order_type_value in ["take away", "takeaway"]:
        queue_no = data.get("queue") or ""
        if queue_no:
            out += _esc_feed(2)
            out += _esc_align_center()
            out += _esc_bold(True)
            out += b"Your Queue Number:\n"
            out += _esc_bold(False)

            # --- Font besar + center untuk nomor antrian ---
            out += _esc_align_center()          # pastikan tetap di tengah
            out += b"\x1b!\x38"                 # ESC ! 56 → double height & width
            out += f"{queue_no}\n".encode("ascii", "ignore")
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
    """
    API untuk preview receipt POS tanpa printer
    """
    # 1. Cek apakah POS Invoice ada
    if not frappe.db.exists("POS Invoice", name):
        return {"error": f"POS Invoice {name} tidak ditemukan"}

    # 2. Build receipt dalam format ESC/POS (bytes)
    receipt_bytes = build_escpos_bill(name)

    # 3. Konversi bytes ke teks agar bisa dibaca
    # Hilangkan karakter non-printable ESC/POS
    text = receipt_bytes.decode("ascii", "ignore")
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)  # hapus control chars
    text = re.sub(r'\n\s*\n', '\n', text)  # hapus line kosong ganda

    # 4. Kembalikan hasil preview
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
    # Ambil data invoice
    if not frappe.db.exists("POS Invoice", invoice_name):
        return {"error": f"POS Invoice {invoice_name} tidak ditemukan"}

    data = frappe.get_doc("POS Invoice", invoice_name).as_dict()

    # Ambil items dan user (created_by)
    items = data.get("items", [])
    created_by = data.get("owner")  # atau siapa pun yang membuat POS Invoice
    station_name = data.get("branch") or "Kitchen"

    # Build receipt
    receipt_bytes = build_kitchen_receipt(data, station_name, items, created_by)

    # Decode bytes → teks
    text = receipt_bytes.decode("ascii", "ignore")
    text = re.sub(r'[\x00-\x1F\x7F-\x9F]', '', text)
    text = re.sub(r'\n\s*\n', '\n', text)

    # Center header
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("KITCHEN ORDER") or line.startswith("Table:"):
            lines.append(center_line(line))
        else:
            lines.append(line)

    preview_text = "\n".join(lines)

    return {
        "preview": preview_text,
        "invoice": invoice_name,
        "timestamp": now_datetime()
    }
