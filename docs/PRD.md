# Resto Sopwer — Product Requirements Document

> **This is the AUTHORITATIVE document for the Resto system.**
> Consumer apps (mobile RN POS, future web POS, API clients) refer here for business
> rules, DocType model, and endpoint contracts. UI-specific concerns (screens, navigation,
> copy text) live in the consumer repo's own docs.

---

## 1. Executive Summary

`resto` adalah ERPNext custom app yang menyediakan platform POS untuk restoran multi-outlet di Indonesia. Modul ini menambah workflow F&B di atas ERPNext base: order taking (dine-in & take-away), kitchen routing, atomic payment, ESC/POS receipt printing, dan end-day consolidated reporting.

**Stakeholder**: PT Sopwer Teknologi Indonesia (`ramdani@sopwer.net`)
**Site live**: `maystar.dev`
**Branch dev**: `version-2`
**Konsumen saat ini**: 1 mobile RN POS (`sopwer-resto-pos`), didesain agar dapat menerima konsumen tambahan (web POS, REST client) tanpa rewrite backend.

---

## 2. Business Context

- **Pasar**: restoran F&B Indonesia dengan 1+ outlet. Tipikal: 50–500 invoice/hari per outlet.
- **Model**: POS terdedikasi per outlet. Kasir & waiter pakai mobile app, manager & admin pakai ERPNext desk via browser.
- **Integrasi base ERPNext**:
  - `POS Invoice` extends `Sales Invoice` — semua finansial leverage ERPNext.
  - `Customer` reuse (default Walk In Cust untuk anonim).
  - `Sales Taxes and Charges Template` untuk PB1/Service.
  - `Mode of Payment` standar ERPNext (Cash/Bank, parent + child detail bank).
- **Asumsi infrastruktur**:
  - 1 backend ERPNext per multi-outlet group (single tenant Frappe site).
  - Printer thermal ESC/POS terhubung via USB/LAN per outlet.
  - Realtime push via `frappe.realtime` (socket.io).

---

## 3. User Roles & Permissions

| Role | Akses | Lewat |
|---|---|---|
| **Kasir** | POS Profile assigned, lihat tables, terima payment, void item, end-shift | Mobile app, login PIN |
| **Waiter** | POS Profile, lihat tables, send to kitchen, no payment | Mobile app, login PIN |
| **Manager** | Multi-outlet view, end-day report, void invoice, override discount | Mobile + ERPNext desk |
| **Admin Ops** | Setup branch, menu, printer, tax template, kitchen station | ERPNext desk |
| **Owner** | Read-only dashboard, reporting | ERPNext desk (built-in script reports) |

Permission detail per role di-manage via DocType `User POS Permission` + standard Frappe role/permission. PIN login (`api.login_with_pin`) generate API key/secret per user dan store di mobile app's AsyncStorage.

---

## 4. Domain Model — Core Concepts

### Branch / Outlet
Field `branch` ada di POS Invoice, Menu, Printer Settings. Single source untuk outlet scoping.

### Table Hierarchy
```
Table Floor (e.g. "Lantai 1")
  └─ Table Zone (e.g. "Indoor / Outdoor / Smoking")
       └─ Table (e.g. "A1") — status: Kosong | Terisi | Reserved | Pending
            └─ Table Order (link ke 1+ POS Invoice yang aktif di table itu)
```

### POS Invoice Lifecycle
```
DRAFT (docstatus=0, status="Draft")
   ↓ pay_invoice → doc.submit()
PAID (docstatus=1, status="Paid")
   ↓ POS Closing Entry consolidates
CONSOLIDATED (docstatus=1, status="Consolidated") — generates regular Sales Invoice
   ↓ alternatif
CANCELLED (docstatus=2) via void_pos_invoice
```

### Menu Hierarchy
```
Resto Menu (master, brand-scoped)
  └─ Branch Menu (per-outlet availability + price override)
       └─ items dengan parent-child variant (e.g. "Nasi Goreng" parent → "Pedas/Sedang/Mild" child)
```

### Kitchen Station
1 menu item → diroute ke 1+ Kitchen Station (e.g. "Hot Kitchen", "Cold Kitchen", "Bar"). Setiap station punya printer assigned. KS Printing = audit log per print job.

### Payment Method (parent + child bank)
- Parent: `"Debit"`, `"Credit"`, `"QRIS"`, `"Cash"`
- Child bank (untuk non-cash): `"Debit Mandiri"`, `"Debit BCA"`, dst.
- Convention: `payments` di POS Invoice di-key by **child** bank name. UI di-aggregate kembali untuk display by parent.

