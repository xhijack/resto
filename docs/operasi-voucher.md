# Panduan Operasional Voucher — Backend Frappe

Dokumen ini ditujukan untuk **admin / manager / operator** restoran yang akan mengelola fitur voucher di backend Frappe. Tidak perlu background developer.

Untuk referensi teknis (kontrak API, lifecycle internal, code path) lihat `docs/context/cross-repo.md` dan `voucher_setup.py`.

---

## Ringkasan Fitur

Voucher di Sopwer Resto bisa dipakai dua cara:

1. **Dijual** sebagai item POS — customer beli voucher Rp50K, terima kode unik 10 karakter, nanti bisa dipakai untuk bayar.
2. **Dibagi gratis** lewat bulk generate — admin generate ratusan kode sekaligus untuk event/promo, lalu kirim ke peserta lewat WA/email/print.

Setelah voucher diredeem di POS, status berubah dari `Active` → `Redeemed`. Akunting otomatis: liability "Unearned Voucher Revenue" turun, revenue diakui penuh sesuai konsumsi customer.

---

## 1. Setup awal (one-time, sesudah deploy)

Langkah ini dijalankan **sekali** sehabis update aplikasi resto. Sebagian besar otomatis lewat `bench migrate`.

### 1.1 Pastikan migrate jalan tanpa error

```
bench --site <namasite> migrate
```

Setelah selesai, otomatis tercipta:
- **Item Group** "Voucher" (di bawah "All Item Groups")
- **3 sample Item**:
  - `Voucher Rp50.000` (standard_rate = 50.000)
  - `Voucher Rp100.000` (standard_rate = 100.000)
  - `Voucher Rp250.000` (standard_rate = 250.000)
  - Semua: non-stock, `is_voucher_item=1`, masa berlaku 90 hari
- **Account** "Unearned Voucher Revenue" (Liability) per Company
- **Account** "Voucher Promotional Expense" (Expense) per Company
- **Mode of Payment** "Voucher" (type=General) + per-Company default_account = Unearned Voucher Revenue
- **Custom field** `voucher_code` di Sales Invoice Payment

### 1.2 Pastikan MOP "Voucher" muncul di POS Profile

Tombol "Voucher" akan muncul di POS hanya kalau MOP "Voucher" terdaftar di POS Profile yang dipakai cashier.

Cara cek: Frappe desk → **POS Profile** → buka profile yang dipakai (mis. "POS Cabang Cilandak") → tab **Payments** → pastikan ada baris dengan `Mode of Payment = Voucher`.

Kalau belum ada:
1. Klik "Add Row" di tabel Payments.
2. Pilih `Mode of Payment = Voucher`.
3. Default = unchecked (Voucher bukan default payment).
4. Save.

Ulangi untuk setiap POS Profile di setiap cabang yang ingin support voucher.

### 1.3 (Opsional) Tambah voucher dengan nominal lain

Mau jual voucher Rp500K? Cara:

1. Frappe desk → **Item** → New
2. Item Code & Name: `Voucher Rp500.000`
3. Item Group: `Voucher`
4. UOM: `Nos`
5. Is Stock Item: unchecked (non-stock)
6. Section "Voucher" (custom field):
   - Is Voucher Item: ✓ checked
   - Voucher Validity Days: 90 (atau sesuai kebijakan)
7. Standard Selling Rate: 500000
8. Save.

Item baru otomatis siap dipakai cashier untuk jual voucher Rp500K.

---

## 2. Workflow A — Jual voucher ke customer (via POS)

### Cashier:

1. Buka POS mobile, scan/cari item "Voucher Rp50.000" (atau nominal lain) seperti item biasa.
2. Tambah ke cart, lanjut pembayaran (Cash/EDC).
3. Submit POS Invoice.

**Setelah submit, voucher otomatis lahir di backend.** Backend hook `issue_vouchers_from_pos_invoice` scan item, generate satu Voucher record per qty.

### Cek voucher yang baru lahir (admin):

Frappe desk → **Voucher List** → filter:
- `source = Sold`
- `sold_via_invoice = <nama POS Invoice>`

Field penting:
- `code` — kode unik 10 karakter (UPPERCASE, mis. `A3B7F9D1C2`)
- `voucher_value` — nominal
- `valid_upto` — tanggal kadaluarsa (default today + 90 hari)
- `status` — `Active` setelah lahir

### Distribusi kode ke customer (Phase 1, manual):

Pilih salah satu cara:
- **Tulis tangan di receipt**: cashier print receipt biasa, tulis kode voucher di belakang
- **Print sticker / kartu**: lewat report Frappe → export → print
- **WhatsApp**: ekspor list voucher per invoice → kirim manual ke customer

> Phase 3 ke depan: auto-WhatsApp e-voucher saat penjualan. Belum tersedia di v1.3.0.

---

## 3. Workflow B — Bulk generate voucher gratis untuk event

Misal: 100 voucher Rp25K untuk Grand Opening cabang baru.

