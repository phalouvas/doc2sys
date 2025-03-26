# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
import time
from frappe.model.document import Document
from doc2sys.engine.exceptions import ProcessingError
from frappe import _
from doc2sys.engine.llm_processor import LLMProcessor
from doc2sys.engine.text_extractor import TextExtractor
from doc2sys.integrations.utils import process_integrations
from frappe.handler import upload_file

class Doc2SysItem(Document):
    def validate(self):
        if self.single_file:
            self.single_file_name = self.single_file.split("/")[-1]
            self.update_status()

    def after_insert(self):
        """Validate the document before saving"""
        # Set default user if not specified
        if not self.user:
            self.user = frappe.session.user
            
        if self.single_file:
            self.process_all()
      
    def _get_file_path(self):
        """Helper method to get file path from single_file URL"""
        if not self.single_file:
            return None
            
        file_doc = frappe.get_doc("File", {"file_url": self.single_file})
        if not file_doc:
            frappe.msgprint("Could not find the attached file in the system")
            return None
        
        return file_doc.get_full_path()
    
    @frappe.whitelist()
    def extract_data(self):
        if not self.single_file:
            frappe.msgprint("No document is attached to extract data from")
            return False
        
        try:
            file_path = self._get_file_path()
            if not file_path:
                return False
            
            # Get processor and upload file only if needed
            processor = LLMProcessor(doc2sys_item=self)
            if not processor:
                frappe.msgprint("Failed to initialize document processor")
                return False
            
            # Extract data using the classified document type
            processor.extract_data(
                file_path=file_path, 
                document_type=self.document_type
            )

            self.update_status()
            
            return True
        
        except Exception as e:
            frappe.log_error(f"Data extraction error: {str(e)}")
            frappe.msgprint(f"An error occurred during data extraction: {str(e)}")
            return False

    def update_status(self):

        status = "Pending"

        if self.single_file_name:
            status = "Uploaded"

        if self.extracted_data:
            status = "Processed"

        if status == "Processed" and self.status != "Completed":
            integration_status = self.get_integration_status()
            if all([i["status"] == "success" for i in integration_status]):
                status = "Completed"

        if status != self.status:
            self.db_set('status', status, update_modified=False)

    def get_integration_status(self):
        """Get status of integrations for this document"""
        if not self.name:
            return []
            
        # Query integration logs for this document using the direct link field
        logs = frappe.get_all(
            "Doc2Sys Integration Log",
            filters={"document": self.name},  # Use the document field directly
            fields=["integration_type", "status", "message", "creation", "integration_reference", "name"],
            order_by="creation desc"
        )
        
        # Get user's configured integrations
        user_settings = frappe.get_all(
            "Doc2Sys User Settings",
            filters={"user": self.user},
            fields=["name"]
        )
        
        all_integrations = []
        if user_settings:
            # Get all integrations configured for this user
            settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings[0].name)
            all_integrations = [i.integration_type for i in settings_doc.user_integrations if i.enabled]
        
        # Group by integration_type and get the latest status
        integration_status = {}
        for log in logs:
            integration_type = log.integration_type
            if integration_type not in integration_status:
                integration_status[integration_type] = {
                    "integration_type": integration_type,
                    "status": log.status,
                    "message": log.message,
                    "timestamp": log.creation,
                    "integration_reference": log.integration_reference,
                    "log_name": log.name
                }
        
        # Add configured integrations that don't have logs yet
        for integration_type in all_integrations:
            if integration_type not in integration_status:
                integration_status[integration_type] = {
                    "integration_type": integration_type,
                    "status": "pending",
                    "message": "Not yet processed",
                    "timestamp": None,
                    "integration_reference": None,
                    "log_name": None
                }
        
        return list(integration_status.values())

    @frappe.whitelist()
    def trigger_integrations(self):
        
        try:
            process_integrations(self)
            self.update_status()
            return True
        except Exception as e:
            frappe.log_error(f"Integration processing error: {str(e)}")
            frappe.msgprint(f"An error occurred during integration processing: {str(e)}")
            return False


    @frappe.whitelist()
    def process_all(self):
        if not self.single_file:
            frappe.msgprint("No document is attached to process")
            return False
            
        try:
            success = self.extract_data()
            if success:
                process_integrations(self)
                self.update_status()
                return True
            else:
                return False
                
        except Exception as e:
            frappe.log_error(f"Process all error: {str(e)}")
            frappe.msgprint(f"An error occurred during processing: {str(e)}")
            return False

    def on_trash(self):
        """Delete all related integration logs when the document is deleted"""
        try:
            # Find all integration logs linked to this document
            integration_logs = frappe.get_all(
                "Doc2Sys Integration Log", 
                filters={"document": self.name},
                pluck="name"
            )
            
            # Delete each log
            for log_name in integration_logs:
                frappe.delete_doc("Doc2Sys Integration Log", log_name, ignore_permissions=True)
                
            frappe.logger().info(f"Deleted {len(integration_logs)} integration logs for document {self.name}")
        except Exception as e:
            frappe.log_error(f"Failed to delete integration logs for document {self.name}: {str(e)}")

@frappe.whitelist()
def create_item_from_file(file_doc_name):
    """Create a Doc2Sys Item from an existing File document"""
    file_doc = frappe.get_doc("File", file_doc_name)
    if not file_doc:
        frappe.throw(_("File not found"))
    
    # Create new Doc2Sys Item with this file
    doc = frappe.new_doc("Doc2Sys Item")
    doc.single_file = file_doc.file_url
    doc.user = frappe.session.user
    doc.insert()
    
    return doc.name
