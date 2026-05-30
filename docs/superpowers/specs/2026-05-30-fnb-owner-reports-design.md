# F&B Owner Reports Suite — Design

Source brainstorming session: 2026-05-30.

## Context

Client owner restoran will request laporan; user wants to **prepare ahead** before that request lands. User is uncertain what F&B owners typically need, with the constraint that the resulting reports must be **as general as possible** so they can be reused across other clients — detail/complexity is acceptable.

Phase 1 exploration confirmed:

- The resto app already ships 8 basic Script Reports (Daily Sales, Sales Menu COGS, Sales Menu Recapitulation, Sales Summary × 3, Sales Summary v2) and the Stock Usage Tool. None of them deliver an **opinionated executive summary** — ringkasan visual yang owner bisa scan dalam < 60 detik, suitable for WA forwarding.
- The standard F&B owner cadence is harian (kemarin sore vs hari yang sama minggu lalu), mingguan, bulanan. None of those exist as a polished single-document deliverable today.
- The `candidate` backend (head `fd7f4c1`) just landed Phases 4–6 of the Stock Usage refactor, giving us a clean `RawMaterialCalculatorService` we can call to compute COGS on-the-fly for any date range.

**Outcome**: build a suite of 3 Owner Reports (Daily, Weekly, Monthly) using a hybrid Script Report + Jinja PDF pattern that shares one service layer. Ship Daily first to validate the opinionated format with an owner, then clone the pattern for Weekly + Monthly.

## Locked decisions

| Topic | Decision |
|---|---|
| Audience | Owner / Investor — ringkasan eksekutif, PDF-friendly |
| Cadence | Daily + Weekly + Monthly (design covers all three; implementation stages) |
| Multi-cabang | Per-cabang via filter (1 PDF per cabang). Batch generation = Phase 2 |
| Architecture | **Hybrid**: Script Report (filter UI + tabular preview + Excel/CSV export) plus a Jinja template (PDF opinionated 1–2 halaman) |
| Distribution | Manual download in Phase 1 (owner logs in → klik Print PDF). Auto-send via WA/email = Phase 2 |
| COGS | **On-the-fly via `RawMaterialCalculatorService.compute_breakdown`** (~2s per cabang per hari). Requires Stock Usage Tool setup at the outlet |
| MVP | Daily ships first end-to-end (service + Script Report + Jinja PDF + tests); Weekly + Monthly clone the pattern |

## Content blueprint per cadence

### 📄 Daily Owner Snapshot (1–2 halaman)

1. **Header** — outlet · tanggal · currency
2. **Performa Utama** — Revenue H-1 · DoD% vs H-2 · WoW% vs H-7 · Margin Rp + COGS% · total bill · pax · avg check / cover
3. **Sales Mix per Kategori** — kategori × revenue × % share (donut / tabel) + order type split (Dine-In vs Take-Away)
4. **Top 5 Menu** — qty · revenue · COGS%
5. **Alarm Anomali** ⚠️ — void count + Rp (kalau > threshold), discount Rp (kalau > threshold). Thresholds per outlet via Resto Settings — multi-tenant friendly
6. **Payment Mix** — Cash · Cashless · Voucher (% revenue)

### 📄 Weekly Recap (2–3 halaman)

Senin – Minggu, semua isi Daily diagregat 7 hari, plus:

- Trend revenue 7 hari (bar chart, inline SVG)
- Best / worst day + jamnya
- Top 10 menu (vs Daily Top 5)
- WoW comparison di header

### 📄 Monthly Report (3–4 halaman)

1 – akhir bulan, semua isi Weekly diagregat 30 hari, plus:

- Trend revenue + margin 30 hari (line chart, inline SVG)
- Best / worst day & best / worst week
- Top + bottom menu (slow movers — masuk menu engineering)
- COGS % evolution
- MoM comparison

## Technical architecture

### File layout (Phase 1: Daily only)

```
resto/services/owner_report/
├── __init__.py
├── owner_report_service.py        # shared data computation
└── owner_report_periods.py        # date-range helpers (daily/weekly/monthly bucket)

resto/resto_sopwer/report/owner_daily_snapshot/
├── __init__.py
├── owner_daily_snapshot.json      # Script Report metadata + filter definitions
├── owner_daily_snapshot.py        # execute() — delegates to the service
└── owner_daily_snapshot.js        # client-side filter UI + Print PDF button hook

resto/templates/owner_reports/
└── daily_snapshot.html            # Jinja template for PDF render

resto/api.py
└── print_owner_daily_snapshot_pdf(...)    # whitelist endpoint → Jinja + get_pdf

resto/tests/test_owner_report/
├── __init__.py
├── test_owner_report_service.py   # unit tests for pure service functions
└── test_owner_daily_snapshot.py   # integration tests
```

Phase 2 (Weekly + Monthly) clones the `report/` folder structure and adds a template. **The service is reused.**

### Service responsibility (`OwnerReportService`)

