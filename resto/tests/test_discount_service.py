import frappe
from unittest.mock import patch, MagicMock, PropertyMock
from frappe.tests.utils import FrappeTestCase
from resto.services.discount_service import DiscountService
from resto.tests.resto_pos_test_base import RestoPOSTestBase


class TestDiscountService(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.service = DiscountService()

    # ------------------------------------------------------------------
    # Unit tests — remove_discount
    # ------------------------------------------------------------------

    def test_remove_discount_returns_ok_false_when_no_discount_row(self):
        """Harus return ok=False jika tidak ada tax row Discount"""
        mock_doc = MagicMock()
        mock_doc.taxes = []

        with patch("resto.services.discount_service.frappe.get_doc", return_value=mock_doc):
            result = self.service.remove_discount("INV-001")

        self.assertFalse(result["ok"])
        self.assertIn("message", result)

    def test_remove_discount_removes_tax_row_and_saves(self):
        """Harus hapus tax row Discount dan save doc"""
        mock_tax = MagicMock()
        mock_tax.description = "Discount"
        mock_doc = MagicMock()
        mock_doc.taxes = [mock_tax]

        with patch("resto.services.discount_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.discount_service.frappe.db"):
            result = self.service.remove_discount("INV-001")

        mock_doc.remove.assert_called_once_with(mock_tax)
        mock_doc.save.assert_called_once()
        self.assertTrue(result["ok"])

    def test_remove_discount_only_removes_discount_description(self):
        """Hanya hapus row dengan description 'Discount', bukan tax lainnya"""
        mock_tax_other = MagicMock()
        mock_tax_other.description = "PPN 11%"
        mock_doc = MagicMock()
        mock_doc.taxes = [mock_tax_other]

        with patch("resto.services.discount_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.discount_service.frappe.db"):
            result = self.service.remove_discount("INV-001")

        mock_doc.remove.assert_not_called()
        self.assertFalse(result["ok"])

    def test_remove_discount_returns_pos_invoice_name_on_success(self):
        """Response harus menyertakan nama pos_invoice"""
        mock_tax = MagicMock()
        mock_tax.description = "Discount"
        mock_doc = MagicMock()
        mock_doc.taxes = [mock_tax]

        with patch("resto.services.discount_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.discount_service.frappe.db"):
            result = self.service.remove_discount("INV-TEST-001")

        self.assertEqual(result["pos_invoice"], "INV-TEST-001")

    def test_remove_discount_calls_db_commit(self):
        """Harus memanggil frappe.db.commit() setelah save"""
        mock_tax = MagicMock()
        mock_tax.description = "Discount"
        mock_doc = MagicMock()
        mock_doc.taxes = [mock_tax]

        with patch("resto.services.discount_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.discount_service.frappe.db") as mock_db:
            self.service.remove_discount("INV-001")

        mock_db.commit.assert_called_once()

    # ------------------------------------------------------------------
    # Integration test
    # ------------------------------------------------------------------

    def test_remove_discount_integration_no_discount(self):
        """Harus return ok=False pada invoice tanpa row Discount"""
        invoice = self._create_test_pos_invoice()
        result = self.service.remove_discount(invoice.name)
        self.assertFalse(result["ok"])
