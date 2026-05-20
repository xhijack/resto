# ERPNext Resto Module — Architecture Reference

## Token-Efficient Workflow (BACA DULU)

**Untuk hotfix / improve existing feature (use case dominan)**:
1. `cat docs/STATE.md` (~0.7K token) — current focus, blockers, recent changes
2. Identifikasi area kerja dari tabel di bawah, baca 1 context file (~3-5K token)
3. Total per sesi: **~5-8K token** (vs ~28K kalau baca PRD full)

**Area kerja → file yang cukup dibaca**:
| Area | File | Token |
|---|---|---|
| Payment bug / `pay_invoice` | `docs/context/payment-flow.md` | ~4K |
| Kitchen routing / `send_to_kitchen` / status_kitchen | `docs/context/kitchen-flow.md` | ~4K |
| Print issue (bill/receipt/kitchen/report) | `docs/context/printing.md` | ~3K |
| Sales Report / `get_end_day_report_v2` | `docs/context/reporting.md` | ~4K |
| Table lock / race condition | `docs/context/architecture.md` (TableService section) | ~5K |
| Endpoint contract berubah (touches mobile) | `docs/context/cross-repo.md` | ~3K |
| Integration test setup / site issue | `docs/context/integration-tests.md` | ~4K |
| Services overview / new service | `docs/context/architecture.md` | ~5K |

**JANGAN baca PRD lengkap (`docs/PRD.md` ~18K token) kecuali**:
- Onboarding hari pertama (lihat `docs/ONBOARDING.md`)
- Breaking change yang affect semua flow
- Diminta user explicit

**Untuk dev pakai Claude Code — recommended starter prompt**:
> "Saya fix bug di [area]. Baca `docs/STATE.md` dan `docs/context/[topic].md` saja. Jangan baca PRD kecuali saya minta."

## Stack
- Framework: Frappe/ERPNext (Python)
- App name: `resto` | Title: "Resto Sopwer"
- Publisher: PT Sopwer Teknologi Indonesia
- Site: maystar.dev

## Directory Structure
```
resto/
├── resto_sopwer/
│   ├── doctype/          # 34 DocTypes
│   ├── api.py            # 49 @frappe.whitelist() endpoints (387 lines)
│   ├── printing.py       # POS printing logic (2418 lines)
│   ├── install.py        # Setup/install logic (457 lines)
│   └── hooks.py          # App config & integrations (252 lines)
├── services/             # 8 service classes (business logic)
├── repositories/         # 9 repository classes (data layer)
├── tests/                # 18 test files + base class
│   └── resto_pos_test_base.py  # Base test class (426 lines) — ALWAYS extend this
├── events/               # Event handlers
├── fixtures/             # Data fixtures
└── config/               # Configuration
```

## DocTypes (34 total)
| Category | DocTypes |
|---|---|
| Core | `table`, `table_zone`, `table_floor`, `table_order`, `resto_menu`, `branch_menu`, `pos_consumption` |
| Operations | `kitchen_station`, `ks_printing`, `pos_invoice`, `user_pos_action`, `discount` |
| Config | `printer_settings`, `printer`, `resto_settings`, `user_pos_permission` |

## Services (8 classes) — `/resto/services/`
- `POSService` — main POS operations
- `InvoiceService` — invoice creation/management
- `KitchenService` — kitchen order management
- `PrintingService` — printing operations
- `DiscountService` — discount application
- `PaymentService` — payment processing
- `TableService` — table management
- `ReportingService` — sales reports

## Repositories (9 classes) — `/resto/repositories/`
- `invoice`, `kitchen`, `menu`, `discount`, `table`, `pos`, `customer`, `printing`, `reporting`

## API Endpoints (49 total) — `/resto/api.py`
| Category | Key Methods |
|---|---|
| Auth | `login_with_pin()`, `generate_keys()` |
| Orders | `add_table_order()`, `update_table_status()`, `send_to_kitchen()` |
| Invoice | `create_pos_invoice()`, `print_bill_now()`, `print_receipt_now()` |
| Menu | `get_all_branch_menu_with_children()`, `get_branch_menu_by_resto_menu()` |
| Tables | `get_all_tables_with_details()` |
| Discount | `apply_discount()` |
| Config | `get_select_options()` |

## Test Infrastructure
- **Base class**: `resto/tests/resto_pos_test_base.py` — extend for all tests
- **Pattern**: `class TestXxx(ReStoPosTestBase): def test_xxx_happy_path(self): ...`
- **Existing tests**: 31 files (13 DocType tests in `doctype/*/test_*.py`, 18 in `tests/test_*.py`)
- **Run all tests**: `bench run-tests --app resto`
- **Run single**: `bench run-tests --app resto --module resto.tests.test_xxx`

## Token-Saving Rules
- Baca file besar (printing.py 2418 baris) hanya dengan `offset+limit` sesuai fungsi target
- Gunakan `Grep` untuk cari method/class sebelum baca file
- Untuk gap analysis: `Grep "@frappe.whitelist"` di api.py, lalu bandingkan dengan existing tests
- Hotfix workflow: lihat section "Token-Efficient Workflow" di atas — STATE.md + 1 context file biasanya cukup
