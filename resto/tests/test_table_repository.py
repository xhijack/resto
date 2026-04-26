import frappe
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.repositories.table_repository import TableRepository


class TestTableRepository(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.repo = TableRepository()

    # ------------------------------------------------------------------
    # Unit tests — get_table
    # ------------------------------------------------------------------

    def test_get_table_calls_frappe_get_doc(self):
        """Harus memanggil frappe.get_doc dengan doctype Table"""
        mock_doc = MagicMock()
        with patch("resto.repositories.table_repository.frappe.get_doc", return_value=mock_doc) as mock:
            result = self.repo.get_table("TBL-001")
            mock.assert_called_once_with("Table", "TBL-001")
            self.assertEqual(result, mock_doc)

    # ------------------------------------------------------------------
    # Unit tests — save_table
    # ------------------------------------------------------------------

    def test_save_table_calls_save_and_commit(self):
        """Harus memanggil doc.save dan frappe.db.commit"""
        mock_doc = MagicMock()
        with patch("resto.repositories.table_repository.frappe.db") as mock_db:
            self.repo.save_table(mock_doc)
            mock_doc.save.assert_called_once_with(ignore_permissions=True)
            mock_db.commit.assert_called_once()

    # ------------------------------------------------------------------
    # Unit tests — get_all_tables
    # ------------------------------------------------------------------

    def test_get_all_tables_calls_frappe_get_all(self):
        """Harus memanggil frappe.get_all dengan Table"""
        with patch("resto.repositories.table_repository.frappe.get_all", return_value=[]) as mock:
            self.repo.get_all_tables()
            mock.assert_called_once()
            call_args = mock.call_args
            self.assertEqual(call_args[0][0], "Table")

    def test_get_all_tables_returns_list(self):
        """Harus return list"""
        with patch("resto.repositories.table_repository.frappe.get_all", return_value=[]):
            result = self.repo.get_all_tables()
            self.assertIsInstance(result, list)

    def test_get_all_tables_orders_by_table_name_asc(self):
        """Harus order_by table_name asc"""
        with patch("resto.repositories.table_repository.frappe.get_all", return_value=[]) as mock:
            self.repo.get_all_tables()
            kwargs = mock.call_args[1]
            self.assertEqual(kwargs.get("order_by"), "table_name asc")

    # ------------------------------------------------------------------
    # Integration tests
    # ------------------------------------------------------------------

    def _get_or_create_table(self, table_name):
        if frappe.db.exists("Table", table_name):
            return frappe.get_doc("Table", table_name)
        return frappe.get_doc({
            "doctype": "Table", "table_name": table_name, "branch": self.branch
        }).insert(ignore_permissions=True)

    def test_get_table_integration(self):
        """Harus return Table doc yang benar"""
        table = self._get_or_create_table("_Test Repo Table")
        result = self.repo.get_table(table.name)
        self.assertEqual(result.name, table.name)

    def test_save_table_integration(self):
        """Harus simpan perubahan ke database"""
        table = self._get_or_create_table("_Test Save Table")
        table.status = "Terisi"
        self.repo.save_table(table)
        reloaded = frappe.get_doc("Table", table.name)
        self.assertEqual(reloaded.status, "Terisi")

    def test_get_all_tables_integration_contains_created_table(self):
        """Harus memuat table yang baru dibuat"""
        table = self._get_or_create_table("_Test GetAll Table")
        result = self.repo.get_all_tables()
        names = [t.name for t in result]
        self.assertIn(table.name, names)
