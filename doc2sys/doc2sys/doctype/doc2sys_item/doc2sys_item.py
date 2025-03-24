# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import os
import frappe
import time
from frappe.model.document import Document
from doc2sys.engine.exceptions import ProcessingError
from frappe import _
from doc2sys.engine.llm_processor import LLMProcessor
from doc2sys.engine.text_extractor import TextExtractor
from doc2sys.integrations.events import trigger_integrations_on_update
from frappe.handler import upload_file
import json

class Doc2SysItem(Document):
    def validate(self):
        """Validate the document before saving"""
        # Set default user if not specified
        if not self.user:
            self.user = frappe.session.user
            
        if self.has_value_changed("single_file"):
            # Clear the existing file ID if file changed
            self.llm_file_id = ""
            # Only process file if auto_process_file is checked
            if self.auto_process_file:
                # Reset token counts and costs for data extraction
                self.process_attached_file()
    
    def process_attached_file(self):
        """Process the attached file"""
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('process_attached_file')
        
        try:
            if not self.single_file:
                return
                
            try:
                # Get the full file path from the attached file
                file_path = self._get_file_path()
                if not file_path:
                    return
                
                # Process the file directly with LLM
                success = self._process_file_with_llm(file_path)
                
                # Explicitly save the document to persist token usage
                if success:
                    # Use db_set to directly update fields without triggering validation
                    for field in ["input_tokens", "output_tokens", "total_tokens", 
                                "input_cost", "output_cost", "total_cost", "extracted_text"]:
                        self.db_set(field, self.get(field))
                    
                    # Call the integration function directly instead of enqueueing it
                    trigger_integrations_on_update(self, True)
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
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)
    
    def _process_file_with_llm(self, file_path):
        """Process file with LLM after extracting text"""
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('_process_file_with_llm')
        
        try:
            # Step 1: Extract text
            extracted_text = self.get_document_text(file_path)
            self.extracted_text = extracted_text
            
            # Step 2: Get processor and upload file if needed
            processor = self._get_processor_and_upload(file_path, extracted_text)
            if not processor:
                return False
            
            # Step 3: Classify document
            classification = self._classify_document(processor, file_path, extracted_text)
            if not classification:
                return False
                
            # Step 4: Extract data if possible
            if self.document_type and self.document_type != "unknown":
                self._extract_document_data(processor, file_path, extracted_text)
            
            return True
        except ProcessingError as e:
            frappe.log_error(f"LLM processing error: {str(e)}")
            return False
        except IOError as e:
            frappe.log_error(f"File access error: {str(e)}")
            return False
        except Exception as e:
            frappe.log_error(f"Document processing error: {str(e)}")
            return False
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # Pass True if this was called by an even higher-level method
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)

    def _get_processor_and_upload(self, file_path, extracted_text=None):
        """Get LLM processor and upload file if needed
        
        Args:
            file_path: Path to the document file
            extracted_text: Already extracted text content (if available)
            
        Returns:
            LLMProcessor: The processor instance
        """
        # Create processor with user-specific settings
        processor = LLMProcessor(user=self.user)
        
        # Skip file upload if we have sufficient extracted text
        if extracted_text and len(extracted_text) > 100:
            frappe.log_error("Using extracted text instead of uploading file", "Doc2Sys")
            return processor
        
        # Upload file only if not already uploaded or ID isn't stored
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

    def _classify_document(self, processor, file_path, extracted_text=None):
        """Classify document using LLM with extracted text"""
        start_time = time.time()
        
        # Add to timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('_classify_document')
        
        try:
            classification = processor.classify_document(file_path=file_path, text=extracted_text)
            
            # Update token usage from classification
            if "token_usage" in classification:
                self.update_token_usage(classification["token_usage"])
            
            # Save classification results
            self.document_type = classification.get("document_type")
            self.classification_confidence = classification.get("confidence")
            
            return classification
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # Always pass True for is_child_operation since this is always called from other methods
            self.update_processing_duration(duration, is_child_operation=True)

    def _extract_document_data(self, processor, file_path, extracted_text=None):
        """Extract structured data from document with extracted text"""
        start_time = time.time()
        
        # Add to timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('_extract_document_data')
        
        try:
            extracted_data = processor.extract_data(
                file_path=file_path, 
                text=extracted_text,
                document_type=self.document_type
            )
            
            # Update token usage from extraction
            if "_token_usage" in extracted_data:
                token_usage = extracted_data.pop("_token_usage", {})
                self.update_token_usage(token_usage)
            
            # Store extracted data
            self.extracted_data = frappe.as_json(extracted_data, 1, None, False)
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # Always pass True for is_child_operation since this is always called from other methods
            self.update_processing_duration(duration, is_child_operation=True)

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

    def update_processing_duration(self, duration_seconds, is_child_operation=False):
        """
        Update the total processing duration, avoiding double-counting
        
        Args:
            duration_seconds: Duration in seconds to add to the total
            is_child_operation: If True, the timing is from a child operation and may 
                                already be counted in a parent operation's timing
        """
        if not duration_seconds:
            return
            
        # Track which operations are counting duration to avoid double-counting
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
            
        # If this is a child operation and we're already timing a parent operation,
        # don't add the duration (as the parent will include this time)
        if is_child_operation and self._timing_stack:
            return
            
        try:
            # Ensure we have initial values
            if not self.total_duration:
                self.total_duration = 0.0
                
            # Add to existing duration - ensure float conversion
            self.total_duration = float(self.total_duration) + float(duration_seconds)
            
        except (TypeError, ValueError) as e:
            frappe.log_error(f"Error updating duration - type/value error: {str(e)}")
        except Exception as e:
            frappe.log_error(f"Error updating duration: {str(e)}")

    def process_document(self):
        """Process document with LLM classification and extraction"""
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('process_document')
        
        try:
            if not self.single_file:
                frappe.msgprint("No document is attached to process")
                return False
                
            try:
                # Get the full file path from the attached file
                file_path = self._get_file_path()
                if not file_path:
                    return False
                    
                # Process the file with all LLM operations using the existing method
                success = self._process_file_with_llm(file_path)
                
                # Save the document if not submitted and processing was successful
                if success and self.docstatus == 0:
                    self.save()
                    
                return success
                    
            except Exception as e:
                frappe.log_error(f"Document processing error: {str(e)}")
                frappe.msgprint(f"An error occurred during processing: {str(e)}")
                return False
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)

    def _get_file_path(self):
        """Helper method to get file path from single_file URL"""
        if not self.single_file:
            return None
            
        file_doc = frappe.get_doc("File", {"file_url": self.single_file})
        if not file_doc:
            frappe.msgprint("Could not find the attached file in the system")
            return None
        
        return file_doc.get_full_path()
    
    def get_document_text(self, file_path=None):
        """Get text content from the document if available"""
        start_time = time.time()
        
        # Add self to the timing stack to track nested operations
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('get_document_text')
        
        try:
            if not file_path and self.single_file:
                # Get the path using helper method
                file_path = self._get_file_path()
            
            if not file_path:
                return ""
            
            try:
                # Initialize TextExtractor with user-specific settings
                extractor = TextExtractor(user=self.user)
                
                # Extract text from the file
                extracted_text = extractor.extract_text(file_path)
                
                return extracted_text
            except Exception as e:
                frappe.log_error(f"Text extraction error: {str(e)}", "Doc2Sys")
                return ""
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
            
            # Only track time if we actually attempted extraction
            if file_path:
                duration = time.time() - start_time
                # Pass True for is_child_operation if this was called from another timed method
                is_child = len(self._timing_stack) > 0
                self.update_processing_duration(duration, is_child_operation=is_child)

    @frappe.whitelist()
    def extract_text_only(self):
        """Extract text from the attached document without LLM processing"""
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('extract_text_only')
        
        try:
            if not self.single_file:
                frappe.msgprint("No document is attached to extract text from")
                return False
            
            try:
                file_path = self._get_file_path()
                if not file_path:
                    return False
                    
                # Extract text from the file - pass user for user-specific settings
                extracted_text = self.get_document_text(file_path)
                
                # Store the extracted text in the document
                self.extracted_text = extracted_text
                
                # Save the document to persist the extracted text
                self.save()
                
                return True
                
            except Exception as e:
                frappe.log_error(f"Text extraction error: {str(e)}")
                frappe.msgprint(f"An error occurred while extracting text: {str(e)}")
                return False
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)

    @frappe.whitelist()
    def classify_document_only(self):
        """Classify the attached document without extracting data"""
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('classify_document_only')
        
        try:
            if not self.single_file:
                frappe.msgprint("No document is attached to classify")
                return False
            
            try:
                frappe.msgprint("Classifying document...")
                
                file_path = self._get_file_path()
                if not file_path:
                    return False
                    
                # Extract text if not already extracted
                if not self.extracted_text:
                    extracted_text = self.get_document_text(file_path)
                    self.extracted_text = extracted_text
                else:
                    extracted_text = self.extracted_text
                
                # Get processor and upload file only if needed
                processor = self._get_processor_and_upload(file_path, extracted_text)
                if not processor:
                    frappe.msgprint("Failed to initialize document processor")
                    return False
                
                # Classify document with extracted text
                classification = self._classify_document(processor, file_path, extracted_text)
                if not classification:
                    frappe.msgprint("Classification failed")
                    return False
                
                # Save the document
                self.save()
                frappe.msgprint(f"Document classified as: {self.document_type} (confidence: {self.classification_confidence})")
                return True
            
            except Exception as e:
                frappe.log_error(f"Classification error: {str(e)}")
                frappe.msgprint(f"An error occurred during classification: {str(e)}")
                return False
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)

    @frappe.whitelist()
    def extract_data_only(self):
        """Extract data from the attached document based on its classification"""
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('extract_data_only')
        
        try:
            if not self.single_file:
                frappe.msgprint("No document is attached to extract data from")
                return False
            
            if not self.document_type or self.document_type == "unknown":
                frappe.msgprint("Document must be classified before extracting data")
                return False
            
            try:
                frappe.msgprint("Extracting data from document...")
                
                file_path = self._get_file_path()
                if not file_path:
                    return False
                    
                # Use existing extracted text or extract it
                if not self.extracted_text:
                    extracted_text = self.get_document_text(file_path)
                    self.extracted_text = extracted_text
                else:
                    extracted_text = self.extracted_text
                
                # Get processor and upload file only if needed
                processor = self._get_processor_and_upload(file_path, extracted_text)
                if not processor:
                    frappe.msgprint("Failed to initialize document processor")
                    return False
                
                # Extract data using the classified document type
                self._extract_document_data(processor, file_path, extracted_text)
                
                # Save the document
                self.save()
                frappe.msgprint("Data extraction completed")
                return True
            
            except Exception as e:
                frappe.log_error(f"Data extraction error: {str(e)}")
                frappe.msgprint(f"An error occurred during data extraction: {str(e)}")
                return False
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)

    @frappe.whitelist()
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
    def process_all(self):
        """Process the document with all steps: extract text, classify, extract data, and trigger integrations"""
        start_time = time.time()
        
        # Initialize timing stack if needed
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('process_all')
        
        try:
            if not self.single_file:
                frappe.msgprint("No document is attached to process")
                return False
                
            try:
                frappe.msgprint("Processing document with all steps...")
                
                # Use the consolidated process_document method
                success = self.process_document()
                
                # If successful, trigger integrations
                if success:
                    trigger_integrations_on_update(self, True)
                    
                    frappe.msgprint("Document processed and integrations triggered")
                    return True
                else:
                    return False
                    
            except Exception as e:
                frappe.log_error(f"Process all error: {str(e)}")
                frappe.msgprint(f"An error occurred during processing: {str(e)}")
                return False
                
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0  
            self.update_processing_duration(duration, is_child_operation=is_child)

    def _process_document_with_steps(self, steps=None):
        """
        Process document with specified steps
        
        Args:
            steps: List of steps to perform ('extract_text', 'classify', 'extract_data', 'trigger_integrations')
                If None, all steps are performed
        
        Returns:
            bool: True if processing was successful
        """
        start_time = time.time()
        
        # Add self to the timing stack
        if not hasattr(self, '_timing_stack'):
            self._timing_stack = []
        self._timing_stack.append('_process_document_with_steps')
        
        try:
            if not steps:
                steps = ['extract_text', 'classify', 'extract_data', 'trigger_integrations']
                
            if not self.single_file:
                frappe.msgprint("No document is attached to process")
                return False
                
            try:            
                # Get the full file path from the attached file
                file_path = self._get_file_path()
                if not file_path:
                    return False
                
                # Step 1: Extract text if needed
                if 'extract_text' in steps:
                    extracted_text = self.get_document_text(file_path)
                    self.extracted_text = extracted_text
                else:
                    extracted_text = self.extracted_text
                
                # Step 2: Get processor and upload file if needed
                processor = self._get_processor_and_upload(file_path, extracted_text)
                if not processor:
                    return False
                    
                # Step 3: Classify document if needed
                if 'classify' in steps:
                    classification = self._classify_document(processor, file_path, extracted_text)
                    if not classification:
                        return False
                        
                # Step 4: Extract data if needed
                if 'extract_data' in steps and self.document_type and self.document_type != "unknown":
                    self._extract_document_data(processor, file_path, extracted_text)
                
                # Step 5: Save the document if successful
                self.save()
                
                # Step 6: Trigger integrations if needed
                if 'trigger_integrations' in steps:
                    trigger_integrations_on_update(self, True)
                    
                return True
                    
            except Exception as e:
                frappe.log_error(f"Document processing error: {str(e)}")
                frappe.msgprint(f"An error occurred during processing: {str(e)}")
                return False
        finally:
            # Remove from timing stack
            if self._timing_stack:
                self._timing_stack.pop()
                
            duration = time.time() - start_time
            # When timing stack is empty, this is a root operation
            is_child = len(self._timing_stack) > 0
            self.update_processing_duration(duration, is_child_operation=is_child)

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
    def reset_usage_metrics(self):
        """Reset all token usage and duration metrics to zero"""
        try:
            # Reset token usage metrics
            self.input_tokens = 0
            self.output_tokens = 0
            self.total_tokens = 0
            self.input_cost = 0.0
            self.output_cost = 0.0
            self.total_cost = 0.0
            self.total_duration = 0.0
            
            # Save the document to persist changes
            self.save()
            
            frappe.msgprint(_("Usage metrics have been reset successfully"))
            return True
        except Exception as e:
            frappe.log_error(f"Error resetting usage metrics: {str(e)}")
            frappe.msgprint(_("An error occurred while resetting metrics"))
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
    # Set the current user as the document owner
    doc.user = frappe.session.user
    doc.insert()
    
    return doc.name

