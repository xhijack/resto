# Onboarding — Resto Backend

> Selamat datang. Ikuti urutan ini supaya dapat konteks penuh tanpa bikin
> kesalahan umum.

## ⚡ Sudah pernah onboard? Langsung Daily/Hotfix Workflow

Skip ke [section Daily/Hotfix](#daily--hotfix-workflow-token-efficient) di bawah. Untuk use case hotfix + improve existing feature, butuh **~5-8K token per sesi** saja — bukan 28K untuk baca PRD lengkap.

## 📚 Day 1 Onboarding — Sistem & Konteks (one-time, ~28K token, ~3 jam)

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

---

## Daily / Hotfix Workflow (Token-Efficient)

**Dev sudah onboard, mau fix bug atau improve existing feature. Use case dominan.**

### Per-sesi (~5-8K token, vs 28K full)

```bash
git pull
cat docs/STATE.md       # ~0.7K — apa pending, blockers
# CLAUDE.md auto-load oleh Claude Code (~2.5K)
```

Lalu identifikasi area kerja, baca 1 context file relevan saja:

| Area kerja | File | Token |
|---|---|---|
| Payment bug | `docs/context/payment-flow.md` | ~4K |
| Kitchen bug | `docs/context/kitchen-flow.md` | ~4K |
| Print issue | `docs/context/printing.md` | ~3K |
| Sales Report | `docs/context/reporting.md` | ~4K |
| Table lock / race | `docs/context/architecture.md` (TableService) | ~5K |
| Endpoint touch mobile | `docs/context/cross-repo.md` | ~3K |
| Integration test | `docs/context/integration-tests.md` | ~4K |

### Recommended starter prompt (Claude Code)

```
Saya fix bug [area] di [file:line atau description].
Baca docs/STATE.md dan docs/context/[topic].md saja.
Jangan baca PRD kecuali saya minta.
```

### When to escalate ke full PRD reload

- Breaking change yang affect semua flow (rare)
- Refactor besar lintas service
- Diminta klien stakeholder explicit untuk audit sistem

Selain itu, **STATE.md + 1 context file sudah cukup**.

---

## Recommended Claude Code Prompts (Copy-Paste Ready)

Setelah `git pull`, buka Claude Code di folder repo ini. CLAUDE.md auto-load. Pilih template prompt sesuai use case:

### A. Dev baru pertama kali — onboarding (one-time ~28K token)
```
Saya dev baru di project Sopwer Resto backend. Tolong onboard saya:
baca docs/ONBOARDING.md dan ikuti Day 1 reading list.
Setelah baca, summarize highlight yang paling penting untuk
saya tahu sebelum mulai kerja.
```

### B. Resume kerja kemarin (~3K token, paling sering dipakai)
```
Saya lanjut kerja kemarin. Baca docs/STATE.md, lihat current
focus dan in-progress. Apa yang harus saya kerjakan?
```

### C. Hotfix bug spesifik (~5-8K token)
```
Saya fix bug di [AREA]. User lapor: [GEJALA].
Baca docs/STATE.md dan docs/context/[TOPIC].md saja.
Jangan baca PRD kecuali saya minta.
```

Contoh nyata:
```
Saya fix bug di payment flow. User lapor saat split payment Cash+QRIS,
total_paid valid tapi backend reject dengan "Pembayaran Belum Lunas".
Baca docs/STATE.md dan docs/context/payment-flow.md. Jangan baca PRD.
```

```
Saya fix bug di kitchen routing. Tiket dapur tidak nge-print untuk
station "Cold Kitchen". Baca docs/STATE.md dan docs/context/kitchen-flow.md.
Jangan baca PRD.
```

### D. Improve fitur existing (~7-10K token)
```
Saya mau improve fitur [FITUR] di [FILE] — [TUJUAN].
Baca docs/STATE.md, docs/context/[TOPIC].md, dan source file relevan.
Setelah itu propose pendekatan tanpa nulis kode dulu.
```

### E. Ubah endpoint yang dipakai mobile (cross-repo, ~10K token)
```
Saya akan ubah signature endpoint `pay_invoice` (tambah field X).
Baca docs/context/cross-repo.md, beri tau mobile hook/screen mana yang
terdampak, dan checklist apa yang harus update di mobile sebelum deploy.
```

### F. Investigate bug yang belum jelas root cause (~10-15K token)
```
User lapor: [GEJALA]. Belum jelas root cause di service/repo mana.
Baca docs/STATE.md dan docs/context/<topic>.md yang paling mungkin terkait.
Spawn 1 Explore agent untuk trace flow, jangan langsung patch.
```

### G. Investigate cross-repo (mobile lapor backend salah, atau sebaliknya)
```
User lapor di mobile: [GEJALA]. Mungkin backend bug atau mobile bug.
Baca docs/STATE.md, docs/context/cross-repo.md, dan area paling mungkin
terkait. Saya butuh verdict: mobile-side, backend-side, atau keduanya.
```

## Anti-Pattern Prompts (boros token, HINDARI)

- ❌ `"Kenalin saya project ini"` — Claude akan baca semua = 50K+ token
- ❌ `"Apa yang ada di repo ini?"` — terlalu generic
- ❌ `"Tolong baca semua dokumentasi"` — eksplisit minta over-read
- ❌ `"Saya mau audit kode"` tanpa scope — bisa baca seluruh repo

✅ **Selalu spesifik**: area kerja, file/folder yang dimaksud, dan "jangan baca X" kalau perlu.

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
