"""Dynamic Print Format dispatch for Resto.

Phase 1: kitchen receipt path only. Other actions (bill, receipt, checker,
void) still go through legacy builders in `resto.printing` until migrated.

Naming note: package is `print_engine` (not `printing`) because
`resto/printing.py` already exists as the legacy hardcoded builder module.
"""