# Add this function after the create_item_from_file function

@frappe.whitelist()
def upload_and_create_item():
    """
    Upload a file and create a Doc2Sys Item in one step.
    
    This endpoint accepts multipart/form-data with a file field.
    Returns the newly created Doc2Sys Item document name.
    """
    try:
        # Get the uploaded file from request
        if not frappe.request.files or 'file' not in frappe.request.files:
            frappe.throw(_("No file attached"))
        
        # Save original form values before they get consumed by upload_file
        is_private = frappe.form_dict.get('is_private')
        auto_process_file = frappe.form_dict.get('auto_process_file')
        
        # Ensure proper type conversion for is_private
        if is_private is not None:
            if is_private in ("1", "true", "True", "yes", "Yes"):
                frappe.form_dict["is_private"] = 1
            else:
                frappe.form_dict["is_private"] = 0
        
        # First, upload the file using Frappe's handler
        ret = upload_file()
        
        if not ret:
            frappe.throw(_("Failed to upload file"))
            
        # Create Doc2Sys Item with this file
        doc = frappe.new_doc("Doc2Sys Item")
        doc.single_file = ret.get("file_url")
        doc.user = frappe.session.user
        
        # Set auto_process_file with proper type conversion
        if auto_process_file:
            # Convert string values like "0", "1" to actual booleans
            if auto_process_file in ("1", "true", "True", "yes", "Yes"):
                doc.auto_process_file = 1
            else:
                doc.auto_process_file = 0
        
        # Insert the document
        doc.insert()
        
        # Return the document info
        return {
            "success": True,
            "message": "Document created successfully",
            "doc2sys_item": doc.name,
            "file_url": doc.single_file
        }
        
    except Exception as e:
        frappe.log_error(f"Failed to create Doc2Sys Item from file upload: {str(e)}")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }
