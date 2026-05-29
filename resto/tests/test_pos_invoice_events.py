import frappe
from unittest.mock import MagicMock, patch
from resto.tests.resto_pos_test_base import RestoPOSTestBase
from resto.events.pos_invoice import (
    auto_cancel_fully_voided_draft,
    block_partial_payment,
)


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


def _mock_void_invoice(*, docstatus=0, is_pos=1, table="TBL-A", items=None, name="POS-INV-001"):
    """Mock POS Invoice for auto_cancel_fully_voided_draft tests.
    items: list of (status_kitchen,) tuples — each becomes an item row mock.
    """
    doc = MagicMock()
    doc.name = name
    doc.docstatus = docstatus
    doc.is_pos = is_pos
    doc.table = table
    # flags must behave like a dict (.get + attribute assignment)
    doc.flags = MagicMock()
    doc.flags.get = lambda key, default=None: getattr(doc.flags, key, default) if key in doc.flags.__dict__ else default
    # populate item rows
    rows = []
    for status_kitchen in (items or []):
        row = MagicMock()
        row.status_kitchen = status_kitchen
        rows.append(row)
    doc.items = rows
    return doc


class TestAutoCancelFullyVoidedDraft(RestoPOSTestBase):
    """Unit tests for the on_update hook that cancels Draft POS Invoices once
    every item has been flagged Void Menu."""

    def test_cancels_when_all_items_voided_and_clears_meja(self):
        """Draft + every item Void Menu → cancel + remove from table; if the
        meja has no other orders, clear it back to Kosong."""
        doc = _mock_void_invoice(items=["Void Menu", "Void Menu"])

        with patch("resto.services.table_service.TableService") as MockSvc:
            svc = MockSvc.return_value
            empty_table = MagicMock()
            empty_table.orders = []
            svc.repo.get_table.return_value = empty_table

            auto_cancel_fully_voided_draft(doc, method="on_update")

        doc.cancel.assert_called_once()
        svc.remove_table_order.assert_called_once_with("TBL-A", "POS-INV-001")
        svc.clear_table.assert_called_once_with("TBL-A")

    def test_skips_clear_meja_when_other_orders_remain(self):
        """If the meja still has another order after we remove ours, leave
        meja status alone — don't kosongin saat ada order lain."""
        doc = _mock_void_invoice(items=["Void Menu"])

        with patch("resto.services.table_service.TableService") as MockSvc:
            svc = MockSvc.return_value
            busy_table = MagicMock()
            busy_table.orders = [MagicMock(invoice_name="OTHER-INV")]
            svc.repo.get_table.return_value = busy_table

            auto_cancel_fully_voided_draft(doc, method="on_update")

        doc.cancel.assert_called_once()
        svc.remove_table_order.assert_called_once()
        svc.clear_table.assert_not_called()

    def test_no_action_when_any_item_unvoided(self):
        """At least one normal item → no cancel, no table touch."""
        doc = _mock_void_invoice(items=["Void Menu", "Already Send To Kitchen"])

        with patch("resto.services.table_service.TableService") as MockSvc:
            auto_cancel_fully_voided_draft(doc, method="on_update")

            MockSvc.assert_not_called()
        doc.cancel.assert_not_called()

    def test_no_action_on_submitted_invoice(self):
        """Submitted invoice (docstatus=1), even if every item is Void Menu, is
        out of scope — we never cancel post-submit."""
        doc = _mock_void_invoice(docstatus=1, items=["Void Menu"])

        with patch("resto.services.table_service.TableService") as MockSvc:
            auto_cancel_fully_voided_draft(doc, method="on_update")

            MockSvc.assert_not_called()
        doc.cancel.assert_not_called()

    def test_no_action_on_non_pos_invoice(self):
        """Non-POS invoice path (is_pos=0) is not our concern."""
        doc = _mock_void_invoice(is_pos=0, items=["Void Menu"])

        with patch("resto.services.table_service.TableService") as MockSvc:
            auto_cancel_fully_voided_draft(doc, method="on_update")

            MockSvc.assert_not_called()
        doc.cancel.assert_not_called()

    def test_no_action_on_invoice_with_no_items(self):
        """Empty items list — guard short-circuits before the all-voided check
        (an empty list would technically satisfy `all()` and produce a
        false positive otherwise)."""
        doc = _mock_void_invoice(items=[])

        with patch("resto.services.table_service.TableService") as MockSvc:
            auto_cancel_fully_voided_draft(doc, method="on_update")

            MockSvc.assert_not_called()
        doc.cancel.assert_not_called()

    def test_skips_table_cleanup_when_invoice_has_no_table(self):
        """Invoice without a `table` link still gets cancelled, but we don't
        touch any Table doc (nothing to clean)."""
        doc = _mock_void_invoice(table=None, items=["Void Menu"])

        with patch("resto.services.table_service.TableService") as MockSvc:
            auto_cancel_fully_voided_draft(doc, method="on_update")

            MockSvc.assert_not_called()
        doc.cancel.assert_called_once()

    def test_idempotent_via_flag(self):
        """The flag short-circuits any second invocation in the same request."""
        doc = _mock_void_invoice(items=["Void Menu"])
        doc.flags.auto_cancel_fully_voided = True

        with patch("resto.services.table_service.TableService") as MockSvc:
            auto_cancel_fully_voided_draft(doc, method="on_update")

            MockSvc.assert_not_called()
        doc.cancel.assert_not_called()
