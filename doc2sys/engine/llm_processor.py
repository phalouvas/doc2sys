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
from azure.core.exceptions import HttpResponseError
from azure.ai.documentintelligence.models import AnalyzeResult

# Move hardcoded values to constants
MAX_TEXT_LENGTH = 10000
DEFAULT_TEMPERATURE = 0
ACCEPTABLE_CONFIDENCE = 0.1

from typing import Dict, Any, List, Optional  # Add this import line
from frappe.model.document import Document  # Import Document from frappe
from ..doc2sys.utils.payment_integration import deduct_user_credits  # Add this import

class LLMProcessor:
    """Process documents using various LLM providers"""
    
    @staticmethod
    def create(user=None, doc2sys_item=None):
        """
        Factory method to create the appropriate LLM processor
        
        Args:
            user (str): Optional user for user-specific settings. 
                        If None and doc2sys_item is None, uses current user.
            doc2sys_item: Optional Doc2Sys Item document or name.
                        If provided, gets user from this document.
        
        Returns:
            Processor instance based on user's preferred provider
        """
        # If doc2sys_item is provided, get the user from it
        if doc2sys_item:
            if isinstance(doc2sys_item, str):
                try:
                    doc2sys_item_doc = frappe.get_doc("Doc2Sys Item", doc2sys_item)
                    user = doc2sys_item_doc.user
                except Exception as e:
                    logger.error(f"Failed to get Doc2Sys Item {doc2sys_item}: {str(e)}")
            else:
                # Assume it's already a document object
                user = doc2sys_item.user
        
        # Fall back to provided user or session user if we couldn't get user from doc2sys_item
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
            return AzureDocumentIntelligenceProcessor(user=user, doc2sys_item=doc2sys_item)
        else:
            if provider != "Open WebUI":
                logger.warning(f"Provider {provider} not supported, using Open WebUI")
            return AzureDocumentIntelligenceProcessor(user=user, doc2sys_item=doc2sys_item)

    def __init__(self, user=None, doc2sys_item=None):
        """
        Initialize LLMProcessor directly - delegates to factory method
        
        Args:
            user (str): Optional user for user-specific settings.
                        If None and doc2sys_item is None, uses current user.
            doc2sys_item: Optional Doc2Sys Item document or name.
                        If provided, gets user from this document.
        """
        # Store doc2sys_item as instance attribute
        self.doc2sys_item = doc2sys_item
        
        # Delegate to the appropriate processor
        processor = self.create(user=user, doc2sys_item=doc2sys_item)
        
        # Copy attributes from the created processor
        self.__dict__.update(processor.__dict__)
        
        # Store methods from the processor
        for attr_name in dir(processor):
            if callable(getattr(processor, attr_name)) and not attr_name.startswith('__'):
                setattr(self, attr_name, getattr(processor, attr_name))

