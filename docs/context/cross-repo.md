# Cross-Repo Validation — Backend ↔ Mobile

> Kontrak silang dengan mobile RN POS. Setiap perubahan di backend yang
> menyentuh tabel di bawah HARUS validasi ke mobile (atau koordinasi
> dengan dev mobile). Mismatch = invoice rusak / order hilang / report salah.

**Mobile repo**: `github.com/xhijack/sopwer-resto-pos` (branch `version-1`)
**Mobile docs**: `mobile-apps/sopwer-resto-pos/docs/context/cross-repo.md` (versi mirror dari sisi mobile)

---

## Endpoint Consumers

Backend implements → mobile depends. Saat ubah signature/behavior endpoint di bawah, **WAJIB** koordinasi.

| Backend endpoint | Mobile hook/screen | Behavior contract |
|---|---|---|
| `payment_service.pay_invoice` | `src/hooks/useCompletePayment.js:56` (via `payInvoice` di `src/api/transaction.js`) | Atomic full-pay: replace doc.payments + submit. Return harus include `change_amount` untuk toast "Kembalian Rp X". Throw "Pembayaran Belum Lunas" / "Kembalian Tidak Bisa Diberikan" untuk failure cases mobile sudah handle. |
| `api.send_to_kitchen` | `src/hooks/useSaveInvoice.js:206-213` (via `useSendToKitchen`) | Create new draft POS Invoice atau merge ke existing. Return invoice name. Untuk takeaway, generate queue_number. |
| `api.add_table_order` | `src/hooks/useSaveInvoice.js:231` & `src/hooks/useCompletePayment.js` (via `addTableOrder`) | Atomic lock + dedupe. Race condition fix v1.2.x bergantung pada ini. Idempotent. |
| `api.remove_table_order` | `src/hooks/useCompletePayment.js:105` | Remove paid invoice link dari table. Idempotent. |
| `api.update_table_meta` | `src/hooks/useCompletePayment.js:110,113` | Update status/taken_by/pax/customer per table. |
| `api.get_all_tables_with_details` | `src/hooks/useTableLoader.js`, `src/hooks/useTablePolling.js` | Return all tables grouped by zone with orders[]. Allow guest=True. |
| `api.create_pos_invoice` | `src/hooks/useSaveInvoice.js` | Field list mobile kirim vs backend expect — lihat DocType Field Shape di bawah. |
| `reporting_service.get_end_day_report_v2` | `src/pages/SalesReport.js:75` | Shape `{summary, dine_in, take_away, draft: {details[order_type, ...]}, payments, taxes, ...}` — mobile render section berdasar struktur ini. |
| `api.login_with_pin` | `src/pages/Login.js` (via `loginWithPin`) | Allow guest. Return user info + API key + secret. |
| `api.print_bill_now` | `src/hooks/usePrintActions.js` | ESC/POS print bill draft |
| `api.print_receipt_now` | `src/hooks/usePrintActions.js`, `useCompletePayment.js:66` | ESC/POS print receipt setelah Paid. Auto-trigger setelah pay_invoice sukses. |
| `api.print_check_now` | `src/hooks/usePrintActions.js` | ESC/POS print check (verifikasi sebelum bill) |
| `api.apply_discount` | `src/hooks/usePayment.js` (discount flow) | Set discount di POS Invoice draft. Via taxes child table (Discount row). |
| `api.void_pos_invoice` | `src/hooks/useVoidFlow.js` | Cancel invoice (docstatus 1 → 2). Set status_kitchen="Void Menu" per item. |
| `api.get_all_branch_menu_with_children` | `src/hooks/useMenuCatalog.js` | Return menu dengan parent-child variant. Cache di WatermelonDB. |
| `api.end_shift` | `src/pages/SalesReport.js` (end shift button) | Print shift report + close session per kasir. |

_(masih ada ~30 endpoint lain — lihat catalog lengkap di `../PRD.md` §7)_

---

## Status String Conventions (CRITICAL)

Mobile bandingkan literal string ini ke field backend. Backend ubah → mobile crash silent.

