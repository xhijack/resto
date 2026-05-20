# Integration Tests — Site `resto.integration_test`

> Setup integration test cross-stack (backend + mobile). Status: Phase 1-3 done, Phase 4 pending.

## Konsep

Berbeda dari unit test (Jest di mobile, bench run-tests di backend), integration test menjalankan flow end-to-end via HTTP API:
- Dedicated bench site (`resto.integration_test`), tidak shared dengan dev site
- Seed data idempotent (Customer, Brand, Floor, Table Type, POS Profile, dll)
- Test runner di mobile (Jest) call backend via REST, verify response

## Status (snapshot 2026-05-07)

### Selesai
- ✅ Site `resto.integration_test` di-create via `bench new-site` (install erpnext + resto)
- ✅ Seed jalan tanpa error: `bench --site resto.integration_test execute resto.tests.seed.run`
- ✅ Test runner Jest config + helpers
- ✅ Smoke test code (3 test ping/cleanup/create POS Invoice)

### Pending
- ⏳ Phase 4: Regression coverage 6 file: move-item, merge-table, void, payment, update-table-status, kitchen-printing
- ⏳ Phase 5: README + dokumentasi integration-tests/
- ⏳ Phase 6 (defer): CI integration

## Setup Quick Start

```bash
# Sekali, di awal
cd /Users/ramdani/Documents/development/erpnext
bench new-site resto.integration_test
bench --site resto.integration_test install-app erpnext
bench --site resto.integration_test install-app resto

# Seed (idempotent — aman dijalankan ulang)
bench --site resto.integration_test execute resto.tests.seed.run

# Output seed terakhir = API_KEY + API_SECRET — catat
```

Setup mobile:
```bash
cd /Users/ramdani/Documents/development/mobile-apps/sopwer-resto-pos
cp integration-tests/.env.example integration-tests/.env
# Edit .env, paste API_KEY & API_SECRET dari seed
```

Run:
```bash
cd /Users/ramdani/Documents/development/erpnext
bench start  # terminal lain

# Smoke verify
curl http://resto.integration_test:8000/api/method/frappe.ping

# Run integration tests
cd /Users/ramdani/Documents/development/mobile-apps/sopwer-resto-pos
npm run test:integration
```

Reset state (kalau perlu re-run dari clean):
```bash
npm run test:integration:reset
```

## Files

### Backend (`resto/tests/`)
- `seed.py` — Idempotent fixture seeder. Whitelist `run_via_http` (untuk Jest global setup) + plain `run` (untuk bench execute). Site allow-list guard: `SAFE_SITES = {"resto.integration_test"}`.
- `cleanup.py` — Layer 1 reset endpoint `cleanup_test_data`. Cancel + delete POS Invoice, Table Order. Reset Tables ke status="Kosong".

### Mobile (`integration-tests/`)
- `helpers/api-client.js` — axios factory, auth `token <key>:<secret>`
- `helpers/reset-state.js` — wrapper call cleanup endpoint
- `helpers/wait-for-server.js` — polling ping
- `jest.config.integration.js` — testEnvironment node, maxWorkers 1, timeout 30s
- `globalSetup.js` — load .env, ping server, call seed.run_via_http
- `tests/pos-invoice.test.js` — 3 smoke tests

### package.json scripts
- `test:integration` — run integration suite
- `test:integration:watch` — watch mode
- `test:integration:reset` — call cleanup endpoint

## Konstanta Seed (referensi untuk test selanjutnya)

```
COMPANY_NAME = "Sopwer Integration Test"
COMPANY_ABBR = "SIT"
BRANCH_NAME = "BR-INT"
POS_PROFILE_NAME = "PP-INT"
CUSTOMER_NAME = "INT-CUST"
BRAND_NAME = "Sopwer"
ZONE_NAME = "Main"
TEST_USER = "integration@test.local"
ITEMS = ITEM-A..E (Nasi/Mie Goreng, Es Teh/Jeruk, Ayam Bakar)
TABLES = TBL-A1..A5
MOPS = "Cash INT" (Cash), "EDC INT" (Bank)
TAX_TEMPLATES = "Dengan Service" 10%, "Tanpa Service" 0%
```

## 6 Bug Seed yang Sudah Di-Fix (jangan kena lagi)

1. **Warehouse Type "Transit" missing** → solusi: panggil `erpnext.setup.setup_wizard.operations.install_fixtures.install(country="Indonesia")` di `_ensure_erpnext_baseline()`. Idempotent via guard `if frappe.db.exists("Customer Group", "All Customer Groups"): return`.
2. **Customer Group / Territory missing** → sama dengan #1.
3. **Resto Menu mandatory `brand`** → tambah `_ensure_brand()` create Brand "Sopwer", set `brand="Sopwer"` di Resto Menu.
4. **Floor "1" missing** → tambah `_ensure_table_floor()` create Table Floor `name_floor: "1"`.
5. **Table Type "Reguler" invalid** → harus `"2" | "4" | "6"`. Set `table_type: "4"`.
6. **POS Profile.applicable_for_users link error** → User harus dibuat SEBELUM POS Profile. Reorder di `run()`: `_ensure_test_user_record()` lalu `_ensure_pos_profile()`.

## Phase 4 Plan — Regression Coverage 6 File

| File | Test scenarios |
|---|---|
| `move-item.test.js` | Move item antar invoice di table yang sama; antar table |
| `merge-table.test.js` | Merge 2 table → 1 master invoice; un-merge |
| `void.test.js` | Void item di draft; void item di submitted (harus reject); void full invoice |
| `payment.test.js` | Full pay Cash; split Cash+Bank; over-pay dengan change; under-pay reject |
| `update-table-status.test.js` | Status transition: Kosong → Terisi → Kosong; atomic race condition test |
| `kitchen-printing.test.js` | send_to_kitchen idempotency; status_kitchen transition; void → menu count |

Setelah Phase 4 selesai, target: ≥ 20 integration test pass tanpa flake. Coverage > 60% untuk service layer.

## Tips & Gotchas

- **Jangan re-run seed** kecuali ada perubahan schema/fixture. Site sudah seeded — re-seed = waste 1-2 menit.
- **Reset state antar test** via `beforeEach: await resetState()` — pakai helper, jangan inline.
- **maxWorkers=1** wajib — banyak operations punya side effect global (tables, invoices). Parallel = race.
- **Timeout 30s** — beberapa operations (kitchen print, end-day report) butuh > 10s.
- **Auth tiap test** pakai global instance dari `globalSetup.js`. Jangan recreate per test.

## CI Future (Phase 6, defer)

Plan: GitHub Actions workflow di backend repo:
1. Spin Docker Frappe dev container
2. Install resto app
3. Run `bench --site resto.integration_test execute resto.tests.seed.run`
4. Bench start in background
5. Mobile npm install + npm run test:integration

Tantangan: setup Frappe di CI memakan ~5-10 menit per run. Tidak prioritas sampai PR volume justify.
