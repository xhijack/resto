# F&B Owner Daily Snapshot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Phase 1 of the F&B Owner Reports Suite — a single Daily Owner Snapshot accessible as a Frappe Script Report with a "Print Owner PDF" button that renders a 1–2 page opinionated executive summary via a Jinja template.

**Architecture:** Hybrid pattern shared with future Weekly/Monthly cadences. `OwnerReportService.compute_snapshot(branch, period_start, period_end)` produces a single Dict shape covering header, performa (revenue + COGS + trend), sales mix, top menu, alarm, and payment mix. The Script Report calls it for the tabular preview; the PDF endpoint calls it then renders a Jinja template. COGS is computed on-the-fly by looking up the `POS Daily Summary` for the date+branch and delegating to the existing `RawMaterialCalculatorService` (Phase 4–6 refactor that already landed on `candidate`).

**Tech Stack:** Frappe v15 (Python), MariaDB, Jinja2, raw inline SVG for charts, `frappe.utils.pdf.get_pdf` (wkhtmltopdf) for PDF rendering. Tests use `unittest.mock` for service units + `RestoPOSTestBase` (which extends `FrappeTestCase`) for the real-DB integration test.

**Scope correction from spec:** The spec referenced "existing Resto Settings single-doctype", but exploration shows the folder is empty (no JSON, no Python) and no code references it. Task 2 creates the doctype as part of this work.

---

## Task 0: Set up the work branch

**Files:** none — git only

- [ ] **Step 1: Confirm starting point**

```bash
cd /Users/ramdani/Documents/development/erpnext/apps/resto
git status --short
git branch --show-current
git log --oneline -3
```

Expected: clean working tree (only the usual untracked tool artifacts), currently on `candidate` at `3ae4422 docs(owner-reports): spec for F&B Owner Reports Suite — Phase 1 Daily`.

- [ ] **Step 2: Create the feature branch**

```bash
git checkout -b feature/owner-daily-snapshot
git branch --show-current
```

Expected: `feature/owner-daily-snapshot`.

---

## Task 1: Folder skeleton + `__init__.py` files

**Files:**
- Create: `resto/services/owner_report/__init__.py`
- Create: `resto/services/owner_report/owner_report_periods.py` (placeholder)
- Create: `resto/services/owner_report/owner_report_service.py` (placeholder)
- Create: `resto/tests/test_owner_report/__init__.py`
- Create: `resto/templates/owner_reports/__init__.py` (empty marker; Frappe scans for templates)

- [ ] **Step 1: Create empty `__init__.py` files**

```bash
touch resto/services/owner_report/__init__.py
touch resto/tests/test_owner_report/__init__.py
mkdir -p resto/templates/owner_reports
touch resto/templates/owner_reports/__init__.py
```

- [ ] **Step 2: Create empty placeholder modules** so the test discovery doesn't error

`resto/services/owner_report/owner_report_periods.py`:
```python
"""Date-range helpers for OwnerReportService (Daily/Weekly/Monthly buckets)."""
```

`resto/services/owner_report/owner_report_service.py`:
```python
"""OwnerReportService — opinionated F&B owner executive summary."""
```

- [ ] **Step 3: Commit**

```bash
git add resto/services/owner_report/ resto/tests/test_owner_report/ resto/templates/owner_reports/
git commit -m "chore(owner-report): scaffold service + test + template folders"
```

---

## Task 2: Create `Resto Settings` Single doctype with 4 owner-report fields

**Files:**
- Create: `resto/resto_sopwer/doctype/resto_settings/resto_settings.json`
- Create: `resto/resto_sopwer/doctype/resto_settings/resto_settings.py`
- Create: `resto/resto_sopwer/doctype/resto_settings/__init__.py`

- [ ] **Step 1: Create the doctype controller**

`resto/resto_sopwer/doctype/resto_settings/__init__.py` — empty file.

`resto/resto_sopwer/doctype/resto_settings/resto_settings.py`:
```python
import frappe
from frappe.model.document import Document


class RestoSettings(Document):
    pass
```

- [ ] **Step 2: Create the doctype JSON (Single, 4 owner-report fields)**

`resto/resto_sopwer/doctype/resto_settings/resto_settings.json`:
```json
{
 "actions": [],
 "creation": "2026-05-30 00:00:00.000000",
 "doctype": "DocType",
 "engine": "InnoDB",
 "field_order": [
  "owner_reports_section",
  "owner_void_threshold_pct",
  "owner_discount_threshold_pct",
  "column_break_owr_1",
  "owner_report_currency_format",
  "owner_report_top_menu_count"
 ],
 "fields": [
  {
   "fieldname": "owner_reports_section",
   "fieldtype": "Section Break",
   "label": "Owner Reports"
  },
  {
   "default": "5.0",
   "description": "Alarm void fires when (void Rp / revenue Rp) goes above this percent on the daily snapshot.",
   "fieldname": "owner_void_threshold_pct",
   "fieldtype": "Percent",
   "label": "Owner: Void Alarm Threshold (%)"
  },
  {
   "default": "10.0",
   "description": "Alarm discount fires when (discount Rp / revenue Rp) goes above this percent.",
   "fieldname": "owner_discount_threshold_pct",
   "fieldtype": "Percent",
   "label": "Owner: Discount Alarm Threshold (%)"
  },
  {
   "fieldname": "column_break_owr_1",
   "fieldtype": "Column Break"
  },
  {
   "default": "id-ID Rp",
   "fieldname": "owner_report_currency_format",
   "fieldtype": "Select",
   "label": "Owner Report Currency Format",
   "options": "id-ID Rp\nen-US $"
  },
  {
   "default": "5",
   "description": "How many top-selling menus appear on the Daily snapshot (Weekly uses N×2, Monthly uses N×3).",
   "fieldname": "owner_report_top_menu_count",
   "fieldtype": "Int",
   "label": "Owner Report Top Menu Count"
  }
 ],
 "index_web_pages_for_search": 1,
 "issingle": 1,
 "links": [],
 "modified": "2026-05-30 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Resto Sopwer",
 "name": "Resto Settings",
 "owner": "Administrator",
 "permissions": [
  {
   "read": 1,
   "role": "System Manager",
   "write": 1
  }
 ],
 "sort_field": "modified",
 "sort_order": "DESC",
 "states": []
}
```

- [ ] **Step 3: Migrate**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test migrate 2>&1 | tail -5
```

Expected: completes without traceback.

- [ ] **Step 4: Verify the doctype + fields registered**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test console <<'PYEOF'
import frappe
meta = frappe.get_meta("Resto Settings")
print([f.fieldname for f in meta.fields if "owner" in f.fieldname])
PYEOF
```

Expected: `['owner_reports_section', 'owner_void_threshold_pct', 'owner_discount_threshold_pct', 'owner_report_currency_format', 'owner_report_top_menu_count']` (section break inclusive).

- [ ] **Step 5: Commit**

```bash
git add resto/resto_sopwer/doctype/resto_settings/
git commit -m "feat(owner-report): add Resto Settings doctype with 4 owner-report fields"
```

---

## Task 3: `owner_report_periods.daily_compare_ranges()`

**Files:**
- Modify: `resto/services/owner_report/owner_report_periods.py`
- Create: `resto/tests/test_owner_report/test_owner_report_periods.py`

- [ ] **Step 1: Write the failing test**

