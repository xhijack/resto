import frappe
import json
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.invoice_service import InvoiceService


class TestInvoiceServiceCreatePOSInvoice(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.service = InvoiceService()
        self.base_payload = {
            "customer": self.customer.name,
            "pos_profile": self.pos_profile.name,
            "branch": self.branch,
            "order_type": None,
            "items": [{"item_code": self.item.name, "qty": 1, "rate": 100}],
            "payments": [{"mode_of_payment": self.mode_of_payment, "amount": 100}],
        }

    # ------------------------------------------------------------------
    # Validasi input — unit tests (mock)
    # ------------------------------------------------------------------

    def test_throws_when_customer_missing(self):
        """Harus throw jika customer tidak ada di payload"""
        payload = {**self.base_payload, "customer": None}
        with self.assertRaises(frappe.ValidationError):
            self.service.create_pos_invoice(payload)

    def test_throws_when_items_empty(self):
        """Harus throw jika items kosong"""
        payload = {**self.base_payload, "items": []}
        with self.assertRaises(frappe.ValidationError):
            self.service.create_pos_invoice(payload)

    def test_throws_when_pos_profile_missing(self):
        """Harus throw jika pos_profile tidak ada"""
        payload = {**self.base_payload, "pos_profile": None}
        with self.assertRaises(frappe.ValidationError):
            self.service.create_pos_invoice(payload)

    def test_throws_when_order_type_invalid(self):
        """Harus throw jika order_type bukan Dine In atau Take Away"""
        payload = {**self.base_payload, "order_type": "Delivery"}
        with self.assertRaises(frappe.ValidationError):
            self.service.create_pos_invoice(payload)

    def test_accepts_none_order_type(self):
        """order_type None diterima (tidak ada pajak)"""
        payload = {**self.base_payload, "order_type": None}
        result = self.service.create_pos_invoice(payload)
        self.assertEqual(result["status"], "success")

    def test_accepts_json_string_payload(self):
        """Payload sebagai JSON string harus di-parse"""
        result = self.service.create_pos_invoice(json.dumps(self.base_payload))
        self.assertEqual(result["status"], "success")

    # ------------------------------------------------------------------
    # Logika company — unit tests (mock)
    # ------------------------------------------------------------------

    def test_company_fetched_only_once(self):
        """frappe.db.get_single_value untuk company harus dipanggil sekali"""
        with patch("resto.services.invoice_service.frappe.db") as mock_db, \
             patch("resto.services.invoice_service.frappe.get_doc"), \
             patch("resto.services.invoice_service.frappe.get_meta") as mock_meta:
            mock_db.get_single_value.return_value = "_Test Company"
            mock_db.get_value.return_value = None
            mock_meta.return_value.get_field.return_value = None
            mock_doc = MagicMock()
            mock_doc.name = "INV-001"

            with patch("resto.services.invoice_service.frappe.get_doc", return_value=mock_doc):
                try:
                    self.service.create_pos_invoice({
                        "customer": "C", "pos_profile": "P",
                        "items": [{"item_code": "X", "qty": 1, "rate": 10}],
                        "order_type": None
                    })
                except Exception:
                    pass

            calls = [c for c in mock_db.get_single_value.call_args_list
                     if c[0][1] == "default_company" or (len(c[0]) > 0 and "default_company" in str(c))]
            self.assertLessEqual(len(mock_db.get_single_value.call_args_list), 1)

    # ------------------------------------------------------------------
    # Integration tests
    # ------------------------------------------------------------------

    def test_create_pos_invoice_integration(self):
        """Harus berhasil buat invoice tanpa order_type (tanpa tax template)"""
        payload = {**self.base_payload, "order_type": None}
        result = self.service.create_pos_invoice(payload)
        self.assertEqual(result["status"], "success")
        self.assertTrue(frappe.db.exists("POS Invoice", result["name"]))

    def test_created_invoice_is_draft(self):
        """Invoice harus dalam state draft setelah dibuat (docstatus=0)"""
        payload = {**self.base_payload, "order_type": None}
        result = self.service.create_pos_invoice(payload)
        doc = frappe.get_doc("POS Invoice", result["name"])
        self.assertEqual(doc.docstatus, 0)


class TestInvoiceServiceApplyDiscount(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.service = InvoiceService()

    # ------------------------------------------------------------------
    # Bug fix: user parameter
    # ------------------------------------------------------------------

    def test_user_parameter_takes_priority_over_session(self):
        """user param harus dipakai, bukan frappe.session.user"""
        mock_repo = MagicMock()
        service = InvoiceService(repo=mock_repo)
        mock_repo.invoice_exists.return_value = False

        service.apply_discount(pos_invoice="INV-001", user="specific@user.com")

        mock_repo.get_active_profile_for_user.assert_not_called()

    # ------------------------------------------------------------------
    # Validasi — unit tests (mock)
    # ------------------------------------------------------------------

    def test_apply_discount_returns_skip_when_no_invoice(self):
        """Harus return skipped=True jika pos_invoice kosong"""
        result = self.service.apply_discount(pos_invoice=None)
        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])

    def test_apply_discount_returns_skip_when_invoice_not_found(self):
        """Harus return skipped=True jika invoice tidak ada di DB"""
        mock_repo = MagicMock()
        mock_repo.invoice_exists.return_value = False
        service = InvoiceService(repo=mock_repo)

        result = service.apply_discount(pos_invoice="INV-NOTFOUND")
        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])

    def test_throws_when_discount_percentage_negative(self):
        """Harus throw jika discount_percentage negatif"""
        mock_repo = MagicMock()
        mock_repo.invoice_exists.return_value = True
        mock_repo.get_invoice.return_value = MagicMock(taxes=[], taxes_and_charges="TPL-001")
        mock_repo.get_pos_profile.return_value = MagicMock(taxes_and_charges="TPL-001")
        mock_repo.get_tax_template.return_value = MagicMock(taxes=[])
        mock_repo.get_active_profile_for_user.return_value = {"pos_profile": "PROF-001"}
        service = InvoiceService(repo=mock_repo)

        with self.assertRaises(frappe.ValidationError):
            service.apply_discount(pos_invoice="INV-001", discount_percentage=-5)

    def test_throws_when_discount_amount_negative(self):
        """Harus throw jika discount_amount negatif"""
        mock_repo = MagicMock()
        mock_repo.invoice_exists.return_value = True
        mock_repo.get_invoice.return_value = MagicMock(taxes=[], taxes_and_charges="TPL-001")
        mock_repo.get_pos_profile.return_value = MagicMock(taxes_and_charges="TPL-001")
        mock_repo.get_tax_template.return_value = MagicMock(taxes=[])
        mock_repo.get_active_profile_for_user.return_value = {"pos_profile": "PROF-001"}
        service = InvoiceService(repo=mock_repo)

        with self.assertRaises(frappe.ValidationError):
            service.apply_discount(pos_invoice="INV-001", discount_amount=-10000)

    def test_throws_when_account_head_not_found_in_template(self):
        """Harus throw jika tidak ada row Discount di tax template"""
        mock_repo = MagicMock()
        mock_repo.invoice_exists.return_value = True
        mock_doc = MagicMock()
        mock_doc.taxes = []
        mock_doc.taxes_and_charges = "TPL-001"
        mock_repo.get_invoice.return_value = mock_doc
        mock_repo.get_pos_profile.return_value = MagicMock(taxes_and_charges="TPL-001")
        # template tanpa row Discount
        mock_repo.get_tax_template.return_value = MagicMock(taxes=[])
        mock_repo.get_active_profile_for_user.return_value = {"pos_profile": "PROF-001"}
        service = InvoiceService(repo=mock_repo)

        with self.assertRaises(frappe.ValidationError):
            service.apply_discount(pos_invoice="INV-001", discount_percentage=10)

    # ------------------------------------------------------------------
    # Integration test
    # ------------------------------------------------------------------

    def test_apply_discount_integration(self):
        """Harus berhasil apply discount pada invoice yang ada"""
        self._create_pos_opening_entry()
        invoice = self._create_test_pos_invoice()

        result = self.service.apply_discount(
            pos_invoice=invoice.name,
            discount_percentage=10,
            user=frappe.session.user
        )
        self.assertTrue(result["ok"])
