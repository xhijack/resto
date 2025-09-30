# apps/your_app/your_app/pos_receipt.py
from __future__ import annotations
import math
import tempfile
import cups
import frappe
from typing import List, Dict, Any

# ========== Konstanta & Util ==========
LINE_WIDTH = 42  # 80mm biasanya nyaman di 42 kolom. Sesuaikan 32-48 jika perlu.

ESC = b"\x1b"
GS  = b"\x1d"

def _esc_init() -> bytes:
    return ESC + b'@'  # Initialize

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
    # Beberapa printer pakai GS V 0 (full cut). Di TM-U220, potongannya tergantung model.
    return GS + b'V' + b'\x00'

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

def _fmt_money(val: float, currency: str = "IDR") -> str:
    # Format Rp dengan pemisah ribuan; tanpa desimal utk rupiah.
    # Jika butuh desimal, ubah jadi: f"{val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    n = 0 if currency.upper() in ("IDR", "RP") else 2
    if n == 0:
        s = f"{int(round(val)):n}"
    else:
        s = f"{val:,.2f}"
    # Lokal ID: titik ribuan, koma desimal. Converter sederhana:
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

def _line(char: str = "-") -> str:
    return (char * LINE_WIDTH)[:LINE_WIDTH]

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
        # Ambil tax_amount_after_discount_amount bila ada, fallback ke tax_amount
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
    # Format baris:
    # Item name (wrap)
    #   qty x rate ............. amount
    for it in data["items"]:
        name = it["item_name"] or it["item_code"] or "-"
        for w in _wrap_text(name, LINE_WIDTH):
            lines.append(w)
        qty_rate = f"{int(it['qty']) if it['qty'].is_integer() else it['qty']} x {_fmt_money(it['rate'], cur)}"
        amount = _fmt_money(it["amount"], cur)
        lines.append(_pad_lr("  " + qty_rate, amount, LINE_WIDTH))
        # Diskon baris (optional)
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

    # Pajak (kalau ada, tampilkan per baris)
    if data["taxes"]:
        for tx in data["taxes"]:
            desc = tx["description"] or "Tax"
            amt  = tx["amount"] or 0.0
            lines.append(_pad_lr(desc, _fmt_money(amt, cur), LINE_WIDTH))

    # Grand Total / Rounded
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

    # Tambah QR (opsional): mis. link ke /printview atau POS Invoice URL
    if add_qr and qr_data:
        out += _esc_align_center()
        out += _esc_qr(qr_data)
        out += _esc_align_left()
        out += _esc_feed(1)

    out += _esc_feed(3) + _esc_cut_full()
    return out

# ========== CUPS RAW PRINT ==========
def cups_print_raw(raw_bytes: bytes, printer_name: str) -> int:
    conn = cups.Connection()
    printers = conn.getPrinters()
    if printer_name not in printers:
        raise frappe.ValidationError(f"Printer '{printer_name}' tidak ditemukan di CUPS")

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(raw_bytes)
        tmp_path = tmp.name

    # Kunci: opsi "raw": "true" agar ESC/POS tak difilter
    job_id = conn.printFile(printer_name, tmp_path, "POS_Receipt", {"raw": "true"})
    return job_id

# ========== API: cetak sekarang (sync) ==========
@frappe.whitelist()
def pos_invoice_print_now(name: str, printer_name: str, add_qr: int = 0, qr_data: str | None = None) -> dict:
    raw = build_escpos_from_pos_invoice(name, bool(int(add_qr)), qr_data)
    job_id = cups_print_raw(raw, printer_name)
    frappe.msgprint(f"Terkirim ke printer '{printer_name}' (Job ID: {job_id})")
    return {"ok": True, "job_id": job_id, "printer": printer_name}

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