`resto/tests/test_owner_report/test_owner_report_periods.py`:
```python
import unittest
from datetime import date

from resto.services.owner_report.owner_report_periods import daily_compare_ranges


class TestDailyCompareRanges(unittest.TestCase):
    def test_returns_three_labelled_ranges_for_a_target_date(self):
        target = date(2026, 5, 29)  # Friday
        ranges = daily_compare_ranges(target)

        self.assertEqual(
            ranges,
            [
                ("current", date(2026, 5, 29), date(2026, 5, 29)),
                ("prev_day", date(2026, 5, 28), date(2026, 5, 28)),
                ("same_day_last_week", date(2026, 5, 22), date(2026, 5, 22)),
            ],
        )

    def test_handles_month_boundary(self):
        target = date(2026, 6, 1)  # crosses month boundary going back
        ranges = daily_compare_ranges(target)

        self.assertEqual(ranges[1], ("prev_day", date(2026, 5, 31), date(2026, 5, 31)))
        self.assertEqual(ranges[2], ("same_day_last_week", date(2026, 5, 25), date(2026, 5, 25)))
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_periods 2>&1 | tail -5
```

Expected: `ImportError: cannot import name 'daily_compare_ranges'`.

- [ ] **Step 3: Implement**

`resto/services/owner_report/owner_report_periods.py`:
```python
"""Date-range helpers for OwnerReportService (Daily/Weekly/Monthly buckets)."""

from datetime import date, timedelta
from typing import List, Tuple

CompareRange = Tuple[str, date, date]


def daily_compare_ranges(target: date) -> List[CompareRange]:
    """Return three labelled (start, end) tuples for the Daily snapshot:
    the target day, the previous calendar day, and the same day one week back.

    Used by OwnerReportService.compute_snapshot to fan out three queries and
    derive DoD / WoW deltas.
    """
    return [
        ("current", target, target),
        ("prev_day", target - timedelta(days=1), target - timedelta(days=1)),
        ("same_day_last_week", target - timedelta(days=7), target - timedelta(days=7)),
    ]
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_periods 2>&1 | tail -5
```

Expected: `Ran 2 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_periods.py resto/tests/test_owner_report/test_owner_report_periods.py
git commit -m "feat(owner-report): daily_compare_ranges helper + tests"
```

---

## Task 4: `OwnerReportService` shell + `compute_snapshot` dict skeleton

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Create: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test**

`resto/tests/test_owner_report/test_owner_report_service.py`:
```python
import unittest
from datetime import date
from unittest.mock import patch

from resto.services.owner_report.owner_report_service import OwnerReportService


class TestComputeSnapshotShape(unittest.TestCase):
    def test_returns_dict_with_required_top_level_keys(self):
        with patch.object(OwnerReportService, "_fetch_invoices", return_value=[]), \
             patch.object(OwnerReportService, "_lookup_thresholds",
                          return_value={"void_pct": 5.0, "discount_pct": 10.0,
                                        "top_menu_count": 5, "currency": "id-ID Rp"}):
            result = OwnerReportService().compute_snapshot(
                branch="_Test Branch",
                period_start=date(2026, 5, 29),
                period_end=date(2026, 5, 29),
            )

        for key in ("header", "performa", "sales_mix", "top_menu", "alarm", "payment_mix"):
            self.assertIn(key, result, f"missing top-level key: {key}")
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `AttributeError: ... has no attribute 'compute_snapshot'` (or `_fetch_invoices`).

- [ ] **Step 3: Implement the shell**

`resto/services/owner_report/owner_report_service.py`:
```python
"""OwnerReportService — opinionated F&B owner executive summary."""

from datetime import date
from typing import Dict, List, Optional

import frappe


class OwnerReportService:
    """Build the Daily/Weekly/Monthly owner snapshot for one branch + range."""

    def compute_snapshot(
        self,
        branch: str,
        period_start: date,
        period_end: date,
    ) -> Dict:
        thresholds = self._lookup_thresholds()
        invoices = self._fetch_invoices(branch, period_start, period_end)

        return {
            "header": {
                "branch": branch,
                "period_start": period_start,
                "period_end": period_end,
                "currency": thresholds["currency"],
            },
            "performa": {
                "revenue": 0.0, "margin_rp": 0.0, "cogs_pct": 0.0,
                "bill_count": 0, "pax": 0, "avg_check": 0.0,
                "dod_pct": None, "wow_pct": None, "mom_pct": None,
            },
            "sales_mix": {"kategori": [], "order_type": {}},
            "top_menu": [],
            "alarm": {
                "void_count": 0, "void_rp": 0.0, "discount_rp": 0.0,
                "void_alert": False, "discount_alert": False,
                "thresholds": {"void_pct": thresholds["void_pct"],
                               "discount_pct": thresholds["discount_pct"]},
            },
            "payment_mix": {"cash": 0.0, "cashless": 0.0, "voucher": 0.0},
        }

    # --- private helpers (filled in by later tasks) ---

    def _fetch_invoices(self, branch: str, period_start: date, period_end: date) -> List[Dict]:
        """Bulk-fetch submitted POS Invoice headers for the range. Filled in Task 5."""
        return []

    def _lookup_thresholds(self) -> Dict:
        """Read the four owner_* fields from Resto Settings. Filled in Task 10."""
        return {"void_pct": 5.0, "discount_pct": 10.0,
                "top_menu_count": 5, "currency": "id-ID Rp"}
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 1 test` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): OwnerReportService shell + compute_snapshot skeleton"
```

---

## Task 5: `_fetch_invoices` bulk query

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (add to test file)**

Append to `test_owner_report_service.py`:
```python
class TestFetchInvoices(unittest.TestCase):
    def test_calls_frappe_get_all_with_correct_filters(self):
        with patch("resto.services.owner_report.owner_report_service.frappe.get_all",
                   return_value=[]) as mock_ga:
            OwnerReportService()._fetch_invoices(
                "BR-1", date(2026, 5, 29), date(2026, 5, 29),
            )

        args, kwargs = mock_ga.call_args
        self.assertEqual(args[0], "POS Invoice")
        filters = kwargs["filters"]
        self.assertEqual(filters["docstatus"], 1)
        self.assertEqual(filters["is_pos"], 1)
        self.assertEqual(filters["branch"], "BR-1")
        self.assertEqual(
            filters["posting_date"],
            ["between", [date(2026, 5, 29), date(2026, 5, 29)]],
        )
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: assertion failure (frappe.get_all not called because helper currently returns hardcoded `[]`).

- [ ] **Step 3: Implement the real fetch**

Replace `_fetch_invoices` in `owner_report_service.py` with:
```python
    INVOICE_FIELDS = [
        "name", "posting_date", "posting_time", "branch", "order_type",
        "pax", "grand_total", "net_total", "discount_amount", "status",
    ]

    def _fetch_invoices(self, branch: str, period_start: date, period_end: date) -> List[Dict]:
        """Bulk-fetch submitted POS Invoice headers for the range."""
        return frappe.get_all(
            "POS Invoice",
            filters={
                "docstatus": 1,
                "is_pos": 1,
                "branch": branch,
                "posting_date": ["between", [period_start, period_end]],
            },
            fields=self.INVOICE_FIELDS,
        )
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 2 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _fetch_invoices bulk query"
```

---

## Task 6: `compute_performa` (revenue, bills, pax, avg_check)

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (append)**

```python
def _inv(grand_total, pax=2, **extra):
    """Mini factory for a POS Invoice dict row."""
    return {"name": "PI-X", "grand_total": grand_total, "net_total": grand_total,
            "pax": pax, "discount_amount": 0, "branch": "BR-1",
            "posting_date": date(2026, 5, 29), "posting_time": "12:00:00",
            "order_type": "Dine-In", "status": "Paid", **extra}


