# Printing — ESC/POS Convention

> Detail print convention. Overview di PRD §5.6.

## File Utama

`resto/printing.py` — 2418 baris. Berisi semua ESC/POS payload generation untuk:
- Kitchen ticket
- Bill (draft)
- Check (intermediate)
- Receipt (paid)
- Shift report
- End-day consolidated report

## Cut Convention

ESC/POS pakai command `GS V` (group separator + V) untuk cut paper. Variant:
- `_esc_cut_full()` — full cut
- `_esc_cut_partial()` — partial cut (paper masih nempel sedikit, robekan manual)
- ~~`_esc_cut_full_with_feed()`~~ — **BROKEN** (return `GS V 65` tanpa parameter n yang dibutuhkan Function B). Tidak dipakai. Jangan dipakai sampai di-fix signature.

**Feed sebelum cut**:
- Thermal printer punya gap fisik antara print head dan blade cutter (~12-15mm).
- Tanpa feed sebelum cut, baris terakhir yang baru saja di-print akan kepotong di tengah.
- Solusi: `_esc_feed(N)` sebelum `_esc_cut_full()` — feed N baris dulu supaya last line lewat blade.

### Convention per Output Type

| Output | Feed | Lokasi | Rationale |
|---|---|---|---|
| Bill / Receipt | `_esc_feed(8)` | `printing.py:1477,1757,1934,2189,2499` | Total/footer customer-facing, harus utuh |
| Kitchen Ticket | `_esc_feed(3)` | `printing.py:446` | Pendek, hemat kertas, kitchen tidak baca footer |
| Checker | `_esc_feed(3)` | `printing.py:720` | Sama: pendek untuk waiter |
| Shift Report | `_esc_feed(8)` | `printing.py` | Akhir report (VOID MENU summary) harus utuh |
| End-day Consolidated | `_esc_feed(8)` | `printing.py` | "END OF REPORT" harus utuh |

### Sejarah Bug v1.2.18 backend (commit `d215b3c`)

**Before**: shift report & consolidated pakai `_esc_feed(3)` → last lines kepotong / nempel ke job berikutnya.

**Symptoms**:
- "VOID MENU" section di shift report kelewat (nempel ke awal consolidated job)
- "END OF REPORT" di consolidated kelewat (tidak sampai print)

**Fix**: bump `feed(3) → feed(8)` di 5 lokasi dalam `printing.py`. Kitchen ticket & checker **tidak disentuh** (user tidak lapor masalah di sana — jangan opportunistic).

**Pending deploy**: commit `d215b3c` di branch `version-2` sudah pushed tapi belum `bench restart` di prod. Lihat `../STATE.md`.

## Rule untuk Future Print

Saat menambah print output baru atau ada laporan cut issue:

1. **Default feed 8** untuk customer-facing (bill, receipt, report). Hemat kertas tidak worth risiko user complaint.
2. **Feed 3 boleh** untuk internal-only (kitchen, checker). Audit dulu — kalau pernah ada laporan kelewat, escalate ke 8.
3. **Jangan opportunistic** bump feed di tempat user tidak lapor. Risiko regresi format report yang sudah stable.
4. **Validate di printer fisik** sebelum ship. Test di printer thermal Sopwer standard (lihat Sopwer Standard Print Profile di Printer Settings).

## ESC/POS Reference Commands

| Command | Hex | Purpose |
|---|---|---|
| ESC @ | 1B 40 | Initialize printer |
| ESC ! | 1B 21 | Select print mode (bold, double, etc) |
| ESC E | 1B 45 | Bold on/off |
| ESC a | 1B 61 | Justification (0=left, 1=center, 2=right) |
| GS ! | 1D 21 | Character size |
| GS V | 1D 56 | Cut paper (Function A: `GS V m`, Function B: `GS V 65 n`) |
| LF | 0A | Line feed |

Helper functions di `printing.py`:
- `_esc_init()`, `_esc_bold()`, `_esc_align_center()`, `_esc_double()`
- `_esc_feed(n)` — n line feeds
- `_esc_cut_full()`, `_esc_cut_partial()`

## Sopwer Printer Standard

DocType `Printer Settings` per outlet:
- Paper width: 80mm (default)
- DPI: 203 (standard thermal)
- Character per line: ~48 (80mm/203dpi)
- Codepage: 437 (US) — handle Latin chars
- Cut after print: enabled

Printer fisik test sebelum production:
1. `test_print(printer_name)` endpoint — sample print untuk verifikasi width & cut

## Notes

- ESC/POS specific ke printer thermal. Kalau pakai printer regular (inkjet/laser) → bypass, render PDF instead (tidak diimplementasi saat ini).
- Print job execute synchronous untuk receipt (user tunggu). Async untuk kitchen ticket (lewat queue).
- Print failure → log via `frappe.log_error("...", "Kitchen Print Error")`. Bisa di-view via ERPNext Error Log.
