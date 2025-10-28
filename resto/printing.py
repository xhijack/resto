# apps/your_app/your_app/pos_receipt.py
from __future__ import annotations
import math
import tempfile
import cups
import frappe
from typing import List, Dict, Any

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

def _pad_lr(left: str, right: str, width: int) -> str:
    # Satu baris: left ... right (rata kiri-kanan)
    space = width - len(left) - len(right)
    if space < 1:
        return (left + " " + right)[0:width]
    return f"{left}{' ' * space}{right}"

# ========== Normalisasi POS Invoice ==========
def _collect_pos_invoice(name: str) -> Dict[str, Any]:
    """Ambil POS Invoice + items/payments/taxes lewat frappe.get_doc."""
    doc = frappe.get_doc("POS Invoice", name)

    currency = doc.get("currency") or "IDR"
    items = []
    for it in doc.get("items", []):
        items.append({
            "item_code": it.get("item_code"),
            "item_name": it.get("item_name") or it.get("item_code"),
            "qty": float(it.get("qty") or 0),
            "rate": float(it.get("rate") or 0),
            "amount": float(it.get("amount") or 0),
            "uom": it.get("uom") or it.get("stock_uom"),
            "discount_percentage": float(it.get("discount_percentage") or 0),
            "discount_amount": float(it.get("discount_amount") or 0),
            "description": it.get("description") or "",
        })

    taxes = []
    for tx in doc.get("taxes", []):
        tval = tx.get("tax_amount_after_discount_amount")
        if tval is None:
            tval = tx.get("tax_amount")
        taxes.append({
            "description": tx.get("description") or "Tax",
            "amount": float(tval or 0),
            "rate": float(tx.get("rate") or 0),
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

    grand_total = float(doc.get("rounded_total") or doc.get("grand_total") or 0)
    change_amount = doc.get("change_amount")
    if change_amount is None:
        change_amount = max(0.0, total_paid - grand_total)

    return {
        "name": doc.get("name"),
        "posting_date": str(doc.get("posting_date") or ""),
        "posting_time": str(doc.get("posting_time") or ""),
        "company": doc.get("company") or "",
        "customer": doc.get("customer") or "",
        "customer_name": doc.get("customer_name") or "",
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

def build_kitchen_receipt(data: Dict[str, Any], station_name: str, items: List[Dict]) -> bytes:
    out = b""
    out += _esc_init()
    out += _esc_font_a()
    out += _esc_align_center() + _esc_bold(True)
    out += (f"KITCHEN ORDER - {station_name}\n").encode("ascii", "ignore")
    out += _esc_bold(False) + _esc_align_left()

    out += (f"Invoice: {data['name']}\n").encode("ascii", "ignore")
    out += (f"Tanggal: {data['posting_date']} {data['posting_time']}\n").encode("ascii", "ignore")
    out += _line("-").encode() + b"\n"

    for it in items:
        qty = int(it["qty"]) if it["qty"].is_integer() else it["qty"]
        line = f"{qty} x {it['item_name']}"
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
        results = []

        raw = build_escpos_from_pos_invoice(name, bool(int(add_qr)), qr_data)
        job_id = cups_print_raw(raw, printer_name)
        results.append({"printer": printer_name, "job_id": job_id, "type": "bill"})

        kitchen_groups: Dict[str, List[Dict]] = {}
        for it in data["items"]:
            for printer in get_item_printers(it):
                kitchen_groups.setdefault(printer, []).append(it)

        for kprinter, items in kitchen_groups.items():
            raw_kitchen = build_kitchen_receipt(data, kprinter, items)
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
        if add_ons:
            out += (f"  Add  : {_fit(add_ons, LINE_WIDTH-8)}\n").encode("ascii", "ignore")
        if qnotes:
            out += (f"  Note : {_fit(qnotes, LINE_WIDTH-8)}\n").encode("ascii", "ignore")

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
# ========== Builder ESC/POS Print Bill ==========
def build_escpos_bill(name: str) -> bytes:
    data = _collect_pos_invoice(name)

    items = data.get("items", [])
    payments = data.get("payments", [])
    taxes = data.get("taxes", [])

    company = data.get("company") or ""
    customer = data.get("customer_name") or data.get("customer") or ""
    total = data.get("total", 0)
    discount = data.get("discount_amount", 0)
    tax_total = data.get("total_taxes_and_charges", 0)
    grand_total = data.get("grand_total", 0)
    paid = data.get("paid_amount", 0)
    change = data.get("change_amount", 0)

    out = b""
    out += _esc_init()
    out += _esc_font_a()

    # ===== HEADER =====
    if company:
        out += _esc_align_center() + _esc_bold(True)
        out += (f"{company}\n").encode("ascii", "ignore")
        out += _esc_bold(False)

    out += _esc_align_left()
    out += (f"Invoice: {data['name']}\n").encode("ascii", "ignore")
    if customer:
        out += (f"Customer: {customer}\n").encode("ascii", "ignore")
    out += b"\n"

    # ===== ITEMS =====
    for item in items:
        item_name = item.get("item_name", "")
        qty = item.get("qty", 0)
        rate = item.get("rate", 0)
        amount = item.get("amount", 0)

        # Nama item
        out += (f"{item_name}\n").encode("ascii", "ignore")

        # Qty x Harga = Subtotal
        line = f"  {qty} x {format_number(rate)}".ljust(24) + f"{format_number(amount)}"
        out += (line + "\n").encode("ascii", "ignore")

    out += b"\n"

    # ===== TOTALS =====
    out += ("Subtotal:".ljust(24) + f"{format_number(total)}\n").encode("ascii", "ignore")
    if discount:
        out += ("Discount:".ljust(24) + f"-{format_number(discount)}\n").encode("ascii", "ignore")
    if tax_total:
        out += ("Tax:".ljust(24) + f"{format_number(tax_total)}\n").encode("ascii", "ignore")

    out += _esc_bold(True)
    out += ("TOTAL:".ljust(24) + f"{format_number(grand_total)}\n").encode("ascii", "ignore")
    out += _esc_bold(False)

    # ===== PAYMENT =====
    out += b"\n"
    for pay in payments:
        mop = pay.get("mode_of_payment") or "-"
        amt = pay.get("amount") or 0
        out += (f"{mop}:".ljust(24) + f"{format_number(amt)}\n").encode("ascii", "ignore")

    if change:
        out += ("Change:".ljust(24) + f"{format_number(change)}\n").encode("ascii", "ignore")

    # ===== FOOTER =====
    out += b"\n"
    out += _esc_align_center()
    out += b"Terima kasih!\n"
    out += _esc_feed(2)
    out += _esc_cut_full()

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