class AzureDocumentIntelligenceProcessor:
    """Process documents using Azure AI Document Intelligence"""
    
    def __init__(self, user=None, doc2sys_item=None):
        """
        Initialize Azure Document Intelligence processor with user-specific settings
        
        Args:
            user (str): Optional user for user-specific settings.
                        If None, uses current user.
            doc2sys_item: Optional Doc2Sys Item document or name.
        """
        self.user = user or frappe.session.user
        self.doc2sys_item = doc2sys_item
        
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
            self.model = user_settings.azure_model or "prebuilt-invoice"
            
            # Get API key securely from user settings
            self.api_key = frappe.utils.password.get_decrypted_password(
                "Doc2Sys User Settings", 
                user_settings_list[0].name, 
                "azure_key"
            ) or ""
            
            # Cache token pricing (per million tokens)
            self.cost_prebuilt_invoice_per_page = float(user_settings.cost_prebuilt_invoice_per_page or 0.0)
            
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
  
    def extract_data(self, file_path=None, document_type=None):
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
            extracted_data = {}  # Initialize empty dictionary

            # First check if we have cached results in doc2sys_item
            if self.doc2sys_item:
                try:
                    # Check if doc2sys_item is a string or document object
                    if isinstance(self.doc2sys_item, str):
                        doc2sys_item_doc = frappe.get_doc("Doc2Sys Item", self.doc2sys_item)
                    else:
                        doc2sys_item_doc = self.doc2sys_item
                    
                    # Check if we have cached Azure raw response
                    if hasattr(doc2sys_item_doc, 'azure_raw_response') and doc2sys_item_doc.azure_raw_response:
                        logger.info(f"Using cached Azure response from doc2sys_item")
                        
                        # Deserialize the stored response
                        result_dict = json.loads(doc2sys_item_doc.azure_raw_response)

                        # Process the cached result to extract structured data
                        extracted_data, extracted_doc = self._process_azure_extraction_results(result_dict)
                        extracted_data = frappe.as_json(extracted_data, 1, None, False)
                        doc2sys_item_doc.db_set('extracted_data', extracted_data, update_modified=False)
                        extracted_doc = frappe.as_json(extracted_doc, 1, None, False)
                        doc2sys_item_doc.db_set('extracted_doc', extracted_doc, update_modified=False)
                        frappe.db.commit()
                        
                        return extracted_data
                except Exception as e:
                    logger.warning(f"Failed to use cached Azure response: {str(e)}, proceeding with API call")
                    return {}
            
            # Azure requires a file to process, so check if file path is provided
            if not file_path:
                logger.warning("Azure Document Intelligence requires a file to process")
                return {}
                
            if not self.client:
                logger.error("Azure Document Intelligence client not initialized")
                return {}
            
            # Select appropriate model based on document type
            model_id = self.doc2sys_item.document_type or self.model
            
            # Process the document with the selected model
            with open(file_path, "rb") as file:
                poller = self.client.begin_analyze_document(model_id=model_id, body=file)
            
            # Wait for the operation to complete
            result = poller.result()

            # Check if result is None and throw an error if it is
            if not result:
                raise LLMProcessingError("Azure Document Intelligence returned no result")
            
            # Convert Azure result to serializable JSON
            result_dict = result.as_dict()
            extracted_text = result_dict.get("content")
            serialized_result = json.dumps(result_dict, ensure_ascii=False)
            
            # Process the result to extract structured data
            extracted_data, extracted_doc = self._process_azure_extraction_results(result_dict)
            extracted_data = frappe.as_json(extracted_data, 1, None, False)
            extracted_doc = frappe.as_json(extracted_doc, 1, None, False)

            # Calculate cost
            cost = len(result_dict.get("pages", [])) * self.cost_prebuilt_invoice_per_page / 1000
            try:
                currency_precision = frappe.get_precision("Currency", "amount")
                if currency_precision is None:
                    currency_precision = 2  # Default to 2 decimal places
            except:
                currency_precision = 2  # Default to 2 decimal places if anything goes wrong
            cost = round(cost, currency_precision)

            doc = result_dict.get("documents")[0]
            confidence = doc.get("confidence")
            
            # Save the raw response to doc2sys_item for future use if available
            if self.doc2sys_item:
                try:
                    if isinstance(self.doc2sys_item, str):
                        doc2sys_item_doc = frappe.get_doc("Doc2Sys Item", self.doc2sys_item)
                    else:
                        doc2sys_item_doc = self.doc2sys_item
                    
                    # Use db_set to directly update field without triggering validation
                    doc2sys_item_doc.db_set('extracted_data', extracted_data, update_modified=False)
                    doc2sys_item_doc.db_set('extracted_doc', extracted_doc, update_modified=False)
                    doc2sys_item_doc.db_set('azure_raw_response', serialized_result, update_modified=False)
                    doc2sys_item_doc.db_set('extracted_text', extracted_text, update_modified=False)
                    doc2sys_item_doc.db_set('cost', cost, update_modified=False)
                    doc2sys_item_doc.db_set('classification_confidence', confidence, update_modified=False)
                    frappe.db.commit()
                    
                    # Deduct credits from user account based on processing cost
                    if cost > 0:
                        new_balance = deduct_user_credits(
                            user=self.user,
                            amount=cost,
                            doc_reference=f"Doc2Sys Item: {doc2sys_item_doc.name}"
                        )
                        
                except Exception as e:
                    logger.error(f"Failed to cache Azure response or update credits: {str(e)}")
            
            return extracted_data
                
        except HttpResponseError as error:
            logger.error(f"Azure Document Intelligence API error: {str(e)}")
            return {}
        except Exception as e:
            logger.error(f"Azure data extraction error: {str(e)}")
            return {}        
    
    def _process_azure_extraction_results(self, result_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Process the raw Azure Document Intelligence results into a structured format"""
        try:
            # Initialize an empty dictionary to store the extracted data
            extracted_data = {}
            
            # Get the document type from the object or fallback
            document_type = self.doc2sys_item.document_type if isinstance(self.doc2sys_item, Document) else "prebuilt-document"
            
            # Get the extracted fields from the Azure response
            if 'documents' in result_dict and len(result_dict['documents']) > 0:
                doc = result_dict['documents'][0]
                extracted_doc = self._process_azure_doc(doc)
                fields = doc.get('fields', {})
                
                # Extract generic document data based on document type
                if document_type == "prebuilt-invoice":
                    extracted_data = self._process_invoice_result(fields)
                elif document_type == "prebuilt-receipt":
                    extracted_data = self._process_receipt_result(fields)
                elif document_type in ["prebuilt-document", "prebuilt-layout", "prebuilt-read"]:
                    extracted_data = self._process_generic_document_result(result_dict)
            
            return extracted_data, extracted_doc
        except Exception as e:
            logger.error(f"Error processing Azure extraction results: {str(e)}")
            return {}
        
    def _process_azure_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        extracted_doc = {}

        extracted_doc['confidence'] = doc.get('confidence', 0.0)
        extracted_doc['docType'] = doc.get('docType', 'Unknown')

        # Extract document fields
        if 'fields' in doc:
            fields = doc['fields']
            for field_name, field_value in fields.items():
                if isinstance(field_value, dict):
                    extracted_doc[field_name] = self._extract_nested_fields(field_value)
                else:
                    extracted_doc[field_name] = field_value
        return extracted_doc
    
    def _extract_nested_fields(self, field_value: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively extract nested fields from Azure Document Intelligence response"""
        extracted_fields = {}
        for key, value in field_value.items():
            if key == "boundingRegions" or key == "spans":
                continue
            if isinstance(value, dict):
                extracted_fields[key] = self._extract_nested_fields(value)
            elif isinstance(value, list):
                extracted_fields[key] = [self._extract_nested_fields(item) if isinstance(item, dict) else item for item in value]
            else:
                extracted_fields[key] = value
        return extracted_fields
        
    def _process_invoice_result(self, fields: Dict) -> Dict:
        """Process invoice-specific fields from Azure"""
        # Common invoice metadata in generic format
        extracted_data = {
            "document_type": "Invoice",
            "invoice_number": self._get_field_value(fields, "InvoiceId"),
            "invoice_date": self._get_field_value(fields, "InvoiceDate"),
            "due_date": self._get_field_value(fields, "DueDate"),
            "total_amount": self._get_field_value(fields, "InvoiceTotal"),
            "subtotal": self._get_field_value(fields, "SubTotal"),
            "tax_amount": self._get_field_value(fields, "TotalTax"),
            "currency": self._get_nested_value(fields, "InvoiceTotal", "valueCurrency", "currencyCode") or 
                       self._get_nested_value(fields, "SubTotal", "valueCurrency", "currencyCode"),
            
            # Vendor/supplier information
            "supplier_name": self._get_field_value(fields, "VendorName"),
            "supplier_address": self._get_field_value(fields, "VendorAddress"),
            "supplier_email": self._get_field_value(fields, "VendorEmail"),
            "supplier_phone": self._get_field_value(fields, "VendorPhone"),
            "supplier_tax_id": self._get_field_value(fields, "VendorTaxId"),
            
            # Customer information (if available)
            "customer_name": self._get_field_value(fields, "CustomerName"),
            "customer_address": self._get_field_value(fields, "CustomerAddress"),
            "customer_id": self._get_field_value(fields, "CustomerId"),
            
            # Additional references
            "purchase_order": self._get_field_value(fields, "PurchaseOrder"),
            "payment_terms": self._get_field_value(fields, "PaymentTerms"),
            
            # Discount information
            "discount_amount": self._get_field_value(fields, "DiscountAmount"),
            
            # Line items in a generic format
            "items": []
        }
        
        # Validate and reconcile monetary values
        total = extracted_data["total_amount"] 
        subtotal = extracted_data["subtotal"]
        tax = extracted_data["tax_amount"]
        discount = extracted_data["discount_amount"] or 0
        
        # Check if we have meaningful values for validation
        if total is not None and subtotal is not None and tax is not None:
            # With discount: total = subtotal - discount + tax
            expected_total = subtotal - discount + tax
            if abs(expected_total - total) > 0.01:
                logger.warning(f"Invoice total validation failed: {subtotal} - {discount} + {tax} != {total}")
                # Recalculate to ensure consistency
                extracted_data["total_amount"] = expected_total
        # Handle cases where one value is missing
        elif total is not None and subtotal is not None:
            # Calculate tax from total, subtotal and discount
            extracted_data["tax_amount"] = total - subtotal + discount
        elif total is not None and tax is not None:
            # Calculate subtotal from total, tax and discount
            extracted_data["subtotal"] = total - tax + discount
        elif subtotal is not None and tax is not None:
            # Calculate total from subtotal, tax and discount
            extracted_data["total_amount"] = subtotal - discount + tax
        
        # Extract line items from Azure response
        items = self._get_field_value(fields, "Items") or []
        items_total = 0
        
        for item in items:
            if 'valueObject' in item:
                value_obj = item['valueObject']
                
                # Extract basic item details in a generic format
                item_data = {
                    "description": self._get_nested_value(value_obj, "Description", "valueString"),
                    "quantity": self._get_nested_value(value_obj, "Quantity", "valueNumber"),
                    "unit_price": self._get_nested_value(value_obj, "UnitPrice", "valueCurrency", "amount"),
                    "amount": self._get_nested_value(value_obj, "Amount", "valueCurrency", "amount"),
                    "tax": self._get_nested_value(value_obj, "Tax", "valueCurrency", "amount"),
                    "item_code": self._get_nested_value(value_obj, "ProductCode", "valueString"),
                    "discount": self._get_nested_value(value_obj, "Discount", "valueCurrency", "amount") or 0,
                    "unit": self._get_nested_value(value_obj, "Unit", "valueString"),
                    "date": self._get_nested_value(value_obj, "Date", "valueDate")
                }
    
                # Set item_code to a default value if missing
                if item_data["item_code"] is None:
                    item_data["item_code"] = self._create_item_code_from_description(item_data["description"])
                
                # Set quantity to 1 if missing
                if item_data["quantity"] is None:
                    item_data["quantity"] = 1
                    logger.info(f"Setting missing quantity to 1 for item: {item_data['description']}")
                
                # Handle item-level discounts if present
                item_discount = item_data["discount"]
                
                # Validate that amount = (quantity * unit_price) - discount
                if item_data["quantity"] and item_data["unit_price"]:
                    expected_amount = (item_data["quantity"] * item_data["unit_price"]) - item_discount
                    
                    if item_data["amount"] and abs(expected_amount - item_data["amount"]) > 0.01:
                        logger.warning(f"Item amount validation failed: ({item_data['quantity']} * {item_data['unit_price']}) - {item_discount} != {item_data['amount']}")
                        # Recalculate to ensure consistency
                        item_data["amount"] = expected_amount
                    elif not item_data["amount"]:
                        item_data["amount"] = expected_amount
                
                # Calculate missing values where possible
                elif item_data["quantity"] and item_data["amount"] is not None:
                    # Account for discount when calculating unit price
                    item_data["unit_price"] = (item_data["amount"] + item_discount) / item_data["quantity"]
                elif item_data["unit_price"] and item_data["amount"] is not None:
                    # Since we default quantity to 1, this case should rarely occur
                    item_data["quantity"] = (item_data["amount"] + item_discount) / item_data["unit_price"]
                
                # Add to running total
                if item_data["amount"] is not None:
                    items_total += item_data["amount"]
                
                extracted_data["items"].append(item_data)
        
        # Validate that sum of line items equals subtotal 
        if items_total > 0 and subtotal is not None and abs(items_total - subtotal) > 0.01:
            logger.warning(f"Sum of line items ({items_total}) doesn't match subtotal ({subtotal})")
            
            # If the difference is significant, try to reconcile
            if abs(items_total - subtotal) / max(items_total, subtotal) > 0.05:  # More than 5% difference
                # Check if items_total + discount = subtotal (discount already applied to line items)
                if abs((items_total + discount) - subtotal) < 0.01:
                    logger.info("Discount appears to be already applied to line items")
                else:
                    # Scale all item amounts proportionally 
                    scale_factor = subtotal / items_total
                    logger.info(f"Scaling line items by factor {scale_factor} to match subtotal")
                    
                    for item in extracted_data["items"]:
                        if item["amount"] is not None:
                            item["amount"] = round(item["amount"] * scale_factor, 2)
                            if item["quantity"] and item["quantity"] > 0:
                                # Recalculate unit price
                                item["unit_price"] = item["amount"] / item["quantity"]
        
        return extracted_data

    def _process_receipt_result(self, fields: Dict) -> Dict:
        """Process receipt-specific fields from Azure"""
        # Common receipt metadata
        extracted_data = {
            "document_type": "Receipt",
            "receipt_number": self._get_field_value(fields, "ReceiptNumber") or self._get_field_value(fields, "InvoiceId"),
            "transaction_date": self._get_field_value(fields, "TransactionDate"),
            "total_amount": self._get_field_value(fields, "Total"),
            "subtotal": self._get_field_value(fields, "Subtotal"),
            "tax_amount": self._get_field_value(fields, "TotalTax"),
            
            # Merchant information
            "merchant_name": self._get_field_value(fields, "MerchantName"),
            "merchant_address": self._get_field_value(fields, "MerchantAddress"),
            "merchant_phone": self._get_field_value(fields, "MerchantPhoneNumber"),
            
            # Payment information
            "payment_method": self._get_field_value(fields, "PaymentMethod"),
            "card_last4": self._get_field_value(fields, "PaymentCardNumber"),
            
            # Items in a generic format
            "items": []
        }
        
        # Extract line items from Azure response
        items = self._get_field_value(fields, "Items") or []
        for item in items:
            if 'valueObject' in item:
                value_obj = item['valueObject']
                
                # Extract basic item details in a generic format
                item_data = {
                    "description": self._get_nested_value(value_obj, "Description", "valueString"),
                    "quantity": self._get_nested_value(value_obj, "Quantity", "valueNumber"),
                    "price": self._get_nested_value(value_obj, "Price", "valueCurrency", "amount"),
                    "total_price": self._get_nested_value(value_obj, "TotalPrice", "valueCurrency", "amount"),
                }
                
                extracted_data["items"].append(item_data)
        
        return extracted_data

    def _process_generic_document_result(self, result_dict: Dict) -> Dict:
        """Process general document extraction results from Azure"""
        extracted_data = {
            "document_type": "Document",
            "content": result_dict.get("content", ""),
            "pages": len(result_dict.get("pages", [])),
            "tables": [],
            "key_value_pairs": []
        }
        
        # Extract tables if available
        if "tables" in result_dict:
            for table in result_dict["tables"]:
                table_data = {
                    "row_count": len(table.get("cells", [])),
                    "column_count": table.get("columnCount", 0),
                    "cells": []
                }
                
                # Process cells
                for cell in table.get("cells", []):
                    table_data["cells"].append({
                        "text": cell.get("content", ""),
                        "row_index": cell.get("rowIndex", 0),
                        "column_index": cell.get("columnIndex", 0)
                    })
                    
                extracted_data["tables"].append(table_data)
        
        # For prebuilt-document, also extract key-value pairs
        if "keyValuePairs" in result_dict:
            for kv_pair in result_dict["keyValuePairs"]:
                key = kv_pair.get("key", {}).get("content", "")
                value = kv_pair.get("value", {}).get("content", "")
                
                if key and value:
                    extracted_data["key_value_pairs"].append({
                        "key": key,
                        "value": value
                    })
        
        return extracted_data

    def _get_nested_value(self, obj, *keys):
        """Get a value from a nested dictionary by navigating through multiple keys"""
        current = obj
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _process_invoice_results(self, result:dict):
        """Process invoice-specific results from Azure"""
        try:

            doc = result.get("documents")[0]  # Get the first document
            if not doc:
                return {}
            if doc.get('confidence') < ACCEPTABLE_CONFIDENCE:
                raise ProcessingError("Confidence level too low")

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
            fields = doc.get("fields")
            
            # Extract basic invoice fields
            supplier_name = self._get_field_value(fields, "VendorName") or "Unknown Supplier"
            supplier_name = supplier_name[:140]
            invoice_id = self._get_field_value(fields, "InvoiceId") or ""
            invoice_id = invoice_id[:140]
            # Default invoice date to today if missing
            today = datetime.datetime.now().strftime("%Y-%m-%d")
            invoice_date = self._get_field_value(fields, "InvoiceDate") or today
            due_date = self._get_field_value(fields, "DueDate") or invoice_date

            # Ensure due_date is not before invoice_date
            try:
                invoice_date_obj = datetime.datetime.strptime(invoice_date, "%Y-%m-%d").date()
                due_date_obj = datetime.datetime.strptime(due_date, "%Y-%m-%d").date()
                if due_date_obj < invoice_date_obj:
                    due_date = invoice_date
            except (ValueError, TypeError):
                # If date parsing fails, ensure due_date equals invoice_date
                due_date = invoice_date
            tax = self._get_field_value(fields, "TotalTax") or 0.0
            net = self._get_field_value(fields, "SubTotal") or 0.0
            total = self._get_field_value(fields, "InvoiceTotal") or 0.0
            
            # Validate that total = net + tax (allowing for small floating point differences)
            if abs((net + tax) - total) > 0.01 and total > 0:
                logger.warning(f"Invoice total validation failed: {net} + {tax} != {total}")
                # Recalculate to ensure consistency - prefer total as the source of truth
                if net > 0 and tax > 0:
                    # Both net and tax values are available, keep them
                    total = net + tax
                elif total > 0 and tax > 0:
                    # Derive net from total and tax
                    net = total - tax
                elif total > 0 and net > 0:
                    # Derive tax from total and net
                    tax = total - net
            
            items = self._get_field_value(fields, "Items") or []
            
            # Process line items if available
            line_items = []
            total_items_amount = 0
            
            for item_obj in items:
                if item_obj.get("confidence") < ACCEPTABLE_CONFIDENCE:
                    continue
                
                value_obj = item_obj.get("valueObject")
                description = value_obj.get("Description").get("valueString")
                if value_obj.get("ItemCode"):
                    item_code = value_obj.get("ItemCode").get("valueString")
                else:
                    item_code = self._create_item_code_from_description(description)
                quantity = value_obj.get("Quantity").get("valueNumber") if value_obj.get("Quantity") else 1
                amount = value_obj.get("Amount").get("valueCurrency").get("amount") or 0
                stock_uom = value_obj.get("Unit").get("valueString") if value_obj.get("Unit") else None
                stock_uom = stock_uom[:140] if stock_uom else "Nos"
                
                # Ensure item amount excludes tax
                unit_price = round(amount / quantity if quantity else amount, 2)
                total_items_amount += amount
                
                line_items.append({
                    "item_code": item_code,
                    "description": description,
                    "qty": quantity,
                    "rate": unit_price,
                    "amount": amount,
                    "stock_uom": stock_uom,
                    "item_group": "All Item Groups"
                })
            
            # Scale item amounts if their total differs significantly from net amount
            if line_items and abs(total_items_amount - net) > 0.01 and net > 0:
                scale_factor = net / total_items_amount
                # Apply scaling with rounding
                for item in line_items:
                    item["rate"] = round(item["rate"] * scale_factor, 2)
                    item["amount"] = round(item["amount"] * scale_factor, 2)
                
                # After scaling, check if the sum still matches the target
                new_total = sum(item["amount"] for item in line_items)
                diff = round(net - new_total, 2)
                
                # If there's still a difference, adjust the largest item
                if abs(diff) > 0.001:
                    # Find the item with the largest amount
                    largest_item = max(line_items, key=lambda x: x["amount"])
                    # Adjust its amount to make the total match exactly
                    largest_item["amount"] = round(largest_item["amount"] + diff, 2)
                    # Recalculate its rate if quantity is not zero
                    if largest_item["qty"]:
                        largest_item["rate"] = round(largest_item["amount"] / largest_item["qty"], 2)
            
            # If no line items detected, create one based on net amount (not total)
            if not line_items and net:
                line_items.append({
                    "item_code": "Item",
                    "Description": "Item",
                    "qty": 1,
                    "rate": net,
                    "amount": net,
                    "item_group": "All Item Groups"
                })
            
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
                        "description": item["description"],
                        "item_group": "All Item Groups",
                        "stock_uom": item["stock_uom"],
                        "is_stock_item": 0
                    }
                })
            
            # Add purchase invoice with all details
            result.append({
                "doc": {
                    "doctype": "Purchase Invoice",
                    "supplier": supplier_name,
                    "bill_no": invoice_id,
                    "bill_date": invoice_date,
                    "posting_date": invoice_date,
                    "set_posting_time": 1,
                    "due_date": due_date,
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
            })
            
            return {"items": result}
            
        except Exception as e:
            logger.error(f"Error processing invoice results: {str(e)}")
            return {}
    
    def _get_field_value(self, fields, field_name):
        """Helper to extract field value from Azure SDK objects or dictionaries"""
        # Check if field exists
        if field_name not in fields:
            return None
        
        field = fields[field_name]
        
        # If field is None or empty
        if not field:
            return None
        
        if isinstance(field, dict):
            
            # Fpr string values
            if 'valueString' in field:
                value_string = field.get('valueString')
                return value_string[:140] if value_string else None
            
            # For array values (like Items)
            if 'valueArray' in field:
                return field.get('valueArray')
            
            # For currency values
            if 'valueCurrency' in field:
                return field.get('valueCurrency')['amount']
            
            # For date values
            if 'valueDate' in field:
                return field.get('valueDate')
        
        # Fallback: try to get content or return the field itself
        if isinstance(field, dict):
            return field.get('content') if 'content' in field else field
        else:
            return field.content if hasattr(field, 'content') else field

    def _create_item_code_from_description(self, description):
        """Generate a meaningful item code from description when ItemCode is missing"""
        import re
        import hashlib
        
        if not description:
            return "ITEM"
        
        description = description[:15]
        
        # Convert to lowercase and remove special characters
        slug = description.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug)
        
        # Trim and take first 15 chars of the slug
        slug = slug.strip('-').strip()[:15]
        
        # Add a short hash to ensure uniqueness
        hash_suffix = hashlib.md5(description.encode()).hexdigest()[:5]
        
        return f"{slug}-{hash_suffix}"
    
    def _create_item_code_from_description(self, description):
        """Generate a meaningful item code from description when ItemCode is missing"""
        import re
        import hashlib
        
        if not description:
            return "ITEM"
        
        description = description[:15]
        
        # Convert to lowercase and remove special characters
        slug = description.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s-]+', '-', slug)
        
        # Trim and take first 15 chars of the slug
        slug = slug.strip('-').strip()[:15]
        
        # Add a short hash to ensure uniqueness
        hash_suffix = hashlib.md5(description.encode()).hexdigest()[:5]
        
        return f"{slug}-{hash_suffix}"