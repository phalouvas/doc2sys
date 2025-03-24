import frappe
import requests
import json
import os
import base64
import time
import datetime
from .utils import logger
from .exceptions import ProcessingError, LLMProcessingError

# Import Azure SDK
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence import DocumentAnalysisClient
from azure.core.exceptions import HttpResponseError

# Move hardcoded values to constants
MAX_TEXT_LENGTH = 10000
DEFAULT_TEMPERATURE = 0

class LLMProcessor:
    """Process documents using various LLM providers"""
    
    @staticmethod
    def create(user=None):
        """
        Factory method to create the appropriate LLM processor
        
        Args:
            user (str): Optional user for user-specific settings. 
                        If None, uses current user.
        
        Returns:
            Processor instance based on user's preferred provider
        """
        # Determine which user to use for settings
        user = user or frappe.session.user
        
        # Try to get user-specific settings
        user_settings_list = frappe.get_all(
            'Doc2Sys User Settings',
            filters={'user': user},
            fields=['name']
        )
        
        if user_settings_list:
            # User settings exist, use them
            user_settings = frappe.get_doc('Doc2Sys User Settings', user_settings_list[0].name)
            provider = user_settings.llm_provider
        else:
            # Fallback to global settings for backward compatibility
            logger.warning(f"No Doc2Sys User Settings found for user {user}, using defaults")
            provider = frappe.db.get_single_value("Doc2Sys Settings", "llm_provider") or "Open WebUI"
        
        # Return the appropriate processor based on the provider
        if provider == "Azure AI Document Intelligence":
            return AzureDocumentIntelligenceProcessor(user=user)
        else:
            if provider != "Open WebUI":
                logger.warning(f"Provider {provider} not supported, using Open WebUI")
            return OpenWebUIProcessor(user=user)
    
    def __init__(self, user=None):
        """
        Initialize LLMProcessor directly - delegates to factory method
        
        Args:
            user (str): Optional user for user-specific settings.
                        If None, uses current user.
        """
        # Delegate to the appropriate processor
        processor = self.create(user=user)
        
        # Copy attributes from the created processor
        self.__dict__.update(processor.__dict__)
        
        # Store methods from the processor
        for attr_name in dir(processor):
            if callable(getattr(processor, attr_name)) and not attr_name.startswith('__'):
                setattr(self, attr_name, getattr(processor, attr_name))


