import frappe


class CustomerRepository:
    def create_customer(self, name, mobile_no=None):
        doc = frappe.get_doc({
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Company",
            "mobile_no": mobile_no,
            "mobile_number": mobile_no
        })
        doc.insert(ignore_permissions=True)
        return doc.as_dict()
