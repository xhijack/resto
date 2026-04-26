import frappe
from unittest.mock import patch
from frappe.tests.utils import FrappeTestCase
from resto.repositories.menu_repository import MenuRepository


class TestMenuRepository(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self.repo = MenuRepository()

    def tearDown(self):
        frappe.set_user("Guest")
        super().tearDown()

    # ------------------------------------------------------------------
    # get_all_branches — unit tests
    # ------------------------------------------------------------------

    def test_get_all_branches_calls_frappe_with_correct_args(self):
        """Repository harus memanggil frappe.get_all dengan doctype dan fields yang benar"""
        expected = [{"name": "Branch-001", "branch": "Cabang Utama"}]
        with patch("resto.repositories.menu_repository.frappe.get_all", return_value=expected) as mock_get_all:
            result = self.repo.get_all_branches()
            mock_get_all.assert_called_once_with("Branch", fields=["name", "branch"])
            self.assertEqual(result, expected)

    def test_get_all_branches_returns_empty_when_no_branches(self):
        """Harus return list kosong jika tidak ada Branch"""
        with patch("resto.repositories.menu_repository.frappe.get_all", return_value=[]):
            result = self.repo.get_all_branches()
            self.assertEqual(result, [])

    def test_get_all_branches_returns_all_items_from_frappe(self):
        """Harus return semua data yang dikembalikan frappe tanpa modifikasi"""
        mock_data = [
            {"name": "Branch-001", "branch": "Cabang A"},
            {"name": "Branch-002", "branch": "Cabang B"},
            {"name": "Branch-003", "branch": "Cabang C"},
        ]
        with patch("resto.repositories.menu_repository.frappe.get_all", return_value=mock_data):
            result = self.repo.get_all_branches()
            self.assertEqual(len(result), 3)
            self.assertEqual(result, mock_data)

    # ------------------------------------------------------------------
    # get_all_branches — integration tests
    # ------------------------------------------------------------------

    def test_get_all_branches_integration_returns_list(self):
        """Return value harus berupa list"""
        result = self.repo.get_all_branches()
        self.assertIsInstance(result, list)

    def test_get_all_branches_integration_contains_created_branch(self):
        """Branch yang baru dibuat harus muncul di hasil"""
        branch_name = "_Test MenuRepo Branch"
        if not frappe.db.exists("Branch", branch_name):
            frappe.get_doc({
                "doctype": "Branch",
                "branch": branch_name
            }).insert(ignore_permissions=True)

        result = self.repo.get_all_branches()
        names = [r["name"] for r in result]
        self.assertIn(branch_name, names)

    def test_get_all_branches_integration_result_has_correct_fields(self):
        """Setiap item harus punya field 'name' dan 'branch'"""
        result = self.repo.get_all_branches()
        if result:
            for item in result:
                self.assertIn("name", item)
                self.assertIn("branch", item)

    # ------------------------------------------------------------------
    # get_company_name — unit tests
    # ------------------------------------------------------------------

    def test_get_company_name_returns_list(self):
        """Harus return list"""
        mock_data = [frappe._dict({"company_name": "PT Test"})]
        with patch("resto.repositories.menu_repository.frappe.get_all", return_value=mock_data):
            result = self.repo.get_company_name()
        self.assertIsInstance(result, list)

    def test_get_company_name_calls_with_correct_args(self):
        """Harus query Company dengan fields company_name, limit 1, order creation asc"""
        with patch("resto.repositories.menu_repository.frappe.get_all", return_value=[]) as mock_get_all:
            self.repo.get_company_name()
            mock_get_all.assert_called_once_with(
                "Company",
                fields=["company_name"],
                limit_page_length=1,
                order_by="creation asc"
            )

    def test_get_company_name_returns_empty_when_no_company(self):
        """Harus return [] jika tidak ada company"""
        with patch("resto.repositories.menu_repository.frappe.get_all", return_value=[]):
            result = self.repo.get_company_name()
        self.assertEqual(result, [])

    # ------------------------------------------------------------------
    # get_company_name — integration test
    # ------------------------------------------------------------------

    def test_get_company_name_integration_returns_company(self):
        """Harus return minimal satu company dari DB"""
        result = self.repo.get_company_name()
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)
        self.assertIn("company_name", result[0])
