# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import os
import frappe
from frappe.model.document import Document
from doc2sys.engine.processor import DocumentProcessor
from doc2sys.engine.config import EngineConfig
from doc2sys.engine.exceptions import ProcessingError
from doc2sys.engine.ml_classifier import MLDocumentClassifier
from doc2sys.engine.nlp_extractor import NLPDataExtractor

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
    
    def ml_process_document(self, text):
        """Process document using ML/NLP"""
        try:
            # Initialize ML classifier and NLP extractor
            classifier = MLDocumentClassifier()
            extractor = NLPDataExtractor()
            
            # Classify document
            classification = classifier.classify_document(text)
            doc_type = classification["document_type"]
            confidence = classification["confidence"]
            target_doctype = classification["target_doctype"]
            
            # Save classification results
            self.document_type = doc_type
            self.classification_confidence = confidence
            
            # Extract structured data if document type was identified
            if doc_type != "unknown":
                # Extract data using NLP
                extracted_data = extractor.extract_data(text, doc_type)
                
                # Store extracted data
                self.extracted_data = frappe.as_json(extracted_data)
                
                # Create ERPNext document if configured
                if self.auto_create_documents and target_doctype:
                    self.create_erpnext_document(target_doctype, extracted_data)
        
        except Exception as e:
            frappe.log_error(f"ML document processing error: {str(e)}")
    
    def create_erpnext_document(self, target_doctype, data):
        """Create an ERPNext document based on extracted data"""
        try:
            # Create new document
            new_doc = frappe.new_doc(target_doctype)
            
            # Get field mapping for this target doctype
            field_mapping = self._get_field_mapping(target_doctype)
            
            # Set mapped fields
            for doc2sys_field, erp_field in field_mapping.items():
                if doc2sys_field in data and data[doc2sys_field]:
                    # Set the field value
                    new_doc.set(erp_field, data[doc2sys_field])
            
            # Link back to Doc2Sys Item
            if hasattr(new_doc, "doc2sys_item"):
                new_doc.doc2sys_item = self.name
            
            # Insert document
            new_doc.insert(ignore_permissions=True)
            
            # Save document reference
            self.erpnext_document_type = target_doctype
            self.erpnext_document = new_doc.name
            
            frappe.msgprint(f"Created {target_doctype} {new_doc.name} from document")
            
            # Submit if configured to do so
            create_as_draft = frappe.db.get_single_value("Doc2Sys Settings", "create_as_draft")
            if not create_as_draft and hasattr(new_doc, "submit"):
                new_doc.submit()
                
        except Exception as e:
            frappe.log_error(f"Error creating {target_doctype}: {str(e)}")
            frappe.msgprint(f"Failed to create {target_doctype}: {str(e)}")
    
    def _get_field_mapping(self, target_doctype):
        """Get field mapping for target doctype"""
        mapping = {}
        try:
            # Get field mappings from Doc2Sys Field Mapping
            mappings = frappe.get_all("Doc2Sys Field Mapping",
                                     filters={"target_doctype": target_doctype},
                                     fields=["source_field", "target_field"])
            
            for field in mappings:
                mapping[field.source_field] = field.target_field
                
            return mapping
        except Exception as e:
            frappe.log_error(f"Error loading field mappings: {str(e)}")
            return {}

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
