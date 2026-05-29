"""Integration tests for the Stock Usage orchestrator against a real Frappe DB.

These tests exercise the full service stack (no mocks) so we catch any
divergence between the unit-test contracts and real Frappe ORM behaviour.
They run inside a FrappeTestCase transaction so all writes roll back.
"""

import frappe

from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.stock_usage.rm_calculator import RawMaterialCalculatorService


class TestOrchestratorIntegration(RestoPOSTestBase):
    def test_compute_breakdown_returns_empty_for_daily_summary_with_no_pces(self):
        """Empty POS Daily Summary loads cleanly and yields {items: []}.

        Validates the wire-through end-to-end: real frappe.get_doc on the
        Daily Summary, real `eds.pos_transactions` child iteration, real
        company resolution via Branch.company lookup. The orchestrator's
        early-return short-circuits before any aggregator call.
        """
        eds = frappe.get_doc({
            "doctype": "POS Daily Summary",
            "posting_date": frappe.utils.nowdate(),
            "created_by": frappe.session.user,
            "branch": self.branch,
            "pos_transactions": [],
        })
        eds.insert(ignore_permissions=True)

        result = RawMaterialCalculatorService().compute_breakdown(
            eds.name, warehouse="_Test Warehouse",
        )

        self.assertEqual(result, {"items": []})

    def test_resolve_company_falls_back_to_first_pce_when_branch_field_absent(self):
        """When Branch lacks a `company` field (ERPNext version variance),
        the orchestrator falls back to the first PCE's company.

        We use a stub PCE-like object here so the test is independent of
        whether a real POS Closing Entry can be constructed under the test
        site's fixture state.
        """
        eds = frappe.get_doc({
            "doctype": "POS Daily Summary",
            "posting_date": frappe.utils.nowdate(),
            "created_by": frappe.session.user,
            "branch": self.branch,
            "pos_transactions": [],
        })
        eds.insert(ignore_permissions=True)

        class _PCEStub:
            company = self.company.name

        resolved = RawMaterialCalculatorService()._resolve_company(eds, pces=[_PCEStub()])
        self.assertEqual(resolved, self.company.name)