class AzureDocumentIntelligenceProcessor:
    """Process documents using Azure AI Document Intelligence"""
    
    def __init__(self, user=None):
        """
        Initialize Azure Document Intelligence processor with user-specific settings
        
        Args:
            user (str): Optional user for user-specific settings.
                        If None, uses current user.
        """
        self.user = user or frappe.session.user
        
        # Try to get user-specific settings first
        user_settings = None
        user_settings_list = frappe.get_all(
            'Doc2Sys User Settings',
            filters={'user': self.user},
            fields=['name']
        )
        
        if user_settings_list:
            
            user_settings = frappe.get_doc('Doc2Sys User Settings', user_settings_list[0].name)
            
            # Get settings from user preferences
            self.endpoint = user_settings.azure_endpoint
            self.model = user_settings.azure_model or "prebuilt-document"
            
            # Get API key securely from user settings
            self.api_key = frappe.utils.password.get_decrypted_password(
                "Doc2Sys User Settings", 
                user_settings_list[0].name, 
                "azure_key"
            ) or ""
            
            # Cache token pricing (per million tokens)
            self.input_price_per_million = float(user_settings.input_token_price or 0.0)
            self.output_price_per_million = float(user_settings.output_token_price or 0.0)
            
            # Initialize Azure client
            try:
                self.credential = AzureKeyCredential(self.api_key)
                self.client = DocumentIntelligenceClient(
                    endpoint=self.endpoint,
                    credential=self.credential
                )
                logger.info(f"Initialized Azure Document Intelligence client for {self.user}")
            except Exception as e:
                logger.error(f"Failed to initialize Azure Document Intelligence client: {str(e)}")
                self.client = None
                
            logger.info(f"Using Azure Document Intelligence for {self.user}")
        else:
            raise LLMProcessingError(f"No Doc2Sys User Settings found for user {self.user}")
        
        # Initialize file cache
        self.file_cache = {}
    
    def upload_file(self, file_path):
        """
        Upload a file to Azure Document Intelligence for processing
        
        Args:
            file_path: Path to the file to be uploaded
            
        Returns:
            str: File ID or URL for reference in API calls
        """
        # Check if this file has already been uploaded in this session
        if (file_path in self.file_cache):
            return self.file_cache[file_path]
            
        # Azure doesn't require pre-upload, we'll process directly in the analyze methods
        # Just return the file path as the identifier
        self.file_cache[file_path] = file_path
        return file_path
        
    def classify_document(self, file_path=None, text=None):
        """
        Classify document using Azure Document Intelligence
        
        Args:
            file_path: Path to the document file (preferred)
            text: Document text content (fallback if file_path not provided)
            
        Returns:
            dict: Classification result with document type and confidence
        """
        try:
            # Get available document types for context
            doc_types = frappe.get_all("Doc2Sys Document Type", 
                                     fields=["document_type"],
                                     filters={"enabled": 1})
            
            available_types = [dt.document_type for dt in doc_types]
            
            # Azure requires a file to process, so check if file path is provided
            if not file_path:
                logger.warning("Azure Document Intelligence requires a file to process")
                return {"document_type": "unknown", "confidence": 0.0}
                
            if not self.client:
                logger.error("Azure Document Intelligence client not initialized")
                return {"document_type": "unknown", "confidence": 0.0}
            
            # Use the appropriate model
            model_id = self._select_azure_model_by_document_type(None)  # No document type yet for classification
            
            # Process the document
            with open(file_path, "rb") as file:
                poller = self.client.begin_analyze_document(
                    model_id=model_id,
                    document=file
                )
            
            # Wait for the operation to complete
            result = poller.result()
            
            # Process the result to determine document type
            document_type, confidence = self._determine_document_type(result, available_types)
            
            return {
                "document_type": document_type,
                "confidence": confidence,
                "reasoning": f"Classified based on Azure Document Intelligence {model_id} model analysis"
            }
                
        except HttpResponseError as error:
            logger.error(f"Azure Document Intelligence API error: {str(error)}")
            return {"document_type": "unknown", "confidence": 0.0}
        except Exception as e:
            logger.error(f"Azure classification error: {str(e)}")
            return {"document_type": "unknown", "confidence": 0.0}
    
    def _determine_document_type(self, azure_result, available_types):
        """
        Determine document type from Azure Document Intelligence results
        
        Args:
            azure_result: Azure Document Intelligence API response object
            available_types: List of available document types
            
        Returns:
            tuple: (document_type, confidence)
        """
        try:
            # Different handling based on model type
            if self.model == "prebuilt-document":
                # For the document model, use document type if available
                doc_type = getattr(azure_result, "doc_type", None)
                confidence = getattr(azure_result, "confidence", 0.5)
                
                # If document type not available, try to infer from content
                if not doc_type or doc_type == "unspecified":
                    # Try to determine from content and structure
                    has_invoice_fields = False
                    has_receipt_fields = False
                    
                    # Check for invoice-specific fields
                    for doc in azure_result.documents:
                        fields = doc.fields
                        if "InvoiceId" in fields or "InvoiceNumber" in fields:
                            has_invoice_fields = True
                        if "MerchantName" in fields and "Total" in fields:
                            has_receipt_fields = True
                    
                    if has_invoice_fields:
                        doc_type = "Invoice"
                        confidence = 0.7
                    elif has_receipt_fields:
                        doc_type = "Receipt"
                        confidence = 0.7
                    else:
                        doc_type = "Document"
                        confidence = 0.5
                
                # Try to match with our available types
                for available_type in available_types:
                    if doc_type and doc_type.lower() in available_type.lower():
                        return available_type, confidence
                
                # Default to unknown if no match found
                return "unknown", confidence
            
            elif self.model in ["prebuilt-invoice", "prebuilt-receipt", "prebuilt-tax.us.w2"]:
                # For specialized models, use the model type as document type
                model_type_map = {
                    "prebuilt-invoice": "Invoice",
                    "prebuilt-receipt": "Receipt",
                    "prebuilt-tax.us.w2": "Tax Document"
                }
                
                # Map model type to our document types
                model_type = model_type_map.get(self.model, "unknown")
                
                # Try to match with available types
                for available_type in available_types:
                    if model_type.lower() in available_type.lower():
                        return available_type, 0.8  # Use high confidence when model specifically matches
                
                # If we have a specialized model but no matching type, use the model type directly
                if model_type in available_types:
                    return model_type, 0.8
                
                return "unknown", 0.5
            
            else:
                # For other models, try to determine from content
                # Extract text content and look for keywords
                all_text = ""
                for page in azure_result.pages:
                    for line in page.lines:
                        all_text += line.content + " "
                
                # Score each document type based on keyword matches
                best_match = "unknown"
                best_score = 0.0
                
                for doc_type in available_types:
                    # Simple scoring based on occurrence of document type name in text
                    keywords = doc_type.lower().split()
                    text_lower = all_text.lower()
                    
                    score = 0.0
                    for keyword in keywords:
                        if keyword in text_lower:
                            score += 0.3
                    
                    if score > best_score:
                        best_score = score
                        best_match = doc_type
                
                return best_match, min(best_score, 0.9)  # Cap at 0.9 confidence
                
        except Exception as e:
            logger.error(f"Error determining document type from Azure results: {str(e)}")
            return "unknown", 0.0
            
    def extract_data(self, file_path=None, text=None, document_type=None):
        """
        Extract structured data from document using Azure Document Intelligence
        
        Args:
            file_path: Path to the document file (preferred)
            text: Document text content (fallback if file_path not provided)
            document_type: Type of document
            
        Returns:
            dict: Extracted data fields
        """
        try:
            # Azure requires a file to process, so check if file path is provided
            if not file_path:
                logger.warning("Azure Document Intelligence requires a file to process")
                return {}
                
            if not self.client:
                logger.error("Azure Document Intelligence client not initialized")
                return {}
            
            # Select appropriate model based on document type
            model_id = self._select_azure_model_by_document_type(document_type)
            
            # Process the document with the selected model
            with open(file_path, "rb") as file:
                poller = self.client.begin_analyze_document(
                    model_id=model_id,
                    document=file
                )
            
            # Wait for the operation to complete
            result = poller.result()
            
            # Process the result to extract structured data
            extracted_data = self._process_azure_extraction_results(result, document_type)
            
            # Add token usage/cost estimate
            token_cost = self._calculate_token_cost({"prompt_tokens": 0, "completion_tokens": 0})
            extracted_data["_token_usage"] = token_cost
            
            return extracted_data
                
        except HttpResponseError as error:
            logger.error(f"Azure Document Intelligence API error: {str(error)}")
            return {}
        except Exception as e:
            logger.error(f"Azure data extraction error: {str(e)}")
            return {}
    
    def _select_azure_model_by_document_type(self, document_type):
        """
        Select appropriate Azure model based on document type
        
        Args:
            document_type: Type of document
            
        Returns:
            str: Azure model ID
        """
        # Use user-specified model as default
        model_id = self.model
        
        # If document type provided, try to match with specialized model
        if document_type:
            document_type_lower = document_type.lower()
            
            # Map common document types to Azure models
            if "invoice" in document_type_lower:
                model_id = "prebuilt-invoice"
            elif "receipt" in document_type_lower:
                model_id = "prebuilt-receipt"
            elif "tax" in document_type_lower and "w2" in document_type_lower:
                model_id = "prebuilt-tax.us.w2"
        
        return model_id
    
    def _process_azure_extraction_results(self, azure_result, document_type):
        """
        Process Azure Document Intelligence results into structured data
        
        Args:
            azure_result: Azure Document Intelligence API response object
            document_type: Type of document
            
        Returns:
            dict: Structured data extracted from document
        """
        try:
            # Different handling based on model type and document type
            if "prebuilt-invoice" in self.model or "invoice" in str(document_type).lower():
                return self._process_invoice_results(azure_result)
            elif "prebuilt-receipt" in self.model or "receipt" in str(document_type).lower():
                return self._process_receipt_results(azure_result)
            else:
                # Generic document processing
                return self._process_generic_document_results(azure_result)
                
        except Exception as e:
            logger.error(f"Error processing Azure extraction results: {str(e)}")
            return {}
    
    def _process_invoice_results(self, result):
        """Process invoice-specific results from Azure"""
        try:
            # Use the SDK's structured objects instead of JSON
            # Initialize empty result
            supplier_name = "Unknown Supplier"
            invoice_id = ""
            invoice_date = ""
            due_date = ""
            subtotal = 0.0
            tax = 0.0
            total = 0.0
            
            # Extract invoice fields from document analysis
            if result.documents:
                doc = result.documents[0]  # Get the first document
                fields = doc.fields
                
                # Extract basic invoice fields
                supplier_name = self._get_field_value_sdk(fields, "VendorName") or "Unknown Supplier"
                invoice_id = self._get_field_value_sdk(fields, "InvoiceId") or ""
                invoice_date = self._get_field_value_sdk(fields, "InvoiceDate") or ""
                due_date = self._get_field_value_sdk(fields, "DueDate") or invoice_date
                subtotal = self._get_field_value_sdk(fields, "SubTotal") or 0.0
                tax = self._get_field_value_sdk(fields, "TotalTax") or 0.0
                total = self._get_field_value_sdk(fields, "InvoiceTotal") or 0.0
            
            # Process line items if available
            line_items = []
            
            # Check if we have the Items field and it's an array
            if result.documents and "Items" in result.documents[0].fields:
                items_field = result.documents[0].fields["Items"]
                if items_field.value and hasattr(items_field.value, "values"):
                    # Process each item in the array
                    for item_obj in items_field.value.values:
                        item_fields = item_obj.value.fields if (hasattr(item_obj, "value") and hasattr(item_obj.value, "fields")) else {}
                        
                        # Extract line item details
                        description = self._get_field_value_sdk(item_fields, "Description") or "Item"
                        quantity = float(self._get_field_value_sdk(item_fields, "Quantity") or 1)
                        unit_price = float(self._get_field_value_sdk(item_fields, "UnitPrice") or 0)
                        amount = float(self._get_field_value_sdk(item_fields, "Amount") or (quantity * unit_price))
                        
                        line_items.append({
                            "item_code": description,
                            "qty": quantity,
                            "rate": unit_price,
                            "amount": amount,
                            "item_group": "All Item Groups"
                        })
            
            # If no line items detected, create one based on total amount
            if not line_items and total:
                line_items.append({
                    "item_code": "Invoice Item",
                    "qty": 1,
                    "rate": total,
                    "amount": total,
                    "item_group": "All Item Groups"
                })
            
            # Format date strings to YYYY-MM-DD
            invoice_date_formatted = self._format_date(invoice_date)
            due_date_formatted = self._format_date(due_date)
            
            # Construct ERPNext compatible JSON
            result = [
                {
                    "doc": {
                        "doctype": "Supplier",
                        "supplier_name": supplier_name
                    }
                }
            ]
            
            # Add item entries for each line item
            for item in line_items:
                result.append({
                    "doc": {
                        "doctype": "Item",
                        "item_code": item["item_code"],
                        "item_group": "All Item Groups",
                        "is_stock_item": 0
                    }
                })
            
            # Add purchase invoice with all details
            result.append({
                "doc": {
                    "doctype": "Purchase Invoice",
                    "supplier": supplier_name,
                    "bill_no": invoice_id,
                    "bill_date": invoice_date_formatted,
                    "posting_date": invoice_date_formatted,
                    "set_posting_time": 1,
                    "due_date": due_date_formatted,
                    "items": line_items,
                    "taxes": [
                        {
                            "account_head": "VAT - KPL",
                            "charge_type": "Actual",
                            "description": "Tax",
                            "tax_amount": tax
                        }
                    ],
                    "company": "KAINOTOMO PH LTD"
                }
            ])
            
            return {"items": result}
            
        except Exception as e:
            logger.error(f"Error processing invoice results: {str(e)}")
            return {}
    
    def _process_receipt_results(self, result):
        """Process receipt-specific results from Azure using SDK objects"""
        try:
            # Initialize empty result
            merchant_name = "Unknown Merchant"
            receipt_date = ""
            receipt_time = ""
            receipt_total = 0.0
            subtotal = 0.0
            tax = 0.0
            
            # Extract receipt fields from document analysis
            if result.documents:
                doc = result.documents[0]  # Get the first document
                fields = doc.fields
                
                # Extract basic receipt fields
                merchant_name = self._get_field_value_sdk(fields, "MerchantName") or "Unknown Merchant"
                receipt_date = self._get_field_value_sdk(fields, "TransactionDate") or ""
                receipt_time = self._get_field_value_sdk(fields, "TransactionTime") or ""
                receipt_total = float(self._get_field_value_sdk(fields, "Total") or 0.0)
                subtotal = float(self._get_field_value_sdk(fields, "Subtotal") or receipt_total)
                tax = float(self._get_field_value_sdk(fields, "TotalTax") or 0.0)
            
            # Process line items if available
            line_items = []
            
            # Check if we have the Items field and it's an array
            if result.documents and "Items" in result.documents[0].fields:
                items_field = result.documents[0].fields["Items"]
                if items_field.value and hasattr(items_field.value, "values"):
                    # Process each item in the array
                    for item_obj in items_field.value.values:
                        item_fields = item_obj.value.fields if (hasattr(item_obj, "value") and hasattr(item_obj.value, "fields")) else {}
                        
                        # Extract line item details
                        description = self._get_field_value_sdk(item_fields, "Description") or "Item"
                        quantity = float(self._get_field_value_sdk(item_fields, "Quantity") or 1)
                        price = float(self._get_field_value_sdk(item_fields, "Price") or 0)
                        total_price = float(self._get_field_value_sdk(item_fields, "TotalPrice") or (quantity * price))
                        
                        line_items.append({
                            "item_code": description,
                            "qty": quantity,
                            "rate": price,
                            "amount": total_price,
                            "item_group": "All Item Groups"
                        })
            
            # If no line items found, create one generic item
            if not line_items:
                line_items.append({
                    "item_code": "Receipt Item",
                    "qty": 1,
                    "rate": subtotal,
                    "amount": subtotal,
                    "item_group": "All Item Groups"
                })
            
            # Format date string to YYYY-MM-DD
            receipt_date_formatted = self._format_date(receipt_date)
            
            # Construct ERPNext compatible JSON
            result = [
                {
                    "doc": {
                        "doctype": "Supplier",
                        "supplier_name": merchant_name
                    }
                }
            ]
            
            # Add item entries for each line item
            for item in line_items:
                result.append({
                    "doc": {
                        "doctype": "Item",
                        "item_code": item["item_code"],
                        "item_group": "All Item Groups",
                        "is_stock_item": 0
                    }
                })
            
            # Add purchase invoice with all details
            result.append({
                "doc": {
                    "doctype": "Purchase Invoice",
                    "supplier": merchant_name,
                    "bill_no": f"Receipt-{receipt_date_formatted}",
                    "bill_date": receipt_date_formatted,
                    "posting_date": receipt_date_formatted,
                    "set_posting_time": 1,
                    "due_date": receipt_date_formatted,
                    "items": line_items,
                    "taxes": [
                        {
                            "account_head": "VAT - KPL",
                            "charge_type": "Actual",
                            "description": "Tax",
                            "tax_amount": tax
                        }
                    ],
                    "company": "KAINOTOMO PH LTD"
                }
            ])
            
            return {"items": result}
            
        except Exception as e:
            logger.error(f"Error processing receipt results: {str(e)}")
            return {}
    
    def _process_generic_document_results(self, result):
        """Process generic document results from Azure using SDK objects"""
        try:
            # For generic documents, extract key-value pairs from forms recognition
            key_value_pairs = {}
            
            # Extract form fields if available
            if result.documents:
                for doc in result.documents:
                    for field_name, field in doc.fields.items():
                        field_value = field.content if hasattr(field, "content") else str(field.value) if field.value is not None else ""
                        key_value_pairs[field_name] = field_value
            
            # Extract tables if available
            tables = []
            for table in result.tables:
                table_data = []
                
                # Initialize empty table with the right dimensions
                rows = max(cell.row_index for cell in table.cells) + 1 if table.cells else 0
                cols = max(cell.column_index for cell in table.cells) + 1 if table.cells else 0
                
                for _ in range(rows):
                    table_data.append([""] * cols)
                
                # Fill in the table data
                for cell in table.cells:
                    row_index = cell.row_index
                    col_index = cell.column_index
                    table_data[row_index][col_index] = cell.content
                
                tables.append(table_data)
            
            # Extract full text content
            full_text = ""
            for page in result.pages:
                for line in page.lines:
                    full_text += line.content + "\n"
            
            # Construct result
            extracted_result = {
                "extracted_fields": key_value_pairs,
                "extracted_tables": tables,
                "full_text": full_text
            }
            
            return extracted_result
            
        except Exception as e:
            logger.error(f"Error processing generic document results: {str(e)}")
            return {}

    def _get_field_value_sdk(self, fields, field_name):
        """Helper to extract field value from Azure SDK objects"""
        if field_name not in fields:
            return None
        
        field = fields[field_name]
        
        # Return the appropriate value based on field type
        if field.value is None:
            return None
        
        # Handle different value types in the SDK
        if hasattr(field.value, "content"):
            return field.value.content
        elif field.value_type == "string":
            return field.value
        elif field.value_type == "number":
            return field.value
        elif field.value_type == "date":
            return field.value
        else:
            # For other types, just convert to string
            return str(field.value)
    
    def _format_date(self, date_str):
        """Format date string to YYYY-MM-DD format"""
        if not date_str:
            return ""
        
        try:
            # Check if date is already a datetime object
            if isinstance(date_str, datetime.datetime) or isinstance(date_str, datetime.date):
                return date_str.strftime("%Y-%m-%d")
                
            # Check if the date is already in ISO format
            if isinstance(date_str, str) and "-" in date_str and len(date_str) >= 10:
                return date_str[:10]  # Return just the date part
            
            # Try parsing various date formats
            from datetime import datetime
            import locale
            
            # Try different formats
            formats = [
                "%Y-%m-%d",
                "%d/%m/%Y",
                "%m/%d/%Y",
                "%d-%m-%Y",
                "%m-%d-%Y",
                "%d.%m.%Y",
                "%m.%d.%Y",
                "%B %d, %Y",
                "%d %B %Y"
            ]
            
            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    continue
            
            # If none of the formats worked
            logger.warning(f"Could not parse date: {date_str}")
            return date_str
            
        except Exception as e:
            logger.error(f"Error formatting date {date_str}: {str(e)}")
            return date_str

    def _calculate_token_cost(self, usage):
        """
        Calculate cost based on token usage from API response
        
        Args:
            usage: Token usage dict from API response
            
        Returns:
            dict: Token usage and cost information
        """
        try:
            # Extract token counts
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            
            # Calculate cost (convert from price per million to price per token)
            input_cost = (input_tokens * self.input_price_per_million) / 1000000
            output_cost = (output_tokens * self.output_price_per_million) / 1000000
            total_cost = input_cost + output_cost
            
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "total_cost": total_cost
            }
        except Exception as e:
            logger.error(f"Error calculating token cost: {str(e)}")
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0
            }