class TestComputePerforma(unittest.TestCase):
    def test_sums_revenue_bills_pax_and_computes_avg_check(self):
        invoices = [_inv(100000, pax=2), _inv(50000, pax=1), _inv(150000, pax=4)]
        result = OwnerReportService()._compute_performa(invoices)

        self.assertEqual(result["revenue"], 300000)
        self.assertEqual(result["bill_count"], 3)
        self.assertEqual(result["pax"], 7)
        self.assertAlmostEqual(result["avg_check"], 300000 / 7, places=2)

    def test_avg_check_is_zero_when_pax_is_zero(self):
        result = OwnerReportService()._compute_performa([_inv(100000, pax=0)])
        self.assertEqual(result["avg_check"], 0.0)

    def test_empty_invoices_returns_zeros(self):
        result = OwnerReportService()._compute_performa([])
        self.assertEqual(result, {"revenue": 0.0, "bill_count": 0, "pax": 0, "avg_check": 0.0})
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `AttributeError: ... _compute_performa`.

- [ ] **Step 3: Implement**

Add to `OwnerReportService`:
```python
    @staticmethod
    def _compute_performa(invoices: List[Dict]) -> Dict:
        from frappe.utils import flt
        revenue = sum(flt(inv.get("grand_total")) for inv in invoices)
        bill_count = len(invoices)
        pax = sum(int(inv.get("pax") or 0) for inv in invoices)
        avg_check = (revenue / pax) if pax else 0.0
        return {
            "revenue": revenue,
            "bill_count": bill_count,
            "pax": pax,
            "avg_check": avg_check,
        }
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 5 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _compute_performa (revenue, bills, pax, avg check)"
```

---

## Task 7: COGS lookup via POS Daily Summary + `RawMaterialCalculatorService`

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (append)**

```python
class TestComputeCOGS(unittest.TestCase):
    def test_uses_daily_summary_when_present(self):
        with patch("resto.services.owner_report.owner_report_service.frappe.db.exists",
                   return_value="EDS-001"), \
             patch("resto.services.owner_report.owner_report_service."
                   "RawMaterialCalculatorService") as MockRM:
            MockRM.return_value.compute_breakdown.return_value = {
                "items": [
                    {"qty": 3, "selling_amount": 30000,
                     "rm_items": [{"cost": 12000}, {"cost": 3000}]},
                    {"qty": 1, "selling_amount": 20000,
                     "rm_items": [{"cost": 5000}]},
                ]
            }

            result = OwnerReportService()._compute_cogs("BR-1", date(2026, 5, 29))

        self.assertEqual(result["cost_rp"], 20000)
        self.assertEqual(result["selling_rp"], 50000)
        self.assertAlmostEqual(result["cogs_pct"], 40.0, places=2)

    def test_returns_zeros_when_no_daily_summary(self):
        with patch("resto.services.owner_report.owner_report_service.frappe.db.exists",
                   return_value=None):
            result = OwnerReportService()._compute_cogs("BR-1", date(2026, 5, 29))

        self.assertEqual(result, {"cost_rp": 0.0, "selling_rp": 0.0, "cogs_pct": 0.0,
                                  "has_data": False})
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `AttributeError: ... _compute_cogs` (and the import for `RawMaterialCalculatorService` is missing).

- [ ] **Step 3: Implement**

Add the import at the top of `owner_report_service.py`:
```python
from resto.services.stock_usage.rm_calculator import RawMaterialCalculatorService
```

Add the method:
```python
    @staticmethod
    def _compute_cogs(branch: str, posting_date: date) -> Dict:
        """COGS via POS Daily Summary + rm_calculator. Returns zeros when the
        Daily Summary doesn't exist yet (e.g., owner views same-day report
        before end-of-shift). Designed to fail gracefully so the rest of the
        snapshot is still useful."""
        from frappe.utils import flt
        eds_name = frappe.db.exists(
            "POS Daily Summary",
            {"posting_date": posting_date, "branch": branch, "docstatus": 1},
        )
        if not eds_name:
            return {"cost_rp": 0.0, "selling_rp": 0.0, "cogs_pct": 0.0,
                    "has_data": False}

        breakdown = RawMaterialCalculatorService().compute_breakdown(eds_name)
        cost_rp = 0.0
        selling_rp = 0.0
        for item in breakdown.get("items", []):
            selling_rp += flt(item.get("selling_amount"))
            for rm in item.get("rm_items") or []:
                cost_rp += flt(rm.get("cost"))

        cogs_pct = (cost_rp / selling_rp * 100) if selling_rp else 0.0
        return {"cost_rp": cost_rp, "selling_rp": selling_rp,
                "cogs_pct": cogs_pct, "has_data": True}
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 7 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _compute_cogs via POS Daily Summary + rm_calculator"
```

---

## Task 8: `compute_sales_mix` (kategori + order type)

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (append)**

```python
class TestComputeSalesMix(unittest.TestCase):
    def _items(self):
        return [
            {"item_code": "ITEM-1", "qty": 2, "amount": 30000,
             "category": "Food", "is_voucher_item": 0, "status_kitchen": "Already Send To Kitchen"},
            {"item_code": "ITEM-2", "qty": 3, "amount": 15000,
             "category": "Beverage", "is_voucher_item": 0, "status_kitchen": "Already Send To Kitchen"},
            {"item_code": "ITEM-3", "qty": 1, "amount": 5000,
             "category": "Food", "is_voucher_item": 0, "status_kitchen": "Void Menu"},
            {"item_code": "VOUCHER-50K", "qty": 1, "amount": 50000,
             "category": "Voucher", "is_voucher_item": 1, "status_kitchen": "Not Send"},
        ]

    def test_groups_revenue_by_category_excluding_voids_and_vouchers(self):
        result = OwnerReportService()._compute_sales_mix(self._items(),
            invoices=[_inv(45000, order_type="Dine-In"),
                      _inv(0, order_type="Take Away")])

        food = next(c for c in result["kategori"] if c["name"] == "Food")
        bev = next(c for c in result["kategori"] if c["name"] == "Beverage")
        self.assertEqual(food["revenue"], 30000)
        self.assertEqual(bev["revenue"], 15000)
        # Voucher item is excluded
        self.assertFalse(any(c["name"] == "Voucher" for c in result["kategori"]))

    def test_pct_share_sums_to_100_when_revenue_present(self):
        result = OwnerReportService()._compute_sales_mix(self._items(), invoices=[])
        total_pct = sum(c["pct"] for c in result["kategori"])
        self.assertAlmostEqual(total_pct, 100.0, places=1)

    def test_order_type_split_from_invoices(self):
        invoices = [_inv(100000, order_type="Dine-In"),
                    _inv(60000, order_type="Take Away")]
        result = OwnerReportService()._compute_sales_mix([], invoices=invoices)

        self.assertEqual(result["order_type"]["Dine-In"], 100000)
        self.assertEqual(result["order_type"]["Take Away"], 60000)
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `AttributeError: ... _compute_sales_mix`.

- [ ] **Step 3: Implement**

