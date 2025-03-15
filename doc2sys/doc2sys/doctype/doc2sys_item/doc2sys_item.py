# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import os
import frappe
from frappe.model.document import Document
from doc2sys.engine.exceptions import ProcessingError
from doc2sys.engine.llm_processor import LLMProcessor
import json

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
            
            # Explicitly save the document to persist token usage
            if success:
                # Use db_set to directly update fields without triggering validation
                for field in ["input_tokens", "output_tokens", "total_tokens", 
                             "input_cost", "output_cost", "total_cost"]:
                    self.db_set(field, self.get(field))
                    
                frappe.db.commit()  # Commit the changes to database
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
            # Reset token counts and costs
            self._reset_token_usage()
            
            # Get processor and upload file
            processor = self._get_processor_and_upload(file_path)
            if not processor:
                return False
            
            # Classify document
            classification = self._classify_document(processor, file_path)
            if not classification:
                return False
                
            # Extract data if possible
            if self.document_type != "unknown":
                self._extract_document_data(processor, file_path)
            
            return True
           
        except Exception as e:
            frappe.log_error(f"Document processing error: {str(e)}")
            return False

    def _get_processor_and_upload(self, file_path):
        """Get LLM processor and upload file if needed"""
        processor = LLMProcessor.create()
        
        # Upload file if not already uploaded or ID isn't stored
        if not self.llm_file_id:
            file_id = processor.upload_file(file_path)
            if file_id:
                # Store the file ID for future use
                self.llm_file_id = file_id
            else:
                return None
        
        # Get stored file_id and cache it
        file_id = self.llm_file_id
        if file_id and file_path:
            processor.file_cache[file_path] = file_id
            
        return processor

    def _classify_document(self, processor, file_path):
        """Classify document using LLM"""
        classification = processor.classify_document(file_path=file_path)
        
        # Update token usage from classification
        if "token_usage" in classification:
            self.update_token_usage(classification["token_usage"])
        
        # Save classification results
        self.document_type = classification.get("document_type")
        self.classification_confidence = classification.get("confidence")
        
        return classification

    def _extract_document_data(self, processor, file_path):
        """Extract structured data from document"""
        extracted_data = processor.extract_data(
            file_path=file_path, 
            document_type=self.document_type
        )
        
        # Update token usage from extraction
        if "_token_usage" in extracted_data:
            token_usage = extracted_data.pop("_token_usage", {})
            self.update_token_usage(token_usage)
        
        # Store extracted data
        self.extracted_data = frappe.as_json(extracted_data)
        self.party_name = extracted_data.get("party_name")
        
        # Create ERPNext document if configured
        target_doctype = getattr(self, "target_doctype", None)
        if self.auto_create_documents and target_doctype:
            self.create_erpnext_document(target_doctype, extracted_data)

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
            
            # Process the file directly with LLM
            success = self._process_file_with_llm(file_path)
            
            # Save the document
            if success:
                self.save()
                frappe.msgprint("Document reprocessed successfully")
            else:
                frappe.msgprint("Failed to reprocess document")
                
        except Exception as e:
            frappe.log_error(f"Reprocessing error: {str(e)}")
            frappe.msgprint(f"An error occurred while reprocessing: {str(e)}")

        return True

    def update_token_usage(self, token_usage):
        """
        Update token usage and cost fields
        
        Args:
            token_usage: Dictionary with token usage and cost information
        """
        if not token_usage:
            return
            
        try:
            # Ensure we have initial values
            if not self.input_tokens:
                self.input_tokens = 0
            if not self.output_tokens:
                self.output_tokens = 0
            if not self.total_tokens:
                self.total_tokens = 0
            if not self.input_cost:
                self.input_cost = 0.0
            if not self.output_cost:
                self.output_cost = 0.0
            if not self.total_cost:
                self.total_cost = 0.0
                
            # Add to existing counts
            self.input_tokens += token_usage.get("input_tokens", 0) or 0
            self.output_tokens += token_usage.get("output_tokens", 0) or 0
            self.total_tokens += token_usage.get("total_tokens", 0) or 0
            
            # Add to existing costs - ensure float conversion
            input_cost = float(token_usage.get("input_cost", 0.0) or 0.0)
            output_cost = float(token_usage.get("output_cost", 0.0) or 0.0)
            total_cost = float(token_usage.get("total_cost", 0.0) or 0.0)
            
            self.input_cost = float(self.input_cost) + input_cost
            self.output_cost = float(self.output_cost) + output_cost
            self.total_cost = float(self.total_cost) + total_cost
            
        except (TypeError, ValueError) as e:
            frappe.log_error(f"Error updating token usage - type/value error: {str(e)}")
        except Exception as e:
            frappe.log_error(f"Error updating token usage: {str(e)}")

    def process_document(self):
        """Process document with LLM classification and extraction"""
        processor = LLMProcessor.create()
        
        # Reset token counts and costs for fresh calculation
        self._reset_token_usage()
        
        # Classify document
        classification_result = processor.classify_document(
            file_path=self.single_file, 
            text=self.get_document_text()
        )
        
        # Store document type
        self.document_type = classification_result.get("document_type")
        self.classification_confidence = classification_result.get("confidence", 0.0)
        
        # Update token usage from classification
        token_usage = classification_result.get("token_usage", {})
        self.update_token_usage(token_usage)
        
        # If document type is known, extract data
        if self.document_type and self.document_type != "unknown":
            extraction_result = processor.extract_data(
                file_path=self.single_file,
                text=self.get_document_text(),
                document_type=self.document_type
            )
            
            # Update token usage from extraction
            token_usage = extraction_result.pop("_token_usage", {})  # Remove metadata
            self.update_token_usage(token_usage)
            
            # Store extraction results
            self.extracted_data = json.dumps(extraction_result)
            
            # Try to extract party name if available
            if "party_name" in extraction_result:
                self.party_name = extraction_result.get("party_name")
        
        # Save the document
        if self.docstatus == 0:  # Only if not submitted
            self.save()

    def _reset_token_usage(self):
        """Reset all token usage and cost fields to zero"""
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.input_cost = 0.0
        self.output_cost = 0.0
        self.total_cost = 0.0

    def get_document_text(self):
        """Get text content from the document if available"""
        # Implement based on your requirements
        # This method is called by process_document but not defined
        return ""

@frappe.whitelist()
def create_item_from_file(file_doc_name):
    """Create a Doc2Sys Item from an existing File document"""
    file_doc = frappe.get_doc("File", file_doc_name)
    if not file_doc:
        frappe.throw(_("File not found"))
    
    # Create new Doc2Sys Item with this file
    doc = frappe.new_doc("Doc2Sys Item")
    doc.single_file = file_doc.file_url
    doc.insert()
    
    return doc.name
