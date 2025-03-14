import frappe
import requests
import json
import os
import base64
from .utils import logger

class LLMProcessor:
    """Process documents using various LLM providers"""
    
    @staticmethod
    def create():
        """Factory method to create the appropriate LLM processor"""
        # Always return OpenWebUI processor regardless of settings for backward compatibility
        provider = frappe.db.get_single_value("Doc2Sys Settings", "llm_provider") or "Open WebUI"
        
        if provider != "Open WebUI":
            logger.warning(f"Only Open WebUI provider is supported, got: {provider}, using Open WebUI")
            
        return OpenWebUIProcessor()


class OpenWebUIProcessor:
    """Process documents using Open WebUI"""
    
    def __init__(self):
        """Initialize Open WebUI processor"""
        self.endpoint = frappe.db.get_single_value("Doc2Sys Settings", "openwebui_endpoint") or "http://localhost:3000/api/v1"
        self.model = frappe.db.get_single_value("Doc2Sys Settings", "openwebui_model") or "llama3"
        self.api_key = frappe.utils.password.get_decrypted_password("Doc2Sys Settings", "Doc2Sys Settings", "openwebui_apikey") or ""
        self.file_cache = {}  # Cache for uploaded file IDs
    
    def upload_file(self, file_path):
        """
        Upload a file to Open WebUI for processing
        
        Args:
            file_path: Path to the file to be uploaded
            
        Returns:
            str: File ID or URL for reference in API calls
        """
        # Check if this file has already been uploaded in this session
        if file_path in self.file_cache:
            return self.file_cache[file_path]  # Fixed incomplete line
            
        try:
            # Set up headers with API key if provided
            headers = {
                "Content-Type": "application/json"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Read file and encode as base64
            file_name = os.path.basename(file_path)
            file_extension = os.path.splitext(file_name)[1].lower()
            
            with open(file_path, "rb") as f:
                file_content = f.read()
                base64_encoded = base64.b64encode(file_content).decode("utf-8")
            
            # Determine content type based on file extension
            content_type = self._get_content_type(file_extension)
            
            # Upload file to Open WebUI
            response = requests.post(
                f"{self.endpoint}/api/files",
                headers=headers,
                json={
                    "file": base64_encoded,
                    "filename": file_name,
                    "content_type": content_type
                }
            )
            
            if response.status_code != 200:
                logger.error(f"File upload error: {response.text}")
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
                                     fields=["document_type", "target_doctype"],
                                     filters={"enabled": 1})
            
            available_types = [dt.document_type for dt in doc_types]
            type_to_doctype = {dt.document_type: dt.target_doctype for dt in doc_types}
            
            # Set up headers with API key if provided
            headers = {
                "Content-Type": "application/json"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            messages = [
                {"role": "system", "content": "You are a document classification assistant. Always respond in JSON."}
            ]
            
            # If a file path is provided, upload the file and reference it
            if file_path:
                file_id = self.upload_file(file_path)
                if file_id:
                    prompt = f"""
                    Your task is to classify the attached document. Analyze it and determine what type of document it is.
                    Available document types: {', '.join(available_types)}
                    
                    If the document doesn't match any of the available types, classify it as "unknown".
                    
                    Respond in JSON format only:
                    {{
                        "document_type": "the determined document type",
                        "confidence": 0.0-1.0 (your confidence level),
                        "reasoning": "brief explanation of why"
                    }}
                    """
                    
                    messages.append({
                        "role": "user", 
                        "content": prompt,
                        "file_ids": [file_id]
                    })
                else:
                    # Fallback to text if file upload failed
                    if text:
                        text_for_api = text[:10000]  # Truncate if too long
                    else:
                        return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
            else:
                # Use text if no file path provided
                if not text:
                    return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
                
                text_for_api = text[:10000]  # Truncate if too long
                
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
                messages.append({"role": "user", "content": prompt})
            
            # Call Open WebUI API (compatible with OpenAI format)
            response = requests.post(
                f"{self.endpoint}/api/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Open WebUI API error: {response.text}")
                return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
                
            # Parse response
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            try:
                # Try to parse the JSON response
                cleaned_content = self._clean_json_response(content)
                classification = json.loads(cleaned_content)
                
                # Add target doctype based on document type
                doc_type = classification.get("document_type", "unknown")
                classification["target_doctype"] = type_to_doctype.get(doc_type)
                
                return classification
            except json.JSONDecodeError:
                # If we couldn't parse JSON, do basic text analysis
                logger.warning(f"Failed to parse JSON from Open WebUI: {content}")
                
                # Try to extract document type through simple text matching
                return self._extract_document_type_from_text(content, available_types, type_to_doctype)
                
        except Exception as e:
            logger.error(f"Open WebUI processing error: {str(e)}")
            return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
            
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
            
            # Set up headers with API key if provided
            headers = {
                "Content-Type": "application/json"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            messages = [
                {"role": "system", "content": "You are an AI language model. Always respond in JSON."}
            ]
            
            # If a file path is provided, upload the file and reference it
            if file_path:
                file_id = self.upload_file(file_path)
                if file_id:
                    if custom_prompt:
                        prompt = custom_prompt
                    else:
                        # Fallback to default prompt
                        prompt = f"""
                        Identify the JSON structure of an ERPNext {document_type} doctype. 
                        Analyze the attached document, extract the relevant data and present the extracted data in JSON format.
                        Only include fields that are present in the document.
                        """
                    
                    messages.append({
                        "role": "user", 
                        "content": prompt,
                        "file_ids": [file_id]
                    })
                else:
                    # Fallback to text if file upload failed
                    if not text:
                        return {}
                    text_for_api = text[:10000]  # Truncate if too long
            else:
                # Use text if no file path provided
                if not text:
                    return {}
                
                text_for_api = text[:10000]  # Truncate if too long
                
                # Use custom prompt if available, otherwise use default
                if custom_prompt:
                    prompt = f"{custom_prompt}\n\n{text_for_api}"
                else:
                    # Fallback to default prompt
                    prompt = f"""
                    Identify the json structure of an erpnext {document_type} doctype. 
                    Then based on below text extract the relevant data and present to me only the extracted data.
                    
                    {text_for_api}
                    """
                messages.append({"role": "user", "content": prompt})
            
            # Call Open WebUI API
            response = requests.post(
                f"{self.endpoint}/api/chat/completions",
                headers=headers,
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"}
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Open WebUI API error: {response.text}")
                return {}
                
            # Parse response
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            try:
                # Try to parse the JSON response
                cleaned_content = self._clean_json_response(content)
                extracted_data = json.loads(cleaned_content)
                return extracted_data
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Open WebUI: {content}")
                return {}
                
        except Exception as e:
            logger.error(f"Open WebUI processing error: {str(e)}")
            return {}
    
    def _clean_json_response(self, content):
        """Helper method to clean JSON response from markdown formatting"""
        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content[7:]
        elif cleaned_content.startswith("```"):
            cleaned_content = cleaned_content[3:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
            
        return cleaned_content.strip()
    
    def _extract_document_type_from_text(self, content, available_types, type_to_doctype):
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
                "confidence": 0.6,  # Moderate confidence for text matching
                "target_doctype": type_to_doctype.get(best_match)
            }
        else:
            return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
