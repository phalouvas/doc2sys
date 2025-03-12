import frappe
import requests
import json
import os
from .utils import logger

class DeepSeekProcessor:
    """Process documents using DeepSeek LLM"""
    
    def __init__(self, config=None):
        """Initialize with optional configuration"""
        self.config = config
        self.api_key = self._get_api_key()
        self.api_url = "https://api.deepseek.com/v1/chat/completions"  # Replace with actual DeepSeek API endpoint
        
    def _get_api_key(self):
        """Get API key from settings"""
        try:
            return frappe.db.get_single_value("Doc2Sys Settings", "deepseek_api_key")
        except:
            logger.warning("DeepSeek API key not found in settings")
            return None
            
    def classify_document(self, text):
        """
        Classify document using DeepSeek
        
        Args:
            text: Document text content
            
        Returns:
            dict: Classification result with document type and confidence
        """
        if not self.api_key:
            logger.error("DeepSeek API key not configured")
            return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
        
        # Truncate text if too long (DeepSeek has token limits)
        text_for_api = text[:8000]  # Adjust based on model token limits
        
        try:
            # Get available document types for context
            doc_types = frappe.get_all("Doc2Sys Document Type", 
                                     fields=["document_type", "target_doctype"],
                                     filters={"enabled": 1})
            
            available_types = [dt.document_type for dt in doc_types]
            type_to_doctype = {dt.document_type: dt.target_doctype for dt in doc_types}
            
            # Create prompt for document classification
            prompt = f"""
            Your task is to classify a document. Analyze the text and determine what type of document it is.
            Available document types: {', '.join(available_types)}
            
            If the document doesn't match any of the available types, classify it as "unknown".
            
            Document text:
            {text_for_api}
            
            Respond in JSON format only:
            {{
                "document_type": "the determined document type",
                "confidence": 0.0-1.0 (your confidence level),
                "reasoning": "brief explanation of why"
            }}
            """
            
            # Call DeepSeek API
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",  # Replace with actual model name
                    "messages": [
                        {"role": "system", "content": "You are a document classification assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,  # Low temperature for more deterministic output
                    "response_format": {"type": "json_object"}
                }
            )
            
            # Parse response
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                classification = json.loads(content)
                
                # Add target doctype based on document type
                doc_type = classification.get("document_type", "unknown")
                classification["target_doctype"] = type_to_doctype.get(doc_type)
                
                return classification
            else:
                logger.error(f"Unexpected API response: {result}")
                return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
                
        except Exception as e:
            logger.error(f"DeepSeek API error: {str(e)}")
            return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
            
    def extract_data(self, text, document_type):
        """
        Extract structured data from document using DeepSeek
        
        Args:
            text: Document text content
            document_type: Type of document
            
        Returns:
            dict: Extracted data fields
        """
        if not self.api_key:
            logger.error("DeepSeek API key not configured")
            return {}
        
        # Truncate text if too long
        text_for_api = text[:8000]
        
        try:
            # Get field mappings for context
            field_mappings = self._get_field_mapping(document_type)
            fields_to_extract = list(field_mappings.keys())
            
            # Create prompt for data extraction
            prompt = f"""
            Extract information from this {document_type} document.
            
            Please extract the following fields:
            {', '.join(fields_to_extract)}
            
            Document text:
            {text_for_api}
            
            Respond in JSON format only with the extracted fields.
            For example:
            {{
                "invoice_number": "INV-12345",
                "date": "2025-03-12",
                "total_amount": 1250.00
            }}
            
            Only include fields where you found values. If a field can't be found, omit it.
            """
            
            # Call DeepSeek API
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",  # Replace with actual model name
                    "messages": [
                        {"role": "system", "content": "You are a document information extraction assistant."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            
            # Parse response
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                extracted_data = json.loads(content)
                return extracted_data
            else:
                logger.error(f"Unexpected API response: {result}")
                return {}
                
        except Exception as e:
            logger.error(f"DeepSeek API error: {str(e)}")
            return {}
            
    def _get_field_mapping(self, document_type):
        """Get field mapping for document type"""
        mapping = {}
        try:
            # Get DocType ID for document type
            doc_type_id = frappe.get_value("Doc2Sys Document Type", {"document_type": document_type}, "name")
            if not doc_type_id:
                return {}
                
            # Get target doctype
            target_doctype = frappe.get_value("Doc2Sys Document Type", doc_type_id, "target_doctype")
            if not target_doctype:
                return {}
                
            # Get field mappings
            mappings = frappe.get_all("Doc2Sys Field Mapping",
                                    filters={"target_doctype": target_doctype, "enabled": 1},
                                    fields=["source_field", "target_field"])
            
            for field in mappings:
                mapping[field.source_field] = field.target_field
                
            return mapping
        except Exception as e:
            logger.error(f"Error loading field mappings: {str(e)}")
            return {}