### Langkah:

1. Frappe desk → **Voucher Batch** → **New**.
2. Isi field:
   - **Batch Name**: `Event Grand Opening Cilandak Mei 2026` (unik)
   - **Purpose**: deskripsi event
   - **Voucher Kind**: `Nominal`
   - **Voucher Value**: `25000`
   - **Voucher Count**: `100`
   - **Valid Upto**: `2026-08-31` (3 bulan dari sekarang)
3. **Save** (record sekarang status: `is_generated = 0`, belum generate)
4. Klik tombol biru **"Generate Vouchers"** di pojok kanan atas form. Muncul confirm dialog: "Generate 100 vouchers? Tindakan ini tidak bisa diundo." Klik Yes.
5. Setelah selesai: muncul toast "100 voucher berhasil di-generate". Form reload otomatis: `is_generated = 1`, `generated_count = 100`, `generated_by = <user>`, `generated_at = <waktu>`. Tombol Generate Vouchers hilang (idempotent guard).
6. (Alternatif via console kalau Frappe desk tidak available: `frappe.get_doc("Voucher Batch", "Event Grand Opening...").generate_vouchers()`)

### Ambil daftar kode (untuk dibagikan):

Frappe desk → **Voucher List** → filter `batch_id = Event Grand Opening Cilandak Mei 2026`.

Klik **Menu → Export** → CSV/Excel. Hasilnya kolom `code` yang bisa dibagi ke peserta event.

### Aturan:

- **Sekali generate per batch**. Mau tambah voucher? Bikin Voucher Batch baru. Re-generate batch yang sudah terisi akan throw error.
- Voucher dari batch (source=Free) **tidak punya `sold_via_invoice`** — tidak ada penjualan, tidak ada liability yang dicatat. Saat diredeem, GL impact lewat akun "Voucher Promotional Expense" (Phase 2 — saat ini belum di-handle otomatis; kalau pakai free voucher di Phase 1, GL adjustment manual).

---

## 4. Workflow C — Customer pakai voucher di POS

Ini sisi mobile (cashier). Sebagai admin perlu tahu flow-nya buat support cashier:

1. Customer order makanan total Rp80.000.
2. Di payment screen, cashier tap tombol **"Voucher"** di grid Mode of Payment.
3. Modal popup: input kode 10 karakter.
4. Klik **"Validasi"** → app call backend `validate_voucher_code` → cek voucher Active + dalam masa berlaku.
5. Kalau valid: muncul "Voucher valid — Rp50.000". Klik **"Pakai Voucher"**.
6. Voucher row muncul di Payment Breakdown bersama Cash/EDC.
7. Sisa Rp30.000 dibayar dengan metode lain (cash/EDC).
8. Klik **"Complete Payment"** → POS Invoice submit.

**Backend auto-lakukan:**
- `validate_voucher_payments` (before_submit): cek `amount === voucher_value` (single-use, sisa hangus). Mismatch → reject.
- `redeem_vouchers_on_pos_invoice_submit` (on_submit): Voucher.status → `Redeemed`, set `redeemed_via_invoice` + `redeemed_at`.
- GL Entry auto via Mode of Payment Voucher → Dr Unearned Voucher Revenue, Cr Revenue.

### Verify di backend:

Frappe desk → **Voucher List** → filter `status = Redeemed` → buka record:
- `redeemed_via_invoice` linked ke POS Invoice yang baru
- `redeemed_at` = waktu redeem

---

## 5. Monitoring & laporan harian

### List voucher aktif (belum dipakai)

Frappe desk → **Voucher** → filter:
- `status = Active`

Ini posisi liability outstanding di balance sheet.

### List voucher kadaluarsa hari ini

Filter:
- `status = Active`
- `valid_upto <= today`

Bisa untuk follow-up customer "voucher anda akan expired hari ini".

> **Catatan v1.3.0**: status `Expired` belum auto-set otomatis. Voucher kadaluarsa status tetap `Active`, tapi `is_redeemable()` return false. Auto-expire scheduled task akan ditambah di Phase berikut.

### List voucher dijual per kasir

Filter `source = Sold`, lalu group by `sold_via_invoice → owner` (cashier yang submit invoice).

### List voucher diredeem per hari

Filter:
- `status = Redeemed`
- `redeemed_at >= today 00:00`

### Posisi akunting (liability voucher outstanding)

Frappe desk → **General Ledger** → filter `account = Unearned Voucher Revenue - <Company Abbr>` → posisi balance = total voucher value yang belum diredeem.

Total ini harus sama dengan `SUM(voucher_value)` untuk voucher dengan `source=Sold` AND `status=Active`.

---

## 6. Cara cancel / batal voucher

### Voucher belum dipakai (status = Active):

**Cara 1 — via Frappe desk:**
1. Buka Voucher record.
2. Belum ada tombol UI khusus di v1.3.0 — pakai console.

