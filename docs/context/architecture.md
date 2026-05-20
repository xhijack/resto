# Backend Architecture — Services, Repositories, Events

> Deep view backend internals. PRD (`../PRD.md`) berisi high-level overview;
> file ini drill down ke implementasi.

## Layered Architecture

```
┌─────────────────────────────────────────────────┐
│  api.py — thin controllers (49 @frappe.whitelist)│
│  Validate input, call service, return JSON      │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  services/ — business logic                     │
│  Orchestration, validation, transaction         │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│  repositories/ — data access                    │
│  SQL, frappe.get_all, frappe.get_doc            │
└─────────────────────────────────────────────────┘
```

**Aturan**: api.py jangan sentuh DB langsung. Service jangan call frappe.db.sql langsung — lewat repository.

## Services Detail

### `PaymentService` (`services/payment_service.py`, 4.3K)
**Public**: `pay_invoice(pos_invoice, payments)`, `_is_cash_mode(mode_of_payment)`
**Behavior**: Atomic full-pay. Validate change tertutup cash. Submit invoice. Cleanup table_merged. → `payment-flow.md`

### `KitchenService` (`services/kitchen_service.py`, 12.2K)
**Public**: `send_to_kitchen`, `process_kitchen_printing`, `reprint_kitchen_tickets`, `enqueue_checker_after_kitchen`
**Behavior**: Route item ke kitchen station. Queue async print job. Track status_kitchen lifecycle. → `kitchen-flow.md`

### `PrintingService` (`services/printing_service.py`, 14.2K)
**Public**: `print_bill_now`, `print_check_now`, `print_receipt_now`, `print_to_ks_now`, `test_print`
**Behavior**: ESC/POS payload generation, kirim ke printer via socket/USB. → `printing.md`

### `InvoiceService` (`services/invoice_service.py`, 22.1K) — paling besar
**Public**: `create_pos_invoice`, `void_pos_invoice`, item merge, cart-to-invoice translation
**Behavior**: Convert mobile cart payload → POS Invoice DocType. Handle add-item flow untuk existing invoice (extract existing items, merge dengan cart baru). Void item dengan audit fields.

### `ReportingService` (`services/reporting_service.py`, 19.8K)
**Public**: `get_end_day_report_v2(posting_date, outlet, do_print)`, `end_shift`, `get_daily_sales_summary`
**Behavior**: Aggregate paid invoices, draft, void, session time bucketing. → `reporting.md`

### `TableService` (`services/table_service.py`, 27.9K) — paling besar
**Public**: `add_table_order`, `remove_table_order`, `update_table_meta`, `update_table_status`, merge/split table
**Behavior**: Table state machine. Atomic order lock (mencegah race condition 2 waiter bersamaan add ke meja yang sama).

### `POSService` (`services/pos_service.py`, 1.3K)
**Public**: POS opening/closing wrapper
**Behavior**: Wrapper around ERPNext POS Opening Entry & POS Closing Entry.

### `DiscountService` (`services/discount_service.py`, 0.5K)
**Public**: `apply_discount(invoice_name, discount_data)`
**Behavior**: Set discount via taxes child table (Discount row). Distribusi proporsional saat split bill.

## Repositories Detail

### `reporting_repository` (14.7K) — paling kompleks
Method utama:
- `get_paid_invoices(posting_date, outlet_filter)` — filter `docstatus=1, status IN ['Paid','Consolidated']`
- `get_draft_invoices(posting_date, outlet_filter)` — filter `docstatus=0, status='Draft'`
- `get_void_invoices_with_items`, `get_void_bills`, `get_void_items`
- `get_payments_summary_v2`, `get_taxes_summary_v2`, `get_discount_by_order_type_v2`, `get_discount_by_bank`
- `get_session_time_data` — bucketing per jam untuk session report

### Lainnya
- `invoice_repository` (3.8K), `kitchen_repository` (4.2K), `table_repository` (2.8K), `printing_repository` (2.3K), `pos_repository` (1.6K), `discount_repository` (1.0K), `customer_repository` (0.4K), `menu_repository` (0.3K)

## Events (`events/pos_invoice.py`, 6.2K)

| Event | Handler | Purpose |
|---|---|---|
| `before_save` | `exclude_void_items_from_total` | Recalc total tanpa void items |
| `before_save` | `handle_kitchen_stock` | Decrement stock saat draft |
| `before_submit` | `block_partial_payment` | Reject submit kalau outstanding > 0 |
| `on_submit` | `lock_void_value_after_submit` | Freeze void_amount setelah Paid |
| `on_cancel` | `rollback_kitchen_stock_on_cancel` | Restore stock |

Registered di `hooks.py:143-153`.

## Schedulers (`hooks.py:158-174`)

- `daily`: `resto.resto_sopwer.doctype.resto_menu.resto_menu.reset_daily_resto_stock` — reset stock counter harian per menu

## File Layout

```
resto/
├── resto_sopwer/
│   ├── doctype/          # 34 DocTypes
│   ├── api.py            # 49 endpoints
│   ├── printing.py       # 2418 baris ESC/POS
│   ├── install.py        # 457 baris setup
│   └── hooks.py          # 252 baris
├── services/             # 8 files
├── repositories/         # 9 files
├── events/               # pos_invoice.py
├── fixtures/             # data seed (load saat install)
├── tests/                # 18 files + resto_pos_test_base.py
└── config/
```

## Pattern Notes

1. **Service WAJIB lewat repository** untuk DB access. Pelanggaran muncul sebagai 22.1K InvoiceService — kalau bersih, harusnya ~10K.
2. **api.py = thin wrapper** — kalau ada > 20 baris di endpoint, refactor ke service.
3. **Idempotency** — `add_table_order` & `send_to_kitchen` retry-safe. Kalau buat endpoint baru yang mutasi state, design idempotent (atau document explicitly kalau tidak).
4. **DocType naming** — snake_case untuk module/folder, Title Case untuk DocType nama (`POS Invoice` bukan `pos_invoice` saat akses via `frappe.get_doc`).