### Discount
2 jenis:
- **Template Discount** — DocType `Discount`, reusable (e.g. "Member 10%")
- **Bank-Specific Discount** — promo bank tertentu (e.g. "Mandiri Cashback 50rb")

Saat split bill, discount **proporsional by subtotal share**.

### POS Consumption
Audit trail per outlet — record qty terpakai per menu per hari untuk reset stock & analytics.

---

## 5. Core Workflows

### 5.1 Login & Session
1. User input PIN di mobile → `api.login_with_pin(pin)` → generate API key/secret
2. Mobile cek POS opening via `useCheckPosOpening` hook → kalau belum ada hari ini, redirect ke buka kasir
3. Session aktif sampai logout manual atau auto-logout (untuk shared device, lihat 5.9)

### 5.2 Dine-In Flow
1. Tap meja di Table screen → buat order baru atau buka existing
2. Tambah item ke cart → `send_to_kitchen` (atau button "Kirim ke Dapur")
3. Backend: create POS Invoice draft + `add_table_order` (atomic lock) + kitchen ticket print
4. Tambah item baru → repeat (existing invoice di-update)
5. User print bill (`print_bill_now`) saat customer minta
6. Terima payment via `pay_invoice` → `doc.submit()` → status="Paid"
7. Mobile clear cart + update table status via `removeTableOrder` + `updateTableMeta`
8. Saat semua invoice di table sudah Paid, table kembali "Kosong"

### 5.3 Take-Away Flow
1. Header tap "Takeaway" → navigate ke NewOrder dengan `orderType="Take Away"`, `id=null`, `selectedTable=null`
2. Tambah item → tap "Proses Order" (button label berbeda dari dine-in "Kirim ke Dapur")
3. Backend: create POS Invoice draft dengan `order_type="Take Away"`, generate `queue_number`, kitchen ticket print
4. **Tidak ada `add_table_order`** (takeaway tidak terikat meja)
5. User langsung lanjut payment → `pay_invoice` → `doc.submit()`
6. Mobile clear cart + navigate balik ke main (tidak ada table cleanup)

**Catatan**: dari v1.2.42, Take Away **tidak auto-logout** setelah save (lihat 5.9).

### 5.4 Payment Flow — Atomic Full-Pay

**Endpoint**: `resto.api.pay_invoice` → `services/payment_service.py: PaymentService.pay_invoice()`

**Kontrak**:
- Input: `pos_invoice` (name) + `payments: [{mode_of_payment, amount}, ...]`
- Behavior:
  1. Validasi: `total_paid >= grand_total` (tolerance 1 rupiah). Kurang → throw "Pembayaran Belum Lunas".
  2. Validasi change: jika `total_paid > grand_total`, `cash_total >= change`. Card tidak boleh kasih kembalian.
  3. `doc.set("payments", [])` → clear existing
  4. `doc.append("payments", p)` untuk setiap row
  5. `doc.change_amount = change` jika ada kembalian
  6. `doc.submit()` — ERPNext auto-set `status="Paid"` + `outstanding_amount=0`
  7. `clear_table_merged(pos_invoice)` — cleanup table merged state
  8. `frappe.db.commit()`

**Rules**:
- ❌ **NO PARTIAL PAYMENT** — `before_submit` event `block_partial_payment` enforce ini di level DocType
- ❌ **NO CARD CHANGE** — kembalian wajib via Cash mode of payment (`type=="Cash"` di DocType MOP)
- ✅ **SPLIT METHODS** — boleh multi-payment dalam 1 invoice (e.g. Cash 800rb + Mandiri Debit 200rb)
- ✅ **PARENT/CHILD BANK** — `mode_of_payment` di payments[] = nama **child** (e.g. "Debit Mandiri"), bukan parent ("Debit"). Sejak v1.2.41 cashAmount di mobile key by child.

### 5.5 Kitchen Flow
1. `send_to_kitchen(payload, table_name, ...)` → create POS Invoice + queue process kitchen printing
2. `_process_kitchen_printing_worker` async — route item ke station-nya, print ticket per station
3. Item field `status_kitchen` lifecycle: `"Not Send"` → `"Already Send"` → optional `"Void Menu"`
4. `void_pos_invoice` set `status_kitchen="Void Menu"` + record `void_qty`, `void_rate`, `void_amount` untuk audit & end-day report
5. `reprint_kitchen_tickets(pos_invoice, item_row_names)` — opsional reprint per item row (mis. kitchen tukar shift)
6. `enqueue_checker_after_kitchen` — print checker (rangkuman order untuk waiter)

