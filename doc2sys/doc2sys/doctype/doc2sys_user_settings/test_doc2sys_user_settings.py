# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock, call
from unittest import skip  # Fixed import for skip decorator
import unittest
import datetime
from doc2sys.doc2sys.doctype.doc2sys_user_settings.doc2sys_user_settings import (
    Doc2SysUserSettings,
    process_user_folder,
    test_integration,
    test_integration_user,
    delete_old_doc2sys_files,
    get_user_credits,
    get_quickbooks_auth_url,
    get_quickbooks_auth_url_for_user
)
from doc2sys.doc2sys.utils.payment_integration import update_user_credits


class TestDoc2SysUserSettings(FrappeTestCase):
    def setUp(self):
        # Create test user if it doesn't exist
        if not frappe.db.exists("User", "test_doc2sys@example.com"):
            frappe.get_doc({
                "doctype": "User",
                "email": "test_doc2sys@example.com",
                "first_name": "Test",
                "last_name": "Doc2Sys"
            }).insert(ignore_permissions=True)
            
        # Create Doc2Sys directory structure if it doesn't exist
        if not frappe.db.exists("File", {"is_folder": 1, "file_name": "Doc2Sys", "folder": "Home"}):
            doc = frappe.new_doc("File")
            doc.file_name = "Doc2Sys"
            doc.is_folder = 1
            doc.folder = "Home"
            doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
            
         # Check if settings for this user already exist and delete if found
        existing_settings = frappe.db.get_value("Doc2Sys User Settings", {"user": "test_doc2sys@example.com"})
        if existing_settings:
            frappe.delete_doc("Doc2Sys User Settings", existing_settings)
            
        # Create test settings document
        self.settings = frappe.get_doc({
            "doctype": "Doc2Sys User Settings",
            "user": "test_doc2sys@example.com",
            "monitor_interval": 10,
            "monitoring_enabled": 1,
            "folder_to_monitor": "/test/folder",
            "delete_old_files": 1,
            "days_to_keep_files": 30,
            "integration_type": "ERPNext",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "credits": 100
        })
        self.settings.insert(ignore_permissions=True)
        
    def tearDown(self):
        # Delete test settings
        if frappe.db.exists("Doc2Sys User Settings", {"user": "test_doc2sys@example.com"}):
            frappe.delete_doc("Doc2Sys User Settings", 
                            frappe.get_value("Doc2Sys User Settings", {"user": "test_doc2sys@example.com"}))
                            
        # Remove test user folder
        user_folder = frappe.db.get_value("File", 
                                        {"is_folder": 1, "file_name": "test_doc2sys@example.com", 
                                        "folder": "Home/Doc2Sys"})
        if user_folder:
            frappe.delete_doc("File", user_folder)
            
    def test_validate_with_valid_settings(self):
        """Test validate method with valid settings"""
        # Should not throw any exceptions
        self.settings.monitor_interval = 15
        self.settings.validate()
        self.assertEqual(self.settings.monitor_interval, 15)
        
    def test_validate_with_invalid_monitor_interval(self):
        """Test validate method with invalid monitor interval"""
        self.settings.monitor_interval = 0
        with self.assertRaises(frappe.ValidationError):
            self.settings.validate()
            
    def test_ensure_user_folder_exists_creates_folder(self):
        """Test that ensure_user_folder_exists creates user folder if it doesn't exist"""
        # First, make sure the folder doesn't exist
        user_folder = frappe.db.get_value("File", 
                                        {"is_folder": 1, "file_name": "test_doc2sys@example.com", 
                                        "folder": "Home/Doc2Sys"})
        if user_folder:
            frappe.delete_doc("File", user_folder)
            
        # Call the method
        self.settings.ensure_user_folder_exists()
        
        # Check that folder now exists
        self.assertTrue(frappe.db.exists("File", 
                                        {"is_folder": 1, "file_name": "test_doc2sys@example.com", 
                                        "folder": "Home/Doc2Sys"}))
    
    def test_create_new_folder(self):
        """Test that create_new_folder creates a new folder"""
        # Make sure test folder doesn't exist
        test_folder = frappe.db.get_value("File", 
                                        {"is_folder": 1, "file_name": "test_folder", 
                                        "folder": "Home"})
        if test_folder:
            frappe.delete_doc("File", test_folder)
            
        # Create the folder
        file_doc = self.settings.create_new_folder("test_folder", "Home")
        
        # Verify folder was created
        self.assertTrue(frappe.db.exists("File", {"name": file_doc.name}))
        self.assertEqual(file_doc.file_name, "test_folder")
        self.assertEqual(file_doc.folder, "Home")
        self.assertTrue(file_doc.is_folder)
        
        # Clean up
        frappe.delete_doc("File", file_doc.name)
        
    @skip("Skipping folder monitor test")
    @patch("doc2sys.doc2sys.tasks.folder_monitor.process_folder")
    def test_process_user_folder_success(self, mock_process_folder):
        """Test process_user_folder with successful processing"""
        # Setup mock
        mock_process_folder.return_value = {"processed": 5}
        
        # Call the function
        result = process_user_folder(self.settings.name)
        
        # Verify results
        self.assertTrue(result["success"])
        self.assertIn("Processed 5 files", result["message"])
        mock_process_folder.assert_called_once_with(self.settings.folder_to_monitor, self.settings)
        
    def test_process_user_folder_monitoring_disabled(self):
        """Test process_user_folder with monitoring disabled"""
        # Disable monitoring
        self.settings.monitoring_enabled = 0
        self.settings.save()
        
        # Call the function
        result = process_user_folder(self.settings.name)
        
        # Verify results
        self.assertFalse(result["success"])
        self.assertIn("not properly configured", result["message"])
        
    @skip("Skipping folder monitor test")
    @patch("doc2sys.doc2sys.tasks.folder_monitor.process_folder")
    def test_process_user_folder_exception(self, mock_process_folder):
        """Test process_user_folder with an exception"""
        # Setup mock
        mock_process_folder.side_effect = Exception("Test error")
        
        # Call the function
        result = process_user_folder(self.settings.name)
        
        # Verify results
        self.assertFalse(result["success"])
        self.assertIn("Error: Test error", result["message"])
        
    def test_get_user_credits_with_valid_user(self):
        """Test get_user_credits with a valid user"""
        # Call the function
        result = get_user_credits("test_doc2sys@example.com")
        
        # Verify results
        self.assertTrue(result["success"])
        self.assertEqual(result["credits"], 100)
        self.assertEqual(result["settings_id"], self.settings.name)
        
    def test_get_user_credits_with_invalid_user(self):
        """Test get_user_credits with an invalid user"""
        # Call the function
        result = get_user_credits("nonexistent_user@example.com")
        
        # Verify results
        self.assertFalse(result["success"])
        self.assertEqual(result["credits"], 0)
        self.assertIn("not found", result["message"])


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