```python
    @staticmethod
    def _compute_sales_mix(items: List[Dict], invoices: List[Dict]) -> Dict:
        from collections import defaultdict
        from frappe.utils import flt

        cat_revenue = defaultdict(float)
        cat_qty = defaultdict(float)

        for it in items:
            if it.get("is_voucher_item"):
                continue
            if it.get("status_kitchen") == "Void Menu":
                continue
            cat = (it.get("category") or "Lainnya").strip() or "Lainnya"
            cat_revenue[cat] += flt(it.get("amount"))
            cat_qty[cat] += flt(it.get("qty"))

        total = sum(cat_revenue.values())
        kategori = []
        for name, rev in cat_revenue.items():
            kategori.append({
                "name": name,
                "revenue": rev,
                "qty": cat_qty[name],
                "pct": (rev / total * 100) if total else 0.0,
            })
        kategori.sort(key=lambda r: r["revenue"], reverse=True)

        order_type = defaultdict(float)
        for inv in invoices:
            ot = inv.get("order_type") or "Lainnya"
            order_type[ot] += flt(inv.get("grand_total"))

        return {"kategori": kategori, "order_type": dict(order_type)}
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 10 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _compute_sales_mix (kategori + order_type)"
```

---

## Task 9: `compute_top_menu` (top N by qty)

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (append)**

```python
class TestComputeTopMenu(unittest.TestCase):
    def test_picks_top_n_by_qty_excluding_voids_and_vouchers(self):
        items = [
            {"item_code": "ITEM-A", "item_name": "Nasi Goreng", "qty": 10, "amount": 100000,
             "is_voucher_item": 0, "status_kitchen": ""},
            {"item_code": "ITEM-B", "item_name": "Es Teh", "qty": 25, "amount": 75000,
             "is_voucher_item": 0, "status_kitchen": ""},
            {"item_code": "ITEM-C", "item_name": "Sate", "qty": 5, "amount": 60000,
             "is_voucher_item": 0, "status_kitchen": ""},
            {"item_code": "ITEM-D", "item_name": "Bakso", "qty": 8, "amount": 64000,
             "is_voucher_item": 0, "status_kitchen": "Void Menu"},
            {"item_code": "VOUCHER", "item_name": "Voucher 50K", "qty": 100, "amount": 5000000,
             "is_voucher_item": 1, "status_kitchen": ""},
        ]
        result = OwnerReportService()._compute_top_menu(items, top_n=2)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["item_code"], "ITEM-B")
        self.assertEqual(result[0]["qty"], 25)
        self.assertEqual(result[1]["item_code"], "ITEM-A")
        self.assertEqual(result[1]["qty"], 10)

    def test_returns_empty_list_when_no_items(self):
        self.assertEqual(OwnerReportService()._compute_top_menu([], top_n=5), [])
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `AttributeError: ... _compute_top_menu`.

- [ ] **Step 3: Implement**

```python
    @staticmethod
    def _compute_top_menu(items: List[Dict], top_n: int) -> List[Dict]:
        from collections import defaultdict
        from frappe.utils import flt

        agg = defaultdict(lambda: {"qty": 0.0, "revenue": 0.0, "item_name": ""})
        for it in items:
            if it.get("is_voucher_item") or it.get("status_kitchen") == "Void Menu":
                continue
            code = it.get("item_code")
            if not code:
                continue
            agg[code]["qty"] += flt(it.get("qty"))
            agg[code]["revenue"] += flt(it.get("amount"))
            if not agg[code]["item_name"]:
                agg[code]["item_name"] = it.get("item_name") or code

        rows = [
            {"item_code": code, "item_name": data["item_name"],
             "qty": data["qty"], "revenue": data["revenue"], "cogs_pct": 0.0}
            for code, data in agg.items()
        ]
        rows.sort(key=lambda r: r["qty"], reverse=True)
        return rows[:top_n]
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 12 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _compute_top_menu (top N by qty)"
```

---

## Task 10: `_lookup_thresholds` reading Resto Settings

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (append)**

```python
class TestLookupThresholds(unittest.TestCase):
    def test_reads_four_owner_fields_from_resto_settings(self):
        with patch("resto.services.owner_report.owner_report_service.frappe.get_single_value") as mock:
            mock.side_effect = lambda dt, fn: {
                ("Resto Settings", "owner_void_threshold_pct"): 4.5,
                ("Resto Settings", "owner_discount_threshold_pct"): 12.0,
                ("Resto Settings", "owner_report_top_menu_count"): 7,
                ("Resto Settings", "owner_report_currency_format"): "en-US $",
            }[(dt, fn)]

            result = OwnerReportService()._lookup_thresholds()

        self.assertEqual(result["void_pct"], 4.5)
        self.assertEqual(result["discount_pct"], 12.0)
        self.assertEqual(result["top_menu_count"], 7)
        self.assertEqual(result["currency"], "en-US $")

    def test_falls_back_to_spec_defaults_when_fields_unset(self):
        with patch("resto.services.owner_report.owner_report_service.frappe.get_single_value",
                   return_value=None):
            result = OwnerReportService()._lookup_thresholds()
        self.assertEqual(result, {"void_pct": 5.0, "discount_pct": 10.0,
                                  "top_menu_count": 5, "currency": "id-ID Rp"})
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: assertion failure — the placeholder returns the defaults regardless of the mock.

- [ ] **Step 3: Implement**

Replace `_lookup_thresholds` with:
```python
    DEFAULT_THRESHOLDS = {"void_pct": 5.0, "discount_pct": 10.0,
                          "top_menu_count": 5, "currency": "id-ID Rp"}

    def _lookup_thresholds(self) -> Dict:
        def read(field: str, default):
            value = frappe.get_single_value("Resto Settings", field)
            return value if value not in (None, "", 0) else default

        return {
            "void_pct": float(read("owner_void_threshold_pct",
                                   self.DEFAULT_THRESHOLDS["void_pct"])),
            "discount_pct": float(read("owner_discount_threshold_pct",
                                       self.DEFAULT_THRESHOLDS["discount_pct"])),
            "top_menu_count": int(read("owner_report_top_menu_count",
                                       self.DEFAULT_THRESHOLDS["top_menu_count"])),
            "currency": read("owner_report_currency_format",
                             self.DEFAULT_THRESHOLDS["currency"]),
        }
```

- [ ] **Step 4: Run the test — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 14 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _lookup_thresholds reads Resto Settings with sane fallbacks"
```

---

## Task 11: `_compute_alarm` + `_compute_payment_mix`

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing tests (append)**

```python
class TestComputeAlarm(unittest.TestCase):
    def test_alarm_fires_when_thresholds_exceeded(self):
        result = OwnerReportService()._compute_alarm(
            revenue=1_000_000,
            void_count=4, void_rp=80_000,        # 8% > 5%
            discount_rp=150_000,                  # 15% > 10%
            thresholds={"void_pct": 5.0, "discount_pct": 10.0},
        )
        self.assertTrue(result["void_alert"])
        self.assertTrue(result["discount_alert"])
        self.assertEqual(result["void_count"], 4)
        self.assertEqual(result["void_rp"], 80_000)

    def test_alarm_silent_when_under_threshold(self):
        result = OwnerReportService()._compute_alarm(
            revenue=1_000_000, void_count=1, void_rp=10_000,
            discount_rp=50_000,
            thresholds={"void_pct": 5.0, "discount_pct": 10.0},
        )
        self.assertFalse(result["void_alert"])
        self.assertFalse(result["discount_alert"])

    def test_zero_revenue_does_not_throw(self):
        result = OwnerReportService()._compute_alarm(
            revenue=0, void_count=0, void_rp=0, discount_rp=0,
            thresholds={"void_pct": 5.0, "discount_pct": 10.0},
        )
        self.assertFalse(result["void_alert"])
        self.assertFalse(result["discount_alert"])