**Event hook**: `handle_kitchen_stock` (before_save) — decrement stock saat send. `rollback_kitchen_stock_on_cancel` (on_cancel) — restore stock saat invoice cancelled.

### 5.6 Print Flow
| Output | Endpoint | Kapan |
|---|---|---|
| Kitchen ticket | `process_kitchen_printing` | Auto saat send_to_kitchen |
| Checker | `enqueue_checker_after_kitchen` | Auto setelah kitchen, untuk waiter |
| Bill (draft, sebelum bayar) | `print_bill_now` | Customer minta bill |
| Check (intermediate) | `print_check_now` | Verifikasi item sebelum print bill |
| Receipt (setelah Paid) | `print_receipt_now` | Auto setelah pay_invoice |
| Shift report | `end_shift` | Kasir tutup shift |
| End-day consolidated | `get_end_day_report_v2(do_print=True)` | Admin tutup hari |

**Konvensi cut**: receipt/bill/report pakai `_esc_feed(8) + _esc_cut_full()`. Kitchen ticket pakai `_esc_feed(3)` (lebih kecil, sengaja). Kalau ada laporan "ujung struk kelewat cutter", default escalate feed→8 (commit `d215b3c`).

### 5.7 Discount Flow
1. `apply_discount(invoice_name, discount_data)` — set discount di POS Invoice
2. Backend simpan di taxes child table (Discount row), bukan di header `discount_amount` (sejak v1.2.40)
3. Saat split bill, extractor baca dari taxes child dulu, fallback ke header
4. Distribusi: proportional by subtotal share. Invoice 150K diskon 15K, split 100K + 50K → diskon 10K + 5K.

### 5.8 End-of-Day Flow
1. Per kasir: `end_shift(user, is_submit=True)` → print shift report (per-user summary)
2. Per outlet, admin: `get_end_day_report_v2(posting_date, outlet, do_print=True)` → consolidated print
3. Manual: admin buat POS Closing Entry via desk → invoice di-link, status berubah jadi "Consolidated", generate regular Sales Invoice

### 5.9 Auto-Logout (Shared Device Pattern)
Feature v1.1.6: setelah Dine-In send to kitchen sukses, mobile auto-logout 2.3 detik kemudian (asumsi waiter tablet shared, kasir terpisah). Sejak v1.2.42, **Take Away di-skip** (karena customer perlu langsung bayar di POS yang sama, tidak ada kasir terpisah).

---

## 6. DocType Catalog (34 total)

### Core (7)
| DocType | Purpose |
|---|---|
| `table` | Master meja per outlet — status, kapasitas, current pax |
| `table_zone` | Grouping meja (Indoor/Outdoor/dll) |
| `table_floor` | Lantai dalam outlet |
| `table_order` | Link table ↔ POS Invoice active (atomic via lock) |
| `resto_menu` | Master menu, brand-scoped, parent-child variant |
| `branch_menu` | Per-outlet availability + price override |
| `pos_consumption` | Audit qty terpakai per menu per hari |

### Operations (5)
| DocType | Purpose |
|---|---|
| `kitchen_station` | Master station (Hot, Cold, Bar) + printer link |
| `ks_printing` | Audit log per kitchen print job |
| `pos_invoice` | Extension Sales Invoice — order_type, queue_number, void fields, kitchen status |
| `user_pos_action` | Audit aksi user (void, override, dll) |
| `discount` | Template discount reusable |

### Config (4)
| DocType | Purpose |
|---|---|
| `printer_settings` | Per-outlet printer config (paper width, dpi) |
| `printer` | Individual printer entity (USB/LAN address) |
| `resto_settings` | Single doctype, global config (tax mode, queue counter, dll) |
| `user_pos_permission` | Per-user POS Profile assignment + role |

### Plus ~18 child tables (POS Invoice Item extensions, dll).

---

## 7. API Endpoint Catalog (49 total)

Semua di `resto/api.py` dengan decorator `@frappe.whitelist()`. Grup:

