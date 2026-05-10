import frappe
from unittest.mock import MagicMock
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.events.pos_invoice import block_partial_payment


def _mock_invoice(*, is_pos=1, grand_total=100000, rounded_total=None, payments=None):
    """Mock POS Invoice doc minimal untuk test block_partial_payment.
    payments: list of dicts/objects with .amount attribute."""
    doc = MagicMock()
    doc.is_pos = is_pos
    doc.grand_total = grand_total
    doc.rounded_total = rounded_total if rounded_total is not None else grand_total
    doc.payments = []
    for p in (payments or []):
        m = MagicMock()
        m.amount = p["amount"] if isinstance(p, dict) else p
        doc.payments.append(m)
    return doc


class TestBlockPartialPayment(RestoPOSTestBase):
    """Unit tests untuk block_partial_payment guard di before_submit hook."""

    def test_rejects_underpayment(self):
        """grand_total=100K, paid=50K → throws ValidationError dengan message 'Kurang'"""
        doc = _mock_invoice(grand_total=100000, payments=[{"amount": 50000}])
        with self.assertRaises(frappe.ValidationError) as ctx:
            block_partial_payment(doc, method="before_submit")
        self.assertIn("Kurang", str(ctx.exception))

    def test_allows_full_single_payment(self):
        """grand_total=100K, paid=100K (single mode) → no throw"""
        doc = _mock_invoice(grand_total=100000, payments=[{"amount": 100000}])
        # Should not raise
        block_partial_payment(doc, method="before_submit")

    def test_allows_full_split_modes(self):
        """grand_total=100K, paid=Cash 50K + Card 50K → no throw"""
        doc = _mock_invoice(grand_total=100000, payments=[
            {"amount": 50000},
            {"amount": 50000},
        ])
        block_partial_payment(doc, method="before_submit")

    def test_skips_non_pos_invoice(self):
        """is_pos=0 → guard return early, tidak peduli paid amount"""
        doc = _mock_invoice(is_pos=0, grand_total=100000, payments=[{"amount": 0}])
        # Should not raise meskipun paid 0 < grand_total
        block_partial_payment(doc, method="before_submit")

    def test_tolerance_under_one_rupiah(self):
        """grand_total=100,000.5, paid=100,000 (kurang 0.5) → no throw (tolerance 1 rupiah)"""
        doc = _mock_invoice(grand_total=100000.5, rounded_total=100000.5,
                             payments=[{"amount": 100000}])
        block_partial_payment(doc, method="before_submit")

    def test_uses_rounded_total_when_present(self):
        """rounded_total=99,999, grand_total=99,999.5, paid=99,999 → no throw
        (rounded_total dipakai dulu, tolerance 1 rupiah)"""
        doc = _mock_invoice(grand_total=99999.5, rounded_total=99999,
                             payments=[{"amount": 99999}])
        block_partial_payment(doc, method="before_submit")

    def test_falls_back_to_grand_total_when_rounded_zero(self):
        """rounded_total=0/falsy → fallback ke grand_total"""
        doc = _mock_invoice(grand_total=100000, rounded_total=0,
                             payments=[{"amount": 50000}])
        with self.assertRaises(frappe.ValidationError):
            block_partial_payment(doc, method="before_submit")

    def test_empty_payments_throws(self):
        """grand_total>0, payments=[] → reject (paid=0)"""
        doc = _mock_invoice(grand_total=100000, payments=[])
        with self.assertRaises(frappe.ValidationError) as ctx:
            block_partial_payment(doc, method="before_submit")
        self.assertIn("Kurang", str(ctx.exception))

    def test_overpayment_allowed(self):
        """paid > grand_total → allowed (over-payment bukan target guard ini)"""
        doc = _mock_invoice(grand_total=100000, payments=[{"amount": 150000}])
        block_partial_payment(doc, method="before_submit")
