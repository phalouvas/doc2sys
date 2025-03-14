# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import os
import frappe
from frappe.model.document import Document
from doc2sys.engine.exceptions import ProcessingError

class Doc2SysItem(Document):
    def validate(self):
        """Validate the document before saving"""
        if self.has_value_changed("single_file"):
            # Clear the existing file ID if file changed
            self.llm_file_id = ""
            self.process_attached_file()
    
    def process_attached_file(self):
        """Process the attached file"""
        if not self.single_file:
            return
            
        try:
            # Get the full file path from the attached file
            file_doc = frappe.get_doc("File", {"file_url": self.single_file})
            if not file_doc:
                frappe.msgprint("Could not find the attached file in the system")
                return
                
            file_path = file_doc.get_full_path()
            
            # Process the file directly with LLM
            success = self._process_file_with_llm(file_path)
            
            if success:
                frappe.msgprint(f"Document processed successfully")
            else:
                frappe.msgprint("Failed to process document")
                
        except ProcessingError as e:
            frappe.log_error(f"Error processing document: {str(e)}")
            frappe.msgprint(f"Error processing document: {str(e)}")
        except IOError as e:
            frappe.log_error(f"File access error: {str(e)}")
            frappe.msgprint("Unable to access the document file. Please check if the file exists.")
        except Exception as e:
            frappe.log_error(f"Unexpected error: {str(e)}")
            frappe.msgprint(f"An unexpected error occurred while processing the document")
    
    def _process_file_with_llm(self, file_path):
        """Process file directly with LLM without extracting text"""
        try:
            from doc2sys.engine.llm_processor import LLMProcessor
            
            # Use the factory method to get the appropriate processor
            processor = LLMProcessor.create()
            
            # Upload file if not already uploaded or ID isn't stored
            if not self.llm_file_id:
                file_id = processor.upload_file(file_path)
                if file_id:
                    # Store the file ID for future use
                    self.llm_file_id = file_id
                else:
                    return False
            
            # Get stored file_id
            file_id = self.llm_file_id
            
            # Store the file ID in the processor's cache to avoid duplicate uploads
            if file_id and file_path:
                processor.file_cache[file_path] = file_id
            
            # Classify document using LLM with file path
            classification = processor.classify_document(file_path=file_path)
            doc_type = classification["document_type"]
            confidence = classification["confidence"]
            target_doctype = classification["target_doctype"]
            
            # Save classification results
            self.document_type = doc_type
            self.classification_confidence = confidence
            
            # Extract structured data if document type was identified
            if doc_type != "unknown":
                # Extract data using LLM, using the file path
                extracted_data = processor.extract_data(file_path=file_path, document_type=doc_type)
                
                # Store extracted data
                self.extracted_data = frappe.as_json(extracted_data)
                self.party_name = extracted_data.get("party_name")
                
                # Create ERPNext document if configured
                if self.auto_create_documents and target_doctype:
                    self.create_erpnext_document(target_doctype, extracted_data)
            
            return True
           
        except Exception as e:
            frappe.log_error(f"Document processing error: {str(e)}")
            return False
    
    def create_erpnext_document(self, target_doctype, data):
        """Create an ERPNext document based on extracted data"""
        # TODO: Implement document creation logic
        frappe.log_error("Document creation not yet implemented", "Doc2Sys")
        return

    @frappe.whitelist()
    def reprocess_document(self):
        """Reprocess the attached document"""
        if not self.single_file:
            frappe.msgprint("No document is attached to reprocess")
            return
        
        try:
            frappe.msgprint("Reprocessing document...")
            
            # Get the full file path from the attached file (needed for cache lookup)
            file_doc = frappe.get_doc("File", {"file_url": self.single_file})
            if not file_doc:
                frappe.msgprint("Could not find the attached file in the system")
                return
                
            file_path = file_doc.get_full_path()
            
            # Only clear the file ID if explicitly requested or if there's no file ID
            # self.llm_file_id = ""  # Remove this line - we want to keep the ID
            
            # Process the file directly with LLM
            success = self._process_file_with_llm(file_path)
            
            # Save the document
            if success:
                self.save()
                frappe.msgprint("Document reprocessed successfully")
            else:
                frappe.msgprint("Failed to reprocess document")
                
        except ProcessingError as e:
            frappe.log_error(f"Error reprocessing document: {str(e)}")
            frappe.msgprint(f"Error reprocessing document: {str(e)}")
        except IOError as e:
            frappe.log_error(f"File access error: {str(e)}")
            frappe.msgprint("Unable to access the document file. Please check if the file exists.")
        except Exception as e:
            frappe.log_error(f"Unexpected error during reprocessing: {str(e)}")
            frappe.msgprint(f"An unexpected error occurred while reprocessing the document")

        return True
