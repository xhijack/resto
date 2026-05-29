"""Unit tests for BatchAllocatorService.

CRITICAL service — FIFO batch allocation for batched items.
Fixes Phase 1 audit critical bug #1: Bin lookup TIDAK batch-aware.
"""

import unittest
from unittest.mock import MagicMock, patch

from resto.services.stock_usage.batch_allocator import BatchAllocatorService


class TestBatchAllocatorService(unittest.TestCase):
    def setUp(self):
        self.service = BatchAllocatorService()

    def test_is_item_batched_true_for_has_batch_no(self):
        """Item dengan has_batch_no=1 → return True."""
        with patch("resto.services.stock_usage.batch_allocator.frappe.db.get_value",
                   return_value=1):
            self.assertTrue(self.service.is_item_batched("ITEM-BATCHED"))

    def test_is_item_batched_false_for_non_batch(self):
        with patch("resto.services.stock_usage.batch_allocator.frappe.db.get_value",
                   return_value=0):
            self.assertFalse(self.service.is_item_batched("ITEM-NORMAL"))

    def test_get_available_batches_sorted_fifo(self):
        """get_available_batches sorted oldest first (FIFO), skip expired."""
        mock_batches = [
            {"batch_no": "BATCH-NEW", "creation": "2026-03-01", "expiry_date": "2026-12-31"},
            {"batch_no": "BATCH-OLD", "creation": "2026-01-01", "expiry_date": "2026-12-31"},
            {"batch_no": "BATCH-EXPIRED", "creation": "2026-02-01", "expiry_date": "2026-05-01"},
        ]
        sle_qty_per_batch = {
            "BATCH-NEW": 10.0,
            "BATCH-OLD": 5.0,
            "BATCH-EXPIRED": 7.0,
        }

        with patch("resto.services.stock_usage.batch_allocator.frappe") as mock_frappe:
            mock_frappe.utils.nowdate.return_value = "2026-05-29"
            mock_frappe.get_all.return_value = mock_batches
            mock_frappe.db.sql.return_value = [(k, v) for k, v in sle_qty_per_batch.items()]

            batches = self.service.get_available_batches("ITEM-BATCHED", "Stores - M")

        codes = [b["batch_no"] for b in batches]
        # Expired BATCH-EXPIRED removed; FIFO order: oldest first
        self.assertEqual(codes, ["BATCH-OLD", "BATCH-NEW"])

    def test_allocate_fifo_walks_through_batches(self):
        """allocate_fifo: requirement 8 → take 5 dari BATCH-OLD + 3 dari BATCH-NEW."""
        with patch.object(self.service, "get_available_batches",
                          return_value=[
                              {"batch_no": "BATCH-OLD", "available_qty": 5.0,
                               "expiry_date": "2026-12-31"},
                              {"batch_no": "BATCH-NEW", "available_qty": 10.0,
                               "expiry_date": "2026-12-31"},
                          ]):
            result = self.service.allocate_fifo("ITEM-X", "Stores - M", required_qty=8.0)

        self.assertEqual(len(result["allocations"]), 2)
        self.assertEqual(result["allocations"][0]["batch_no"], "BATCH-OLD")
        self.assertEqual(result["allocations"][0]["allocated_qty"], 5.0)
        self.assertEqual(result["allocations"][1]["batch_no"], "BATCH-NEW")
        self.assertEqual(result["allocations"][1]["allocated_qty"], 3.0)
        self.assertFalse(result["partial"])

    def test_allocate_fifo_partial_when_insufficient(self):
        """Total available < required → partial=True, return whatever yang ada."""
        with patch.object(self.service, "get_available_batches",
                          return_value=[
                              {"batch_no": "BATCH-001", "available_qty": 3.0,
                               "expiry_date": "2026-12-31"},
                          ]):
            result = self.service.allocate_fifo("ITEM-X", "Stores - M", required_qty=10.0)

        self.assertTrue(result["partial"])
        self.assertEqual(result["allocations"][0]["allocated_qty"], 3.0)
        self.assertEqual(result["shortage_qty"], 7.0)
