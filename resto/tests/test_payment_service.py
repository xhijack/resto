import frappe
from unittest.mock import patch, MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.services.payment_service import PaymentService


def _full_paid_mock(amount=50000, existing_payments=None):
    """Mock POS Invoice doc dengan grand_total=amount + existing payments
    yang menambah ke fully-paid kalau caller bayar sisanya."""
    mock_doc = MagicMock()
    mock_doc.taxes = []
    mock_doc.payments = list(existing_payments or [])
    mock_doc.grand_total = amount
    mock_doc.rounded_total = amount
    return mock_doc


class TestPaymentService(RestoPOSTestBase):
    def setUp(self):
        super().setUp()
        self.service = PaymentService()

    # ------------------------------------------------------------------
    # Unit tests — create_payment (full payment cases)
    # ------------------------------------------------------------------

    def test_create_payment_appends_payment_to_invoice(self):
        """Harus append payment ke doc.payments"""
        mock_doc = _full_paid_mock(50000)

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
        mock_doc = _full_paid_mock(50000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_doc.submit.assert_called_once()

    def test_create_payment_calls_clear_table_merged(self):
        """Harus memanggil clear_table_merged setelah submit"""
        mock_doc = _full_paid_mock(50000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged") as mock_clear:
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_clear.assert_called_once_with("INV-001")

    def test_create_payment_calls_db_commit(self):
        """Harus memanggil frappe.db.commit()"""
        mock_doc = _full_paid_mock(50000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db") as mock_db, \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        mock_db.commit.assert_called_once()

    def test_create_payment_returns_ok_true(self):
        """Harus return ok=True dan pos_invoice name"""
        mock_doc = _full_paid_mock(50000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-001", 50000, "Cash")

        self.assertTrue(result["ok"])
        self.assertEqual(result["pos_invoice"], "INV-001")
        self.assertIn("message", result)

    # ------------------------------------------------------------------
    # Anti-partial validation
    # ------------------------------------------------------------------

    def test_create_payment_rejects_underpayment(self):
        """amount < grand_total → throws ValidationError, doc.submit tidak dipanggil"""
        mock_doc = _full_paid_mock(100000)  # grand_total 100K

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            with self.assertRaises(frappe.ValidationError) as ctx:
                self.service.create_payment("INV-001", 50000, "Cash")

        self.assertIn("Kurang", str(ctx.exception))
        mock_doc.submit.assert_not_called()
        mock_doc.append.assert_not_called()

    def test_create_payment_allows_topup_to_full(self):
        """existing partial payment + new payment yang melengkapi → success"""
        existing = [MagicMock(amount=30000)]
        mock_doc = _full_paid_mock(100000, existing_payments=existing)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-001", 70000, "Cash")

        self.assertTrue(result["ok"])
        mock_doc.submit.assert_called_once()

    def test_create_payment_tolerance_under_one_rupiah(self):
        """Selisih <1 rupiah (rounding) → tetap diterima"""
        mock_doc = _full_paid_mock(100000.5)  # grand_total 100,000.5

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-001", 100000, "Cash")

        self.assertTrue(result["ok"])
        mock_doc.submit.assert_called_once()

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
    # Boundary cases
    # ------------------------------------------------------------------

    def test_create_payment_with_amount_zero_rejects(self):
        """amount=0 (under-payment) → reject (kebijakan baru anti-partial)"""
        mock_doc = _full_paid_mock(50000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            with self.assertRaises(frappe.ValidationError):
                self.service.create_payment("INV-001", 0, "Cash")

        mock_doc.append.assert_not_called()

    def test_create_payment_with_very_large_amount_no_crash(self):
        """amount=99999999 (over-payment) → tetap allowed, submit dipanggil"""
        mock_doc = _full_paid_mock(100)  # grand_total kecil

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-001", 99999999, "Transfer")

        mock_doc.submit.assert_called_once()
        self.assertTrue(result["ok"])

    def test_create_payment_result_includes_pos_invoice_name(self):
        """result['pos_invoice'] harus sama dengan invoice name yang dikirim"""
        mock_doc = _full_paid_mock(50000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.create_payment("INV-SPECIFIC-001", 50000, "Cash")

        self.assertEqual(result["pos_invoice"], "INV-SPECIFIC-001")

    def test_create_payment_taxes_not_modified(self):
        """create_payment tidak boleh menyentuh doc.taxes"""
        mock_doc = _full_paid_mock(50000)
        original_taxes = [MagicMock(), MagicMock()]
        mock_doc.taxes = list(original_taxes)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            self.service.create_payment("INV-001", 50000, "Cash")

        self.assertEqual(len(mock_doc.taxes), len(original_taxes))

    # ------------------------------------------------------------------
    # pay_invoice — atomic full-pay dengan split payment methods
    # ------------------------------------------------------------------

    def test_pay_invoice_single_method_full_amount(self):
        """1 method covers full grand_total → submit OK"""
        mock_doc = _full_paid_mock(100000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.pay_invoice(
                "INV-001",
                [{"mode_of_payment": "Cash", "amount": 100000}],
            )

        self.assertTrue(result["ok"])
        mock_doc.set.assert_called_once_with("payments", [])
        mock_doc.append.assert_called_once_with("payments", {
            "mode_of_payment": "Cash", "amount": 100000.0,
        })
        mock_doc.submit.assert_called_once()

    def test_pay_invoice_split_methods_sum_equals_grand(self):
        """Split (Cash 800rb + Mandiri 200rb = 1jt) → submit OK, 2 append"""
        mock_doc = _full_paid_mock(1_000_000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.pay_invoice(
                "INV-001",
                [
                    {"mode_of_payment": "Cash", "amount": 800_000},
                    {"mode_of_payment": "Debit Mandiri", "amount": 200_000},
                ],
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["total_paid"], 1_000_000)
        mock_doc.set.assert_called_once_with("payments", [])
        self.assertEqual(mock_doc.append.call_count, 2)
        mock_doc.submit.assert_called_once()

    def test_pay_invoice_rejects_sum_less_than_grand(self):
        """Sum < grand → throws, tidak submit, tidak append"""
        mock_doc = _full_paid_mock(1_000_000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            with self.assertRaises(frappe.ValidationError):
                self.service.pay_invoice(
                    "INV-001",
                    [{"mode_of_payment": "Cash", "amount": 800_000}],
                )

        mock_doc.submit.assert_not_called()
        mock_doc.set.assert_not_called()
        mock_doc.append.assert_not_called()

    def test_pay_invoice_rejects_sum_greater_than_grand(self):
        """Sum > grand (over-payment) → throws (kebijakan ketat sum==grand)"""
        mock_doc = _full_paid_mock(1_000_000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            with self.assertRaises(frappe.ValidationError):
                self.service.pay_invoice(
                    "INV-001",
                    [{"mode_of_payment": "Cash", "amount": 1_100_000}],
                )

        mock_doc.submit.assert_not_called()

    def test_pay_invoice_clears_existing_partial_payments(self):
        """Residu partial payment di DRAFT harus di-clear sebelum append set baru.
        Skenario: user pernah simpan 300rb di create_pos_invoice payload (bug
        lama 'pay sebagian → tutup → masuk lagi'). pay_invoice harus replace,
        bukan menambah di atas residu."""
        residual = MagicMock(amount=300_000)
        mock_doc = _full_paid_mock(1_000_000, existing_payments=[residual])

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.pay_invoice(
                "INV-001",
                [{"mode_of_payment": "Cash", "amount": 1_000_000}],
            )

        self.assertTrue(result["ok"])
        # set("payments", []) HARUS dipanggil → membersihkan residu 300rb
        mock_doc.set.assert_called_once_with("payments", [])
        mock_doc.append.assert_called_once()
        mock_doc.submit.assert_called_once()

    def test_pay_invoice_rejects_empty_list(self):
        """payments=[] → throws"""
        with patch("resto.services.payment_service.frappe.get_doc"):
            with self.assertRaises(frappe.ValidationError):
                self.service.pay_invoice("INV-001", [])

    def test_pay_invoice_rejects_row_without_mode(self):
        """row tanpa mode_of_payment → throws sebelum touching doc"""
        with patch("resto.services.payment_service.frappe.get_doc"):
            with self.assertRaises(frappe.ValidationError):
                self.service.pay_invoice(
                    "INV-001",
                    [{"mode_of_payment": "", "amount": 100000}],
                )

    def test_pay_invoice_rejects_zero_or_negative_amount(self):
        """row dengan amount <= 0 → throws"""
        with patch("resto.services.payment_service.frappe.get_doc"):
            with self.assertRaises(frappe.ValidationError):
                self.service.pay_invoice(
                    "INV-001",
                    [{"mode_of_payment": "Cash", "amount": 0}],
                )

    def test_pay_invoice_accepts_json_string(self):
        """payments di-pass sebagai JSON string (caller mobile via whitelist) → parsed"""
        mock_doc = _full_paid_mock(100000)

        with patch("resto.services.payment_service.frappe.get_doc", return_value=mock_doc), \
             patch("resto.services.payment_service.frappe.db"), \
             patch("resto.services.payment_service.clear_table_merged"):
            result = self.service.pay_invoice(
                "INV-001",
                '[{"mode_of_payment": "Cash", "amount": 100000}]',
            )

        self.assertTrue(result["ok"])
        mock_doc.submit.assert_called_once()
