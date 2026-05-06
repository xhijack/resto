import frappe
from unittest.mock import patch, MagicMock, call
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.payment_service import PaymentService


class TestPaymentService(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.service = PaymentService()

    # ------------------------------------------------------------------
    # Unit tests — create_payment
    # ------------------------------------------------------------------

    def test_create_payment_appends_payment_to_invoice(self):
        """Harus append payment ke doc.payments"""
        mock_doc = MagicMock()
        mock_doc.taxes = []

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_doc.append.assert_called_once_with("payments", {
            "mode_of_payment": "Cash",
            "amount": 50000
        })

    def test_create_payment_submits_invoice(self):
        """Harus memanggil doc.submit() setelah append payment"""
        mock_doc = MagicMock()

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_doc.submit.assert_called_once()

    def test_create_payment_calls_clear_table_merged(self):
        """Harus memanggil clear_table_merged setelah submit"""
        mock_doc = MagicMock()

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged") as mock_clear:
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_clear.assert_called_once_with("INV-001")

    def test_create_payment_calls_db_commit(self):
        """Harus memanggil frappe.db.commit()"""
        mock_doc = MagicMock()

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db") as mock_db, \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_db.commit.assert_called_once()

    def test_create_payment_returns_ok_true(self):
        """Harus return ok=True dan pos_invoice name"""
        mock_doc = MagicMock()

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-001", 50000, "Cash")

        self.assertTrue(result["ok"])
        self.assertEqual(result["pos_invoice"], "INV-001")
        self.assertIn("message", result)

    # ------------------------------------------------------------------
    # Integration test
    # ------------------------------------------------------------------

    def test_create_payment_integration(self):
        """Harus submit invoice setelah payment ditambahkan"""
        invoice = self._create_test_pos_invoice(submit=False)
        self.assertEqual(invoice.docstatus, 0)

        result = self.service.create_payment(
            invoice.name,
            amount=100,
            mode_of_payment=self.mode_of_payment
        )

        self.assertTrue(result["ok"])
        updated = frappe.get_doc("POS Invoice", invoice.name)
        self.assertEqual(updated.docstatus, 1)

    # ------------------------------------------------------------------
    # Extreme variation tests — payment boundary cases
    # ------------------------------------------------------------------

    def test_create_payment_with_amount_zero_still_appends(self):
        """amount=0 → append tetap dipanggil (backend tidak validasi amount>0)"""
        mock_doc = MagicMock()
        mock_doc.taxes = []

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 0, "Cash")

        mock_doc.append.assert_called_once_with("payments", {
            "mode_of_payment": "Cash",
            "amount": 0
        })

    def test_create_payment_with_very_large_amount_no_crash(self):
        """amount=99999999 → tidak crash, submit dipanggil normal"""
        mock_doc = MagicMock()
        mock_doc.taxes = []

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-001", 99999999, "Transfer")

        mock_doc.submit.assert_called_once()
        self.assertTrue(result["ok"])

    def test_create_payment_result_includes_pos_invoice_name(self):
        """result['pos_invoice'] harus sama dengan invoice name yang dikirim"""
        mock_doc = MagicMock()
        mock_doc.taxes = []

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-SPECIFIC-001", 50000, "Cash")

        self.assertEqual(result["pos_invoice"], "INV-SPECIFIC-001")

    def test_create_payment_taxes_not_modified(self):
        """create_payment tidak boleh menyentuh doc.taxes"""
        mock_doc = MagicMock()
        original_taxes = [MagicMock(), MagicMock()]
        mock_doc.taxes = list(original_taxes)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        self.assertEqual(len(mock_doc.taxes), len(original_taxes))
