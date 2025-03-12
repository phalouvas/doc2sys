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
                    self.text_content = self.get_full_extracted_text(file_path, processor)
                    
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
        
        if file_ext == 'pdf':
            return processor._extract_text_from_pdf(file_path)
        elif file_ext in ['jpg', 'jpeg', 'png', 'tif', 'tiff', 'bmp']:
            return processor._extract_text_with_ocr(file_path)
        elif file_ext in ['txt', 'md', 'csv']:
            return processor._extract_text_from_text_file(file_path)
        elif file_ext in ['docx']:
            return processor._extract_text_from_docx(file_path)
        else:
            return "Unsupported file type for text extraction"