class TestComputePaymentMix(unittest.TestCase):
    def test_splits_cash_cashless_voucher(self):
        invoices = [
            {"name": "PI-1", "grand_total": 100000,
             "payments": [{"mode_of_payment": "Cash", "amount": 100000}]},
            {"name": "PI-2", "grand_total": 50000,
             "payments": [{"mode_of_payment": "QRIS", "amount": 50000}]},
            {"name": "PI-3", "grand_total": 75000,
             "payments": [{"mode_of_payment": "Voucher", "amount": 75000}]},
        ]
        result = OwnerReportService()._compute_payment_mix(invoices)

        self.assertEqual(result["cash"], 100000)
        self.assertEqual(result["cashless"], 50000)
        self.assertEqual(result["voucher"], 75000)
```

- [ ] **Step 2: Run the tests — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `AttributeError: ... _compute_alarm`.

- [ ] **Step 3: Implement both**

```python
    CASHLESS_MODES = {"QRIS", "EDC", "Debit", "Credit Card", "Card",
                      "Transfer", "Bank Transfer", "GoPay", "OVO", "DANA", "ShopeePay"}
    VOUCHER_MODES = {"Voucher"}

    @staticmethod
    def _compute_alarm(*, revenue: float, void_count: int, void_rp: float,
                       discount_rp: float, thresholds: Dict) -> Dict:
        from frappe.utils import flt
        rev = flt(revenue) or 1e-9  # avoid div/0; flag stays False at 0 revenue
        void_pct = (flt(void_rp) / rev) * 100 if revenue else 0.0
        disc_pct = (flt(discount_rp) / rev) * 100 if revenue else 0.0
        return {
            "void_count": int(void_count),
            "void_rp": flt(void_rp),
            "discount_rp": flt(discount_rp),
            "void_alert": void_pct > thresholds["void_pct"],
            "discount_alert": disc_pct > thresholds["discount_pct"],
            "thresholds": dict(thresholds),
        }

    def _compute_payment_mix(self, invoices: List[Dict]) -> Dict:
        from frappe.utils import flt
        mix = {"cash": 0.0, "cashless": 0.0, "voucher": 0.0}
        for inv in invoices:
            for p in inv.get("payments") or []:
                mode = (p.get("mode_of_payment") or "").strip()
                amount = flt(p.get("amount"))
                if mode in self.VOUCHER_MODES:
                    mix["voucher"] += amount
                elif mode in self.CASHLESS_MODES:
                    mix["cashless"] += amount
                else:
                    mix["cash"] += amount
        return mix
```

- [ ] **Step 4: Run the tests — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 18 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): _compute_alarm + _compute_payment_mix"
```

---

## Task 12: Wire all subcomputations into `compute_snapshot` with DoD/WoW trend

**Files:**
- Modify: `resto/services/owner_report/owner_report_service.py`
- Modify: `resto/tests/test_owner_report/test_owner_report_service.py`

- [ ] **Step 1: Write the failing test (append)**

```python
class TestComputeSnapshotIntegration(unittest.TestCase):
    """End-to-end shape test for compute_snapshot. All deps mocked."""

    def test_dod_and_wow_pct_are_set_when_comparison_data_present(self):
        target = date(2026, 5, 29)

        invoices_by_range = {
            (date(2026, 5, 29),): [_inv(300000, pax=3)],
            (date(2026, 5, 28),): [_inv(200000, pax=2)],
            (date(2026, 5, 22),): [_inv(150000, pax=2)],
        }

        def fake_fetch(self, branch, period_start, period_end):
            return invoices_by_range.get((period_start,), [])

        with patch.object(OwnerReportService, "_fetch_invoices", autospec=True,
                          side_effect=fake_fetch), \
             patch.object(OwnerReportService, "_fetch_items", autospec=True,
                          return_value=[]), \
             patch.object(OwnerReportService, "_compute_cogs",
                          return_value={"cost_rp": 0, "selling_rp": 0,
                                        "cogs_pct": 0, "has_data": False}), \
             patch.object(OwnerReportService, "_lookup_thresholds",
                          return_value={"void_pct": 5.0, "discount_pct": 10.0,
                                        "top_menu_count": 5, "currency": "id-ID Rp"}):
            result = OwnerReportService().compute_snapshot("BR-1", target, target)

        self.assertEqual(result["performa"]["revenue"], 300000)
        self.assertEqual(result["performa"]["bill_count"], 1)
        self.assertAlmostEqual(result["performa"]["dod_pct"], 50.0, places=1)   # 300k vs 200k
        self.assertAlmostEqual(result["performa"]["wow_pct"], 100.0, places=1)  # 300k vs 150k
```