### `order_type`
- Valid: `"Dine In"` | `"Take Away"`
- Mobile compare di: `useSaveInvoice.js:226,244`, `useCompletePayment.js:74`, banyak tempat
- Jangan: case berbeda (`"dine in"`, `"DINE-IN"`), i18n (`"Makan di Tempat"`)

### POS Invoice `status`
- Valid: `"Draft"` | `"Paid"` | `"Consolidated"` | (cancelled = `docstatus=2`, status biasanya `"Cancelled"`)
- Mobile compare di: `useCompletePayment.js:93`, `SalesReport.js` (paid vs draft section)
- Jangan: introduce status baru tanpa update mobile

### `table.status`
- Valid: `"Kosong"` | `"Terisi"` | `"Reserved"` | `"Pending"`
- Mobile render di: `src/components/TableSelect.js`, `Table.js` color/badge logic
- Jangan: rename ("Empty", "Available")

### `mode_of_payment` (di payments[])
- Pakai nama child bank (`"Debit Mandiri"`, `"Debit BCA"`, `"QRIS DANA"`), bukan parent
- Cash mode pakai `type="Cash"` di MOP doctype (nama bisa `"Cash"`, `"Tunai"`, dll asal type cocok)

### `status_kitchen` (per POS Invoice Item)
- Valid: `"Not Send"` | `"Already Send"` | `"Void Menu"`
- Mobile cek di: `useSaveInvoice.js` (filter items untuk send), `useVoidFlow.js`
- Jangan: rename / hapus state

---

## DocType Field Shape

Mobile baca field berikut langsung dari response. Backend hapus/rename = mobile crash.

### POS Invoice (extends Sales Invoice)
Required oleh mobile:
```
name, posting_date, posting_time, customer, branch, order_type, queue_number,
docstatus, status,
grand_total, rounded_total, outstanding_amount, discount_amount, change_amount,
payments[] (with mode_of_payment, amount),
items[] (with item_code, item_name, qty, rate, amount, status_kitchen,
         void_qty, void_rate, void_amount, addOns, notes),
taxes[] (Sales Taxes and Charges rows, untuk Discount + PB1)
```

### Table
```
name, name_table, status, name_floor, name_zone, capacity, current_pax,
taken_by, customer, type_customer, type_table,
orders[] (with invoice_name)
```

### Branch Menu (mobile cache di WatermelonDB)
```
name, branch, resto_menu, item_code, item_name, item_group, brand,
standard_rate, is_available, image,
children[] (variants: spice level, size, etc)
```

---

## Voucher Feature Contract (Phase 1)

Backend `feature/voucher` branch — DocType + hooks + API. Mobile `feature/voucher` branch — hook + popup + wiring. Kontrak silang voucher di bawah, **wajib sinkron** kalau salah satu sisi berubah.

### Endpoint

| Endpoint | Mobile consumer | Contract |
|---|---|---|
| `resto.api.validate_voucher_code` | `src/api/voucher.js::validateVoucherCode`, `src/hooks/useVoucher.js`, `src/components/PopupVoucherInput.js` | Input `{code: string}`. Output `{valid: bool, value: number|null, kind: "Nominal"|"Free Item"|null, valid_upto: "YYYY-MM-DD"|null, status: "Active"|"Redeemed"|"Cancelled"|"Expired"|null, error_message: string|null}`. `valid=true` IFF voucher exists + Active + dalam validity window. Backend tidak mutate state — pure read. |
| `resto.api.create_direct_sale_invoice` | `src/api/directSale.js::createDirectSaleInvoice`, `src/pages/DirectSale.js` | Input `{payload: JSON, payments: JSON}`. `payload = {customer, pos_profile, branch, items:[{item_code,qty,rate}]}` — semua item harus `is_voucher_item=1` (cart voucher-only). `payments = [{mode_of_payment, amount}, ...]` — multi-payment supported (split + change). Output `{invoice_name, status, total_paid, change_amount, issued_vouchers:[{code, voucher_value, valid_from, valid_upto, status}]}`. Backend guards: Customer/POS Profile/Mode of Payment existence (throws clear ValidationError, no 500). Payment processing via `PaymentService.pay_invoice` (sama dengan resto POS reguler). |

