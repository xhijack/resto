# apps/your_app/your_app/pos_receipt.py
from __future__ import annotations
import math
import tempfile
import frappe
from typing import List, Dict, Any
from frappe.utils import now_datetime, getdate, get_time
from PIL import Image
from io import BytesIO
import requests
import re


# ========== Konstanta & Util ==========
LINE_WIDTH = 32           # ganti ke 42 jika printer 42 kolom
ITEM_HEIGHT_MULT = 4      # 2 = aman di banyak printer; coba 3 kalau masih kecil

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

def _esc_char_size_dotmatrix(width_mul: int = 1, height_mul: int = 1) -> bytes:
    """
    Set character size untuk printer dot matrix (ESC ! n)
    width_mul, height_mul: 1 = normal, 2 = double
    Nilai maksimal biasanya 2 untuk printer seperti TM-U220.
    """
    w = 1 if width_mul <= 1 else 2
    h = 1 if height_mul <= 1 else 2
    # bit 3: double-height, bit 4: double-width
    n = ((h-1) << 3) | ((w-1) << 4)
    return ESC + b'!' + bytes([n])

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
            val = str(it.get(field) or "")

            for b in blacklist:
                val = val.replace(b, "")

            it[field] = val.strip()

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

        short_name = frappe.db.get_value("Resto Menu", {"sell_item": item_code}, "short_name") or it.get("item_name")

        items.append({
            "name": it.get("name"),
            "item_code": it.get("item_code"),
            "item_name": it.get("item_name") or it.get("item_code"),
            "short_name": short_name,
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
            "is_checked": int(it.get("is_checked") or 0),
            "is_print_kitchen": int(it.get("is_print_kitchen") or 0),
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
        "discount_for_bank": doc.get("discount_for_bank") or "",
        "discount_name": doc.get("discount_name") or "",
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

def build_kitchen_receipt(data: Dict[str, Any], station_name: str, items: List[Dict], created_by=None) -> bytes:
    out = b""

    # ===== FILTER ITEM YANG BELUM PERNAH DI PRINT =====
    filtered_items = [
        it for it in items
        if int(it.get("is_print_kitchen") or 0) == 0
        # and it.get("status_kitchen") == "Already Send To Kitchen"
    ]

    # Jika tidak ada item baru → tidak print apapun
    if not filtered_items:
        return b""

    out += _esc_init()
    out += _esc_font_a()
    out += _esc_char_size(0, )

    out += _esc_align_center() + _esc_bold(True)
    out += (f"{station_name}\n").encode("ascii", "ignore")
    out += _esc_bold(False) + _esc_align_left()

    # out += (f"Invoice: {data['name']}\n").encode("ascii", "ignore")
    out += (f"Tanggal: {data['posting_date']} {data['posting_time']}\n").encode("ascii", "ignore")
    out += (f"Petugas: {created_by}\n").encode("ascii", "ignore")

    table_names = get_table_names_from_pos_invoice(data["name"])
    if table_names:
        out += _esc_bold(True)
        out += (f"Table: {table_names}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (f"Purpose : {data['order_type']}\n").encode("ascii", "ignore")

    out += _line("-").encode() + b"\n"

    # ===== PREPARE MANDARIN MAP (HANYA ITEM YANG DI PRINT) =====
    resto_menus = list(set([
        i.get("resto_menu")
        for i in filtered_items
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

    # ===== PRINT ITEM =====
    for it in filtered_items:
        qty_val = it.get("qty", 0)

        if isinstance(qty_val, float) and qty_val.is_integer():
            qty = int(qty_val)
        else:
            qty = qty_val

        item_name = it.get("item_name", "")
        resto_menu = it.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu) or ""

        # ===== ITEM UTAMA =====
        # if mandarin_name:
        #     line = f"{qty} x {item_name} ({mandarin_name})"
        # else:
        line = f"{qty} x {item_name}"

        for w in _wrap_text(line, LINE_WIDTH):
            out += (w + "\n").encode("utf-8")

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
                    out += (w + "\n").encode("utf-8")

        # ===== NOTES =====
        notes = it.get("quick_notes", "")
        if notes:
            note_line = f"  # {notes}"

            for w in _wrap_text(note_line, LINE_WIDTH):
                out += (w + "\n").encode("utf-8")

        # Spasi antar item
        out += b"\n"

    out += _line("-").encode() + b"\n"

    out += _esc_char_size(0, 0)
    out += _esc_feed(3)
    out += _esc_cut_full()

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
            raw_kitchen = build_kitchen_receipt(
                data,
                kprinter,
                items,
                created_by=full_name
            )

            # jika tidak ada item baru → skip print
            if not raw_kitchen:
                frappe.logger("pos_print").info({
                    "invoice": name,
                    "printer": kprinter,
                    "message": "Tidak ada item baru untuk kitchen"
                })
                continue

            kitchen_job = cups_print_raw(raw_kitchen, kprinter)

            # ===== UPDATE STATUS PRINT =====
            for it in items:
                if int(it.get("is_print_kitchen") or 0) == 0:
                    frappe.db.set_value(
                        "POS Invoice Item",
                        it.get("name"),
                        "is_print_kitchen",
                        1
                    )

            results.append({
                "printer": kprinter,
                "job_id": kitchen_job,
                "type": "kitchen"
            })

        frappe.db.commit()

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
    printer_name = _safe_str(entry.get("printer_name")) or ""
    # # Daftar kata kunci untuk mendeteksi printer dot matrix
    # dotmatrix_keywords = ["U220", "BAR", "PANTRY", "DOT", "MATRIX", "EPSON"]
    # is_dotmatrix = any(kw in printer_name.upper() for kw in dotmatrix_keywords)
    
    current_user = frappe.session.user
    full_name = frappe.db.get_value("User", current_user, "full_name")
    station = _safe_str(entry.get("kitchen_station")) or "-"
    inv     = _safe_str(entry.get("pos_invoice")) or "-"
    tdate   = _safe_str(entry.get("transaction_date")) or frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    items = entry.get("items") or []
    
    resto_menus = list(set([i.get("resto_menu") for i in items if i.get("resto_menu")]))
    mandarin_map = {}
    if resto_menus:
        menu_data = frappe.get_all(
            "Resto Menu",
            filters={"name": ["in", resto_menus]},
            fields=["name", "custom_mandarin_name"]
        )
        mandarin_map = {d.name: d.custom_mandarin_name for d in menu_data if d.custom_mandarin_name}

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    table_name = get_table_names_from_pos_invoice(inv)

    # HEADER
    out += _esc_char_size_dotmatrix(3, 3) + _esc_bold(True) 
    out += _esc_align_center() + _esc_bold(True)
    out += (f"{station}\n").encode("ascii", "ignore")
    out += _esc_bold(False) + _esc_align_left()
    out += _esc_char_size_dotmatrix(0, 0)

    out += _esc_char_size_dotmatrix(2, 2) + _esc_bold(True)   # double both (0x18)
    out += (f"No Meja : {table_name}\n").encode("ascii", "ignore")
    pax = get_total_pax_from_pos_invoice(inv)
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += (f"Pax     : {pax_int}\n").encode("ascii", "ignore")
        out += _esc_bold(False)
    out += _esc_char_size_dotmatrix(0, 0)

    out += (f"Tanggal : {tdate}\n").encode("ascii", "ignore")
    out += (f"Petugas : {full_name}\n").encode("ascii", "ignore")
    out += (_line("-") + "\n").encode("ascii", "ignore")

    # ITEMS
    for it in items:
        qty_s      = _fmt_qty(it.get("qty") or 0)
        item_name  = _safe_str(it.get("item_name"))
        short_name = _safe_str(it.get("short_name"))
        menu_name  = _safe_str(it.get("resto_menu"))
        add_ons    = _safe_str(it.get("add_ons"))
        qnotes     = _safe_str(it.get("quick_notes"))
        
        # title = item_name or short_name or menu_name or "-"
        title = short_name or item_name
        display_line = f"{qty_s} x {title}"

        # Pilih ukuran font berdasarkan jenis printer
        # if is_dotmatrix:
        out += _esc_char_size_dotmatrix(3, 3) + _esc_bold(True)   # double both (0x18)
        # else:
            # out += _esc_char_size(1, 6) + _esc_bold(True)             # tinggi 6x untuk thermal

        big_line = _fit(display_line, LINE_WIDTH)
        out += (big_line + "\n").encode("ascii", "ignore")

        # Reset ukuran dan bold
        # if is_dotmatrix:
        out += _esc_bold(False) + _esc_char_size_dotmatrix(1, 1)  # normal
        # else:
        #     out += _esc_bold(False) + _esc_char_size(0, 0)            # normal

        # Add-ons
        out += _esc_char_size_dotmatrix(2, 3)
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
                else:
                    out += (f"  {add}\n").encode("ascii", "ignore")

        # Notes
        notes = it.get("quick_notes", "")
        if notes:
            out += (f"  # {notes}\n").encode("ascii", "ignore")

        out += b"\n"  # spacer antar item
        out += _esc_char_size_dotmatrix(1, 1)

    out += (_line("-") + "\n").encode("ascii", "ignore")
    out += _esc_feed(5)
    out += _esc_cut_full()
    return out

@frappe.whitelist()
def kitchen_print_from_payload(payload, title_prefix: str = "") -> dict:
    import json
    import cups
    try:
        # ===== NORMALIZE PAYLOAD =====
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
            pos_invoice = _safe_str(entry.get("pos_invoice"))
            if not station:
                raise ValueError("Setiap entry wajib memiliki 'kitchen_station'")
            if not printer_name:
                raise ValueError("Setiap entry wajib memiliki 'printer_name'")

            if printer_name not in printers:
                raise frappe.ValidationError(
                    f"Printer '{printer_name}' tidak ditemukan di CUPS"
                )

            entry.setdefault("transaction_date", frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S"))
            entry.setdefault("items", [])

            # ===== FILTER ITEM BELUM DI PRINT =====
            items_to_print = [
                item for item in entry["items"]
                if int(item.get("is_print_kitchen") or 0) == 0
            ]

            if not items_to_print:
                frappe.logger("pos_print").info({
                    "invoice": pos_invoice,
                    "printer": printer_name,
                    "message": "Tidak ada item baru untuk kitchen"
                })
                continue

            # 🔥 HAPUS LOOP PER ITEM, LANGSUNG CETAK SEMUA ITEM SEKALIGUS 🔥
            single_entry = {
                "kitchen_station": station,
                "printer_name": printer_name,
                "pos_invoice": pos_invoice,
                "transaction_date": entry.get("transaction_date"),
                "items": items_to_print   # semua item yang belum dicetak
            }

            raw = build_kitchen_receipt_from_payload(single_entry)

            if not raw:
                frappe.logger("pos_print").warning({
                    "invoice": pos_invoice,
                    "printer": printer_name,
                    "message": "Gagal membangun data cetak"
                })
                continue

            # ===== WRITE TEMP FILE =====
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name

            # ===== PRINT KE CUPS =====
            job_id = conn.printFile(
                printer_name,
                tmp_path,
                f"KITCHEN_{station}_{pos_invoice}",
                {"raw": "true"}
            )

            # ===== UPDATE STATUS PRINT UNTUK SEMUA ITEM =====
            for item in items_to_print:
                if item.get("name"):
                    frappe.db.set_value(
                        "POS Invoice Item",
                        item.get("name"),
                        "is_print_kitchen",
                        1
                    )
            frappe.db.commit()

            # ===== LOG PRINT =====
            frappe.logger("pos_print").info({
                "invoice": pos_invoice,
                "printer": printer_name,
                "job_id": job_id,
                "items_printed": len(items_to_print)
            })

            results.append({
                "station": station,
                "printer": printer_name,
                "job_id": job_id,
                "pos_invoice": pos_invoice,
                "items_printed": len(items_to_print)
            })

        frappe.msgprint(f"{len(results)} kitchen ticket dikirim ke printer")
        return {"ok": True, "jobs": results}

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Kitchen Print Error (from payload)"
        )
        frappe.throw("Gagal print kitchen. Silakan cek error log.")
        
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
    user_id = invoice.modified_by or invoice.owner
    user = frappe.get_doc("User", user_id)
    return user.full_name or user_id  

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

def get_current_cashier_name(pos_invoice_name: str) -> str:
    current_user = frappe.session.user

    # Jika ada user aktif dan bukan Guest → pakai user yang print
    if current_user and current_user != "Guest":
        user = frappe.get_cached_doc("User", current_user)
        return user.full_name or current_user

    # Fallback → pakai owner POS Invoice
    invoice = frappe.get_cached_doc("POS Invoice", pos_invoice_name)
    owner_user = frappe.get_cached_doc("User", invoice.owner)

    return owner_user.full_name or invoice.owner

def build_escpos_bill(name: str) -> bytes:
    data = _collect_pos_invoice(name)

    items = data.get("items", [])
    payments = data.get("payments", [])
    taxes = data.get("taxes", [])

    company = data.get("company") or ""
    order_type = data.get("order_type") or ""
    customer = data.get("customer_name") or data.get("customer") or ""
    total = data.get("total", 0)
    discount_for_bank = data.get("discount_for_bank", "")
    discount_name = data.get("discount_name", "")
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

    # if company or branch:
    #     header_line = f"{company}"
    #     if branch:
    #         header_line += f" - {branch}"
    #     out += (header_line + "\n").encode("ascii", "ignore")

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
    # cashier_name = get_cashier_name(data["name"])
    # cashier_name = get_waiter_name(data["name"])
    cashier_name = get_current_cashier_name(data["name"])
    out += (f"Cashier : {cashier_name}\n").encode("ascii", "ignore")

    # Customer
    if customer:
        out += (f"Customer: {customer}\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")

    grouped_items = {}

    def normalize_addons(add_ons):
        if not add_ons:
            return ""
        parts = sorted([a.strip() for a in add_ons.split(",") if a.strip()])
        return ",".join(parts)

    for item in items:
        if item.get("status_kitchen") == "Void Menu":
            continue
        
        normalized_addons = normalize_addons(item.get("add_ons"))

        key = (
            item.get("short_name"),
            float(item.get("rate") or 0),
            normalized_addons
        )
        
        if key not in grouped_items:
            grouped_items[key] = {
                "name": item.get("short_name"),
                "qty": 0,
                "rate": float(item.get("rate") or 0),
                "amount": 0,
                "add_ons": normalized_addons
            }
        
        grouped_items[key]["qty"] += int(item.get("qty") or 0)
        grouped_items[key]["amount"] += float(item.get("amount") or 0)

    # ===== ITEMS =====
    for item in sorted(grouped_items.values(), key=lambda x: x["name"]):
        # if item.get("status_kitchen") == "Void Menu":
        #     continue
        
        item_name = (item.get("name") or "").strip()
        qty = int(item.get("qty") or 0)
        rate = float(item.get("rate") or 0)
        amount = float(item.get("amount") or (qty * rate))
        resto_menu = item.get("resto_menu")

        # mandarin_name = mandarin_map.get(resto_menu) or ""

        # # ===== NAMA ITEM =====
        # if mandarin_name:
        #     display_name = f"{item_name} ({mandarin_name})"
        # else:
        display_name = item_name

        out += (display_name + "\n").encode("utf-8")

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
                    add_line = f"  {name}".ljust(LINE_WIDTH - 12) + \
                            f"{format_number(float(price)).rjust(12)}"
                    out += (add_line + "\n").encode("ascii", "ignore")
                else:
                    out += (f"  {add}\n").encode("utf-8")

        # ===== NOTES =====
        # notes = (item.get("quick_notes") or "").strip()
        # if notes:
        #     out += (f"  # {notes}\n").encode("utf-8")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    # out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== TOTALS =====
    sc_amount = 0
    tax_amount = 0
    discount = 0

    for tax in taxes:
        tax_name = tax.get("description", "")
        amount = tax.get("amount", 0)

        if "Pendapatan Service" in tax_name:
            sc_amount += amount
        elif "VAT" in tax_name:
            tax_amount += amount
        elif "Diskon Penjualan" or "Discount" in tax_name:
            discount += abs(amount)

    out += (_format_line(f"Total Item:", format_number(total)) + "\n").encode("ascii", "ignore")
    
    if discount:
        if discount_name:
            label = f"Discount {discount_name}"
        else:
            label = "Discount"

        out += (_format_line(f"{label}:", f"-{format_number(discount)}") + "\n").encode("ascii", "ignore")
            
    if sc_amount:
        out += (_format_line("Sc:", format_number(sc_amount)) + "\n").encode("ascii", "ignore")

    if tax_amount:
        out += (_format_line("Tax:", format_number(tax_amount)) + "\n").encode("ascii", "ignore")
    
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_bold(True)
    out += (_format_line("Total:", format_number(grand_total)) + "\n").encode("ascii", "ignore")
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
    discount_for_bank = data.get("discount_for_bank", "")
    discount_name = data.get("discount_name", "")
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
        out += (company_city_line + "\n").encode("ascii", "ignore")

    # Alamat lengkap
    if address1:
        out += (address1 + "\n").encode("ascii", "ignore")
    if address2:
        out += (address2 + "\n").encode("ascii", "ignore")
    if phone:
        out += (f"Tlp. {phone}\n").encode("ascii", "ignore")

    out += _esc_bold(False)
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
    # cashier_name = get_cashier_name(data["name"])
    cashier_name = get_current_cashier_name(data["name"])
    out += (f"Cashier : {cashier_name}\n").encode("ascii", "ignore")

    # Customer
    if customer:
        out += (f"Customer: {customer}\n").encode("ascii", "ignore")

    out += (separator + "\n").encode("ascii", "ignore")

    grouped_items = {}

    def normalize_addons(add_ons):
        if not add_ons:
            return ""
        parts = sorted([a.strip() for a in add_ons.split(",") if a.strip()])
        return ",".join(parts)

    for item in items:
        if item.get("status_kitchen") == "Void Menu":
            continue
        
        normalized_addons = normalize_addons(item.get("add_ons"))

        key = (
            item.get("short_name"),
            float(item.get("rate") or 0),
            normalized_addons
        )
        
        if key not in grouped_items:
            grouped_items[key] = {
                "name": item.get("short_name"),
                "qty": 0,
                "rate": float(item.get("rate") or 0),
                "amount": 0,
                "add_ons": normalized_addons
            }
        
        grouped_items[key]["qty"] += int(item.get("qty") or 0)
        grouped_items[key]["amount"] += float(item.get("amount") or 0)

    # ===== ITEMS =====
    for item in sorted(grouped_items.values(), key=lambda x: x["name"]):
        # if item.get("status_kitchen") == "Void Menu":
        #     continue
        
        item_name = item.get("name", "")
        qty = int(item.get("qty", 0))
        rate = item.get("rate", 0)
        amount = float(item.get("amount") or (qty * rate))

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
        # notes = item.get("quick_notes", "")
        # if notes:
        #     out += (f"  # {notes}\n").encode("ascii", "ignore")

    # ===== TOTAL QTY =====
    out += (separator + "\n").encode("ascii", "ignore")
    # out += (f"{total_qty} items\n").encode("ascii", "ignore")

    # ===== TOTALS =====
    sc_amount = 0
    tax_amount = 0
    discount = 0

    for tax in taxes:
        tax_name = tax.get("description", "")
        amount = tax.get("amount", 0)

        if "Pendapatan Service" in tax_name:
            sc_amount += amount
        elif "VAT" in tax_name:
            tax_amount += amount
        elif "Diskon Penjualan" or "Discount" in tax_name:
            discount += abs(amount)

    out += (_format_line(f"Total Item:", format_number(total)) + "\n").encode("ascii", "ignore")
    
    if discount:
        if discount_name:
            label = f"Discount {discount_name}"
        else:
            label = "Discount"

        out += (_format_line(f"{label}:", f"-{format_number(discount)}") + "\n").encode("ascii", "ignore")
            
    if sc_amount:
        out += (_format_line("Sc:", format_number(sc_amount)) + "\n").encode("ascii", "ignore")

    if tax_amount:
        out += (_format_line("Tax:", format_number(tax_amount)) + "\n").encode("ascii", "ignore")
    
    out += (separator + "\n").encode("ascii", "ignore")
    out += _esc_bold(True)
    out += (_format_line("Total:", format_number(grand_total)) + "\n").encode("ascii", "ignore")
    out += _esc_bold(False)
    
    # ===== PAYMENT =====
    for pay in payments:
        mop = pay.get("mode_of_payment") or "-"
        amt = pay.get("amount") or 0
        out += (f"{mop}:".rjust(LINE_WIDTH - 12) + f"{format_number(amt).rjust(12)}\n").encode("ascii", "ignore")

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
        # if item.get("status_kitchen") == "Already Send To Kitchen"
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
    out += (f"CHECKER\n").encode("ascii", "ignore")

    if company or branch:
        header_line = f"{company}"
        if branch:
            header_line += f" - {branch}"
        out += (header_line + "\n").encode("ascii", "ignore")

    out += _esc_bold(False)

    out += _esc_align_left()
    out += (separator + "\n").encode("ascii", "ignore")
    
    # Nama table
    table_names = get_table_names_from_pos_invoice(data["name"])

    # ===== INFORMASI INVOICE =====
    out += (f"No Meja : {table_names}\n").encode("ascii", "ignore")
    out += (f"Date : {print_time}\n").encode("ascii", "ignore")
    out += (f"Purpose : {order_type}\n").encode("ascii", "ignore")
    out += (f"Waiter : {get_waiter_name(data['name'])}\n").encode("ascii", "ignore")
    pax = get_total_pax_from_pos_invoice(data["name"])
    if pax:
        pax_int = int(pax) if isinstance(pax, (int, float)) else pax
        out += _esc_bold(True)
        out += (f"Pax : {pax_int}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += (separator + "\n").encode("ascii", "ignore")

    # ===== ITEMS =====
    for item in items:
        item_name = (item.get("short_name") or "").strip()
        qty = item.get("qty") or 1
        resto_menu = item.get("resto_menu")
        mandarin_name = mandarin_map.get(resto_menu) or ""

        # Format qty
        if isinstance(qty, (int, float)):
            qty_str = f"{int(qty)}x"
        else:
            qty_str = f"{qty}x"

        full_item_name = item_name
        line = f"{qty_str.ljust(5)}{full_item_name}"

        # ===== CETAK ITEM UTAMA DENGAN FONT LEBIH BESAR =====
        out += _esc_char_size(0, 1)   # double-height, lebar normal
        out += (line + "\n").encode("utf-8")
        out += _esc_char_size(0, 0)   # reset ke ukuran normal

        # ===== ADD ONS =====
        add_ons_str = item.get("add_ons") or ""
        if add_ons_str:
            add_ons_list = [a.strip() for a in add_ons_str.split(",") if a.strip()]
            for add in add_ons_list:
                out += (" " * 7 + add + "\n").encode("utf-8")

        # ===== QUICK NOTES =====
        notes = (item.get("quick_notes") or "").strip()
        if notes:
            out += (" " * 7 + f"# {notes}\n").encode("utf-8")

        # ===== SPASI ANTAR ITEM =====
        out += b"\n"

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
            out += b"Your Queue Number:\n"
            out += _esc_bold(False)

            # --- Font besar + center untuk nomor antrian ---
            out += _esc_align_center()
            out += _esc_char_size(2, 2)   # double width & height
            out += f"{queue_no}\n".encode("ascii", "ignore")
            out += _esc_char_size(0, 0)
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


import cups
import tempfile
import os
from frappe import _
import frappe
from frappe.utils import flt

def clean_item_name(name):
    name = (name or "").strip()
    
    if "-" in name:
        parts = name.split("-", 1)
        
        if parts[0].isdigit():
            return parts[1].strip()
    
    return name

def print_shift_report(closing_name, printer_name=None):
    """
    Mencetak laporan shift dari POS Closing Entry menggunakan printer thermal 75mm.
    """
    closing = frappe.get_doc("POS Closing Entry", closing_name)
    
    # Ambil semua invoice yang terkait
    invoices = [frappe.get_doc("POS Invoice", t.pos_invoice) for t in closing.pos_transactions]
    
    # Kumpulkan data item per invoice
    items_summary = {}  # key: (item_code, item_name, item_group)
    total_discount = 0
    discount_map = {}
    void_qty = 0
    void_amount = 0
    for inv in invoices:
        # DISCOUNT (AMBIL DARI TAX TABLE)
        discount_added = False

        for tax in inv.taxes:
            if not tax.description or "discount" not in tax.description.lower():
                continue

            total_discount += abs(flt(tax.tax_amount))

            key = f"{inv.discount_for_bank or ''} {inv.discount_name or 'No Name'}"

            if key not in discount_map:
                discount_map[key] = {
                    "total_bill": 0,
                    "total_amount": 0
                }

            discount_map[key]["total_amount"] += abs(flt(tax.tax_amount))

            if not discount_added:
                discount_map[key]["total_bill"] += 1
                discount_added = True

        # ITEMS
        for item in inv.items:
            # VOID MENU
            if (item.status_kitchen or "") == "Void Menu":
                void_qty += flt(item.void_qty or item.qty)
                void_amount += flt(item.void_amount or item.amount)
                continue

            clean_name = clean_item_name(item.item_name)
            key = (item.item_code, clean_name, item.item_group)

            if key not in items_summary:
                items_summary[key] = {
                    "qty": 0,
                    "amount": 0,
                    "item_name": clean_name,
                    "item_group": item.item_group
                }

            items_summary[key]["qty"] += flt(item.qty)
            items_summary[key]["amount"] += flt(item.amount)
    
    # Urutkan berdasarkan item_group dan nama item
    sorted_items = sorted(items_summary.values(), key=lambda x: (x["item_group"], x["item_name"]))
    
    WIDTH = 32
    def format_row(name, qty, price):
        name = str(name)[:16]
        qty = str(qty)[:4]
        price = str(price)
        return f"{name:<16}{qty:>4} {price:>10}"
    
    def format_lr(left, right):
        left = str(left)
        right = str(right)
        space = WIDTH - len(left) - len(right)
        if space < 1:
            space = 1
        return left + (" " * space) + right
    
    # --- Persiapan teks ---
    lines = []
    
    # Fungsi bantu format angka ribuan (titik)
    def fmt_amt(amt):
        return f"{flt(amt):,.0f}".replace(",", ".")
    
    # Header
    posting_date = closing.posting_date
    bulan_indonesia = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
                       "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
    tgl = posting_date.day
    bln = bulan_indonesia[posting_date.month - 1]
    thn = posting_date.year
    lines.append(f"{tgl} {bln} {thn}")
    
    # Waktu tutup
    posting_time = closing.posting_time
    lines.append(f"End Time {posting_time}")
    
    # Nama toko / profil POS
    pos_profile = closing.pos_profile
    lines.append(f"Shop: {pos_profile}")
    # lines.append(f"PVJ: {pos_profile}")  # bisa disesuaikan dengan cabang
    lines.append("# PAID SALES")
    lines.append("")
    
    # --- Tabel Item ---
    lines.append(format_row("Item", "Qty", "Price"))
    lines.append("-" * 32)
    
    current_group = None
    for item in sorted_items:
        if item["item_group"] != current_group:
            current_group = item["item_group"]
            lines.append(f"* {current_group}")
        # Potong nama item maks 18 karakter
        clean_name = clean_item_name(item["item_name"])
        name = clean_name[:18]
        qty = f"{item['qty']:.0f}"
        price = fmt_amt(item["amount"])
        lines.append(format_row(name, qty, price))
    
    # Sub total dan ringkasan
    net_total = closing.net_total
    total_qty = int(closing.total_quantity or 0)
    lines.append("-" * 32)
    lines.append(format_row("Sub Total", total_qty, fmt_amt(net_total)))
    lines.append(format_lr("Discount", f"-{fmt_amt(total_discount)}"))
    lines.append(format_row("Total Sales", total_qty, fmt_amt(net_total)))
    lines.append("")
    
    # --- Grand Total ---
    lines.append(format_row("Item", "Qty", "Price"))
    lines.append("-" * 32)
    lines.append(format_lr("Sub Total", fmt_amt(net_total)))
    lines.append(format_lr("Discount", f"-{fmt_amt(total_discount)}"))
    grand_total = closing.grand_total
    lines.append(format_row("Grand Total", total_qty, fmt_amt(grand_total)))
    lines.append("")
    
    # --- Discount Detail ---
    if discount_map:

        lines.append("DISCOUNT")
        lines.append("-" * 32)

        for name, val in discount_map.items():
            qty = val["total_bill"]
            amt = val["total_amount"]
            
            if not amt:
                continue

            lines.append(
                format_lr(f"{name} ({qty})", f"-{fmt_amt(amt)}")
            )

        lines.append("")
    
    # --- Rincian Pajak ---
    lines.append(format_row("Item", "Qty", "Price"))
    lines.append("-" * 32)
    # lines.append(f"PVJ: {pos_profile}")
    # lines.append(format_lr("Discount", "0"))  # asumsi tidak ada diskon di sini
    lines.append(format_lr("Sub Total", fmt_amt(net_total)))
    # Tampilkan semua pajak dari child table taxes
    for tax in closing.taxes:
        parts = [p.strip() for p in tax.account_head.split(" - ")]

        tax_name = parts[1] if len(parts) > 2 else parts[0]

        lines.append(format_lr(tax_name[:20], fmt_amt(tax.amount)))
    # Total Sales (mungkin net total)
    lines.append(format_lr("Total Sales", fmt_amt(net_total)))
    lines.append("")
    
    # --- Pembayaran ---
    lines.append(format_row("Item", "Qty", "Price"))
    lines.append("-" * 32)
    lines.append("TYPE PAYMENT")
    for pay in closing.payment_reconciliation:
        mop = pay.mode_of_payment
        amount = pay.expected_amount
        lines.append(format_lr(mop[:20], fmt_amt(amount)))
    
    # VOID MENU
    lines.append("")
    lines.append("VOID MENU")
    lines.append("-" * 32)

    lines.append(format_lr("Total Qty", int(void_qty or 0)))
    lines.append(format_lr("Total Amount", fmt_amt(void_amount or 0)))
    lines.append("")

    # Akhir
    lines.append("")
    lines.append("")
    text = "\n".join(lines)
    # esc_commads = _esc_feed(8) + _esc_cut_full()
    # out = text.encode("ascii", "ignore") + esc_commads
    
    # --- Cetak dengan CUPS ---
    try:
        # Jika printer_name tidak diberikan, gunakan default
        if not printer_name:
            conn = cups.Connection()
            printer_name = conn.getDefault()
            if not printer_name:
                printers = conn.getPrinters()
                printer_name = list(printers.keys())[0] if printers else None
            if not printer_name:
                frappe.throw(_("Tidak ada printer terdeteksi."))
        
        # Kirim job cetak (langsung bytes)
        job_id = cups_print_raw(text.encode('utf-8'), printer_name)
        frappe.logger().info(f"Print job sent: {job_id}")
        return job_id
    except Exception as e:
        frappe.log_error(f"Gagal mencetak laporan shift: {str(e)}", "Print Error")
        raise
    
def print_end_day_report_v2(report_data, printer_name=None, debug=False):
    """
    Print End Day Report dari API get_end_day_report_v2
    Layout aman untuk printer thermal 58mm (32 char)
    """

    WIDTH = 32

    def fmt_amt(v):
        return f"{round(flt(v)):,}".replace(",", ".")

    def line():
        return "-" * WIDTH

    def format_lr(left, right):
        left = str(left)
        right = str(right)

        if len(left) > WIDTH - 10:
            left = left[:WIDTH - 10]

        space = WIDTH - len(left) - len(right)
        if space < 1:
            space = 1

        return left + (" " * space) + right

    # FORMAT ITEM TABLE
    # 18 char item | 4 qty | 9 amount
    def format_item(name, qty, amt):
        name = str(name)[:18]
        qty = str(int(qty))[:4]
        amt = fmt_amt(amt)
        return f"{name:<18}{qty:>4} {amt:>9}"

    lines = []

    posting_date = report_data.get("posting_date")
    outlet = report_data.get("outlet")

    summary = report_data.get("summary", {})
    dine_in = report_data.get("dine_in", {})
    take_away = report_data.get("take_away", {})
    payments = report_data.get("payments", {})
    taxes = report_data.get("taxes", {})
    discount_by_order_type = report_data.get("discount_by_order_type", {})
    draft = report_data.get("draft", {})
    void_bill = report_data.get("void_bill", {})
    void_menu = report_data.get("void_menu", {})
    session_time = report_data.get("session_time", {})

    # =========================
    # HEADER
    # =========================

    lines.append("Consolidate Sales".center(WIDTH))
    lines.append(f"Date   : {posting_date}")
    lines.append(f"Shop   : {outlet}")
    lines.append(line())

    # =========================
    # DINE IN SALES
    # =========================

    if dine_in:

        lines.append("DINE IN")
        lines.append(line())
        lines.append(f"{'Item':<18}{'Qty':>4} {'Amount':>9}")
        lines.append(line())

        total_qty = 0
        total_amount = 0

        for group, val in dine_in.items():

            qty = val["qty"]
            amt = val["amount"]

            total_qty += qty
            total_amount += amt

            lines.append(format_item(group, qty, amt))

        lines.append(line())
        lines.append(format_item("TOTAL", total_qty, total_amount))
        lines.append("")

    # =========================
    # TAKE AWAY SALES
    # =========================

    if take_away:

        lines.append("TAKE AWAY")
        lines.append(line())
        lines.append(f"{'Item':<18}{'Qty':>4} {'Amount':>9}")
        lines.append(line())

        total_qty = 0
        total_amount = 0

        for group, val in take_away.items():

            qty = val["qty"]
            amt = val["amount"]

            total_qty += qty
            total_amount += amt

            lines.append(format_item(group, qty, amt))

        lines.append(line())
        lines.append(format_item("TOTAL", total_qty, total_amount))
        lines.append("")

    # =========================
    # SALES SUMMARY
    # =========================

    lines.append("SALES")
    lines.append(line())

    lines.append(format_lr("Total Pax", summary.get("total_pax", 0)))
    lines.append(format_lr("Sub Total", fmt_amt(summary.get("sub_total", 0))))

    discount = summary.get("discount") or 0
    if discount:
        lines.append(format_lr("Discount", f"-{fmt_amt(discount)}"))

    # =========================
    # TAXES (ONLY SKIP ZERO DISCOUNT)
    # =========================
    for tax_name, amt in taxes.items():

        if "discount" in tax_name.lower() and (amt is None or amt == 0):
            continue

        if amt is None or amt == 0:
            continue

        lines.append(format_lr(tax_name, fmt_amt(amt)))

    lines.append(line())
    lines.append(format_lr("GRAND TOTAL", fmt_amt(summary.get("grand_total", 0))))
    lines.append("")

    # =========================
    # ORDER SUMMARY
    # =========================

    # total_dine = sum(v["qty"] for v in dine_in.values()) if dine_in else 0
    # total_take = sum(v["qty"] for v in take_away.values()) if take_away else 0

    # lines.append("TOTAL ORDER")
    # lines.append(line())
    # lines.append(format_lr("Dine In Item", total_dine))
    # lines.append(format_lr("Take Away Item", total_take))
    # lines.append("")

    # =========================
    # DISCOUNT SUMMARY
    # =========================

    if discount_by_order_type:

        lines.append("DISCOUNT")
        lines.append(line())

        for name, val in discount_by_order_type.items():
            qty = val["total_bill"]
            amt = val["total_amount"]

            lines.append(
                format_lr(f"{name} ({qty})", f"-{fmt_amt(amt)}")
            )

        lines.append("")
    
    # =========================
    # PAYMENT SUMMARY
    # =========================

    lines.append("PAYMENT")
    lines.append(line())

    for mop, amt in payments.items():
        lines.append(format_lr(mop, fmt_amt(amt)))

    lines.append("")
        
    # =========================
    # VOID MENU
    # =========================
    lines.append("VOID MENU")
    lines.append(line())

    items = void_menu.get("items") or {}

    if items:
        lines.append(f"{'Item':<18}{'Qty':>4} {'Amount':>9}")
        lines.append(line())

        for name, val in items.items():
            qty = val.get("qty", 0)
            amt = val.get("amount", 0)

            if qty <= 0:
                continue  # safety

            clean_name = clean_item_name(name)
            lines.append(format_item(clean_name, qty, amt))

        lines.append(line())

    # TOTAL
    lines.append(format_lr("Total Qty", int(void_menu.get('total_qty', 0) or 0)))
    lines.append(format_lr("Total Amount", fmt_amt(void_menu.get('total_amount', 0) or 0)))
    lines.append("")

    # =========================
    # VOID BILL
    # =========================

    lines.append("VOID BILL")
    lines.append(line())

    details = void_bill.get("details", [])

    if details:
        for v in details:
            inv = v["invoice"][-8:]
            amt = fmt_amt(v["amount"])
            lines.append(format_lr(inv, amt))

        lines.append(line())

    lines.append(format_lr("Total Bill", void_bill.get("total_bill", 0)))
    lines.append(format_lr("Amount", fmt_amt(void_bill.get("total_amount", 0))))
    lines.append("")
    
    # =========================
    # SESSION TIME
    # =========================
    if session_time:
        lines.append("SESSION TIME")
        lines.append(line())

        for label, val in session_time.items():
            lines.append(label)
            lines.append(format_lr("Pax", val.get("pax", 0)))
            lines.append(format_lr("Bill", val.get("bill", 0)))
            lines.append(format_lr("Avg Pax", val.get("avg_pax", 0)))
            lines.append(format_lr("Avg Bill", fmt_amt(val.get("avg_bill", 0))))
            lines.append("")

    # =========================
    # DRAFT BILL
    # =========================

    if draft.get("total_bill"):

        lines.append("UNPAID SALES")
        lines.append(line())

        for d in draft.get("details", []):

            inv = d["invoice"][-8:]
            amt = fmt_amt(d["amount"])

            lines.append(format_lr(inv, amt))

        lines.append(line())
        lines.append(format_lr("Total Bill", draft.get("total_bill")))
        lines.append(format_lr("Amount", fmt_amt(draft.get("total_amount"))))
        lines.append("")
        
    lines.append("END OF REPORT".center(WIDTH))
    lines.append("")

    text = "\n".join(lines)
    
    if debug:
        print("\n".join(lines))
        return text  
    
    esc_commads = _esc_feed(8) + _esc_cut_full()
    out = text.encode("ascii", "ignore") + esc_commads

    # =========================
    # PRINT
    # =========================

    try:

        if not printer_name:

            conn = cups.Connection()
            printer_name = conn.getDefault()

            if not printer_name:
                printers = conn.getPrinters()
                printer_name = list(printers.keys())[0] if printers else None

            if not printer_name:
                frappe.throw("Tidak ada printer terdeteksi")

        job_id = cups_print_raw(out, printer_name)

        return job_id

    except Exception as e:
        frappe.log_error(str(e), "Print End Day Report Error")
        raise
    
def build_void_item_receipt(pos_invoice: str, items: list[dict], printer_name=None) -> bytes:
    """
    Build ESC/POS print data untuk Void Menu
    """
    WIDTH = 32
    def format_lr(left, right):
        left = str(left)
        right = str(right)

        space = WIDTH - len(left) - len(right)
        if space < 1:
            space = 1

        return left + (" " * space) + right
    
    data = _collect_pos_invoice(pos_invoice)
    current_user = frappe.session.user
    full_name = frappe.db.get_value("User", current_user, "full_name") or current_user
    table_name = get_table_names_from_pos_invoice(pos_invoice)
    pax = get_total_pax_from_pos_invoice(pos_invoice)
    posting_date = data.get("posting_date")
    posting_time = data.get("posting_time")
    try:
        tanggal = getdate(posting_date).strftime("%d-%m-%Y") if posting_date else "-"
    except:
        tanggal = str(posting_date) or "-"
    try:
        jam = get_time(posting_time).strftime("%H:%M:%S") if posting_time else "-"
    except:
        jam = str(posting_time)[:8] if posting_time else "-"
    table_short = str(table_name)[:12]
    
    out = b""
    out += _esc_init()
    out += _esc_font_a()
    out += _esc_align_center() + _esc_bold(True)
    out += b"VOID MENU\n"
    out += _esc_bold(False)
    out += _esc_align_left()
    out += (_line("-") + "\n").encode("ascii", "ignore")
    # out += (f"Invoice : {pos_invoice}\n").encode("ascii", "ignore")
    out += (format_lr(f"Table : {table_short}", tanggal)).encode("ascii", "ignore") + b"\n"
    out += (format_lr(f"Pax   : {int(flt(pax))}", jam)).encode("ascii", "ignore") + b"\n"
    out += (f"Petugas : {get_waiter_name(data['name'])}\n").encode("ascii", "ignore")
    out += (_line("-") + "\n").encode("ascii", "ignore")

    for it in items:
        qty_s = str(it.get("qty") or 0)
        item_name = it.get("item_name") or it.get("resto_menu") or "-"

        # out += _esc_char_size(1, 2)   # double-height, lebar normal
        out += _esc_char_size_dotmatrix(3, 3) + _esc_bold(True)
        display_line = f"{int(flt(qty_s))} x {item_name}"
        out += (display_line + "\n").encode("ascii", "ignore")
        # out += _esc_char_size(0, 0)   # reset ke ukuran normal
        out += _esc_char_size_dotmatrix(0, 0)

        # Add-ons
        add_ons = it.get("add_ons") or ""
        if add_ons:
            add_ons_list = [a.strip() for a in add_ons.split(",")]
            for a in add_ons_list:
                out += (f"  + {a}\n").encode("ascii", "ignore")

        # Notes
        # notes = it.get("quick_notes") or ""
        # if notes:
        #     out += (f"  # {notes}\n").encode("ascii", "ignore")

    out += (_line("-") + "\n").encode("ascii", "ignore")
    out += _esc_feed(5)
    out += _esc_cut_full()

    return out