**Cara 2 — via console:**
```python
voucher = frappe.get_doc("Voucher", "A3B7F9D1C2")
voucher.cancel_voucher()
```
Status berubah ke `Cancelled`. Voucher tidak bisa dipakai lagi.

**Cara 3 — cancel POS Invoice penerbit:**
Cancel POS Invoice yang menjual voucher tersebut (`sold_via_invoice`). Voucher otomatis auto-cancel via hook (kalau belum redeemed).

### Voucher sudah dipakai (status = Redeemed) — refund customer:

Cancel POS Invoice yang me-redeem voucher tersebut (`redeemed_via_invoice`).

Backend hook `unredeem_vouchers_on_pos_invoice_cancel` otomatis revert voucher ke `Active` (status balik, `redeemed_via_invoice` + `redeemed_at` di-clear). Voucher bisa dipakai lagi atau di-cancel manual.

### Voucher sudah Redeemed, tidak mau dikembalikan:

POS Invoice penerbit (`sold_via_invoice`) sudah TIDAK bisa di-cancel — voucher di-link ke invoice redeemer. Backend throw error kalau coba cancel.

Workaround: cancel POS Invoice redeemer dulu → un-redeem → baru bisa cancel chain ke atas.

---

## 7. Akunting check (panduan untuk akunting)

### Saat voucher dijual (POS Invoice submit dengan item voucher):

```
Dr Cash / Bank (sesuai MOP customer bayar voucher)    50.000
   Cr Unearned Voucher Revenue                              50.000
```
Liability bertambah Rp50K. Revenue **belum** diakui.

### Saat voucher diredeem (POS Invoice submit dengan payment voucher Rp50K + cash Rp30K, total Rp80K):

```
Dr Cash                              30.000
Dr Unearned Voucher Revenue          50.000     ← liability turun
   Cr Revenue (per item makanan)            80.000
```
Revenue diakui penuh (Rp80K), liability terkurangi sesuai voucher yang dipakai.

### Net effect:

Untuk satu voucher yang dijual lalu diredeem:
- Total Dr Cash/Bank: 50.000 (saat jual) + 30.000 (saat redeem) = 80.000
- Total Cr Revenue: 80.000
- Posisi liability voucher: 0 (net)

Untuk voucher gratis (source=Free) yang diredeem — akun "Voucher Promotional Expense" akan dipakai. Detail mekanisme di Phase 2.

---

## 8. Troubleshoot umum

### "Tombol Voucher tidak muncul di POS mobile"

→ Cek POS Profile yang dipakai cashier punya MOP "Voucher" di tabel Payments. Lihat section 1.2.

### "Voucher code tidak ditemukan saat redeem"

→ Cek typo (uppercase/lowercase sensitive — semua kode uppercase). Cek voucher record di Frappe — mungkin status sudah `Cancelled` atau `Redeemed` (sudah dipakai).

### "Voucher amount mismatch error" saat customer mau bayar pakai voucher

→ Aturan single-use: payment amount **HARUS** sama persis dengan voucher_value. Misal voucher Rp50K — customer harus belanja minimal Rp50K, dan voucher dipakai full Rp50K. Sisa hangus. Customer belanja Rp30K → tolak (transaksi minimal Rp50K).

### "Saya butuh voucher dengan nominal custom (Rp75K, Rp500K, dll)"

→ Tambah Item baru via Item desk. Lihat section 1.3.

### "Voucher kadaluarsa tapi statusnya masih Active"

→ Normal di v1.3.0. Auto-expire scheduled task belum ada. Tapi mobile dan backend tetap reject saat customer mau redeem (cek validity window). Untuk cleanup periodic, bisa jalankan manual:
```python
import frappe
from frappe.utils import nowdate
expired = frappe.get_all("Voucher", filters={"status": "Active", "valid_upto": ["<", nowdate()]}, pluck="name")
for code in expired:
    v = frappe.get_doc("Voucher", code)
    v.cancel_voucher()
```

### "Saya melihat voucher dengan source=Free, batch_id ada — itu dari mana?"

→ Voucher batch (event gratis) — lihat section 3. Cek Voucher Batch dengan `batch_name = <batch_id>` di Frappe desk untuk detail event.

---

## Versi & referensi

- **App backend**: `resto` di `apps/resto`, branch `feature/voucher` (Phase 1, head `41f295d`)
- **Mobile**: `sopwer-resto-pos` v1.3.0 (APK `pos-resto-v1.3.0.apk`)
- **Site test**: `resto.test`
- **Kontrak teknis silang**: `docs/context/cross-repo.md` (section "Voucher Feature Contract")
- **Plan brainstorming awal**: `.claude/plans/kita-brainstorming-yah-jadi-drifting-octopus.md`

## Phase berikut (sneak peek)

- **Phase 2**: voucher kind `Free Item` (1 menu gratis), bukan cuma nominal.
- **Phase 3**: e-voucher auto-WhatsApp saat penjualan, QR code di receipt, voucher single-issue dari POS untuk kompensasi customer.
