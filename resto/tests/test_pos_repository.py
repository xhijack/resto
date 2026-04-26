import frappe
from unittest.mock import patch
from frappe.tests.utils import FrappeTestCase
from resto.repositories.pos_repository import POSRepository
from resto.tests.resto_pos_test_base import RestoPOSTestBase


class TestPOSRepository(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.repo = POSRepository()

    # ------------------------------------------------------------------
    # Unit tests (mock) — get_active_pos_profile_for_user
    # ------------------------------------------------------------------

    def test_get_active_pos_profile_throws_when_user_has_no_profile(self):
        """Harus throw jika user tidak punya POS Profile"""
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[]), \
             patch("resto.repositories.pos_repository.frappe.throw", side_effect=frappe.ValidationError("no profile")):
            with self.assertRaises(frappe.ValidationError):
                self.repo.get_active_pos_profile_for_user("user@test.com")

    def test_get_active_pos_profile_throws_when_no_open_entry(self):
        """Harus throw jika tidak ada POS Opening Entry yang Open"""
        def fake_get_all(doctype, **kwargs):
            if doctype == "POS Profile User":
                return ["PROF-001"]
            return []

        with patch("resto.repositories.pos_repository.frappe.get_all", side_effect=fake_get_all), \
             patch("resto.repositories.pos_repository.frappe.throw", side_effect=frappe.ValidationError("not open")):
            with self.assertRaises(frappe.ValidationError):
                self.repo.get_active_pos_profile_for_user("user@test.com")

    def test_get_active_pos_profile_returns_first_open_entry(self):
        """Harus return opening entry pertama yang Open"""
        expected = {"name": "POS-OPEN-001", "pos_profile": "PROF-001", "user": "user@test.com", "branch": "Cabang A"}

        def fake_get_all(doctype, **kwargs):
            if doctype == "POS Profile User":
                return ["PROF-001"]
            return [expected]

        with patch("resto.repositories.pos_repository.frappe.get_all", side_effect=fake_get_all):
            result = self.repo.get_active_pos_profile_for_user("user@test.com")

        self.assertEqual(result, expected)

    # ------------------------------------------------------------------
    # Unit tests (mock) — get_active_pos_opening
    # ------------------------------------------------------------------

    def test_get_active_pos_opening_throws_when_user_has_no_profile(self):
        """Harus throw jika user tidak punya POS Profile"""
        with patch("resto.repositories.pos_repository.frappe.get_all", return_value=[]), \
             patch("resto.repositories.pos_repository.frappe.throw", side_effect=frappe.ValidationError("no profile")):
            with self.assertRaises(frappe.ValidationError):
                self.repo.get_active_pos_opening("user@test.com")

    def test_get_active_pos_opening_throws_when_no_open_entry(self):
        """Harus throw jika tidak ada POS Opening Entry yang Open"""
        def fake_get_all(doctype, **kwargs):
            if doctype == "POS Profile User":
                return ["PROF-001"]
            return []

        with patch("resto.repositories.pos_repository.frappe.get_all", side_effect=fake_get_all), \
             patch("resto.repositories.pos_repository.frappe.throw", side_effect=frappe.ValidationError("not open")):
            with self.assertRaises(frappe.ValidationError):
                self.repo.get_active_pos_opening("user@test.com")

    def test_get_active_pos_opening_returns_correct_fields(self):
        """Harus return fields: name, pos_profile, branch, period_start_date"""
        expected = {
            "name": "POS-OPEN-001",
            "pos_profile": "PROF-001",
            "branch": "Cabang A",
            "period_start_date": "2026-04-26 08:00:00"
        }

        def fake_get_all(doctype, **kwargs):
            if doctype == "POS Profile User":
                return ["PROF-001"]
            return [expected]

        with patch("resto.repositories.pos_repository.frappe.get_all", side_effect=fake_get_all):
            result = self.repo.get_active_pos_opening("user@test.com")

        self.assertIn("name", result)
        self.assertIn("pos_profile", result)
        self.assertIn("branch", result)
        self.assertIn("period_start_date", result)

    # ------------------------------------------------------------------
    # Integration test — pakai Frappe DB sungguhan
    # ------------------------------------------------------------------

    def test_get_active_pos_profile_integration(self):
        """Harus return opening entry setelah POS dibuka"""
        opening = self._create_pos_opening_entry()
        result = self.repo.get_active_pos_profile_for_user(frappe.session.user)

        self.assertEqual(result["pos_profile"], self.pos_profile.name)
        self.assertIn("name", result)
        self.assertIn("branch", result)
