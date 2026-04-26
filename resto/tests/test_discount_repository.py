import frappe
from unittest.mock import patch, MagicMock
from frappe.tests.utils import FrappeTestCase
from resto.repositories.discount_repository import DiscountRepository


class TestDiscountRepository(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.repo = DiscountRepository()

    def tearDown(self):
        frappe.set_user("Guest")
        super().tearDown()

    # ------------------------------------------------------------------
    # Unit tests (mock)
    # ------------------------------------------------------------------

    def _fdict(self, data):
        """Helper: buat frappe._dict agar attribute access bisa dipakai seperti di Frappe asli"""
        return frappe._dict(data)

    def test_returns_empty_list_when_no_discounts(self):
        """Harus return [] jika tidak ada Discount doctype"""
        with patch("resto.repositories.discount_repository.frappe.get_all", return_value=[]):
            result = self.repo.get_discounts_with_options()
            self.assertEqual(result, [])

    def test_result_contains_required_keys(self):
        """Setiap item hasil harus punya key: name, description, discount_options, menu_category"""
        mock_option = MagicMock(
            label="10%", discount_type="Percentage", value=10,
            min_sales_price=0, max_discount=0, start_date=None, end_date=None
        )
        mock_category = MagicMock(menu_name="Makanan")
        mock_doc = MagicMock(description="Diskon Reguler", discount_options=[mock_option], menu_category=[mock_category])
        mock_doc.configure_mock(**{"name": "DISC-001"})

        with patch("resto.repositories.discount_repository.frappe.get_all", return_value=[self._fdict({"name": "DISC-001", "description": "Diskon Reguler"})]), \
             patch("resto.repositories.discount_repository.frappe.get_doc", return_value=mock_doc):
            result = self.repo.get_discounts_with_options()

        self.assertEqual(len(result), 1)
        item = result[0]
        self.assertIn("name", item)
        self.assertIn("description", item)
        self.assertIn("discount_options", item)
        self.assertIn("menu_category", item)

    def test_discount_options_fields_are_mapped_correctly(self):
        """Field discount_options harus dipetakan dengan benar dari child table"""
        mock_option = MagicMock(
            label="Diskon Member", discount_type="Percentage", value=15,
            min_sales_price=50000, max_discount=100000,
            start_date="2026-01-01", end_date="2026-12-31"
        )
        mock_doc = MagicMock(description="Member", discount_options=[mock_option], menu_category=[])
        mock_doc.configure_mock(**{"name": "DISC-001"})

        with patch("resto.repositories.discount_repository.frappe.get_all", return_value=[self._fdict({"name": "DISC-001", "description": "Member"})]), \
             patch("resto.repositories.discount_repository.frappe.get_doc", return_value=mock_doc):
            result = self.repo.get_discounts_with_options()

        opt = result[0]["discount_options"][0]
        self.assertEqual(opt["label"], "Diskon Member")
        self.assertEqual(opt["discount_type"], "Percentage")
        self.assertEqual(opt["value"], 15)
        self.assertEqual(opt["min_sales_price"], 50000)
        self.assertEqual(opt["max_discount"], 100000)
        self.assertEqual(opt["start_date"], "2026-01-01")
        self.assertEqual(opt["end_date"], "2026-12-31")

    def test_menu_category_fields_are_mapped_correctly(self):
        """Field menu_category harus dipetakan dengan benar dari child table"""
        mock_category = MagicMock(menu_name="Minuman")
        mock_doc = MagicMock(description="Test", discount_options=[], menu_category=[mock_category])
        mock_doc.configure_mock(**{"name": "DISC-001"})

        with patch("resto.repositories.discount_repository.frappe.get_all", return_value=[self._fdict({"name": "DISC-001", "description": "Test"})]), \
             patch("resto.repositories.discount_repository.frappe.get_doc", return_value=mock_doc):
            result = self.repo.get_discounts_with_options()

        cat = result[0]["menu_category"][0]
        self.assertEqual(cat["menu_name"], "Minuman")

    def test_multiple_discounts_are_all_returned(self):
        """Semua Discount harus diproses, bukan hanya yang pertama"""
        mock_doc_a = MagicMock(description="A", discount_options=[], menu_category=[])
        mock_doc_a.configure_mock(**{"name": "DISC-A"})
        mock_doc_b = MagicMock(description="B", discount_options=[], menu_category=[])
        mock_doc_b.configure_mock(**{"name": "DISC-B"})

        def fake_get_doc(doctype, name):
            return mock_doc_a if name == "DISC-A" else mock_doc_b

        with patch("resto.repositories.discount_repository.frappe.get_all", return_value=[
            self._fdict({"name": "DISC-A", "description": "A"}),
            self._fdict({"name": "DISC-B", "description": "B"}),
        ]), patch("resto.repositories.discount_repository.frappe.get_doc", side_effect=fake_get_doc):
            result = self.repo.get_discounts_with_options()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "DISC-A")
        self.assertEqual(result[1]["name"], "DISC-B")
