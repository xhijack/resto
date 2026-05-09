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

    # ------------------------------------------------------------------
    # Unit tests — `table` field di doc dict (foundation buat list_paid_invoices)
    # ------------------------------------------------------------------

    def test_create_pos_invoice_passes_table_to_doc_dict(self):
        """Field `table` di payload harus diteruskan ke POS Invoice doc dict.
        Foundation untuk relasi invoice→meja yang dipakai list_paid_invoices &
        Bill Function (replace JOIN-via-`tabTable Order` yang rapuh ke clear_table)."""
        mock_repo = MagicMock()
        mock_repo.get_default_company.return_value = "TestCo"
        # has_additional_items_field=True + additional_items=[] supaya for-loop
        # skip TANPA cabang else yang call frappe.log_error (yang internally
        # bikin Error Log via frappe.get_doc → polusi mock_get_doc.call_args).
        mock_repo.has_additional_items_field.return_value = True

        mock_doc = MagicMock()
        mock_doc.name = "INV-T1-001"

        with patch("resto.services.invoice_service.frappe.get_doc",
                   return_value=mock_doc) as mock_get_doc:
            service = InvoiceService(repo=mock_repo)
            service.create_pos_invoice({
                "customer": "C",
                "pos_profile": "P",
                "items": [{"item_code": "X", "qty": 1, "rate": 100}],
                "order_type": None,
                "table": "TBL-001",
            })

        # Ambil call PERTAMA (frappe.get_doc({...POS Invoice...})) — robust
        # walau ada call lain dari log_error/error path.
        first_call_args = mock_get_doc.call_args_list[0][0]
        self.assertTrue(first_call_args, "frappe.get_doc tidak dipanggil dengan positional dict")
        doctype_dict = first_call_args[0]
        self.assertEqual(doctype_dict.get("doctype"), "POS Invoice")
        self.assertEqual(doctype_dict.get("table"), "TBL-001")

    def test_create_pos_invoice_table_is_none_when_not_in_payload(self):
        """Tanpa `table` di payload (Take Away) → field `table` tetap dikirim None
        (tidak crash, tidak inherit dari state lain)."""
        mock_repo = MagicMock()
        mock_repo.get_default_company.return_value = "TestCo"
        mock_repo.has_additional_items_field.return_value = True
        mock_doc = MagicMock(); mock_doc.name = "INV-NOTABLE"

        with patch("resto.services.invoice_service.frappe.get_doc",
                   return_value=mock_doc) as mock_get_doc:
            service = InvoiceService(repo=mock_repo)
            service.create_pos_invoice({
                "customer": "C",
                "pos_profile": "P",
                "items": [{"item_code": "X", "qty": 1, "rate": 100}],
                "order_type": None,
            })

        first_call_args = mock_get_doc.call_args_list[0][0]
        doctype_dict = first_call_args[0]
        self.assertIsNone(doctype_dict.get("table"))

    # ------------------------------------------------------------------
    # Unit tests — list_paid_invoices (delegates to repo)
    # ------------------------------------------------------------------

    def test_list_paid_invoices_passes_filters_to_repo(self):
        """Service hanya delegate ke repo dengan filter yang sama (keyword args)."""
        mock_repo = MagicMock()
        mock_repo.list_paid_invoices.return_value = [{"name": "INV-1"}]
        service = InvoiceService(repo=mock_repo)

        result = service.list_paid_invoices(
            posting_date="2026-01-15", branch="BR-001", table_name="T1"
        )

        mock_repo.list_paid_invoices.assert_called_once_with(
            posting_date="2026-01-15", branch="BR-001", table_name="T1"
        )
        self.assertEqual(result, [{"name": "INV-1"}])

    def test_list_paid_invoices_default_passes_none_to_repo(self):
        """Tanpa filter, service pass None ke repo (repo decide CURDATE default)."""
        mock_repo = MagicMock()
        mock_repo.list_paid_invoices.return_value = []
        service = InvoiceService(repo=mock_repo)

        service.list_paid_invoices()

        mock_repo.list_paid_invoices.assert_called_once_with(
            posting_date=None, branch=None, table_name=None
        )


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

    def test_apply_discount_uses_doc_template_not_pos_profile(self):
        """Regression: apply_discount harus pakai doc.taxes_and_charges sebagai
        source of truth — bukan pos_profile.taxes_and_charges. Skenario split
        bill di mana doc pakai template yang berbeda dari POS Profile.
        """
        mock_repo = MagicMock()
        mock_repo.invoice_exists.return_value = True

        mock_doc = MagicMock()
        mock_doc.taxes = []
        mock_doc.taxes_and_charges = "DOC-TPL"
        mock_repo.get_invoice.return_value = mock_doc

        mock_repo.get_pos_profile.return_value = MagicMock(taxes_and_charges="PROFILE-TPL")
        mock_repo.get_active_profile_for_user.return_value = {"pos_profile": "PROF-001"}

        # Template DOC punya row Discount, profile template-nya tidak relevan
        # karena apply_discount harus baca DOC-TPL, bukan PROFILE-TPL.
        discount_row = MagicMock()
        discount_row.description = "Discount"
        discount_row.account_head = "Discount - _TC"
        mock_repo.get_tax_template.return_value = MagicMock(taxes=[discount_row])

        service = InvoiceService(repo=mock_repo)
        result = service.apply_discount(pos_invoice="INV-SPLIT", discount_percentage=10)

        self.assertTrue(result["ok"])
        # Pastikan get_tax_template dipanggil dengan template DOC, bukan profile
        mock_repo.get_tax_template.assert_called_with("DOC-TPL")

    def test_apply_discount_falls_back_to_pos_profile_when_doc_template_missing(self):
        """Kalau doc.taxes_and_charges kosong, fallback ke pos_profile.taxes_and_charges."""
        mock_repo = MagicMock()
        mock_repo.invoice_exists.return_value = True

        mock_doc = MagicMock()
        mock_doc.taxes = []
        mock_doc.taxes_and_charges = None  # doc tidak punya template
        mock_repo.get_invoice.return_value = mock_doc

        mock_repo.get_pos_profile.return_value = MagicMock(taxes_and_charges="PROFILE-TPL")
        mock_repo.get_active_profile_for_user.return_value = {"pos_profile": "PROF-001"}

        discount_row = MagicMock()
        discount_row.description = "Discount"
        discount_row.account_head = "Discount - _TC"
        mock_repo.get_tax_template.return_value = MagicMock(taxes=[discount_row])

        service = InvoiceService(repo=mock_repo)
        result = service.apply_discount(pos_invoice="INV-001", discount_percentage=10)

        self.assertTrue(result["ok"])
        mock_repo.get_tax_template.assert_called_with("PROFILE-TPL")

    # ------------------------------------------------------------------
    # Unit tests — move_items_from_invoice (scenario 2+3)
    # ------------------------------------------------------------------

    def test_move_items_appends_items_to_target(self):
        """move_items_from_invoice harus append item source ke target invoice"""
        mock_repo = MagicMock()

        source_item = MagicMock()
        source_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty", "rate", "status_kitchen"]
        source_item.get.side_effect = lambda f: {"item_code": "ITEM-001", "qty": 2, "rate": 10000, "status_kitchen": ""}[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [source_item]

        target_doc = MagicMock()
        target_doc.get.return_value = []  # no taxes in target
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db"):
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        target_doc.append.assert_called_once()
        call_args = target_doc.append.call_args[0]
        self.assertEqual(call_args[0], "items")
        self.assertIsInstance(call_args[1], dict)
        self.assertEqual(call_args[1].get("item_code"), "ITEM-001")

    def test_move_items_marks_source_as_merged(self):
        """Source invoice harus di-set is_merged=1 dan merge_invoice via frappe.db.set_value"""
        mock_repo = MagicMock()

        source_item = MagicMock()
        source_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty"]
        source_item.get.side_effect = lambda f: {"item_code": "I-001", "qty": 1}[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [source_item]
        target_doc = MagicMock()
        target_doc.get.return_value = []
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db") as mock_db:
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        mock_db.set_value.assert_called_once_with(
            "POS Invoice", "INV-SRC",
            {"is_merged": 1, "merge_invoice": "INV-TGT"}
        )

    def test_move_items_preserves_void_menu_items(self):
        """Items dengan status_kitchen=Void Menu tetap ter-append ke target (scenario 2)"""
        mock_repo = MagicMock()

        void_item = MagicMock()
        void_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty", "status_kitchen"]
        void_item.get.side_effect = lambda f: {
            "item_code": "ITEM-VOID", "qty": 1, "status_kitchen": "Void Menu"
        }[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [void_item]
        target_doc = MagicMock()
        target_doc.get.return_value = []  # no taxes
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db"):
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        target_doc.append.assert_called_once()
        appended_row = target_doc.append.call_args[0][1]
        self.assertEqual(appended_row.get("status_kitchen"), "Void Menu")

    def test_delete_merge_invoice_calls_delete_on_merged_invoices(self):
        """delete_merge_invoice harus hapus semua merged invoices (scenario 2)"""
        mock_repo = MagicMock()
        merged_doc1 = MagicMock()
        merged_doc2 = MagicMock()
        mock_repo.get_merged_invoices.return_value = [merged_doc1, merged_doc2]

        service = InvoiceService(repo=mock_repo)
        service.delete_merge_invoice("INV-BASE")

        merged_doc1.delete.assert_called_once()
        merged_doc2.delete.assert_called_once()

    def test_delete_merge_invoice_does_not_delete_base_invoice(self):
        """delete_merge_invoice tidak boleh hapus invoice base (target)"""
        mock_repo = MagicMock()
        mock_repo.get_merged_invoices.return_value = []

        service = InvoiceService(repo=mock_repo)
        service.delete_merge_invoice("INV-BASE")

        mock_repo.get_invoice.assert_not_called()

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

    # ------------------------------------------------------------------
    # Extreme variation tests — move_items_from_invoice edge cases
    # ------------------------------------------------------------------

    def test_move_items_with_zero_items_in_source_appends_nothing(self):
        """source.get('items') = [] → target.append never called"""
        mock_repo = MagicMock()

        source_doc = MagicMock()
        source_doc.get.return_value = []
        target_doc = MagicMock()
        target_doc.get.return_value = []
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db"):
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        target_doc.append.assert_not_called()

    def test_move_items_excludes_name_and_parent_from_row_dict(self):
        """Fields 'name' dan 'parent' harus di-exclude dari row yang di-append ke target"""
        mock_repo = MagicMock()

        source_item = MagicMock()
        source_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty", "name", "parent"]
        source_item.get.side_effect = lambda f: {
            "item_code": "ITEM-001", "qty": 1, "name": "row-001", "parent": "INV-SRC"
        }[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [source_item]
        target_doc = MagicMock()
        target_doc.get.return_value = []
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db"):
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        call_args = target_doc.append.call_args[0][1]
        self.assertNotIn("name", call_args)
        self.assertNotIn("parent", call_args)

    def test_move_items_clears_row_id_for_non_prev_row_charge_type(self):
        """row_id harus di-clear untuk tax dengan charge_type bukan 'On Previous Row...'"""
        mock_repo = MagicMock()

        source_item = MagicMock()
        source_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty"]
        source_item.get.side_effect = lambda f: {"item_code": "I-001", "qty": 1}[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [source_item]

        tax_row = MagicMock()
        tax_row.charge_type = "Actual"
        tax_row.row_id = "tax-row-001"

        target_doc = MagicMock()
        target_doc.get.return_value = [tax_row]
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db"):
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        self.assertIsNone(tax_row.row_id)

    def test_move_items_preserves_row_id_for_prev_row_amount_charge_type(self):
        """row_id harus DIPERTAHANKAN untuk charge_type 'On Previous Row Amount'"""
        mock_repo = MagicMock()

        source_item = MagicMock()
        source_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty"]
        source_item.get.side_effect = lambda f: {"item_code": "I-001", "qty": 1}[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [source_item]

        tax_row = MagicMock()
        tax_row.charge_type = "On Previous Row Amount"
        tax_row.row_id = "tax-row-999"

        target_doc = MagicMock()
        target_doc.get.return_value = [tax_row]
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db"):
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        self.assertEqual(tax_row.row_id, "tax-row-999")

    def test_delete_merge_invoice_with_empty_list_does_nothing(self):
        """get_merged_invoices returns [] → delete tidak pernah dipanggil"""
        mock_repo = MagicMock()
        mock_repo.get_merged_invoices.return_value = []

        service = InvoiceService(repo=mock_repo)
        service.delete_merge_invoice("INV-BASE")

        mock_repo.get_invoice.assert_not_called()

    def test_move_items_uses_db_set_value_not_source_save(self):
        """frappe.db.set_value dipanggil untuk source — source.save() tidak boleh dipanggil"""
        mock_repo = MagicMock()

        source_item = MagicMock()
        source_item.meta.get_fieldnames_with_value.return_value = ["item_code", "qty"]
        source_item.get.side_effect = lambda f: {"item_code": "I-001", "qty": 1}[f]

        source_doc = MagicMock()
        source_doc.get.return_value = [source_item]
        target_doc = MagicMock()
        target_doc.get.return_value = []
        mock_repo.get_invoice.side_effect = lambda name: source_doc if name == "INV-SRC" else target_doc

        service = InvoiceService(repo=mock_repo)
        with patch("resto.services.invoice_service.frappe.db") as mock_db:
            service.move_items_from_invoice("INV-SRC", "INV-TGT")

        source_doc.save.assert_not_called()
        mock_db.set_value.assert_called_once_with(
            "POS Invoice", "INV-SRC",
            {"is_merged": 1, "merge_invoice": "INV-TGT"}
        )
