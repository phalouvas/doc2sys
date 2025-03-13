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
                
                # Initialize document processor with configuration
                config = EngineConfig.from_settings()
                processor = DocumentProcessor(config)
                
                # Process the document and extract text
                result = processor.process_document(file_path)
                
                # Update the text_content field
                if result and "extracted_text" in result:
                    # Get the full text, not just the truncated preview
                    extracted_text = self.get_full_extracted_text(file_path, processor)
                    self.text_content = extracted_text
                    
                    # Use NLP to classify and extract data
                    self.ml_process_document(extracted_text)
                    
                    # Add a message to notify the user
                    frappe.msgprint(f"Text extracted successfully from {os.path.basename(file_path)}")
                else:
                    frappe.msgprint("No text could be extracted from the document")
                    
            except ProcessingError as e:
                frappe.log_error(f"Error processing document: {str(e)}")
                frappe.msgprint(f"Error processing document: {str(e)}")
            except Exception as e:
                frappe.log_error(f"Unexpected error: {str(e)}")
                frappe.msgprint(f"An unexpected error occurred while processing the document")
    
    def get_full_extracted_text(self, file_path, processor):
        """Get the full extracted text from a document"""
        file_ext = os.path.splitext(file_path)[1].lower()[1:]
        
        # Extract raw text based on file type
        if file_ext == 'pdf':
            raw_text = processor._extract_text_from_pdf(file_path)
        elif file_ext in ['jpg', 'jpeg', 'png', 'tif', 'tiff', 'bmp']:
            raw_text = processor._extract_text_with_ocr(file_path)
        elif file_ext in ['txt', 'md', 'csv']:
            raw_text = processor._extract_text_from_text_file(file_path)
        elif file_ext in ['docx']:
            raw_text = processor._extract_text_from_docx(file_path)
        else:
            return "Unsupported file type for text extraction"
        
        # Clean up the text by removing multiple spaces and newlines
        import re
        cleaned_text = re.sub(r'\n+', '\n', raw_text)  # Replace multiple newlines with single newline
        cleaned_text = re.sub(r' +', ' ', cleaned_text)  # Replace multiple spaces with single space
        
        return cleaned_text.strip()
    
    def ml_process_document(self, text):
        """Process document using ML/NLP or LLM"""
        try:
            
            from doc2sys.engine.llm_processor import LLMProcessor
            
            # Use the factory method to get the appropriate processor
            processor = LLMProcessor.create()
            
            # Classify document using LLM
            classification = processor.classify_document(text)
            doc_type = classification["document_type"]
            confidence = classification["confidence"]
            target_doctype = classification["target_doctype"]
            
            # Save classification results
            self.document_type = doc_type
            self.classification_confidence = confidence
            
            # Extract structured data if document type was identified
            if doc_type != "unknown":
                # Extract data using LLM
                extracted_data = processor.extract_data(text, doc_type)
                
                # Store extracted data
                self.extracted_data = frappe.as_json(extracted_data)
                
                # Create ERPNext document if configured
                if self.auto_create_documents and target_doctype:
                    self.create_erpnext_document(target_doctype, extracted_data)
           
        except Exception as e:
            frappe.log_error(f"Document processing error: {str(e)}")
    
    def create_erpnext_document(self, target_doctype, data):
        pass

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
            
            # Initialize document processor with configuration
            config = EngineConfig.from_settings()
            processor = DocumentProcessor(config)
            
            # Process the document and extract text
            result = processor.process_document(file_path)
            
            # Update the text_content field
            if result and "extracted_text" in result:
                # Get the full text, not just the truncated preview
                extracted_text = self.get_full_extracted_text(file_path, processor)
                self.text_content = extracted_text
                
                # Use NLP to classify and extract data
                self.ml_process_document(extracted_text)
                
                # Save the document
                self.save()
                
                # Add a message to notify the user
                frappe.msgprint(f"Document reprocessed successfully: {os.path.basename(file_path)}")
            else:
                frappe.msgprint("No text could be extracted from the document during reprocessing")
                
        except ProcessingError as e:
            frappe.log_error(f"Error reprocessing document: {str(e)}")
            frappe.msgprint(f"Error reprocessing document: {str(e)}")
        except Exception as e:
            frappe.log_error(f"Unexpected error during reprocessing: {str(e)}")
            frappe.msgprint(f"An unexpected error occurred while reprocessing the document")
