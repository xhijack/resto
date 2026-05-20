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

## Checklist Saat Ubah di Backend

- [ ] **Tambah field baru** di DocType yang dibaca mobile? → optional, mobile abaikan extra field, OK
- [ ] **Ubah/hapus field existing** yang dibaca mobile? → **BREAKING** — koordinasi dengan dev mobile dulu. Update tabel "DocType Field Shape" di atas. Bump backend version reference di mobile changelog.
- [ ] **Ubah signature endpoint whitelisted**? → **BREAKING** — update mobile dulu, lalu deploy backend.
- [ ] **Tambah status baru** di POS Invoice / table / status_kitchen? → cek mobile `SalesReport.js`, `useCompletePayment.js:93`, `useSaveInvoice.js`. Update mobile + dokumentasi sebelum merge.
- [ ] **Rename mode_of_payment / discount template**? → mobile masih jalan karena lookup by name, tapi report yang sudah generated akan ada nama lama → flag ke admin.
- [ ] **Migration (alter field tipe/value)**? → tulis ADR di `docs/decisions/NNNN-rename-X.md` (folder belum ada, buat saat dibutuhkan).
- [ ] **Update tabel di file ini** untuk perubahan endpoint baru / signature baru.
- [ ] **Mirror update** di `mobile-apps/sopwer-resto-pos/docs/context/cross-repo.md` (PR di kedua repo, ideal merge sehari).

---

## Pernah Kejadian (audit trail)

- **v1.2.41 mobile** — takeaway auto-logout: feature v1.1.6 (Dine In shared device) tidak dibedakan dari Take Away → invoice draft tertinggal karena logout sebelum payment. Fix di mobile sisi (skip auto-logout untuk Take Away). Backend tidak berubah, tapi pembelajaran: orderType branching wajib di kedua sisi konsisten.
- **v1.2.41 mobile** — parent vs child bank di payments[]: mobile sebelumnya key cashAmount by parent ("Debit"), receipt cetak nama parent padahal user pilih child ("Debit Mandiri"). Fix mobile sisi (key by child). Backend `pay_invoice` apa adanya — terima nama MOP, mobile yang harus kirim correct.
- **v1.1.x race condition** — 2 waiter bersamaan tambah order ke meja sama → 1 invoice orphan. Fix: backend `add_table_order` jadi atomic dengan lock + dedupe. Mobile harus pakai `addTableOrder` (bukan `updateTableStatus` snapshot REPLACE).

Pelajaran: **kontrak silang yang tidak ter-validate = bug production**. File ini ada untuk mencegah recurrence.
