# Onboarding — Resto Backend

> Selamat datang. Ikuti urutan ini supaya dapat konteks penuh tanpa bikin
> kesalahan umum. Total estimasi: 2-3 hari kerja sampai produktif.

## Day 1 — Sistem & Konteks (~3 jam)

**WAJIB baca berurutan**:
1. [`README.md`](../README.md) — pointer + Contributing workflow
2. [`CLAUDE.md`](../CLAUDE.md) — short repo guide (struktur, services, test)
3. [`docs/PRD.md`](PRD.md) — **paling penting**, ~600 baris, 15 section:
   - Section 5 (Workflows) — semua flow dine-in, take-away, payment, kitchen
   - Section 12 (Business Rules Invariants) — aturan yang TIDAK BOLEH dilanggar
4. [`docs/STATE.md`](STATE.md) — apa sedang dikerjain SEKARANG, blockers, next up

**Optional (kalau ada waktu)**:
- [`docs/context/architecture.md`](context/architecture.md) — services + repositories detail

## Day 2 — Setup Local Environment (~3 jam)

1. Clone bench: `/Users/ramdani/Documents/development/erpnext` (atau setup baru bench Frappe)
2. Install app: `bench --site <dev-site> install-app resto` (lihat CLAUDE.md untuk detail)
3. Run unit test sekali untuk verify setup: `bench run-tests --app resto`
4. Setup integration test (optional, lihat [`docs/context/integration-tests.md`](context/integration-tests.md)):
   - `bench new-site resto.integration_test`
   - `bench --site resto.integration_test execute resto.tests.seed.run`
   - `npm run test:integration` di mobile repo

## Day 3 — First Task Workflow (~real work)

**Convention pull-before / update-after**:
```bash
git pull
cat docs/STATE.md      # baca dulu — apa pending, apa next
cat CLAUDE.md          # repo conventions
# ... kerja ...
# selesai? update STATE.md dengan progress baru
git add docs/STATE.md
git commit -m "docs(state): update progress"
git push
```

**Branch**: `version-2` (active dev branch). Jangan langsung commit ke `main`.

## Top 5 Common Pitfalls — JANGAN dilakukan

1. **Partial payment** — `pay_invoice` reject kalau `total_paid < grand_total`. Atomic full-pay only. Detail: [`docs/context/payment-flow.md`](context/payment-flow.md).
2. **Bypass `add_table_order`** — jangan langsung `frappe.db.set_value` untuk update table order. Pakai service method (atomic lock). Race condition tidak akan terdeteksi sampai 2 waiter bersamaan crash 1 invoice.
3. **Ubah string `order_type` / `status` / `table.status`** — itu API contract dengan mobile. Cek `docs/context/cross-repo.md` dulu.
4. **Parent vs child bank** — `payments[].mode_of_payment` pakai nama child (e.g. `"Debit Mandiri"`), bukan parent (`"Debit"`). Struk receipt akan cetak nama yang user simpan.
5. **Print cut feed** — bill/receipt/report pakai `_esc_feed(8)` sebelum `_esc_cut_full()`. Kitchen ticket boleh `_esc_feed(3)`. Kalau ada laporan "ujung struk kelewat", default escalate ke 8 — tapi jangan opportunistic di tempat user tidak lapor.

## Cross-Repo Discipline

Saat menyentuh endpoint, DocType field, atau status string yang dibaca mobile:
1. Update [`docs/context/cross-repo.md`](context/cross-repo.md) di repo ini
2. Buka PR di mobile repo (`github.com/xhijack/sopwer-resto-pos`) yang update mirror `docs/context/cross-repo.md` sisi mobile
3. Merge dua-duanya bareng (ideal: sama hari)

Mismatch = invoice rusak / order hilang / report salah. Sudah pernah kejadian — lihat audit trail di cross-repo.md.

## Where to Ask

- Github Issues di repo ini untuk bug + diskusi public
- Tag `@ramdani` di issue/PR untuk eskalasi
- Context tambahan: claude-mem memory pribadi (per-dev, tidak shared)

Welcome aboard. Baca STATE.md sekarang untuk tau apa yang relevan minggu ini.
