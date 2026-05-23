# Copyright (c) 2026, PT Sopwer Teknologi Indonesia and contributors
# For license information, please see license.txt

"""Idempotent setup of voucher accounting (Chart of Accounts + Mode of Payment).

Triggered from `after_migrate`. Safe to call any number of times.
"""

import frappe

UNEARNED_ACCOUNT_NAME = "Unearned Voucher Revenue"
EXPENSE_ACCOUNT_NAME = "Voucher Promotional Expense"
VOUCHER_MODE_OF_PAYMENT = "Voucher"

VOUCHER_ITEM_GROUP = "Voucher"
VOUCHER_SAMPLE_ITEMS = [
    {"code": "Voucher Rp50.000", "rate": 50000},
    {"code": "Voucher Rp100.000", "rate": 100000},
    {"code": "Voucher Rp250.000", "rate": 250000},
]
DEFAULT_VOUCHER_VALIDITY_DAYS = 90


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


def setup_voucher_items():
    """Idempotent setup of Item Group "Voucher" + 3 sample non-stock items
    that cashiers can sell at POS. Each sample item has is_voucher_item=1
    so the on_submit issuance hook (events.voucher_hooks) auto-materializes
    Voucher records when sold.

    Safe to call from after_migrate any number of times.
    Depends on add_voucher_custom_fields() having installed the Item
    custom fields is_voucher_item + voucher_validity_days first.
    """
    _ensure_item_group(VOUCHER_ITEM_GROUP, parent="All Item Groups")
    for sample in VOUCHER_SAMPLE_ITEMS:
        _ensure_voucher_item(
            item_code=sample["code"],
            standard_rate=sample["rate"],
            item_group=VOUCHER_ITEM_GROUP,
            validity_days=DEFAULT_VOUCHER_VALIDITY_DAYS,
        )


def _ensure_item_group(name: str, parent: str) -> str:
    if frappe.db.exists("Item Group", name):
        return name
    frappe.get_doc(
        {
            "doctype": "Item Group",
            "item_group_name": name,
            "parent_item_group": parent,
            "is_group": 0,
        }
    ).insert(ignore_permissions=True)
    return name


def _ensure_voucher_item(
    item_code: str,
    standard_rate: float,
    item_group: str,
    validity_days: int,
) -> str:
    if frappe.db.exists("Item", item_code):
        return item_code
    frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": item_code,
            "item_name": item_code,
            "item_group": item_group,
            "stock_uom": "Nos",
            "is_stock_item": 0,
            "is_voucher_item": 1,
            "voucher_validity_days": validity_days,
            "standard_rate": standard_rate,
        }
    ).insert(ignore_permissions=True)
    return item_code
