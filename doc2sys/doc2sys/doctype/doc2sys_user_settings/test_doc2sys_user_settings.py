# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import today, add_days
import unittest

class TestDoc2SysUserSettings(FrappeTestCase):

	def test_update_user_credits_simple(self):
		"""Test updating user credits without creating new entities"""
		
		# Create sales invoice using existing item and customer
		sales_invoice = frappe.get_doc({
			"doctype": "Sales Invoice",
			"customer": "John Doe",
			"posting_date": today(),
			"due_date": add_days(today(), 10),
			"items": [
				{
					"item_code": "Credits",
					"qty": 5,
					"rate": 10
				}
			]
		})
		sales_invoice.insert(ignore_permissions=True)
		sales_invoice.submit()
		
		# Create payment entry for the invoice
		payment_entry = frappe.get_doc({
			"doctype": "Payment Entry",
			"payment_type": "Receive",
			"party_type": "Customer",
			"party": "John Doe",
			"paid_amount": 50,
			"received_amount": 50,
			"references": [
				{
					"reference_doctype": "Sales Invoice",
					"reference_name": sales_invoice.name,
					"allocated_amount": 50
				}
			]
		})
		payment_entry.insert(ignore_permissions=True)
		payment_entry.submit()
