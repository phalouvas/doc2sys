# Copyright (c) 2025, KAINOTOMO PH LTD and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch, MagicMock
from unittest import skip  # Fixed import for skip decorator
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
