import frappe
from unittest.mock import MagicMock, patch
from frappe.utils import flt
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.reporting_service import ReportingService


class TestGetEndDayReportV1(RestoPOSTestBase):
    """Test ReportingService.get_end_day_report — verifikasi logika agregasi"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = ReportingService(repo=self.mock_repo)

    def test_throws_when_posting_date_missing(self):
        """Harus throw jika posting_date tidak ada"""
        with self.assertRaises(frappe.ValidationError):
            self.service.get_end_day_report(posting_date=None, outlet="BR-001")

    def test_throws_when_outlet_missing(self):
        """Harus throw jika outlet tidak ada"""
        with self.assertRaises(frappe.ValidationError):
            self.service.get_end_day_report(posting_date="2025-01-01", outlet=None)

    def test_returns_no_invoice_message_when_empty(self):
        """Harus return message jika tidak ada invoice"""
        self.mock_repo.get_submitted_invoices.return_value = []
        result = self.service.get_end_day_report(posting_date="2025-01-01", outlet="BR-001")
        self.assertIn("message", result)

    def test_grand_total_calculation(self):
        """grand_total harus = sub_total + tax - discount"""
        self.mock_repo.get_submitted_invoices.return_value = [
            MagicMock(name="INV-001")
        ]
        self.mock_repo.get_sub_total.return_value = 100000
        self.mock_repo.get_discount_total.return_value = 10000
        self.mock_repo.get_tax_total.return_value = 11000
        self.mock_repo.get_items_by_order_type.return_value = []
        self.mock_repo.get_payments_summary.return_value = []
        self.mock_repo.get_taxes_summary.return_value = []
        self.mock_repo.get_discount_by_order_type.return_value = []
        self.mock_repo.get_discount_by_bank.return_value = []
        self.mock_repo.get_void_items.return_value = []
        self.mock_repo.get_void_bills.return_value = []

        result = self.service.get_end_day_report(posting_date="2025-01-01", outlet="BR-001")

        self.assertEqual(result["summary"]["sub_total"], 100000)
        self.assertEqual(result["summary"]["discount"], 10000)
        self.assertEqual(result["summary"]["tax"], 11000)
        self.assertEqual(result["summary"]["grand_total"], 101000)  # 100000 + 11000 - 10000

    def test_items_grouped_by_order_type(self):
        """Items harus dikelompokkan ke dine_in atau take_away"""
        self.mock_repo.get_submitted_invoices.return_value = [MagicMock(name="INV-001")]
        self.mock_repo.get_sub_total.return_value = 0
        self.mock_repo.get_discount_total.return_value = 0
        self.mock_repo.get_tax_total.return_value = 0
        self.mock_repo.get_payments_summary.return_value = []
        self.mock_repo.get_taxes_summary.return_value = []
        self.mock_repo.get_discount_by_order_type.return_value = []
        self.mock_repo.get_discount_by_bank.return_value = []
        self.mock_repo.get_void_items.return_value = []
        self.mock_repo.get_void_bills.return_value = []

        item_dine = MagicMock()
        item_dine.order_type = "Dine In"
        item_dine.item_group = "Food"
        item_dine.qty = 3
        item_dine.amount = 90000

        item_take = MagicMock()
        item_take.order_type = "Take Away"
        item_take.item_group = "Drinks"
        item_take.qty = 2
        item_take.amount = 40000

        self.mock_repo.get_items_by_order_type.return_value = [item_dine, item_take]

        result = self.service.get_end_day_report(posting_date="2025-01-01", outlet="BR-001")

        self.assertIn("Food", result["dine_in"])
        self.assertIn("Drinks", result["take_away"])
        self.assertEqual(result["dine_in"]["Food"]["qty"], 3)

    def test_response_has_required_keys(self):
        """Response harus memiliki semua key yang dibutuhkan FE"""
        self.mock_repo.get_submitted_invoices.return_value = [MagicMock(name="INV-001")]
        self.mock_repo.get_sub_total.return_value = 0
        self.mock_repo.get_discount_total.return_value = 0
        self.mock_repo.get_tax_total.return_value = 0
        self.mock_repo.get_items_by_order_type.return_value = []
        self.mock_repo.get_payments_summary.return_value = []
        self.mock_repo.get_taxes_summary.return_value = []
        self.mock_repo.get_discount_by_order_type.return_value = []
        self.mock_repo.get_discount_by_bank.return_value = []
        self.mock_repo.get_void_items.return_value = []
        self.mock_repo.get_void_bills.return_value = []

        result = self.service.get_end_day_report(posting_date="2025-01-01", outlet="BR-001")

        required_keys = [
            "posting_date", "outlet_filter", "summary",
            "dine_in", "take_away", "payments", "taxes",
            "discount_by_order_type", "discount_by_bank",
            "void_item", "void_bill"
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Key '{key}' tidak ada di response")


class TestGetEndDayReportV2(RestoPOSTestBase):
    """Test ReportingService.get_end_day_report_v2"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = ReportingService(repo=self.mock_repo)

    def test_throws_when_params_missing(self):
        """Harus throw jika posting_date atau outlet tidak ada"""
        with self.assertRaises(frappe.ValidationError):
            self.service.get_end_day_report_v2(posting_date=None, outlet=None)

    def test_returns_message_when_no_paid_invoices(self):
        """Harus return message + draft jika tidak ada paid invoice"""
        self.mock_repo.get_paid_invoices.return_value = []
        draft = MagicMock()
        draft.grand_total = 50000
        draft.order_type = "Dine In"
        draft.name = "INV-DRAFT"
        self.mock_repo.get_draft_invoices.return_value = [draft]

        result = self.service.get_end_day_report_v2(posting_date="2025-01-01", outlet="BR-001")

        self.assertIn("message", result)
        self.assertIn("draft", result)

    def test_grand_total_v2_calculation(self):
        """grand_total v2 = sub_total + tax - discount"""
        self.mock_repo.get_paid_invoices.return_value = [MagicMock(name="INV-001")]
        self.mock_repo.get_draft_invoices.return_value = []
        self.mock_repo.get_sub_total_v2.return_value = 200000
        self.mock_repo.get_discount_total_v2.return_value = 20000
        self.mock_repo.get_tax_total_v2.return_value = 22000
        self.mock_repo.get_pax_total.return_value = 5
        self.mock_repo.get_items_by_order_type_v2.return_value = []
        self.mock_repo.get_payments_summary_v2.return_value = []
        self.mock_repo.get_taxes_summary_v2.return_value = []
        self.mock_repo.get_discount_by_order_type_v2.return_value = []
        self.mock_repo.get_void_bills_v2.return_value = []
        self.mock_repo.get_void_invoices_with_items.return_value = []

        result = self.service.get_end_day_report_v2(posting_date="2025-01-01", outlet="BR-001")

        self.assertEqual(result["summary"]["grand_total"], 202000)  # 200000 + 22000 - 20000

    def test_response_v2_has_required_keys(self):
        """Response v2 harus memiliki semua key yang dibutuhkan FE"""
        self.mock_repo.get_paid_invoices.return_value = [MagicMock(name="INV-001")]
        self.mock_repo.get_draft_invoices.return_value = []
        self.mock_repo.get_sub_total_v2.return_value = 0
        self.mock_repo.get_discount_total_v2.return_value = 0
        self.mock_repo.get_tax_total_v2.return_value = 0
        self.mock_repo.get_pax_total.return_value = 0
        self.mock_repo.get_items_by_order_type_v2.return_value = []
        self.mock_repo.get_payments_summary_v2.return_value = []
        self.mock_repo.get_taxes_summary_v2.return_value = []
        self.mock_repo.get_discount_by_order_type_v2.return_value = []
        self.mock_repo.get_void_bills_v2.return_value = []
        self.mock_repo.get_void_invoices_with_items.return_value = []

        result = self.service.get_end_day_report_v2(posting_date="2025-01-01", outlet="BR-001")

        required_keys = [
            "posting_date", "outlet_filter", "outlet", "summary",
            "dine_in", "take_away", "payments", "taxes",
            "discount_by_order_type", "draft", "void_bill", "void_menu"
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Key '{key}' tidak ada di response v2")


class TestEndShift(RestoPOSTestBase):
    """Test ReportingService.end_shift — validasi logika"""

    def setUp(self):
        super().setUp()
        self.mock_repo = MagicMock()
        self.service = ReportingService(repo=self.mock_repo)

    def test_throws_when_no_invoices(self):
        """Harus throw jika tidak ada POS Invoice"""
        mock_opening = MagicMock()
        mock_opening.name = "OPEN-001"
        mock_opening.pos_profile = "PROF-001"
        mock_opening.user = "admin@test.com"
        mock_opening.company = "_Test Company"
        mock_opening.branch = "BR-001"

        self.mock_repo.get_active_opening_for_user.return_value = mock_opening
        self.mock_repo.get_paid_invoices_for_closing.return_value = []

        with self.assertRaises(frappe.ValidationError):
            self.service.end_shift(user="admin@test.com")

    def test_throws_when_no_valid_transactions_after_opening(self):
        """Harus throw jika semua invoice sebelum opening time"""
        mock_opening = MagicMock()
        mock_opening.name = "OPEN-001"
        mock_opening.pos_profile = "PROF-001"
        mock_opening.user = "admin@test.com"
        mock_opening.company = "_Test Company"
        mock_opening.branch = "BR-001"
        mock_opening.period_start_date = "2025-01-01 10:00:00"

        # Invoice dengan waktu sebelum opening
        inv = MagicMock()
        inv.name = "INV-001"
        inv.posting_date = "2025-01-01"
        inv.posting_time = "09:00:00"  # sebelum opening 10:00

        self.mock_repo.get_active_opening_for_user.return_value = mock_opening
        self.mock_repo.get_paid_invoices_for_closing.return_value = [inv]
        self.mock_repo.get_invoice_doc.return_value = MagicMock(
            grand_total=0, net_total=0, total_qty=0,
            total_taxes_and_charges=0, taxes=[], payments=[], is_return=0,
            return_against=None, customer="C", posting_date="2025-01-01"
        )

        with self.assertRaises(frappe.ValidationError):
            self.service.end_shift(user="admin@test.com")

    def test_payment_scaling(self):
        """Payment harus di-scale berdasarkan grand_total / payment_total"""
        # Test pure Python payment scaling logic
        payment_map = {}

        grand_total = 90000.0
        payment_rows = [
            MagicMock(mode_of_payment="Cash", amount=100000.0),
        ]
        original_payment_total = sum(flt(p.amount) for p in payment_rows) or 1
        scale = flt(grand_total) / original_payment_total

        for p in payment_rows:
            payment_map.setdefault(p.mode_of_payment, 0)
            payment_map[p.mode_of_payment] += flt(p.amount) * scale

        self.assertAlmostEqual(payment_map["Cash"], 90000.0, places=1)
