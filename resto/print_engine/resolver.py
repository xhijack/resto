"""Resolve which `Resto Print Rule` applies to a given (action, branch, context).

Resolution order (most-specific wins):
1. Filter to enabled rules with matching `action_key`.
2. Branch-specific rules (rule.branch == request.branch) preferred over default (branch empty).
3. Eval `filter_condition_jinja` against context — keep only truthy.
4. Sort by `priority` descending → return top.

Returns `None` when no rule matches → caller falls back to legacy builder.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import frappe


@dataclass(frozen=True)
class ResolvedRule:
	name: str
	rule_name: str
	action_key: str
	branch: Optional[str]
	print_format: str
	printer_resolver: str
	printer_name: Optional[str]
	kitchen_station: Optional[str]
	priority: int


def _row_to_rule(row: dict) -> ResolvedRule:
	return ResolvedRule(
		name=row["name"],
		rule_name=row.get("rule_name") or row["name"],
		action_key=row["action_key"],
		branch=row.get("branch") or None,
		print_format=row["print_format"],
		printer_resolver=row.get("printer_resolver") or "From Payload",
		printer_name=row.get("printer_name") or None,
		kitchen_station=row.get("kitchen_station") or None,
		priority=int(row.get("priority") or 0),
	)


def _filter_condition_passes(expr: Optional[str], context: dict) -> bool:
	expr = (expr or "").strip()
	if not expr:
		return True
	try:
		rendered = frappe.render_template(expr, context or {})
	except Exception as e:
		frappe.log_error(
			f"Filter condition render failed: {e}\nExpr: {expr}",
			"RestoPrintRuleResolver",
		)
		return False
	return _truthy(rendered)


def _truthy(rendered: str) -> bool:
	if rendered is None:
		return False
	s = str(rendered).strip().lower()
	return s not in ("", "false", "0", "none", "no")


def resolve_print_rule(
	action_key: str,
	branch: Optional[str] = None,
	context: Optional[dict] = None,
) -> Optional[ResolvedRule]:
	"""Pick the best matching rule, or None if none applies."""
	if not action_key:
		return None

	rows = frappe.get_all(
		"Resto Print Rule",
		filters={"action_key": action_key, "enabled": 1},
		fields=[
			"name", "rule_name", "action_key", "branch",
			"print_format", "printer_resolver", "printer_name",
			"kitchen_station", "priority", "filter_condition_jinja",
		],
		order_by="priority desc, modified desc",
	)
	if not rows:
		return None

	ctx = context or {}

	# Prefer branch-specific match first; fall back to default (empty branch).
	specific = [r for r in rows if (r.get("branch") or None) == (branch or None) and branch]
	defaults = [r for r in rows if not (r.get("branch") or None)]

	for candidates in (specific, defaults):
		for r in candidates:
			if _filter_condition_passes(r.get("filter_condition_jinja"), ctx):
				return _row_to_rule(r)

	return None
