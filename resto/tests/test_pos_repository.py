import frappe
from unittest.mock import patch
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.repositories.pos_repository import POSRepository


class TestPOSRepository(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.repo = POSRepository()

    # ------------------------------------------------------------------
    # Unit tests — get_pos_profiles_for_user
    # ------------------------------------------------------------------

    def test_get_pos_profiles_returns_empty_when_user_has_none(self):
        """Harus return [] jika user tidak punya POS Profile"""
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[]):
            result = self.repo.get_pos_profiles_for_user("nobody@test.com")
            self.assertEqual(result, [])

    def test_get_pos_profiles_returns_profile_names(self):
        """Harus return list nama POS Profile untuk user"""
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=["PROF-001", "PROF-002"]):
            result = self.repo.get_pos_profiles_for_user("user@test.com")
            self.assertEqual(result, ["PROF-001", "PROF-002"])

    # ------------------------------------------------------------------
    # Unit tests — find_open_pos_entry
    # ------------------------------------------------------------------

    def test_find_open_pos_entry_returns_none_when_not_found(self):
        """Harus return None jika tidak ada entry yang Open"""
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[]):
            result = self.repo.find_open_pos_entry(["PROF-001"])
            self.assertIsNone(result)

    def test_find_open_pos_entry_returns_first_result(self):
        """Harus return item pertama dari hasil query"""
        entry = frappe._dict({"name": "POS-OPEN-001", "pos_profile": "PROF-001", "user": "u@t.com", "branch": "A"})
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[entry]):
            result = self.repo.find_open_pos_entry(["PROF-001"])
            self.assertEqual(result["name"], "POS-OPEN-001")

    # ------------------------------------------------------------------
    # Unit tests — find_open_pos_opening
    # ------------------------------------------------------------------

    def test_find_open_pos_opening_returns_none_when_not_found(self):
        """Harus return None jika tidak ada POS Opening yang Open"""
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[]):
            result = self.repo.find_open_pos_opening(["PROF-001"])
            self.assertIsNone(result)

    def test_find_open_pos_opening_returns_correct_fields(self):
        """Harus return fields: name, pos_profile, branch, period_start_date"""
        entry = frappe._dict({
            "name": "POS-OPEN-001", "pos_profile": "PROF-001",
            "branch": "Cabang A", "period_start_date": "2026-04-26 08:00:00"
        })
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[entry]):
            result = self.repo.find_open_pos_opening(["PROF-001"])
            self.assertIn("name", result)
            self.assertIn("pos_profile", result)
            self.assertIn("branch", result)
            self.assertIn("period_start_date", result)

    # ------------------------------------------------------------------
    # Integration test
    # ------------------------------------------------------------------

    def test_find_open_pos_entry_integration(self):
        """Harus return entry setelah POS dibuka"""
        self._create_pos_opening_entry()
        profiles = self.repo.get_pos_profiles_for_user(frappe.session.user)
        self.assertTrue(len(profiles) > 0)

        result = self.repo.find_open_pos_entry(profiles)
        self.assertIsNotNone(result)
        self.assertEqual(result["pos_profile"], self.pos_profile.name)

    # ------------------------------------------------------------------
    # Unit tests — has_pending_end_day & has_today_opening
    # ------------------------------------------------------------------

    def test_has_pending_end_day_returns_false_when_none(self):
        """Harus return False jika tidak ada POS open dari hari sebelumnya"""
        with patch("resto.repositories.pos_repository.frappe.db.exists", return_value=None):
            result = self.repo.has_pending_end_day(["PROF-001"], "2026-04-26")
        self.assertFalse(result)

    def test_has_pending_end_day_returns_true_when_found(self):
        """Harus return True jika ada POS open dari hari sebelumnya"""
        with patch("resto.repositories.pos_repository.frappe.db.exists", return_value="POS-OPEN-001"):
            result = self.repo.has_pending_end_day(["PROF-001"], "2026-04-26")
        self.assertTrue(result)

    def test_has_today_opening_returns_false_when_none(self):
        """Harus return False jika tidak ada POS open hari ini"""
        with patch("resto.repositories.pos_repository.frappe.db.exists", return_value=None):
            result = self.repo.has_today_opening(["PROF-001"], "2026-04-26")
        self.assertFalse(result)

    def test_has_today_opening_returns_true_when_found(self):
        """Harus return True jika ada POS open hari ini"""
        with patch("resto.repositories.pos_repository.frappe.db.exists", return_value="POS-OPEN-001"):
            result = self.repo.has_today_opening(["PROF-001"], "2026-04-26")
        self.assertTrue(result)
