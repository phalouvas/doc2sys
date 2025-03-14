# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import os
import frappe
from frappe.model.document import Document
from doc2sys.engine.processor import DocumentProcessor
from doc2sys.engine.config import EngineConfig
from doc2sys.engine.exceptions import ProcessingError

class Doc2SysItem(Document):
    def validate(self):
        """Validate the document before saving"""
        if self.has_value_changed("single_file"):
            # Clear the existing file ID if file changed
            self.llm_file_id = ""
        self.process_attached_file()
    
    def process_attached_file(self):
        """Process the attached file and extract text"""
        if not self.single_file:
            return
            
        # Check if file has changed or text_content is empty
        if self.has_value_changed("single_file") or not self.text_content:
            try:
                # Get the full file path from the attached file
                file_doc = frappe.get_doc("File", {"file_url": self.single_file})
                if not file_doc:
                    frappe.msgprint("Could not find the attached file in the system")
                    return
                    
                file_path = file_doc.get_full_path()
                
                # Process the file and extract text
                success, message = self._process_file(file_path)
                
                # Add a message to notify the user
                frappe.msgprint(message)
                    
            except ProcessingError as e:
                frappe.log_error(f"Error processing document: {str(e)}")
                frappe.msgprint(f"Error processing document: {str(e)}")
            except IOError as e:
                frappe.log_error(f"File access error: {str(e)}")
                frappe.msgprint("Unable to access the document file. Please check if the file exists.")
            except Exception as e:
                frappe.log_error(f"Unexpected error: {str(e)}")
                frappe.msgprint(f"An unexpected error occurred while processing the document")
    
    def _process_file(self, file_path):
        """Internal method to process a file and extract text"""
        config = EngineConfig.from_settings()
        processor = DocumentProcessor(config)
        
        result = processor.process_document(file_path)
        
        if result and "extracted_text" in result:
            extracted_text = result['extracted_text']
            self.text_content = extracted_text
            
            # Process document content
            self.process_document(extracted_text)
            return True, f"Text extracted successfully from {os.path.basename(file_path)}"
        else:
            return False, "No text could be extracted from the document"
    
    def process_document(self, text):
        """Process document using LLM"""
        try:
            from doc2sys.engine.llm_processor import LLMProcessor
            
            # Use the factory method to get the appropriate processor
            processor = LLMProcessor.create()
            
            # Get file path again since we need to pass file directly to processor
            file_doc = frappe.get_doc("File", {"file_url": self.single_file})
            file_path = file_doc.get_full_path() if file_doc else None
            
            if file_path:
                # Upload file if not already uploaded or ID isn't stored
                if not self.llm_file_id:
                    file_id = processor.upload_file(file_path)
                    if file_id:
                        # Store the file ID for future use
                        self.llm_file_id = file_id
                
                # Get stored file_id or upload if necessary
                file_id = self.llm_file_id or processor.upload_file(file_path)
                
                # Store the file ID in the processor's cache to avoid duplicate uploads
                if file_id and file_path:
                    processor.file_cache[file_path] = file_id
            
            # Classify document using LLM with file path (preferred) or text (fallback)
            classification = processor.classify_document(file_path=file_path, text=text)
            doc_type = classification["document_type"]
            confidence = classification["confidence"]
            target_doctype = classification["target_doctype"]
            
            # Save classification results
            self.document_type = doc_type
            self.classification_confidence = confidence
            
            # Extract structured data if document type was identified
            if doc_type != "unknown":
                # Extract data using LLM, using the same file_path
                extracted_data = processor.extract_data(file_path=file_path, text=text, document_type=doc_type)
                
                # Store extracted data
                self.extracted_data = frappe.as_json(extracted_data)
                self.party_name = extracted_data.get("party_name")
                
                # Create ERPNext document if configured
                if self.auto_create_documents and target_doctype:
                    self.create_erpnext_document(target_doctype, extracted_data)
           
        except Exception as e:
            frappe.log_error(f"Document processing error: {str(e)}")
    
    def create_erpnext_document(self, target_doctype, data):
        """Create an ERPNext document based on extracted data"""
        # TODO: Implement document creation logic
        frappe.log_error("Document creation not yet implemented", "Doc2Sys")
        return

    @frappe.whitelist()
    def reprocess_document(self):
        """Reprocess the attached document to extract and analyze text again"""
        if not self.single_file:
            frappe.msgprint("No document is attached to reprocess")
            return
        
        try:
            frappe.msgprint("Reprocessing document...")
            
            # Get the full file path from the attached file
            file_doc = frappe.get_doc("File", {"file_url": self.single_file})
            if not file_doc:
                frappe.msgprint("Could not find the attached file in the system")
                return
                
            file_path = file_doc.get_full_path()
            
            # Clear the file ID to force a fresh upload
            self.llm_file_id = ""
            
            # Process the file and extract text
            success, message = self._process_file(file_path)
            
            # Save the document
            if success:
                self.save()
                
            # Add a message to notify the user
            frappe.msgprint(message)
                
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