| Grup | Endpoints |
|---|---|
| **Auth** | `login_with_pin`, `generate_keys` |
| **Branch/Menu** | `get_branch_list`, `get_all_branch_menu_with_children`, `get_branch_menu_by_resto_menu`, `get_branch_menu_for_kitchen_printing` |
| **Customer** | `create_customer` |
| **Tables** | `get_all_tables_with_details`, `update_table_status`, `add_table_order`, `remove_table_order`, `update_table_meta` |
| **Invoice** | `create_pos_invoice`, `void_pos_invoice`, `list_paid_invoices`, `list_paid_invoices_for_table` |
| **Payment** | `pay_invoice` |
| **Kitchen** | `send_to_kitchen`, `process_kitchen_printing`, `print_to_ks_now`, `reprint_kitchen_tickets`, `enqueue_checker_after_kitchen` |
| **Printing** | `print_bill_now`, `print_check_now`, `print_receipt_now`, `list_printers_with_status`, `test_print` |
| **Discount** | `apply_discount` |
| **Reporting** | `get_end_day_report`, `get_end_day_report_v2`, `end_shift` |
| **Realtime** | `print_now`, `get_realtime_namespace` |

Detail mobile consumer per endpoint → `docs/context/cross-repo.md`.

---

## 8. Service Layer (8 services)

Lokasi: `resto/services/`. Pattern: 1 file per concern, business logic terpisah dari controller (api.py = thin wrapper, services = business logic, repositories = data access).

| Service | Size | Tanggung jawab |
|---|---|---|
| `PaymentService` | 4.3K | `pay_invoice` atomic full-pay (lihat 5.4) |
| `KitchenService` | 12.2K | Send to kitchen, station routing, ticket queue |
| `PrintingService` | 14.2K | ESC/POS print orchestration (bill, receipt, kitchen, reports) |
| `InvoiceService` | 22.1K | Invoice CRUD, item merge, cart-to-invoice translation |
| `ReportingService` | 19.8K | `get_end_day_report_v2`, shift report |
| `TableService` | 27.9K | Table state machine, merge/split, atomic order lock |
| `POSService` | 1.3K | POS opening/closing wrapper |
| `DiscountService` | 0.5K | Apply discount + distribution logic |

Detail per service → `docs/context/architecture.md`.

---

## 9. Repository Layer (9 repositories)

Lokasi: `resto/repositories/`. Data access layer — semua SQL/`frappe.get_all`/`frappe.db.sql` di sini. Service layer **wajib** lewat repository, jangan akses DB langsung.

| Repository | Size | Purpose |
|---|---|---|
| `invoice_repository` | 3.8K | Query POS Invoice + items |
| `kitchen_repository` | 4.2K | Kitchen station + KS Printing |
| `reporting_repository` | 14.7K | Complex SQL untuk end-day report (paling besar) |
| `table_repository` | 2.8K | Table + Table Order CRUD |
| `printing_repository` | 2.3K | Printer lookup per branch |
| `pos_repository` | 1.6K | POS Profile + POS Opening |
| `discount_repository` | 1.0K | Discount template lookup |
| `customer_repository` | 0.4K | Customer create/lookup |
| `menu_repository` | 0.3K | Menu lookup by branch |

---

## 10. Event Hooks & Schedulers (`hooks.py`)

### `doc_events`
| Event | Handler | Purpose |
|---|---|---|
| POS Invoice `before_save` | `exclude_void_items_from_total` | Recalc total tanpa void items |
| POS Invoice `before_save` | `handle_kitchen_stock` | Decrement stock saat draft |
| POS Invoice `before_submit` | `block_partial_payment` | Reject submit kalau outstanding > 0 |
| POS Invoice `on_submit` | `lock_void_value_after_submit` | Freeze void_amount setelah Paid |
| POS Invoice `on_cancel` | `rollback_kitchen_stock_on_cancel` | Restore stock |

### `scheduler_events`
| Cron | Job | Purpose |
|---|---|---|
| `daily` | `resto_menu.reset_daily_resto_stock` | Reset daily stock counter per menu |

---

## 11. Integration Architecture

```
                    ┌─────────────────────┐
                    │  Mobile RN POS      │ ← konsumen utama saat ini
                    │  (sopwer-resto-pos) │
                    └─────────┬───────────┘
                              │ REST + socket.io
                              ↓
┌──────────────────────────────────────────────────┐
│  ERPNext Frappe site (maystar.dev)               │
│  ┌────────────────────────────────────────────┐  │
│  │  resto custom app                          │  │
│  │  ├─ api.py (49 endpoints, thin wrapper)    │  │
│  │  ├─ services/ (business logic)             │  │
│  │  ├─ repositories/ (SQL + frappe.get_all)   │  │
│  │  ├─ events/ (DocType hooks)                │  │
│  │  └─ printing.py (ESC/POS)                  │  │
│  └────────────────────────────────────────────┘  │
│  + base ERPNext (Sales Invoice, Customer, MOP)   │
└────────────────┬─────────────────────────────────┘
                 │ ESC/POS over LAN/USB
                 ↓
        ┌─────────────────┐
        │ Thermal printers│ (kitchen + cashier + checker)
        └─────────────────┘
```