Tidak ada endpoint khusus untuk **redeem** — redemption auto-trigger via POS Invoice `pay_invoice` flow (lihat "Voucher Redemption Flow" di bawah).

### Voucher Redemption Flow (atomic, via pay_invoice)

Mobile push payment row dengan `mode_of_payment="Voucher"` ke `payInvoice(invoiceName, payments)` (existing endpoint). Backend hooks gating + state mutation:

```
[mobile]   buildPaymentsList(cashAmount, appliedVouchers)
              -> payments[] inc {mode_of_payment:"Voucher", amount, voucher_code}
[mobile]   payInvoice(invoiceName, payments)  →  resto.api.pay_invoice
[backend]  doc_events POS Invoice:
              before_submit  → validate_voucher_payments(doc)
                                - voucher_code wajib
                                - Voucher exists + Active + within validity
                                - payment.amount == voucher.voucher_value (single-use, no partial)
              on_submit      → redeem_vouchers_on_pos_invoice_submit(doc)
                                - voucher.status: Active → Redeemed
                                - voucher.redeemed_via_invoice = invoice.name
                                - voucher.redeemed_at = now
                                - GL auto via Mode of Payment Voucher → Unearned Voucher Revenue
              on_cancel      → unredeem_vouchers_on_pos_invoice_cancel(doc)
                                - voucher.status: Redeemed → Active
                                - clear redeemed_via_invoice / redeemed_at
```

### Voucher Payment Row Shape (mobile → backend)

| Field | Required | Catatan |
|---|---|---|
| `mode_of_payment` | yes | Harus literal string `"Voucher"` |
| `amount` | yes | Number. **MUST equal** `voucher.voucher_value` — single-use, sisa hangus. Mismatch → backend throw "Voucher Amount Mismatch" |
| `voucher_code` | yes | 10-char uppercase hash (Frappe `generate_hash(length=10).upper()`) |

Mobile build via `src/popupPayment.js::buildPaymentsList(cashAmount, appliedVouchers)` — 1 row per Voucher, **tidak boleh** digabung. Multiple vouchers in 1 invoice → multiple Voucher payment rows.

### Voucher Issuance Flow (sold voucher)

Cashier scan Item yang flag `is_voucher_item=1`. Saat POS Invoice submit:

```
doc_events POS Invoice on_submit
  → issue_vouchers_from_pos_invoice(doc)
    untuk tiap item line:
       jika frappe.db.get_value("Item", item.item_code, "is_voucher_item") == 1:
         loop range(item.qty):
           insert Voucher(
             voucher_kind="Nominal",
             voucher_value=item.rate,
             valid_from=today,
             valid_upto=today + Item.voucher_validity_days (fallback 90 days kalau 0),
             source="Sold",
             sold_via_invoice=doc.name,
           )
```

Item custom fields yang relevan (auto-install via `install.py:add_voucher_custom_fields()`):
- `Item.is_voucher_item` — Check, default 0
- `Item.voucher_validity_days` — Int, default 90, depends_on is_voucher_item

Sample voucher items auto-created via `voucher_setup.py::setup_voucher_items()`:
- Item Group "Voucher" (parent: All Item Groups)
- 3 Items: `Voucher Rp50.000`, `Voucher Rp100.000`, `Voucher Rp250.000` (rate sesuai)

### Direct Sale Mode — Jual Voucher Lewat `create_direct_sale_invoice`

Endpoint dedicated untuk jual voucher tanpa kitchen routing (DirectSale screen mobile). Flow:

