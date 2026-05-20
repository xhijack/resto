# Kitchen Flow

> Detail flow dapur (send → process → status → void). Overview di PRD §5.5.

## End-to-End Chain

```
Mobile useSaveInvoice.js:206 (saat user tap "Kirim ke Dapur" atau "Proses Order")
  → send_to_kitchen() in src/api/transaction.js
    → POST /api/method/resto.api.send_to_kitchen
      → api.py: send_to_kitchen(payload, table_name, status, taken_by, pax, ...)
        → services/kitchen_service.py: KitchenService — create/update POS Invoice + queue print
          → enqueue _process_kitchen_printing_worker (async)
            → repositories/kitchen_repository — route per station
              → services/printing_service.py — ESC/POS print payload
                → printer
```

## status_kitchen Lifecycle (per item row di POS Invoice Item)

```
"Not Send"  (default saat item ditambah ke cart)
    ↓ send_to_kitchen
"Already Send"  (sudah print di kitchen)
    ↓ void_pos_invoice (optional)
"Void Menu"  (di-void, tetap muncul di end-day untuk audit)
```

Field di POS Invoice Item:
- `status_kitchen` — string lifecycle di atas
- `void_qty` — qty yang di-void (≤ qty original)
- `void_rate` — rate saat void (snapshot, immutable post-Paid)
- `void_amount` — alternative explicit amount (kalau di-set, override calculation)

## Endpoints

### `send_to_kitchen(payload, table_name=None, status=None, taken_by=None, pax=0, ...)`
- Convert mobile cart payload → POS Invoice
- Jika `currentOrderName` null → create new invoice (status_kitchen all items = "Not Send" → "Already Send" after print)
- Jika existing → merge cart items dengan existing (extract existing, identify new, update status_kitchen)
- Call `process_kitchen_printing` async
- Untuk dine-in: juga `add_table_order(table_name, invoice_name)` (atomic lock)
- Untuk takeaway: generate `queue_number` (sequential per outlet per day)

### `process_kitchen_printing(pos_invoice)`
- Async worker
- Group items by kitchen_station (via menu's KS Printing mapping)
- Print 1 ticket per station

### `reprint_kitchen_tickets(pos_invoice, item_row_names=None)`
- Reprint partial (specify item row names) atau full
- Use case: kitchen ganti shift, ticket sebelumnya hilang

### `enqueue_checker_after_kitchen(pos_name, branch)`
- Setelah kitchen ticket print, print 1 "checker" untuk waiter
- Berisi rangkuman order untuk verifikasi sebelum serve

### `print_to_ks_now(pos_invoice)`
- Manual trigger print kitchen ticket (kalau auto fail)

### `void_pos_invoice(invoice_name)`
- Cancel invoice (docstatus 1 → 2)
- Set `status_kitchen = "Void Menu"` per item
- Trigger event `rollback_kitchen_stock_on_cancel` (restore stock)

## Kitchen Station Routing

DocType `Kitchen Station`:
- Field: `station_name`, `branch`, `printer`
- Linked dari `KS Printing` (per resto_menu item → 1+ station)

Flow:
1. Saat item ditambah ke invoice, lookup `branch_menu.resto_menu → resto_menu.ks_printing[]` → daftar station
2. Group items by station
3. Per station, print kitchen ticket dengan items grup itu saja

## Stock Handling (Events)

Hook `before_save: handle_kitchen_stock`:
- Decrement `pos_consumption` per resto_menu (qty terpakai hari ini)
- Idempotent: pakai field tracking (`stock_kitchen_handled`) supaya save kedua tidak double-decrement

Hook `on_cancel: rollback_kitchen_stock_on_cancel`:
- Increment kembali stock saat invoice di-cancel
- Reset tracking field

Scheduler `daily: reset_daily_resto_stock`:
- Setiap awal hari (cron), reset `pos_consumption` counter ke 0

## Idempotency

`send_to_kitchen` retry-safe:
- Kalau payload sama dipanggil 2x (mis. network glitch retry), tidak dobel-print
- Implementasi: cek `status_kitchen` per item — kalau sudah "Already Send", skip
- Untuk add_table_order yang ikutan: pakai lock + dedupe di TableService

## Failure Modes

| Skenario | Behavior |
|---|---|
| Printer offline | Print job fail, log via `frappe.log_error`. User dapat retry via `reprint_kitchen_tickets`. |
| Network timeout mobile → backend | Mobile retry. Backend idempotent — invoice tidak dobel, ticket tidak dobel. |
| 2 waiter bersamaan add ke meja sama | Atomic lock di TableService — 1 invoice merge ke existing, tidak orphan. |
| Item di-void setelah Paid | Disallow via `lock_void_value_after_submit` hook. Manager harus cancel invoice dulu. |

## Notes

- Kitchen ticket format: nama menu (bold), qty, addOns, notes. Tanpa harga (kitchen tidak perlu).
- Cut convention: kitchen ticket pakai `_esc_feed(3)` (lebih kecil dari bill/receipt yang `feed(8)`). Sengaja — kitchen ticket pendek, gak perlu boros kertas.
- Mobile button label berbeda per order_type:
  - Dine In: `"Kirim ke Dapur"`
  - Take Away: `"Proses Order"`
  - Implementasi mobile di `src/components/OrderActions.js:56-71`