Future consumer (web POS, REST client) **harus** consume endpoint yang sama dengan kontrak yang sama. Tidak ada side-channel.

---

## 12. Business Rules (Invariants)

Aturan yang **tidak boleh dilanggar** oleh consumer manapun:

1. **NO PARTIAL PAYMENT** — `pay_invoice` reject jika total_paid < grand_total. Enforced di `block_partial_payment` event hook.
2. **NO CARD CHANGE** — kembalian wajib cash mode (`type=="Cash"` di MOP). Card-only payment kalau `total_paid > grand_total` → reject.
3. **ATOMIC TABLE ORDER** — `add_table_order` pakai lock + dedupe (race condition fix v1.2.x). Jangan bypass dengan `updateTableStatus` snapshot REPLACE.
4. **DRAFT INVOICE PERSISTS** — kalau user logout sebelum payment, invoice tetap docstatus=0. Akan muncul di Sales Report `draft` section. Bukan "lost order" — admin bisa lanjutkan atau void.
5. **PARENT/CHILD BANK** — `payments[].mode_of_payment` = nama child (e.g. "Debit Mandiri"). UI di-aggregate untuk display by parent.
6. **DISCOUNT DISTRIBUTION** — split bill bagi discount proportional by subtotal share. Kedua invoice harus total discount sama.
7. **PRINT CUT CONVENTION** — bill/receipt/report pakai `_esc_feed(8) + _esc_cut_full()`. Kitchen ticket boleh `_esc_feed(3)` (output lebih pendek).
8. **STATUS STRING IS API CONTRACT** — `order_type` strings (`"Dine In"`, `"Take Away"`), POS Invoice `status` (`"Draft"`, `"Paid"`, `"Consolidated"`), `table.status` (`"Kosong"`, `"Terisi"`) **TIDAK BOLEH** dirubah/diterjemahkan tanpa update semua consumer.

---

## 13. Non-Functional Requirements

| Aspek | Target / Strategi |
|---|---|
| **Performance** | `get_end_day_report_v2` ≤ 2 detik untuk 200 invoice/hari/outlet |
| **Reliability** | Idempotent endpoints (`add_table_order`, `send_to_kitchen`) — retry safe |
| **Concurrency** | Lock + dedupe untuk table order (mencegah race 2 waiter bersamaan) |
| **Offline tolerance** | Mobile cache via WatermelonDB (master data); backend stateless per request |
| **Localization** | Indonesian-first: Rupiah, dd/mm/yyyy, label UI bahasa Indonesia |
| **Auditability** | KS Printing log, User POS Action log, POS Consumption per outlet |
| **Print latency** | Kitchen ticket ≤ 3 detik dari send_to_kitchen |

---

## 14. Glossary

Backend-specific terms (mobile user-facing terms → `mobile-apps/sopwer-resto-pos/docs/context/terminology.md`):

- **docstatus**: 0=Draft, 1=Submitted, 2=Cancelled (Frappe convention)
- **DocType**: Frappe entity definition (= tabel + schema + controller class)
- **fixtures**: data seed di `resto/fixtures/`, auto-load saat install
- **hooks (Frappe)**: callback config di `hooks.py` — beda dari React hooks
- **realtime namespace**: socket.io channel per-event
- **ESC/POS**: thermal printer command standard (GS V untuk cut)
- **POS Closing Entry**: Frappe doctype yang consolidate POS Invoice jadi Sales Invoice

---

## 15. References

- `docs/STATE.md` — current sprint progress (baca dulu sebelum kerja)
- `docs/context/architecture.md` — deep services + repositories + events
- `docs/context/payment-flow.md` — pay_invoice deep dive
- `docs/context/kitchen-flow.md` — send_to_kitchen + status_kitchen lifecycle
- `docs/context/printing.md` — ESC/POS convention + cut feed history
- `docs/context/reporting.md` — get_end_day_report_v2 shape + filter logic
- `docs/context/integration-tests.md` — site `resto.integration_test` setup
- `docs/context/cross-repo.md` — kontrak silang dengan mobile RN POS
- `CLAUDE.md` — instruksi singkat untuk Claude (token-efficient)
- Mobile consumer: `github.com/xhijack/sopwer-resto-pos` (branch `version-1`)
