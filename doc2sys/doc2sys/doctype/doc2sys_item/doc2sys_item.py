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
from frappe.desk.form.utils import remove_attach  # Add this import

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
                frappe.throw(_("Could not find the file path"))
            
            # Get processor and upload file only if needed
            processor = LLMProcessor(doc2sys_item=self)
            if not processor:
                frappe.throw(_("Could not initialize document processor"))
            
            # Extract data using the appropriate document type
            # Use the document_type field from the DocType
            document_type = self.document_type or "prebuilt-invoice"  # Default to invoice if not specified
            extracted_data = processor.extract_data(file_path=file_path, document_type=document_type)
            
            if extracted_data:
                # Update status to indicate extraction is complete
                self.db_set('status', 'Processed', update_modified=True)
                
                file_doc = frappe.get_all(
                    "File", 
                    filters={
                        "attached_to_doctype": "Doc2Sys Item",
                        "attached_to_name": self.name
                    },
                    fields=["name"]
                )

                if not file_doc or len(file_doc) == 0:
                    files_not_found += 1
                    frappe.db.commit()
                    return True
                
                frappe.form_dict["dn"] = self.name
                frappe.form_dict["dt"] = "Doc2Sys Item"
                frappe.form_dict["fid"] = file_doc[0].name
                
                # Remove the attachment using the file ID
                remove_attach()
                
                # Clear the single_file field and single_file_name
                self.db_set('single_file', '', update_modified=True)
                self.db_set('single_file_name', '', update_modified=True)
                
                frappe.db.commit()
                return True
            else:
                frappe.msgprint(_("No data could be extracted from the document"))
                return False
        
        except Exception as e:
            error_message = f"Error extracting data: {str(e)}"
            frappe.log_error(error_message, _("Document Extraction Error"))
            frappe.msgprint(_(error_message))
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