```
[mobile]   DirectSale.js → "Bayar" → PopupPayment modal
              (multi-method, keypad, change, bank child — sama dengan resto POS reguler)
[mobile]   PopupPayment.onCompletePayment → handleCompletePayment({payments})
              → createDirectSaleInvoice(payload, payments)
              → POST resto.api.create_direct_sale_invoice
[backend]  create_direct_sale_invoice (api.py):
              1. Guard Customer/POS Profile/Mode of Payment existence (throw clear error)
              2. Cart voucher-only enforcement (is_voucher_item=1 untuk semua items)
              3. Insert POS Invoice draft + initial payments (ERPNext require ≥1 payment row di insert)
              4. PaymentService.pay_invoice(invoice, payments) — inherit split/change/cash-cover validation + submit
              5. on_submit hook: issue_vouchers_from_pos_invoice → N Voucher records per qty
              6. Query Voucher WHERE sold_via_invoice=invoice.name
              7. Return {invoice_name, status, total_paid, change_amount, issued_vouchers:[...]}
[mobile]   On success → setIssuedResult({...}) → VoucherIssuedModal opens
              (list code+value+valid_upto, tap code untuk copy ke clipboard)
```

**Mode of Payment guard contract**: kalau MoP `Cash`/`Debit Mandiri`/etc tidak ada di tabMode of Payment, backend throw `frappe.ValidationError` dengan title "Mode of Payment Tidak Valid". Mobile catch via `err?.response?.data?.message`.

**Customer guard contract**: hardcode `DEFAULT_CUSTOMER = 'Walk In Cust'` di mobile (`DirectSale.js:20`) — Customer record dengan nama persis itu **wajib ada di tabCustomer** di setiap site outlet. Kalau tidak, backend throw "Customer Tidak Ditemukan". (Pelajaran: 2026-05-27 RIAU outlet — Customer record absent → ERPNext core unpack TypeError → user lihat 500 generic.)

### Custom Field di Sales Invoice Payment

- `voucher_code` — Data, insert_after `mode_of_payment`. Mobile populate field ini hanya kalau `mode_of_payment == "Voucher"`.

### Voucher Status Canonical (4 states)

| Status | Arti | Transisi keluar |
|---|---|---|
| `Active` | Baru issued atau un-redeemed setelah POS Invoice cancel. Bisa diredeem. | → Redeemed (saat dipakai bayar), → Cancelled (saat SI penerbit cancel sebelum dipakai) |
| `Redeemed` | Sudah dipakai bayar. Linked via `redeemed_via_invoice`. | → Active (saat SI redeemer cancel — un_redeem hook) |
| `Cancelled` | SI penerbit cancelled sebelum voucher dipakai. Terminal. | — |
| `Expired` | (reserved untuk future scheduled task; saat ini status tetap "Active" tapi `is_redeemable()` return False berdasar `valid_upto`) | — |

Mobile harus pakai string ini exact saat display / compare.

### Akun & Mode of Payment

Setup via `voucher_setup.py::setup_voucher_accounting()` (auto via `after_migrate`):
- **Account** "Unearned Voucher Revenue" (Liability, per Company) — credit saat voucher sold, debit saat redeemed
- **Account** "Voucher Promotional Expense" (Expense, per Company) — buat handle voucher gratis (Phase 2 lebih lanjut)
- **Mode of Payment** "Voucher" (type=General, global) — `accounts[].default_account` per company = Unearned Voucher Revenue

GL Entry contoh redemption (customer makan Rp80K, bayar voucher Rp50K + cash Rp30K):
```
Dr Cash                         30,000
Dr Unearned Voucher Revenue     50,000   ← liability released
   Cr Revenue                            80,000
```

### Voucher DocType — Fields yang Dibaca Mobile (via API)

Mobile **tidak baca** Voucher DocType langsung — semua lewat `validate_voucher_code`. Tapi kalau ada feature future yang baca via `frappe.client.get`:

