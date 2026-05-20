# Payment Flow — Atomic Full-Pay

> Detail flow `pay_invoice`. Overview di PRD §5.4.

## Endpoint Chain

```
Mobile useCompletePayment.js:56
  → payInvoice() in src/api/transaction.js
    → POST /api/method/resto.api.pay_invoice
      → resto/api.py: pay_invoice() (thin wrapper)
        → services/payment_service.py: PaymentService.pay_invoice(pos_invoice, payments)
```

## Kontrak Input

```json
{
  "pos_invoice": "ACC-PSINV-2026-00123",
  "payments": [
    {"mode_of_payment": "Cash", "amount": 80000},
    {"mode_of_payment": "Debit Mandiri", "amount": 20000}
  ]
}
```

## Kontrak Output (sukses)

```json
{
  "ok": true,
  "message": "Pembayaran berhasil",
  "pos_invoice": "ACC-PSINV-2026-00123",
  "total_paid": 100000,
  "change_amount": 0
}
```

`change_amount` > 0 jika ada kembalian. Mobile tampilkan "Kembalian: Rp X" di toast.

## Step-by-Step (`payment_service.py:32-98`)

1. **Parse `payments`** — jika string, JSON decode. Validate list non-empty.
2. **Normalize** — strip whitespace mode_of_payment, validate amount > 0.
3. **Sum `total_paid`** = sum(normalized.amount).
4. **Fetch invoice** — `frappe.get_doc("POS Invoice", pos_invoice)`.
5. **Validate full-pay** — `grand = rounded_total or grand_total`. Jika `grand - total_paid > 1` → throw "Pembayaran Belum Lunas".
6. **Validate change cover** — `change = max(0, total_paid - grand)`. Jika `change > 1`, validate `cash_total >= change` (filter `_is_cash_mode`). Jika tidak → throw "Kembalian Tidak Bisa Diberikan".
7. **Replace payments** — `doc.set("payments", [])`, `doc.append(...)` per row.
8. **Set change** — `doc.change_amount = change` jika ada.
9. **`doc.submit()`** — ERPNext auto:
   - Validate docstatus transition (0 → 1)
   - Trigger `before_submit` hook: `block_partial_payment` (event lain `validate_total_paid`)
   - Set `status = "Paid"` jika `outstanding_amount == 0` (via ERPNext base Sales Invoice logic)
   - Trigger `on_submit` hook: `lock_void_value_after_submit`
10. **`clear_table_merged(pos_invoice)`** — cleanup if table was merged
11. **`frappe.db.commit()`** — flush transaksi

## Cash Mode Detection (`payment_service.py:100-105`)

```python
@staticmethod
def _is_cash_mode(mode_of_payment):
    # Cek field `type == "Cash"` di DocType Mode of Payment bawaan ERPNext.
    # Aman: pakai .type, bukan match nama (yang bisa "Cash"/"Tunai"/dll).
    mop = frappe.get_cached_doc("Mode of Payment", mode_of_payment)
    return (mop.type or "").lower() == "cash"
```

Convention: Sopwer pakai 2 MOP cash standar — `"Cash"` dan boleh juga rename per outlet (e.g. `"Tunai Cabang Utama"`), asal `type == "Cash"` di doctype.

## Parent / Child Bank Pattern (v1.2.41)

**Problem awal (sebelum v1.2.41)**: mobile `cashAmount` di-key by parent (`"Debit"`), tapi user pilih child (`"Debit Mandiri"`). Saat dikirim ke backend, `payments[].mode_of_payment` = parent. Akibatnya struk receipt cetak `"Debit"` (parent), bukan `"Debit Mandiri"` (child) → user ngamuk.

**Solusi v1.2.41**: mobile sekarang key cashAmount by **child** saat bank dipilih. Backend tetap atomic — replace payments dari mobile apa adanya. Struk cetak nama child yang sesuai user pilih.

**Implication untuk backend**:
- Validate `mode_of_payment` di payments[] adalah valid MOP (parent atau child). Frappe akan throw kalau invalid.
- Reporting: `payments_summary_v2` di `reporting_repository` group by `mode_of_payment` apa adanya. Kalau mau aggregate per parent, query side perlu join ke MOP parent_account_type.

## Failure Modes & Error Messages

| Error | Throw oleh | Penyebab |
|---|---|---|
| "Pembayaran Belum Lunas" | `payment_service.py:62` | total_paid < grand_total |
| "Kembalian Tidak Bisa Diberikan" | `payment_service.py:75` | cash_total < change |
| "mode_of_payment wajib di setiap row payments" | `payment_service.py:52` | row tanpa mode_of_payment |
| "amount untuk X harus > 0" | `payment_service.py:54` | row amount ≤ 0 |
| "payments tidak valid JSON" | `payment_service.py:42` | parse fail |
| "payments harus list dan tidak boleh kosong" | `payment_service.py:44` | empty list |

Mobile catch `err?.response?.data?._server_messages` → show toast "Gagal proses pembayaran. Pastikan kembalian tertutup pembayaran tunai." (lihat `useCompletePayment.js:58-61`).

## Backend Event Hooks (chained dari `doc.submit()`)

1. `before_submit: block_partial_payment` — extra defense: assert outstanding == 0 post-payments-set
2. `on_submit: lock_void_value_after_submit` — freeze void_amount/void_qty supaya tidak bisa diubah pasca Paid
3. ERPNext base: `set_status()` → `status = "Paid"` jika outstanding == 0

## Catatan

- `pay_invoice` **bukan idempotent** — call kedua untuk invoice yang sudah submitted akan throw (ERPNext block submit-twice). Mobile sudah handle via UI disabled button + error catch.
- `change_amount` di stored di doc.change_amount (ERPNext field). Akan muncul di receipt print.
- Sejak v1.1.6 mobile auto-logout setelah send_to_kitchen (untuk Dine In) — payment dilakukan kasir terpisah. Sejak v1.2.42, Take Away di-skip karena kasir = customer device (lihat PRD §5.9).