class OpenWebUIProcessor:
    """Process documents using Open WebUI"""
    
    def __init__(self, user=None):
        """
        Initialize Open WebUI processor with user-specific settings
        
        Args:
            user (str): Optional user for user-specific settings.
                        If None, uses current user.
        """
        self.user = user or frappe.session.user
        
        # Try to get user-specific settings first
        user_settings = None
        user_settings_list = frappe.get_all(
            'Doc2Sys User Settings',
            filters={'user': self.user},
            fields=['name']
        )
        
        if user_settings_list:
            user_settings = frappe.get_doc('Doc2Sys User Settings', user_settings_list[0].name)
            
            # Get settings from user preferences
            self.endpoint = user_settings.openwebui_endpoint or "http://localhost:3000/api/v1"
            self.model = user_settings.openwebui_model or "llama3"
            
            # Get API key securely from user settings
            self.api_key = frappe.utils.password.get_decrypted_password(
                "Doc2Sys User Settings", 
                user_settings_list[0].name, 
                "openwebui_apikey"
            ) or ""
            
            # Cache token pricing (per million tokens)
            self.input_price_per_million = float(user_settings.input_token_price or 0.0)
            self.output_price_per_million = float(user_settings.output_token_price or 0.0)
            
            logger.info(f"Using user-specific LLM settings for {self.user}")
        else:
            # Use 'raise' instead of 'throw' to raise the exception
            raise LLMProcessingError(f"No Doc2Sys User Settings found for user {self.user}")
        
        # Initialize file cache
        self.file_cache = {}
    
    def upload_file(self, file_path):
        """
        Upload a file to Open WebUI for processing
        
        Args:
            file_path: Path to the file to be uploaded
            
        Returns:
            str: File ID or URL for reference in API calls
        """
        # Check if this file has already been uploaded in this session
        if (file_path in self.file_cache):
            return self.file_cache[file_path]
            
        try:
            # Set up headers with API key if provided
            headers = {
                'Accept': 'application/json'
            }
            if self.api_key:
                headers['Authorization'] = f'Bearer {self.api_key}'
            
            # Open the file for upload
            file_name = os.path.basename(file_path)
            file_extension = os.path.splitext(file_path)[1].lower()
            content_type = self._get_content_type(file_extension)
            
            # Create multipart form data with the file and content type
            files = {'file': (file_name, open(file_path, 'rb'), content_type)}
            
            # Upload file to Open WebUI using multipart form
            response = requests.post(
                f"{self.endpoint}/api/v1/files/",
                headers=headers,
                files=files
            )
            
            if response.status_code != 200:
                logger.error(f"File upload error: {response.status_code, response.text}")
                return None
                
            # Parse response to get file ID
            result = response.json()
            file_id = result.get("id") or result.get("file_id")
            
            # Cache the file_id before returning
            if file_id:
                self.file_cache[file_path] = file_id
                
            return file_id
            
        except Exception as e:
            logger.error(f"File upload error: {str(e)}")
            return None

    def _get_content_type(self, file_extension):
        """Helper method to determine content type from file extension"""
        content_types = {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".txt": "text/plain",
            ".csv": "text/csv",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        }
        return content_types.get(file_extension, "application/octet-stream")
        
    def classify_document(self, file_path=None, text=None):
        """
        Classify document using Open WebUI
        
        Args:
            file_path: Path to the document file (preferred)
            text: Document text content (fallback if file_path not provided)
            
        Returns:
            dict: Classification result with document type and confidence
        """
        try:
            # Get available document types for context
            doc_types = frappe.get_all("Doc2Sys Document Type", 
                                     fields=["document_type"],
                                     filters={"enabled": 1})
            
            available_types = [dt.document_type for dt in doc_types]
            
            # Format available types with quotes to clarify they are exact phrases
            formatted_types = [f'"{doc_type}"' for doc_type in available_types]
            
            # Improved prompt with clear formatting
            prompt = f"""
            # Document Classification Task

            ## Instructions
            Your task is to classify the text in next message into one of the predefined categories. Follow these steps:

            1. Analyze the document's content, structure, formatting, and key identifiers
            2. Look for distinctive headers, labels, and standard phrases that indicate document type
            3. Match to the most appropriate document type from the list below
            4. Provide your classification with a confidence score and detailed reasoning

            ## Available Document Types
            Choose EXACTLY ONE document type from this list (must match exactly, including capitalization):
            {', '.join(formatted_types)}

            ## Special Cases
            If the document doesn't clearly match any of the available types, classify it as "unknown".

            ## Response Format
            Respond in JSON format with these fields:
            {{
                "document_type": "exact match from the list above",
                "confidence": 0.0-1.0,
                "reasoning": "detailed explanation referencing specific evidence from the document"
            }}

            ## Confidence Score Guidelines
            - 0.9-1.0: Very confident (clear markers present)
            - 0.7-0.9: Moderately confident (most markers present)
            - 0.5-0.7: Somewhat confident (some markers present)
            - 0.0-0.5: Low confidence (few or no clear markers)
            """
            
            api_payload = None
            
            # Process text input first if available
            if text:
                api_payload = self._prepare_text_content(text, prompt)
            
            # If text is not available or failed, process file input
            if not api_payload and file_path:
                api_payload, _ = self._prepare_file_content(file_path, prompt)
            
            # If we couldn't create a valid payload, return default response
            if not api_payload:
                return {"document_type": "unknown", "confidence": 0.0}
                
            # Make the API request
            result = self._make_api_request(
                f"{self.endpoint}/api/chat/completions",
                api_payload
            )
            
            if not result:
                return {"document_type": "unknown", "confidence": 0.0}
                
            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            # Calculate token usage costs
            token_cost = self._calculate_token_cost(result.get("usage", {}))
            
            try:
                # Try to parse the JSON response
                cleaned_content = self._clean_json_response(content)
                classification = json.loads(cleaned_content)
                
                # Add token usage and cost data, handling both dict and array responses
                if isinstance(classification, list):
                    # Wrap array data in a container dictionary
                    classification = {
                        "classifications": classification,
                        "token_usage": token_cost
                    }
                else:
                    # Regular dictionary case
                    classification["token_usage"] = token_cost
                
                return classification
            except json.JSONDecodeError:
                # If we couldn't parse JSON, do basic text analysis
                logger.warning(f"Failed to parse JSON from Open WebUI: {content}")
                
                # Try to extract document type through simple text matching
                return self._extract_document_type_from_text(content, available_types)
                
        except Exception as e:
            logger.error(f"Classification error: {str(e)}")
            return {"document_type": "unknown", "confidence": 0.0}
            
    def extract_data(self, file_path=None, text=None, document_type=None):
        """
        Extract structured data from document using Open WebUI
        
        Args:
            file_path: Path to the document file (preferred)
            text: Document text content (fallback if file_path not provided)
            document_type: Type of document
            
        Returns:
            dict: Extracted data fields
        """
        try:
            # Get the custom prompt from the document type
            custom_prompt = frappe.db.get_value(
                "Doc2Sys Document Type", 
                {"document_type": document_type}, 
                "extract_data_prompt"
            )
            
            # Prepare the default prompt text with improved structure
            default_prompt = """
            Analyze the text. Follow these steps **strictly**:
            1. **Translate non-English text to English** (to identify fields), but retain the **original text** for JSON output.
            2. **Extract & Validate**:
            - **Supplier**:
                - From the **translated text**, identify the supplier section.
                - Extract **original supplier name**, **address**, and **country** from the **original text** (e.g., "Proveedor: [Nombre]" → use "[Nombre]").
            - **Invoice**:
                - Dates: Convert to `YYYY-MM-DD` (language-agnostic).
                - Invoice number: Extract from the **original text** (e.g., "Factura N°: 123" → "123").
            - **Items**:
                - From the **translated text**, identify item descriptions.
                - Extract **original item names** from the **original text** (e.g., "Producto: Widget" → use "Widget" if original is in English, else use original term like "Artículo").
            - **Totals**:
                - Calculate `net_total = sum(qty * rate)`.
                - Validate `net_total + tax = grand_total` (using numeric values, not text).
            3. **Generate ERPNext JSON**:
            - Use **original non-English text** for:
                - `supplier_name`
                - `item_code` (item descriptions)
                - `address` (if included)
            - Use **translated text only for validation** (not output).
            - Structure:
                ```json
                [
                {
                    "doc": {
                    "doctype": "Supplier",
                    "supplier_name": "[Original_Supplier_Name]"
                    }
                },
                {
                    "doc": {
                    "doctype": "Item",
                    "item_code": "[Original_Item_Name]",
                    "item_group": "All Item Groups",
                    "is_stock_item": 0
                    }
                },
                {
                    "doc": {
                    "doctype": "Purchase Invoice",
                    "supplier": "[Original_Supplier_Name]",
                    "bill_no": "[Extracted_Invoice_Number]",
                    "bill_date": "YYYY-MM-DD",
                    "posting_date": "YYYY-MM-DD",
                    "set_posting_time": 1,
                    "due_date": "YYYY-MM-DD",
                    "items": [
                        {
                        "item_code": "[Original_Item_Name]",
                        "qty": [Integer],
                        "rate": [Float],
                        "item_group": "All Item Groups"
                        }
                    ],
                    "taxes": [
                        {
                        "account_head": "VAT - KPL",
                        "charge_type": "Actual",
                        "description": "Tax",
                        "tax_amount": [Tax]
                        }
                    ],
                    "company": "KAINOTOMO PH LTD"
                    }
                }
                ]
                ```
            4. **Use original non-English text in the response**
            5. **Respond ONLY with the JSON array or "Error: [Reason]"**.
            """

            # Use custom prompt if available, otherwise use default
            prompt = custom_prompt if custom_prompt else default_prompt
            
            api_payload = None
            
            # Process text input first if available
            if text:
                api_payload = self._prepare_text_content(text, prompt)
            
            # If text is not available or failed, process file input
            if not api_payload and file_path:
                api_payload, _ = self._prepare_file_content(file_path, prompt)
            
            # If we couldn't create a valid payload, return empty dict
            if not api_payload:
                return {}
                
            # Make the API request
            result = self._make_api_request(
                f"{self.endpoint}/api/chat/completions",
                api_payload
            )
            
            if not result:
                return {}
                
            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            # Calculate token usage costs
            token_cost = self._calculate_token_cost(result.get("usage", {}))
            
            try:
                # Try to parse the JSON response
                cleaned_content = self._clean_json_response(content)
                extracted_data = json.loads(cleaned_content)
                
                # Add token usage as metadata, handling both dict and array responses
                if isinstance(extracted_data, list):
                    # Wrap array data in a container dictionary
                    extracted_data = {
                        "items": extracted_data,
                        "_token_usage": token_cost
                    }
                else:
                    # Regular dictionary case
                    extracted_data["_token_usage"] = token_cost
                
                return extracted_data
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Open WebUI: {content}")
                return {}
                
        except Exception as e:
            logger.error(f"Data extraction error: {str(e)}")
            return {}

    def _clean_json_response(self, content):
        """Enhanced JSON cleaning with better edge case handling"""
        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content[7:]
        elif cleaned_content.startswith("```"):
            cleaned_content = cleaned_content[3:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
            
        return cleaned_content.strip()
    
    def _extract_document_type_from_text(self, content, available_types):
        """Helper method to extract document type from text when JSON parsing fails"""
        content_lower = content.lower()
        best_match = None
        for doc_type in available_types:
            if doc_type.lower() in content_lower:
                best_match = doc_type
                break
        
        if best_match:
            return {
                "document_type": best_match,
                "confidence": 0.6  # Moderate confidence for text matching
            }
        else:
            return {"document_type": "unknown", "confidence": 0.0}

    def _calculate_token_cost(self, usage):
        """
        Calculate cost based on token usage from API response
        
        Args:
            usage: Token usage dict from API response
            
        Returns:
            dict: Token usage and cost information
        """
        try:
            # Extract token counts
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)
            
            # Calculate cost (convert from price per million to price per token)
            input_cost = (input_tokens * self.input_price_per_million) / 1000000
            output_cost = (output_tokens * self.output_price_per_million) / 1000000
            total_cost = input_cost + output_cost
            
            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "input_cost": input_cost,
                "output_cost": output_cost,
                "total_cost": total_cost
            }
        except Exception as e:
            logger.error(f"Error calculating token cost: {str(e)}")
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0
            }

    def _make_api_request(self, endpoint, payload, headers=None):
        """
        Centralized method to make API requests with proper error handling
        
        Args:
            endpoint (str): API endpoint to call
            payload (dict): Request payload
            headers (dict, optional): Request headers
            
        Returns:
            dict: API response or empty dict on failure
        """
        try:
            # Prepare headers
            request_headers = {"Content-Type": "application/json"}
            if headers:
                request_headers.update(headers)
            if self.api_key:
                request_headers["Authorization"] = f"Bearer {self.api_key}"
                
            # Make request with timeout
            response = requests.post(endpoint, headers=request_headers, json=payload, timeout=600)
            
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}, {response.text}")
                return {}
            
            # Parse the response
            result = response.json()
            
            # Add duration to the response
            if "usage" not in result:
                result["usage"] = {}
                
            return result
        except Exception as e:
            logger.error(f"API request error: {str(e)}")
            return {}
    
    def _prepare_file_content(self, file_path, prompt, use_text_only=False):
        """
        Prepare file content for API request based on file type
        
        Args:
            file_path (str): Path to the file
            prompt (str): Prompt to use with the file
            use_text_only (bool): If True, skip file upload when possible
            
        Returns:
            tuple: (api_payload, messages) to use in the request
        """
        # If text_only mode is enabled, return None to force text-based processing
        if use_text_only and not file_path.lower().endswith(('.jpg', '.jpeg', '.png', '.gif')):
            return None, None
        
        file_extension = os.path.splitext(file_path)[1].lower()
        content_type = self._get_content_type(file_extension)
        
        # Default API payload structure
        api_payload = {
            "model": self.model,
            "temperature": DEFAULT_TEMPERATURE,
            "response_format": {"type": "json_object"}
        }
        
        messages = [
            {"role": "system", "content": "You are an AI language model. Always respond in JSON."}
        ]
        
        # For images, use direct base64 encoding
        if content_type.startswith('image/'):
            try:
                with open(file_path, 'rb') as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                    
                # Construct message with text and image parts
                message_content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64_image}"}}
                ]
                
                # Set up messages with the mixed content
                api_payload["messages"] = [
                    {"role": "user", "content": message_content}
                ]
            except Exception as e:
                logger.error(f"Error processing image file: {str(e)}")
                return None, None
        else:
            # For non-image files, use the file upload approach
            file_id = self.upload_file(file_path)
            if file_id:
                messages.append({"role": "user", "content": prompt})
                api_payload["messages"] = messages
                api_payload["files"] = [{"type": "file", "id": file_id}]
            else:
                return None, None
                
        return api_payload, messages

    def _prepare_text_content(self, text, prompt):
        """
        Prepare text content for API request with separate messages for prompt and content
        
        Args:
            text (str): Text content to process
            prompt (str): Prompt to use with the text
            
        Returns:
            dict: API payload to use in the request
        """
        if not text:
            return None
            
        text_for_api = text[:MAX_TEXT_LENGTH]  # Truncate if too long
        
        api_payload = {
            "model": self.model,
            "temperature": DEFAULT_TEMPERATURE,
            "messages": [
                {"role": "system", "content": "Always returns data in JSON format."},
                {"role": "user", "content": prompt + text_for_api}
            ]
        }
        
        return api_payload