- [ ] **Step 2: Run the test — expect failure**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `dod_pct` is `None` (the skeleton hasn't been wired yet) or `_fetch_items` attribute error.

- [ ] **Step 3: Implement — replace the body of `compute_snapshot`**

Add the items fetch helper first:
```python
    ITEM_FIELDS = [
        "parent", "item_code", "item_name", "category", "qty", "amount",
        "is_voucher_item", "status_kitchen", "void_amount",
    ]

    def _fetch_items(self, invoice_names: List[str]) -> List[Dict]:
        if not invoice_names:
            return []
        return frappe.get_all(
            "POS Invoice Item",
            filters={"parent": ["in", invoice_names]},
            fields=self.ITEM_FIELDS,
        )

    def _fetch_payments(self, invoice_names: List[str]) -> List[Dict]:
        if not invoice_names:
            return []
        rows = frappe.get_all(
            "Sales Invoice Payment",
            filters={"parenttype": "POS Invoice", "parent": ["in", invoice_names]},
            fields=["parent", "mode_of_payment", "amount"],
        )
        # Attach payments back onto invoice dicts so compute_payment_mix can iterate.
        by_parent = {}
        for r in rows:
            by_parent.setdefault(r["parent"], []).append(r)
        return by_parent
```

Replace `compute_snapshot`:
```python
    def compute_snapshot(
        self,
        branch: str,
        period_start: date,
        period_end: date,
    ) -> Dict:
        from resto.services.owner_report.owner_report_periods import daily_compare_ranges

        thresholds = self._lookup_thresholds()

        # Fan out three queries for the Daily trend windows. Falls back to a
        # single window when start != end (Weekly/Monthly will diverge here).
        if period_start == period_end:
            ranges = daily_compare_ranges(period_start)
        else:
            ranges = [("current", period_start, period_end)]

        slices = {}
        for label, start, end in ranges:
            inv_list = self._fetch_invoices(branch, start, end)
            slices[label] = inv_list

        current_invoices = slices.get("current", [])
        current_names = [inv["name"] for inv in current_invoices]
        items = self._fetch_items(current_names)
        payments_by_parent = self._fetch_payments(current_names)
        for inv in current_invoices:
            inv["payments"] = payments_by_parent.get(inv["name"], [])

        performa_now = self._compute_performa(current_invoices)
        cogs = self._compute_cogs(branch, period_end)
        # Trend uses revenue from comparison slices.
        dod = self._delta_pct(performa_now["revenue"],
                              self._compute_performa(slices.get("prev_day", []))["revenue"])
        wow = self._delta_pct(performa_now["revenue"],
                              self._compute_performa(slices.get("same_day_last_week", []))["revenue"])

        # Void & discount aggregates
        void_count = sum(1 for it in items if it.get("status_kitchen") == "Void Menu")
        void_rp = sum(_flt(it.get("void_amount")) for it in items
                      if it.get("status_kitchen") == "Void Menu")
        discount_rp = sum(_flt(inv.get("discount_amount")) for inv in current_invoices)

        return {
            "header": {
                "branch": branch,
                "period_start": period_start,
                "period_end": period_end,
                "currency": thresholds["currency"],
            },
            "performa": {
                **performa_now,
                "margin_rp": cogs["selling_rp"] - cogs["cost_rp"],
                "cogs_pct": cogs["cogs_pct"],
                "dod_pct": dod,
                "wow_pct": wow,
                "mom_pct": None,  # Weekly/Monthly only — Phase 2
            },
            "sales_mix": self._compute_sales_mix(items, current_invoices),
            "top_menu": self._compute_top_menu(items, thresholds["top_menu_count"]),
            "alarm": self._compute_alarm(
                revenue=performa_now["revenue"],
                void_count=void_count, void_rp=void_rp, discount_rp=discount_rp,
                thresholds=thresholds,
            ),
            "payment_mix": self._compute_payment_mix(current_invoices),
        }

    @staticmethod
    def _delta_pct(current: float, base: float):
        if not base:
            return None
        return (current - base) / base * 100
```

Add the module-level helper:
```python
def _flt(v) -> float:
    from frappe.utils import flt
    return flt(v)
```

- [ ] **Step 4: Run the tests — expect pass**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_report_service 2>&1 | tail -5
```

Expected: `Ran 19 tests` → `OK`.

- [ ] **Step 5: Commit**

```bash
git add resto/services/owner_report/owner_report_service.py resto/tests/test_owner_report/test_owner_report_service.py
git commit -m "feat(owner-report): compute_snapshot orchestrator + DoD/WoW trend"
```

---

## Task 13: Script Report — JSON metadata + Python `execute()`

**Files:**
- Create: `resto/resto_sopwer/report/owner_daily_snapshot/__init__.py`
- Create: `resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.json`
- Create: `resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.py`

- [ ] **Step 1: Create `__init__.py`**

```bash
mkdir -p resto/resto_sopwer/report/owner_daily_snapshot
touch resto/resto_sopwer/report/owner_daily_snapshot/__init__.py
```

- [ ] **Step 2: Create the report JSON**

`resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.json`:
```json
{
 "add_total_row": 0,
 "creation": "2026-05-30 00:00:00.000000",
 "disabled": 0,
 "docstatus": 0,
 "doctype": "Report",
 "is_standard": "Yes",
 "letterhead": null,
 "modified": "2026-05-30 00:00:00.000000",
 "modified_by": "Administrator",
 "module": "Resto Sopwer",
 "name": "Owner Daily Snapshot",
 "owner": "Administrator",
 "prepared_report": 0,
 "ref_doctype": "POS Invoice",
 "report_name": "Owner Daily Snapshot",
 "report_type": "Script Report",
 "roles": [
  {"role": "System Manager"}
 ]
}
```

- [ ] **Step 3: Create the report Python (delegates to the service)**

`resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.py`:
```python
"""Owner Daily Snapshot — Script Report wrapper.

Delegates all computation to OwnerReportService.compute_snapshot and renders
the result as a flat row set so the Frappe report viewer can show a preview
+ offer the standard Excel/CSV export. The opinionated PDF view lives in
templates/owner_reports/daily_snapshot.html and is invoked from the JS
"Print Owner PDF" button.
"""

from datetime import date as _date

import frappe
from frappe.utils import getdate

from resto.services.owner_report.owner_report_service import OwnerReportService


def execute(filters=None):
    filters = frappe._dict(filters or {})
    branch = filters.get("branch")
    posting_date = getdate(filters.get("posting_date") or _date.today())

    if not branch:
        frappe.throw("Branch filter is required for Owner Daily Snapshot.")

    snapshot = OwnerReportService().compute_snapshot(branch, posting_date, posting_date)

    columns = [
        {"label": "Metric", "fieldname": "metric", "fieldtype": "Data", "width": 240},
        {"label": "Value", "fieldname": "value", "fieldtype": "Data", "width": 200},
    ]

    p = snapshot["performa"]
    a = snapshot["alarm"]
    pm = snapshot["payment_mix"]

    data = [
        {"metric": "Revenue", "value": _money(p["revenue"])},
        {"metric": "DoD %", "value": _pct(p["dod_pct"])},
        {"metric": "WoW %", "value": _pct(p["wow_pct"])},
        {"metric": "COGS %", "value": _pct(p["cogs_pct"])},
        {"metric": "Margin Rp", "value": _money(p["margin_rp"])},
        {"metric": "Bills", "value": str(p["bill_count"])},
        {"metric": "Pax", "value": str(p["pax"])},
        {"metric": "Avg Check", "value": _money(p["avg_check"])},
        {"metric": "Void Rp", "value": _money(a["void_rp"]) + (" ⚠️" if a["void_alert"] else "")},
        {"metric": "Discount Rp", "value": _money(a["discount_rp"]) + (" ⚠️" if a["discount_alert"] else "")},
        {"metric": "Cash", "value": _money(pm["cash"])},
        {"metric": "Cashless", "value": _money(pm["cashless"])},
        {"metric": "Voucher", "value": _money(pm["voucher"])},
    ]
    return columns, data


def _money(v):
    try:
        return f"Rp {float(v):,.0f}"
    except (TypeError, ValueError):
        return ""


def _pct(v):
    return "—" if v is None else f"{float(v):.1f}%"
```

- [ ] **Step 4: Verify the report registers**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test migrate 2>&1 | tail -3
/opt/anaconda3/envs/env/bin/bench --site resto.test console <<'PYEOF'
import frappe
print("registered?", frappe.db.exists("Report", "Owner Daily Snapshot"))
PYEOF
```

Expected: `registered? Owner Daily Snapshot`.

- [ ] **Step 5: Commit**

```bash
git add resto/resto_sopwer/report/owner_daily_snapshot/
git commit -m "feat(owner-report): Script Report wrapper for Owner Daily Snapshot"
```

---

## Task 14: Script Report JS — filter UI + "Print Owner PDF" button

**Files:**
- Create: `resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.js`

- [ ] **Step 1: Write the file**

`resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.js`:
```javascript
// Owner Daily Snapshot — filter UI + Print Owner PDF button.
// The button posts (branch, posting_date) to the Python endpoint and triggers
// a PDF download. The Frappe report view itself shows a tabular preview;
// owners use the PDF for WA forwarding.
frappe.query_reports["Owner Daily Snapshot"] = {
  filters: [
    {
      fieldname: "branch",
      label: __("Branch"),
      fieldtype: "Link",
      options: "Branch",
      reqd: 1,
    },
    {
      fieldname: "posting_date",
      label: __("Date"),
      fieldtype: "Date",
      default: frappe.datetime.add_days(frappe.datetime.get_today(), -1),
      reqd: 1,
    },
  ],

  onload(report) {
    report.page.add_inner_button(__("Print Owner PDF"), () => {
      const branch = frappe.query_report.get_filter_value("branch");
      const posting_date = frappe.query_report.get_filter_value("posting_date");
      if (!branch || !posting_date) {
        frappe.msgprint(__("Pick Branch + Date first."));
        return;
      }
      const url =
        "/api/method/resto.api.print_owner_daily_snapshot_pdf" +
        `?branch=${encodeURIComponent(branch)}` +
        `&posting_date=${encodeURIComponent(posting_date)}`;
      window.open(url, "_blank");
    });
  },
};
```

- [ ] **Step 2: Build assets so Frappe picks up the new JS**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test build --app resto 2>&1 | tail -5
```

Expected: `DONE Total Build Time: <under 5s>`.

- [ ] **Step 3: Commit**

```bash
git add resto/resto_sopwer/report/owner_daily_snapshot/owner_daily_snapshot.js
git commit -m "feat(owner-report): Script Report JS filter + Print Owner PDF button"
```

---

## Task 15: Jinja PDF template with inline SVG donut

**Files:**
- Create: `resto/templates/owner_reports/daily_snapshot.html`

- [ ] **Step 1: Write the template**

`resto/templates/owner_reports/daily_snapshot.html`:
```html
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<title>Owner Daily Snapshot — {{ data.header.branch }} — {{ data.header.period_start }}</title>
<style>
  body { font-family: "Helvetica Neue", Arial, sans-serif; color: #222; padding: 18px;
         max-width: 760px; margin: 0 auto; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .sub { color: #666; font-size: 12px; margin-bottom: 14px; }
  .row { display: flex; gap: 16px; margin-bottom: 14px; }
  .card { flex: 1; padding: 10px 12px; border: 1px solid #ddd; border-radius: 6px; }
  .card h2 { font-size: 11px; text-transform: uppercase; color: #888;
             margin: 0 0 6px; letter-spacing: 0.5px; }
  .card .v { font-size: 18px; font-weight: 600; }
  .card .sub-v { color: #666; font-size: 11px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; margin-bottom: 12px; }
  th, td { padding: 6px 8px; border-bottom: 1px solid #eee; text-align: left; }
  th { background: #fafafa; }
  .num { text-align: right; }
  .alarm { color: #b00020; font-weight: 600; }
  .ok { color: #1f8a3c; }
  .donut-wrap { display: flex; align-items: center; gap: 16px; }
  .donut svg { width: 140px; height: 140px; }
  ul.legend { list-style: none; padding: 0; margin: 0; font-size: 12px; }
  ul.legend li { padding: 2px 0; }
  ul.legend .sw { display: inline-block; width: 10px; height: 10px; margin-right: 6px;
                  border-radius: 2px; vertical-align: middle; }
</style>
</head>
<body>

<h1>Owner Daily Snapshot — {{ data.header.branch }}</h1>
<p class="sub">{{ data.header.period_start }} · {{ data.header.currency }}</p>

<div class="row">
  <div class="card">
    <h2>Revenue</h2>
    <div class="v">{{ data.header.currency.split(" ")[1] if " " in data.header.currency else "Rp" }} {{ "{:,.0f}".format(data.performa.revenue) }}</div>
    <div class="sub-v">
      DoD {% if data.performa.dod_pct is none %}—{% else %}{{ "{:+.1f}%".format(data.performa.dod_pct) }}{% endif %}
      · WoW {% if data.performa.wow_pct is none %}—{% else %}{{ "{:+.1f}%".format(data.performa.wow_pct) }}{% endif %}
    </div>
  </div>
  <div class="card">
    <h2>Margin / COGS</h2>
    <div class="v">Rp {{ "{:,.0f}".format(data.performa.margin_rp) }}</div>
    <div class="sub-v">COGS {{ "{:.1f}%".format(data.performa.cogs_pct) }}</div>
  </div>
  <div class="card">
    <h2>Bills · Pax</h2>
    <div class="v">{{ data.performa.bill_count }} bill · {{ data.performa.pax }} pax</div>
    <div class="sub-v">Avg check Rp {{ "{:,.0f}".format(data.performa.avg_check) }}</div>
  </div>
</div>

<h2 style="font-size:13px;margin:18px 0 6px;">Sales Mix per Kategori</h2>
<div class="donut-wrap">
  {%- set total = data.performa.revenue or 1 -%}
  <div class="donut">
    <svg viewBox="0 0 36 36">
      {%- set palette = ["#1f8a3c","#1769aa","#b35900","#8a1f7a","#666","#0e7a86","#a8a800"] -%}
      {%- set ns = namespace(off=0) -%}
      {%- for cat in data.sales_mix.kategori -%}
        {%- set frac = cat.revenue / total -%}
        <circle cx="18" cy="18" r="15.915" fill="transparent"
                stroke="{{ palette[loop.index0 % palette|length] }}"
                stroke-width="4"
                stroke-dasharray="{{ "{:.2f}".format(frac * 100) }} {{ "{:.2f}".format(100 - frac * 100) }}"
                stroke-dashoffset="{{ "{:.2f}".format(-ns.off) }}" />
        {%- set ns.off = ns.off + frac * 100 -%}
      {%- endfor -%}
    </svg>
  </div>
  <ul class="legend">
    {%- for cat in data.sales_mix.kategori -%}
      <li>
        <span class="sw" style="background:{{ palette[loop.index0 % palette|length] }}"></span>
        {{ cat.name }} — Rp {{ "{:,.0f}".format(cat.revenue) }} ({{ "{:.1f}%".format(cat.pct) }})
      </li>
    {%- else -%}
      <li>(no sales)</li>
    {%- endfor -%}
  </ul>
</div>

<h2 style="font-size:13px;margin:18px 0 6px;">Top {{ data.top_menu|length }} Menu</h2>
<table>
  <thead><tr><th>Menu</th><th class="num">Qty</th><th class="num">Revenue</th><th class="num">COGS%</th></tr></thead>
  <tbody>
  {%- for m in data.top_menu -%}
    <tr>
      <td>{{ m.item_name }}</td>
      <td class="num">{{ "{:,.0f}".format(m.qty) }}</td>
      <td class="num">Rp {{ "{:,.0f}".format(m.revenue) }}</td>
      <td class="num">{{ "{:.1f}%".format(m.cogs_pct) }}</td>
    </tr>
  {%- else -%}
    <tr><td colspan="4">(no menu data)</td></tr>
  {%- endfor -%}
  </tbody>
</table>

<h2 style="font-size:13px;margin:18px 0 6px;">Alarm Anomali</h2>
<table>
  <tbody>
    <tr>
      <td>Void</td>
      <td class="num {% if data.alarm.void_alert %}alarm{% else %}ok{% endif %}">
        {{ data.alarm.void_count }} item · Rp {{ "{:,.0f}".format(data.alarm.void_rp) }}
        {% if data.alarm.void_alert %}⚠️ &gt; {{ data.alarm.thresholds.void_pct }}%{% endif %}
      </td>
    </tr>
    <tr>
      <td>Diskon</td>
      <td class="num {% if data.alarm.discount_alert %}alarm{% else %}ok{% endif %}">
        Rp {{ "{:,.0f}".format(data.alarm.discount_rp) }}
        {% if data.alarm.discount_alert %}⚠️ &gt; {{ data.alarm.thresholds.discount_pct }}%{% endif %}
      </td>
    </tr>
  </tbody>
</table>

<h2 style="font-size:13px;margin:18px 0 6px;">Payment Mix</h2>
<table>
  <tbody>
    <tr><td>Cash</td><td class="num">Rp {{ "{:,.0f}".format(data.payment_mix.cash) }}</td></tr>
    <tr><td>Cashless</td><td class="num">Rp {{ "{:,.0f}".format(data.payment_mix.cashless) }}</td></tr>
    <tr><td>Voucher</td><td class="num">Rp {{ "{:,.0f}".format(data.payment_mix.voucher) }}</td></tr>
  </tbody>
</table>

</body>
</html>
```

- [ ] **Step 2: Smoke-render through Frappe**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test console <<'PYEOF'
import frappe
from datetime import date
from resto.services.owner_report.owner_report_service import OwnerReportService
data = OwnerReportService().compute_snapshot("_Test Branch", date(2026, 5, 29), date(2026, 5, 29))
html = frappe.render_template("templates/owner_reports/daily_snapshot.html", {"data": data})
print("rendered", len(html), "chars")
PYEOF
```

Expected: `rendered <number> chars` with no traceback (template parses + service runs on empty data).

- [ ] **Step 3: Commit**

```bash
git add resto/templates/owner_reports/daily_snapshot.html
git commit -m "feat(owner-report): Jinja PDF template with inline SVG donut"
```

---

## Task 16: PDF endpoint in `api.py`

**Files:**
- Modify: `resto/api.py` (append a new whitelisted function)

- [ ] **Step 1: Locate the existing print endpoints**

```bash
grep -n "print_daily_sales_full_pdf\|@frappe.whitelist" resto/api.py | head -10
```

Expected: see `print_daily_sales_full_pdf` near the end, follow the same pattern.

- [ ] **Step 2: Append the endpoint**

Add to the bottom of `resto/api.py`:
```python
@frappe.whitelist()
def print_owner_daily_snapshot_pdf(branch: str, posting_date: str):
    """Render the Owner Daily Snapshot Jinja template + return as PDF download."""
    from frappe.utils import getdate
    from frappe.utils.pdf import get_pdf
    from resto.services.owner_report.owner_report_service import OwnerReportService

    if not branch or not posting_date:
        frappe.throw("branch and posting_date are required")

    target = getdate(posting_date)
    data = OwnerReportService().compute_snapshot(branch, target, target)
    html = frappe.render_template(
        "templates/owner_reports/daily_snapshot.html",
        {"data": data},
    )

    frappe.local.response.filename = f"owner-daily-{branch}-{posting_date}.pdf"
    frappe.local.response.filecontent = get_pdf(html)
    frappe.local.response.type = "pdf"
```

- [ ] **Step 3: Verify the endpoint imports cleanly**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test console <<'PYEOF'
from resto.resto_sopwer.api import print_owner_daily_snapshot_pdf
print("import ok:", print_owner_daily_snapshot_pdf.__name__)
PYEOF
```

Expected: `import ok: print_owner_daily_snapshot_pdf`.

- [ ] **Step 4: Commit**

```bash
git add resto/api.py
git commit -m "feat(owner-report): whitelist endpoint print_owner_daily_snapshot_pdf"
```

---

## Task 17: Real-DB integration test

**Files:**
- Create: `resto/tests/test_owner_report/test_owner_daily_snapshot.py`

- [ ] **Step 1: Write the integration test**

`resto/tests/test_owner_report/test_owner_daily_snapshot.py`:
```python
"""Real-DB integration test for OwnerReportService.compute_snapshot.

Uses RestoPOSTestBase fixtures so we exercise a genuine POS Invoice insert/
submit and read it back through frappe.get_all — no mocks of the data layer.
Transaction rollback comes from FrappeTestCase.
"""

from datetime import date

import frappe

from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.owner_report.owner_report_service import OwnerReportService


class TestOwnerDailySnapshotIntegration(RestoPOSTestBase):
    def test_empty_branch_yields_zeroed_snapshot(self):
        """A branch with zero POS Invoices yields zeros end-to-end without
        throwing. Validates query-shape + dict-shape on real Frappe."""
        result = OwnerReportService().compute_snapshot(
            branch=self.branch,
            period_start=date(2026, 5, 29),
            period_end=date(2026, 5, 29),
        )

        self.assertEqual(result["performa"]["revenue"], 0.0)
        self.assertEqual(result["performa"]["bill_count"], 0)
        self.assertIsNone(result["performa"]["dod_pct"])  # no base data → None
        self.assertEqual(result["sales_mix"]["kategori"], [])
        self.assertEqual(result["top_menu"], [])
        self.assertFalse(result["alarm"]["void_alert"])

    def test_single_submitted_invoice_appears_in_performa(self):
        invoice = self._create_test_pos_invoice(
            qty=2, rate=50000,
            submit=True,
            branch=self.branch,
            order_type="Dine-In",
            pax=2,
        )

        result = OwnerReportService().compute_snapshot(
            branch=self.branch,
            period_start=invoice.posting_date,
            period_end=invoice.posting_date,
        )

        self.assertEqual(result["performa"]["bill_count"], 1)
        self.assertGreater(result["performa"]["revenue"], 0.0)
        self.assertEqual(result["performa"]["pax"], 2)
```

- [ ] **Step 2: Run the integration test**

```bash
/opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.test_owner_daily_snapshot 2>&1 | tail -8
```

Expected: `Ran 2 tests` → `OK`.

- [ ] **Step 3: Run the full Owner Report test suite for the final regression**

```bash
for m in test_owner_report_periods test_owner_report_service test_owner_daily_snapshot; do
  echo "=== $m ==="
  /opt/anaconda3/envs/env/bin/bench --site resto.test run-tests --app resto --module resto.tests.test_owner_report.$m 2>&1 | grep -E "Ran|OK|FAILED"
done
```

Expected: `Ran 2`, `Ran 19`, `Ran 2` — all `OK`.

- [ ] **Step 4: Manual smoke**

Open `http://resto.test:8000/app/query-report/Owner Daily Snapshot` (or your bench port), pick `Branch = _Test Branch` and the date you used in step 1. The tabular preview should render. Click "Print Owner PDF" — the PDF downloads as `owner-daily-<branch>-<date>.pdf`. Open it and confirm it renders the blueprint (header, performa, donut, top menu, alarm, payment mix).

- [ ] **Step 5: Commit**

```bash
git add resto/tests/test_owner_report/test_owner_daily_snapshot.py
git commit -m "test(owner-report): real-DB integration test for Daily Owner Snapshot"
```

---

## Final state

- Branch: `feature/owner-daily-snapshot` off `candidate` @ `3ae4422`.
- 17 commits ahead of base, all green.
- Resto Settings doctype created with 4 owner-report fields (sensible defaults).
- `OwnerReportService` covers performa, sales mix, top menu, alarm, payment mix; DoD/WoW trend wired.
- COGS reads through `RawMaterialCalculatorService` when a `POS Daily Summary` exists for (branch, posting_date); falls back to zeros otherwise without throwing.
- Script Report + JS + Jinja template + PDF endpoint all wired.
- 23 tests green (2 periods + 19 service + 2 integration).

Ready for fast-forward into `candidate` and push to origin for QA. After QA passes, Weekly + Monthly cadences clone Task 13–16 with new templates; the service is unchanged.
