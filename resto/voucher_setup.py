# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

"""Idempotent setup of voucher accounting (Chart of Accounts + Mode of Payment).

Triggered from `after_migrate`. Safe to call any number of times.
"""

import frappe

UNEARNED_ACCOUNT_NAME = "Unearned Voucher Revenue"
EXPENSE_ACCOUNT_NAME = "Voucher Promotional Expense"
VOUCHER_MODE_OF_PAYMENT = "Voucher"


def setup_voucher_accounting():
    companies = frappe.get_all("Company", pluck="name")
    company_to_unearned = {}

    for company in companies:
        unearned = _ensure_account(
            company=company,
            account_name=UNEARNED_ACCOUNT_NAME,
            root_type="Liability",
            preferred_parent_account_type="Current Liabilities",
        )
        _ensure_account(
            company=company,
            account_name=EXPENSE_ACCOUNT_NAME,
            root_type="Expense",
        )
        company_to_unearned[company] = unearned

    _ensure_mode_of_payment(company_to_unearned)


def _ensure_account(
    company: str,
    account_name: str,
    root_type: str,
    preferred_parent_account_type: str | None = None,
) -> str:
    existing = frappe.db.get_value(
        "Account",
        {"account_name": account_name, "company": company},
        "name",
    )
    if existing:
        return existing

    parent = _find_parent_group(company, root_type, preferred_parent_account_type)
    return frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": account_name,
            "parent_account": parent,
            "company": company,
            "root_type": root_type,
            "is_group": 0,
        }
    ).insert(ignore_permissions=True).name


def _find_parent_group(
    company: str,
    root_type: str,
    preferred_account_type: str | None = None,
) -> str:
    if preferred_account_type:
        parent = frappe.db.get_value(
            "Account",
            {
                "company": company,
                "account_type": preferred_account_type,
                "is_group": 1,
            },
            "name",
        )
        if parent:
            return parent

    parent = frappe.db.get_value(
        "Account",
        {"company": company, "root_type": root_type, "is_group": 1},
        "name",
    )
    if parent:
        return parent

    frappe.throw(
        f"No group Account found for root_type={root_type} in company {company}; "
        f"cannot create voucher accounts.",
        title="Voucher Setup Error",
    )


def _ensure_mode_of_payment(company_to_unearned: dict) -> None:
    if not frappe.db.exists("Mode of Payment", VOUCHER_MODE_OF_PAYMENT):
        frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": VOUCHER_MODE_OF_PAYMENT,
                "type": "General",
                "enabled": 1,
            }
        ).insert(ignore_permissions=True)

    mop = frappe.get_doc("Mode of Payment", VOUCHER_MODE_OF_PAYMENT)
    existing_companies = {row.company for row in mop.accounts}

    dirty = False
    for company, unearned_account in company_to_unearned.items():
        if company in existing_companies:
            continue
        mop.append(
            "accounts",
            {"company": company, "default_account": unearned_account},
        )
        dirty = True

    if dirty:
        mop.save(ignore_permissions=True)
