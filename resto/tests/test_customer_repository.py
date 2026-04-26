import frappe
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase
from resto.repositories.customer_repository import CustomerRepository


class TestCustomerRepository(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.repo = CustomerRepository()

    def tearDown(self):
        frappe.set_user("Guest")
        super().tearDown()

    # ------------------------------------------------------------------
    # Unit tests (mock)
    # ------------------------------------------------------------------

    def test_create_customer_calls_get_doc_with_correct_fields(self):
        """Harus membangun doc dengan fields yang benar"""
        mock_doc = MagicMock()
        mock_doc.as_dict.return_value = {"name": "CUST-001", "customer_name": "John"}

        with patch("resto.repositories.customer_repository.frappe.get_doc", return_value=mock_doc) as mock_get_doc:
            self.repo.create_customer("John")
            args = mock_get_doc.call_args[0][0]
            self.assertEqual(args["doctype"], "Customer")
            self.assertEqual(args["customer_name"], "John")
            self.assertEqual(args["customer_type"], "Company")

    def test_create_customer_passes_mobile_no(self):
        """Harus meneruskan mobile_no ke doc"""
        mock_doc = MagicMock()
        mock_doc.as_dict.return_value = {}

        with patch("resto.repositories.customer_repository.frappe.get_doc", return_value=mock_doc) as mock_get_doc:
            self.repo.create_customer("Jane", mobile_no="08123456789")
            args = mock_get_doc.call_args[0][0]
            self.assertEqual(args["mobile_no"], "08123456789")
            self.assertEqual(args["mobile_number"], "08123456789")

    def test_create_customer_mobile_no_none_by_default(self):
        """mobile_no harus None jika tidak diberikan"""
        mock_doc = MagicMock()
        mock_doc.as_dict.return_value = {}

        with patch("resto.repositories.customer_repository.frappe.get_doc", return_value=mock_doc) as mock_get_doc:
            self.repo.create_customer("NoPhone")
            args = mock_get_doc.call_args[0][0]
            self.assertIsNone(args["mobile_no"])

    def test_create_customer_calls_insert(self):
        """Harus memanggil insert pada doc"""
        mock_doc = MagicMock()
        mock_doc.as_dict.return_value = {}

        with patch("resto.repositories.customer_repository.frappe.get_doc", return_value=mock_doc):
            self.repo.create_customer("Test")
            mock_doc.insert.assert_called_once_with(ignore_permissions=True)

    def test_create_customer_returns_dict(self):
        """Harus return as_dict() dari doc"""
        expected = {"name": "CUST-001", "customer_name": "Test"}
        mock_doc = MagicMock()
        mock_doc.as_dict.return_value = expected

        with patch("resto.repositories.customer_repository.frappe.get_doc", return_value=mock_doc):
            result = self.repo.create_customer("Test")
        self.assertEqual(result, expected)

    # ------------------------------------------------------------------
    # Integration test
    # ------------------------------------------------------------------

    def test_create_customer_integration(self):
        """Harus membuat Customer di database"""
        customer_name = "_Test Resto Customer TDD"
        if frappe.db.exists("Customer", customer_name):
            frappe.delete_doc("Customer", customer_name, ignore_permissions=True)

        result = self.repo.create_customer(customer_name, mobile_no="081234")

        self.assertIsNotNone(result)
        self.assertTrue(frappe.db.exists("Customer", customer_name))
