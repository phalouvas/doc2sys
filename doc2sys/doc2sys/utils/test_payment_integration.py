import unittest
from unittest.mock import patch, MagicMock, call
from doc2sys.doc2sys.utils.payment_integration import update_user_credits

# -*- coding: utf-8 -*-
# Copyright (c) 2023, Doc2Sys and Contributors
# See license.txt



class TestUpdateUserCredits(unittest.TestCase):
    def setUp(self):
        # Reset frappe flags for each test
        self.original_flags = MagicMock()
        self.original_flags.ignore_permissions = False
        
        # Create mock payment entry for reuse
        self.payment_entry = MagicMock()
        self.payment_entry.payment_type = "Receive"
        self.payment_entry.party_type = "Customer"
        self.payment_entry.party = "CUST-001"
        
        # Mock references
        mock_ref = MagicMock()
        mock_ref.reference_doctype = "Sales Invoice"
        mock_ref.reference_name = "SINV-001"
        mock_ref.allocated_amount = 100.0
        self.payment_entry.references = [mock_ref]

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.set_value')
    @patch('frappe.msgprint')
    @patch('frappe.log_error')
    def test_update_user_credits_success(self, mock_log_error, mock_msgprint, mock_db_set_value, 
                                        mock_get_all, mock_get_doc, mock_flags):
        # Setup mock objects
        mock_flags.ignore_permissions = False
        
        # Setup Doc2Sys Settings
        mock_settings = MagicMock()
        mock_settings.credits_item_group = "Credits"
        
        # Setup Sales Invoice and Items
        mock_item_doc = MagicMock()
        mock_item_doc.item_group = "Credits"
        
        mock_invoice_item = MagicMock()
        mock_invoice_item.item_code = "ITEM-001"
        mock_invoice_item.net_amount = 50.0
        
        mock_sales_invoice = MagicMock()
        mock_sales_invoice.items = [mock_invoice_item]
        mock_sales_invoice.grand_total = 100.0
        
        # Setup Customer
        mock_portal_user = MagicMock()
        mock_portal_user.user = "test@example.com"
        
        mock_customer = MagicMock()
        mock_customer.portal_users = [mock_portal_user]
        
        # Setup User Settings
        mock_user_setting = MagicMock()
        mock_user_setting.name = "USR-SETTING-001"
        mock_user_setting.credits = 100.0
        
        # Configure mocks to return appropriate values
        def get_doc_side_effect(doctype, docname=None):
            if doctype == "Doc2Sys Settings":
                return mock_settings
            elif doctype == "Sales Invoice":
                return mock_sales_invoice
            elif doctype == "Item":
                return mock_item_doc
            elif doctype == "Customer":
                return mock_customer
            return MagicMock()
            
        mock_get_doc.side_effect = get_doc_side_effect
        mock_get_all.return_value = [mock_user_setting]
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that permissions are handled correctly
        self.assertEqual(mock_flags.ignore_permissions, False)
        
        # Assert that credits were updated
        mock_db_set_value.assert_called_once_with(
            "Doc2Sys User Settings", 
            "USR-SETTING-001", 
            "credits", 
            150.0  # 100 (original) + 50 (added)
        )
        
        # Assert that a message was displayed
        mock_msgprint.assert_called_once()
        self.assertIn("100", mock_msgprint.call_args[0][0])
        self.assertIn("150", mock_msgprint.call_args[0][0])
        
        # Assert log_error was not called
        mock_log_error.assert_not_called()

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_skip_if_not_receive_payment(self, mock_log_error, mock_get_doc, mock_flags):
        # Modify payment type to non-receive
        self.payment_entry.payment_type = "Pay"
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that the function returned early
        mock_get_doc.assert_not_called()
        mock_log_error.assert_not_called()

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_skip_if_not_customer(self, mock_log_error, mock_get_doc, mock_flags):
        # Modify party type to non-customer
        self.payment_entry.party_type = "Supplier"
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that the function returned early
        mock_get_doc.assert_not_called()
        mock_log_error.assert_not_called()

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_skip_if_no_references(self, mock_log_error, mock_get_doc, mock_flags):
        # Set empty references
        self.payment_entry.references = []
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that the function returned early
        mock_get_doc.assert_not_called()
        mock_log_error.assert_not_called()

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.log_error')
    def test_log_error_if_no_credits_item_group(self, mock_log_error, mock_get_doc, mock_flags):
        # Setup mock settings without credits_item_group
        mock_settings = MagicMock()
        mock_settings.credits_item_group = None
        mock_get_doc.return_value = mock_settings
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that error was logged
        mock_log_error.assert_called_once_with(
            "Credits item group not configured in Doc2Sys Settings",
            "Payment Credit Update Error"
        )

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.log_error')
    def test_skip_if_no_credit_items(self, mock_log_error, mock_get_all, mock_get_doc, mock_flags):
        # Setup mocks
        mock_settings = MagicMock()
        mock_settings.credits_item_group = "Credits"
        
        mock_item_doc = MagicMock()
        mock_item_doc.item_group = "Non-Credits"  # Different item group
        
        mock_invoice_item = MagicMock()
        mock_invoice_item.item_code = "ITEM-001"
        mock_invoice_item.net_amount = 50.0
        
        mock_sales_invoice = MagicMock()
        mock_sales_invoice.items = [mock_invoice_item]
        
        def get_doc_side_effect(doctype, docname=None):
            if doctype == "Doc2Sys Settings":
                return mock_settings
            elif doctype == "Sales Invoice":
                return mock_sales_invoice
            elif doctype == "Item":
                return mock_item_doc
            return MagicMock()
            
        mock_get_doc.side_effect = get_doc_side_effect
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that function exited early (get_all not called)
        mock_get_all.assert_not_called()

    @patch('frappe.flags', new_callable=MagicMock)
    @patch('frappe.get_doc')
    @patch('frappe.get_all')
    @patch('frappe.db.set_value')
    @patch('frappe.log_error')
    def test_handle_missing_user_settings(self, mock_log_error, mock_db_set_value, 
                                         mock_get_all, mock_get_doc, mock_flags):
        # Setup mocks for the error case
        mock_settings = MagicMock()
        mock_settings.credits_item_group = "Credits"
        
        mock_item_doc = MagicMock()
        mock_item_doc.item_group = "Credits"
        
        mock_invoice_item = MagicMock()
        mock_invoice_item.item_code = "ITEM-001"
        mock_invoice_item.net_amount = 50.0
        
        mock_sales_invoice = MagicMock()
        mock_sales_invoice.items = [mock_invoice_item]
        mock_sales_invoice.grand_total = 100.0
        
        mock_portal_user = MagicMock()
        mock_portal_user.user = "test@example.com"
        
        mock_customer = MagicMock()
        mock_customer.portal_users = [mock_portal_user]
        
        def get_doc_side_effect(doctype, docname=None):
            if doctype == "Doc2Sys Settings":
                return mock_settings
            elif doctype == "Sales Invoice":
                return mock_sales_invoice
            elif doctype == "Item":
                return mock_item_doc
            elif doctype == "Customer":
                return mock_customer
            return MagicMock()
            
        mock_get_doc.side_effect = get_doc_side_effect
        mock_get_all.return_value = []  # No user settings found
        
        # Call the function
        update_user_credits(self.payment_entry, "on_submit")
        
        # Assert that error was logged
        mock_log_error.assert_called_once()
        self.assertIn("No Doc2Sys User Settings found for user", mock_log_error.call_args[0][0])
        
        # Assert that credits were not updated
        mock_db_set_value.assert_not_called()