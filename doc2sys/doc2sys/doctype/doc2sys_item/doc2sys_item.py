# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
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

        status = None

        if self.single_file_name:
            status = "Uploaded"

        if self.azure_raw_response:
            status = "Processed"

        if status and self.status != "Completed":
            self.db_set('status', status, update_modified=False)

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