| Field | Type | Catatan |
|---|---|---|
| `code` / `name` | Data | Primary key. Sama valuenya. 10-char uppercase. |
| `voucher_kind` | Select | `"Nominal"` Phase 1; `"Free Item"` Phase 2 |
| `voucher_value` | Currency | Wajib > 0 kalau Nominal |
| `valid_from`, `valid_upto` | Date | Inclusive range. Outside → not redeemable. |
| `status` | Select | Lihat tabel canonical di atas. read-only. |
| `source` | Select | `"Sold"` (auto saat POS) atau `"Free"` (bulk batch). read-only. |
| `sold_via_invoice` | Link POS Invoice | read-only. Set saat issuance hook. |
| `redeemed_via_invoice` | Link POS Invoice | read-only. Set saat redemption hook. |
| `redeemed_at` | Datetime | read-only. |
| `batch_id` | Data | Optional. Untuk free voucher dari Voucher Batch. |

### Voucher Batch DocType (free voucher bulk generation, admin Frappe only)

Mobile **tidak interact** dengan Voucher Batch. Admin Frappe desk only. Field utama: `batch_name`, `voucher_kind`, `voucher_value`, `voucher_count`, `valid_upto`, `is_generated` (Check), `generated_count`, `generated_by`, `generated_at`. Method `generate_vouchers()` create N Voucher records `source="Free"`, idempotent guard pakai `is_generated`.

---

## Checklist Saat Ubah di Backend

- [ ] **Tambah field baru** di DocType yang dibaca mobile? → optional, mobile abaikan extra field, OK
- [ ] **Ubah/hapus field existing** yang dibaca mobile? → **BREAKING** — koordinasi dengan dev mobile dulu. Update tabel "DocType Field Shape" di atas. Bump backend version reference di mobile changelog.
- [ ] **Ubah signature endpoint whitelisted**? → **BREAKING** — update mobile dulu, lalu deploy backend.
- [ ] **Tambah status baru** di POS Invoice / table / status_kitchen? → cek mobile `SalesReport.js`, `useCompletePayment.js:93`, `useSaveInvoice.js`. Update mobile + dokumentasi sebelum merge.
- [ ] **Rename mode_of_payment / discount template**? → mobile masih jalan karena lookup by name, tapi report yang sudah generated akan ada nama lama → flag ke admin.
- [ ] **Migration (alter field tipe/value)**? → tulis ADR di `docs/decisions/NNNN-rename-X.md` (folder belum ada, buat saat dibutuhkan).
- [ ] **Update tabel di file ini** untuk perubahan endpoint baru / signature baru.
- [ ] **Mirror update** di `mobile-apps/sopwer-resto-pos/docs/context/cross-repo.md` (PR di kedua repo, ideal merge sehari).
- [ ] **Ubah Voucher kind/status/source enum** atau payment row shape? → **BREAKING** untuk mobile. Update tabel "Voucher Status Canonical" + "Voucher Payment Row Shape" di atas, plus mirror di mobile docs.
- [ ] **Ubah behavior `validate_voucher_code` output**? → **BREAKING**. Field `valid`, `value`, `kind`, `valid_upto`, `status`, `error_message` semuanya dipakai mobile (useVoucher hook + PopupVoucherInput). Tambah field baru OK (mobile abaikan), ubah/hapus existing field bawa down mobile UI.

---

## Pernah Kejadian (audit trail)

- **v1.2.41 mobile** — takeaway auto-logout: feature v1.1.6 (Dine In shared device) tidak dibedakan dari Take Away → invoice draft tertinggal karena logout sebelum payment. Fix di mobile sisi (skip auto-logout untuk Take Away). Backend tidak berubah, tapi pembelajaran: orderType branching wajib di kedua sisi konsisten.
- **v1.2.41 mobile** — parent vs child bank di payments[]: mobile sebelumnya key cashAmount by parent ("Debit"), receipt cetak nama parent padahal user pilih child ("Debit Mandiri"). Fix mobile sisi (key by child). Backend `pay_invoice` apa adanya — terima nama MOP, mobile yang harus kirim correct.
- **v1.1.x race condition** — 2 waiter bersamaan tambah order ke meja sama → 1 invoice orphan. Fix: backend `add_table_order` jadi atomic dengan lock + dedupe. Mobile harus pakai `addTableOrder` (bukan `updateTableStatus` snapshot REPLACE).

Pelajaran: **kontrak silang yang tidak ter-validate = bug production**. File ini ada untuk mencegah recurrence.
