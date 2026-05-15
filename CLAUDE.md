# ERPNext Resto Module — Architecture Reference

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

## Dynamic Print Format Migration (Phase 1)

Migrasi `printing.py` hardcoded ESC/POS → Frappe Print Format yang admin bisa edit di UI tanpa deploy. Phase 1 = **kitchen receipt only**. Builder lain (bill, receipt, checker, void) masih legacy.

**Komponen:**
- `print_helpers.py` — Jinja helpers (`esc_init`, `esc_align_center`, `esc_char_size`, `fmt_idr`, `two_col`, dll). Returns Latin-1 string; dispatcher `.encode("latin-1")` ke bytes.
- `print_engine/` package: `resolver.py` (pick rule), `renderer.py` (PF → bytes), `dispatcher.py` (orchestrator + `test_print_rule` whitelist).
- DocType `Resto Print Rule` — mapping `action_key` → Print Format + printer resolver.
- Pilot PF `Kitchen Receipt (Default)` + Rule `Kitchen Receipt - Default` (created by `install.after_migrate`, default `enabled=0`).

**Default behavior = legacy.** Dynamic path aktif hanya jika ada `Resto Print Rule` enabled untuk `action_key=kitchen_receipt`. Dispatcher return None pada miss/error → fallback ke `build_kitchen_receipt_from_payload`.

**Cara enable dinamis:**
1. Buka **Resto Print Rule** → `Kitchen Receipt - Default`
2. Set `printer_resolver=Static` + `printer_name=<CUPS printer>` (atau pakai Kitchen Station resolver)
3. Klik **Test Print** untuk verifikasi template render OK
4. Centang `enabled` → save → semua send-to-kitchen pakai PF ini

**Authoring template baru:**
- Print Format harus `print_format_type=Jinja` + `raw_printing=1`
- Context tersedia: `payload` (entry dict), `unprinted_items` (pre-filtered), `invoice` (POS Invoice meta), `header` ({date, station_name, table_name, operator_name, pax}), `title_prefix`
- Helper list: lihat `resto/hooks.py` field `jinja.methods`

**Phase 2 (belum):** bill, receipt, checker, void_item Print Format + ASCII preview admin panel.
**Phase 3 (belum):** `Printer Endpoint` DocType buat DB-driven host/port (saat ini host CUPS dari sistem).

## Token-Saving Rules
- Baca file besar (printing.py 2418 baris) hanya dengan `offset+limit` sesuai fungsi target
- Gunakan `Grep` untuk cari method/class sebelum baca file
- Untuk gap analysis: `Grep "@frappe.whitelist"` di api.py, lalu bandingkan dengan existing tests
