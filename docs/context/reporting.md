# Reporting — End-Day Report v2

> Detail `get_end_day_report_v2`. Overview di PRD §5.8.

## Endpoint

`resto.api.get_end_day_report_v2(posting_date=None, outlet=None, do_print=False)`

Mobile consumer: `src/pages/SalesReport.js:75` (single endpoint untuk render sales report screen).

## Output Shape

```json
{
  "posting_date": "2026-05-19",
  "outlet": "Cabang Utama",
  "outlet_filter": { ... },
  "summary": {
    "sub_total": 5000000,
    "discount": 250000,
    "tax": 500000,
    "grand_total": 5250000,
    "total_pax": 87
  },
  "dine_in": {
    "Main Course": {"qty": 45, "amount": 2700000},
    "Beverage": {"qty": 30, "amount": 600000}
  },
  "take_away": {
    "Main Course": {"qty": 15, "amount": 900000}
  },
  "payments": {
    "Cash": 3000000,
    "Debit Mandiri": 1500000,
    "QRIS": 750000
  },
  "taxes": {
    "PB1 10%": 500000
  },
  "discount_by_order_type": {
    "BCA Member 10%": {"total_bill": 12, "total_amount": 250000}
  },
  "draft": {
    "total_bill": 3,
    "total_amount": 450000,
    "details": [
      {"invoice": "ACC-PSINV-2026-00099", "order_type": "Take Away", "amount": 150000}
    ]
  },
  "void_bill": {
    "total_bill": 1,
    "total_amount": 80000,
    "details": [...]
  },
  "void_menu": {
    "total_qty": 5,
    "total_amount": 175000,
    "items": {
      "Nasi Goreng": {"qty": 2, "amount": 60000}
    }
  },
  "session_time": {
    "Happy Hour 1 (09:00-11:59)": {"pax": 10, "bill": 8, "amount": 400000, ...},
    "Lunch (12:00-14:59)": {...},
    ...
  }
}
```

## Filter Logic (Critical)

### `get_paid_invoices` (`reporting_repository.py:148`)
```python
filters = {
    "posting_date": posting_date,
    "docstatus": 1,
    "status": ["in", ["Paid", "Consolidated"]],
    ...outlet_filter
}
```
Include: invoice yang sudah submit & paid, baik standalone "Paid" maupun yang sudah di-consolidate ke Sales Invoice (status="Consolidated").

### `get_draft_invoices` (`reporting_repository.py:161`)
```python
filters = {
    "posting_date": posting_date,
    "docstatus": 0,
    "status": "Draft",
    ...outlet_filter
}
```
Include: invoice yang **belum di-submit**. Kasus umum: kasir buat order tapi belum payment (atau logout sebelum bayar, atau end shift sebelum bayar).

**Implication penting**:
- Kalau invoice masuk `draft` section, artinya `docstatus=0` & `status="Draft"` di backend.
- Mobile render takeaway draft = "belum paid" di section khusus.
- Bug yang sering muncul: setelah fix mobile auto-logout (v1.2.42), invoice lama dari sebelum fix tetap di-state `Draft`. Admin perlu manual lanjutkan payment atau void.

## Section Breakdown

### `summary` — dari paid invoices saja
- `sub_total` = sum POS Invoice Item amount (exclude void items)
- `discount` = sum discount_amount
- `tax` = sum Sales Taxes and Charges amount
- `grand_total` = sub_total + tax - discount
- `total_pax` = sum POS Invoice.pax

### `dine_in` / `take_away` — items by group, split by order_type
Iterate `get_items_by_order_type_v2`, key by `item_group`. Note: implementasi line 144-146 overwrite per iterasi (potensi defect kalau ada multiple item dalam group sama dari order_type sama → cek `reporting_service.py:144`).

### `payments` — sum by mode_of_payment
Aggregate dari paid invoices. **Key by mode_of_payment apa adanya** — kalau payments[] pakai child bank ("Debit Mandiri"), itu yang muncul. Tidak auto-aggregate ke parent.

### `draft` — invoices yang belum dibayar
Berisi `details[]` dengan `order_type` per draft → mobile render breakdown "X takeaway belum paid, Y dine-in belum paid".

### `void_bill` — invoices yang sepenuhnya di-cancel
`docstatus=2`. Berbeda dari void_menu (item-level void di invoice yang masih Paid).

### `void_menu` — items void di paid invoices
Aggregate `void_qty * void_rate` per item. Untuk audit "menu apa yang sering di-void".

### `session_time` — bucketing per jam
5 bucket time range (Happy Hour 1, Lunch, High Tea, Happy Hour 2, Dinner). Aggregate bills/amount/pax per bucket. Untuk analytics admin.

## Performance

Target: ≤ 2 detik untuk 200 invoice/hari.

Strategi:
- `reporting_repository` heavy SQL (14.7K, biggest repo) — gunakan JOIN bukan N+1 query
- Filter `outlet_filter` di-detect dari `outlet` arg via `detect_outlet_filter` — bisa branch (mis. `{"branch": "Cabang Utama"}`) atau company/cost_center
- Tidak ada pagination — single round-trip untuk seluruh report (asumsi: ≤ 500 invoice/hari)

## do_print Mode

Jika `do_print=True`:
- Setelah generate dict, call `print_end_day_report_v2(result, printer)`
- Printer di-lookup via `get_printer_for_branch(outlet)`
- Failure print **tidak fail-fast** — log error, return data tetap (mobile tetap bisa render walau print gagal)

## Defect / Backlog

1. `reporting_service.py:144` items grouping overwrite per iterasi — kalau group muncul 2x untuk order_type sama, hanya satu yang ter-record. Verifikasi di production data sebelum prioritaskan fix.
2. Hardcoded time bucket di `reporting_service.py:199-204` — untuk outlet yang jam ops berbeda (bukan 09-24), tidak akurat. Future: configurable per outlet.
3. `outlet_filter` detection logic perlu didokumentasi explicit — saat ini di `reporting_repository.detect_outlet_filter` (cek file).
