"""Render a Frappe Print Format (Jinja / Raw Commands) to ESC/POS bytes.

`frappe.render_template` returns str. We round-trip the str through Latin-1
to bytes (preserves bytes 0-255 1:1, so all ESC/POS control chars survive).

Caller is responsible for sending the bytes to CUPS.
"""
from __future__ import annotations

from typing import Optional

import frappe


class PrintFormatNotFoundError(Exception):
	pass


class PrintFormatEncodingError(Exception):
	pass


def _load_template(print_format: str) -> str:
	if not print_format:
		raise PrintFormatNotFoundError("print_format is required")
	if not frappe.db.exists("Print Format", print_format):
		raise PrintFormatNotFoundError(f"Print Format '{print_format}' not found")
	# `html` field stores the template body for both Jinja and Raw Commands.
	html = frappe.db.get_value("Print Format", print_format, "html") or ""
	return html


def render_print_format(print_format: str, context: Optional[dict] = None) -> bytes:
	"""Render PF template with context → raw bytes ready for CUPS."""
	template = _load_template(print_format)
	rendered = frappe.render_template(template, context or {})
	try:
		return rendered.encode("latin-1")
	except UnicodeEncodeError as e:
		# Template contains chars outside 0-255 (e.g. emoji). Caller must fall back.
		raise PrintFormatEncodingError(
			f"Print Format '{print_format}' produced non-Latin-1 char at offset {e.start}: "
			f"{rendered[e.start:e.end]!r}"
		) from e