```python
class OwnerReportService:
    def __init__(self):
        self.rm = RawMaterialCalculatorService()  # COGS on-the-fly

    def compute_snapshot(self, branch: str, period_start: date, period_end: date) -> Dict:
        """Return shape:
        {
          "header": {branch, period_start, period_end, currency},
          "performa": {revenue, margin_rp, cogs_pct, bill_count, pax, avg_check,
                       dod_pct, wow_pct, mom_pct},
          "sales_mix": {kategori: [{name, revenue, pct, qty}], order_type: {...}},
          "top_menu": [{item_name, qty, revenue, cogs_pct}],
          "alarm": {void_count, void_rp, discount_rp,
                    void_alert: bool, discount_alert: bool, thresholds: {...}},
          "payment_mix": {cash, cashless, voucher},
        }
        """
```

Daily / Weekly / Monthly reports all call the same method with different `period_start` / `period_end`. Trend numbers (DoD / WoW / MoM) come from extra calls to `compute_snapshot` for the comparison windows.

### Multi-tenant config — Resto Settings

Add 4 new fields to the existing Resto Settings single-doctype:

| Field | Type | Default | Use |
|---|---|---|---|
| `owner_void_threshold_pct` | Percent | 5.0 | Trigger Alarm void when void / revenue > X% |
| `owner_discount_threshold_pct` | Percent | 10.0 | Trigger Alarm discount when discount / revenue > Y% |
| `owner_report_currency_format` | Select | `id-ID Rp` | Currency format in PDF |
| `owner_report_top_menu_count` | Int | 5 | Daily Top N (Weekly = N×2, Monthly = N×3) |

All thresholds are per-site/outlet — no hardcoded numbers. A new client can adjust without a code change.

### Trend computation

DoD (Day-over-Day) compares H-1 vs H-2. WoW (Week-over-Week) compares H-1 vs H-8 (same day last week). MoM (Month-over-Month) lives only on Weekly + Monthly reports. Helper in `owner_report_periods.py`:

```python
def daily_compare_ranges(target: date) -> List[Tuple[str, date, date]]:
    """Return [('current',                target,       target),
                ('prev_day',               target-1d,    target-1d),
                ('same_day_last_week',     target-7d,    target-7d)]"""
```

The service calls `compute_snapshot` three times and returns the diff %.

### PDF rendering

Following the existing pattern at `resto/templates/daily_sales_full_report.html` + `api.py:308-313` (`print_daily_sales_full_pdf`):

```python
@frappe.whitelist()
def print_owner_daily_snapshot_pdf(branch: str, posting_date: str):
    data = OwnerReportService().compute_snapshot(branch, posting_date, posting_date)
    html = frappe.render_template("templates/owner_reports/daily_snapshot.html", {"data": data})
    pdf = frappe.utils.pdf.get_pdf(html)
    frappe.response.filename = f"owner-daily-{branch}-{posting_date}.pdf"
    frappe.response.filecontent = pdf
    frappe.response.type = "download"
```

A JS hook in the Script Report adds a "Print PDF" button that invokes the endpoint via `frappe.call`.

Charts are inline raw SVG — no JS dependency, prints cleanly: donut via `<circle>` `stroke-dasharray`, bar via `<rect>`. Lighter than Chart.js and friendlier to wkhtmltopdf.

## Data dependencies

- `POS Invoice` (revenue, bills, pax, payment mode, discount, taxes)
- `POS Invoice Item` (qty, rate, category, is_voucher_item, status_kitchen, void_*)
- `Branch` (filter scope)
- `Resto Menu` + `Branch Menu` (menu names, recipe BOM)
- `RawMaterialCalculatorService` (COGS via Stock Usage rm_calculator)
- `Resto Settings` (thresholds + format — new fields required)

**Per-client prerequisites** before this report yields good data:

1. `Resto Menu` + `Branch Menu` are set up with BOM (so COGS is accurate)
2. `Resto Settings` → owner threshold fields are tuned per outlet preference
3. `Item.valuation_rate` or `standard_rate` is populated (used by `rm_calculator` as fallback)

## MVP definition (Phase 1 Daily)

Complete when:

1. `OwnerReportService.compute_snapshot()` works → 8+ unit tests (single branch, multi-day, edge cases)
2. The "Owner Daily Snapshot" Script Report shows up in Frappe → branch + date filter → tabular preview
3. "Print Owner PDF" button generates the Jinja PDF → downloads / opens
4. Resto Settings has the 4 new fields migrated with sane defaults
5. Tests pass: service unit tests + 1 integration test (real DB, FrappeTestCase rollback)
6. Manual smoke: owner opens the report on the test site, picks branch + date, clicks Print PDF → PDF renders with the full content blueprint

## Out of scope (Phase 1)

- Weekly & Monthly reports (Phase 2 — clone the pattern)
- Auto-send via email / WhatsApp scheduler (Phase 2)
- Aggregated multi-cabang single report (Phase 2 if a client needs it)
- Interactive Chart.js inside the Script Report UI (we only render SVG inside the PDF)
- Server / waiter performance section (Phase 3 candidate)
- Customer repeat rate (needs extra customer tracking)
- Tax breakdown detail (Phase 3 candidate for compliance teams)

## Verification

1. `bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service` → 8+ tests green
2. `bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_daily_snapshot` → 2+ integration tests green
3. `bench --site resto.test migrate` registers the new Resto Settings fields
4. Manual: open `/app/query-report/Owner Daily Snapshot` → filter Branch + Date → Print PDF → confirm content (revenue, sales mix, top 5, alarm, payment mix) matches the blueprint
5. Cross-site smoke: change a Resto Settings threshold on one outlet, verify the alarm logic respects the new tunable value
