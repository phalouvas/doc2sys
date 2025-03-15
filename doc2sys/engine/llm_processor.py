import frappe
import requests
import json
import os
import base64
from .utils import logger

# Move hardcoded values to constants
MAX_TEXT_LENGTH = 10000
DEFAULT_TEMPERATURE = 0.1

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
                                     fields=["document_type", "target_doctype"],
                                     filters={"enabled": 1})
            
            available_types = [dt.document_type for dt in doc_types]
            type_to_doctype = {dt.document_type: dt.target_doctype for dt in doc_types}
            
            # Format available types with quotes to clarify they are exact phrases
            formatted_types = [f'"{doc_type}"' for doc_type in available_types]
            
            # Set up headers with API key if provided
            headers = {
                "Content-Type": "application/json"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            # Improved prompt with clear formatting
            prompt = f"""
            Your task is to classify the attached document. Analyze it and determine what type of document it is.
            
            Available document types (use EXACT match from this list):
            {', '.join(formatted_types)}
            
            IMPORTANT: You must select document types EXACTLY as written above, including spaces and capitalization.
            If the document doesn't match any of the available types, classify it as "unknown".
            
            Respond in JSON format only:
            {{
                "document_type": "the determined document type - MUST be an exact match from the list above",
                "confidence": 0.0-1.0 (your confidence level),
                "reasoning": "brief explanation of why"
            }}
            """
            
            # Default API payload
            api_payload = {
                "model": self.model,
                "temperature": DEFAULT_TEMPERATURE,
                "response_format": {"type": "json_object"}
            }
            
            # If a file path is provided, handle based on file type
            if file_path:
                file_extension = os.path.splitext(file_path)[1].lower()
                content_type = self._get_content_type(file_extension)
                
                # For images, use direct base64 encoding
                if content_type.startswith('image/'):
                    # Create message with mixed content (text and image)
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
                else:
                    # For non-image files, use the file upload approach
                    file_id = self.upload_file(file_path)
                    if file_id:
                        api_payload["messages"] = [
                            {"role": "user", "content": prompt}
                        ]
                        api_payload["files"] = [{"type": "file", "id": file_id}]
                    else:
                        # Fallback to text if file upload failed
                        if text:
                            text_for_api = text[:MAX_TEXT_LENGTH]  # Truncate if too long
                            api_payload["messages"] = [
                                {"role": "user", "content": prompt + "\n\nDocument text:\n" + text_for_api}
                            ]
                        else:
                            return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
            elif text:
                # Use text if no file path provided
                text_for_api = text[:MAX_TEXT_LENGTH]  # Truncate if too long
                api_payload["messages"] = [
                    {"role": "user", "content": prompt + "\n\nDocument text:\n" + text_for_api}
                ]
            else:
                return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
            
            # Call Open WebUI API
            response = requests.post(
                f"{self.endpoint}/api/chat/completions",
                headers=headers,
                json=api_payload
            )
            
            if response.status_code != 200:
                logger.error(f"Open WebUI API error: {response.text}")
                return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
                
            # Parse response
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")

            # Calculate token usage costs
            token_cost = self._calculate_token_cost(result.get("usage", {}))

            try:
                # Try to parse the JSON response
                cleaned_content = self._clean_json_response(content)
                classification = json.loads(cleaned_content)
                
                # Add target doctype based on document type
                doc_type = classification.get("document_type", "unknown")
                classification["target_doctype"] = type_to_doctype.get(doc_type)
                
                # Add token usage and cost data
                classification["token_usage"] = self._calculate_token_cost(result.get("usage", {}))
                
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
            
            # Default API payload
            api_payload = {
                "model": self.model,
                "messages": messages,
                "temperature": DEFAULT_TEMPERATURE,
                "response_format": {"type": "json_object"}
            }
            
            # Prepare the default prompt text
            default_prompt = f"""
            Identify the JSON structure of an ERPNext {document_type} doctype. 
            Extract the relevant data and present the extracted data in JSON format.
            Only include fields that are present in the document.
            """
            
            # If a file path is provided, handle based on file type
            if file_path:
                file_extension = os.path.splitext(file_path)[1].lower()
                content_type = self._get_content_type(file_extension)
                
                # For images, use direct base64 encoding
                if content_type.startswith('image/'):
                    # Create message with mixed content (text and image)
                    with open(file_path, 'rb') as image_file:
                        base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                        
                    # Use custom prompt if available, otherwise use default
                    prompt = custom_prompt if custom_prompt else default_prompt
                    
                    # Construct message with text and image parts
                    message_content = [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64_image}"}}
                    ]
                    
                    # Set up messages with the mixed content
                    api_payload["messages"].append(
                        {"role": "user", "content": message_content}
                    )
                else:
                    # For non-image files, use the file upload approach
                    file_id = self.upload_file(file_path)
                    if file_id:
                        prompt = custom_prompt if custom_prompt else default_prompt
                        messages.append({"role": "user", "content": prompt})
                        
                        # Add the file to the API payload with correct structure
                        api_payload["files"] = [{"type": "file", "id": file_id}]
                    else:
                        # Fallback to text if file upload failed
                        if not text:
                            return {}
                        text_for_api = text[:MAX_TEXT_LENGTH]  # Truncate if too long
                        
                        # Use custom prompt if available, otherwise use default
                        if custom_prompt:
                            prompt = f"{custom_prompt}\n\n{text_for_api}"
                        else:
                            prompt = f"{default_prompt}\n\n{text_for_api}"
                        messages.append({"role": "user", "content": prompt})
            else:
                # Use text if no file path provided
                if not text:
                    return {}
                
                text_for_api = text[:MAX_TEXT_LENGTH]  # Truncate if too long
                
                # Use custom prompt if available, otherwise use default
                if custom_prompt:
                    prompt = f"{custom_prompt}\n\n{text_for_api}"
                else:
                    prompt = f"{default_prompt}\n\n{text_for_api}"
                messages.append({"role": "user", "content": prompt})
            
            # Update messages in the API payload (for non-image cases where we didn't already set it)
            if "messages" in api_payload and not any(msg.get("role") == "user" for msg in api_payload["messages"]):
                api_payload["messages"] = messages
            
            # Call Open WebUI API
            response = requests.post(
                f"{self.endpoint}/api/chat/completions",
                headers=headers,
                json=api_payload
            )
            
            if response.status_code != 200:
                logger.error(f"Open WebUI API error: {response.text}")
                return {}
                
            # Parse response
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
            
            # Calculate token usage costs
            token_cost = self._calculate_token_cost(result.get("usage", {}))

            try:
                # Try to parse the JSON response
                cleaned_content = self._clean_json_response(content)
                extracted_data = json.loads(cleaned_content)
                
                # Add token usage as metadata - use the already calculated token_cost
                extracted_data["_token_usage"] = token_cost
                
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
            
            # Get cost settings from Doc2Sys Settings - added logging
            input_price_per_million = frappe.db.get_single_value("Doc2Sys Settings", "input_token_price") or 0.0
            output_price_per_million = frappe.db.get_single_value("Doc2Sys Settings", "output_token_price") or 0.0
            
            # Ensure values are numeric
            input_price_per_million = float(input_price_per_million)
            output_price_per_million = float(output_price_per_million)
            
            # Log values for debugging
            logger.debug(f"Token prices - Input: {input_price_per_million}, Output: {output_price_per_million}")
            logger.debug(f"Token counts - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")
            
            # Calculate cost (convert from price per million to price per token)
            input_cost = (input_tokens * input_price_per_million) / 1000000
            output_cost = (output_tokens * output_price_per_million) / 1000000
            total_cost = input_cost + output_cost
            
            # Log calculated costs
            logger.debug(f"Calculated costs - Input: {input_cost}, Output: {output_cost}, Total: {total_cost}")
            
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
