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
        provider = frappe.db.get_single_value("Doc2Sys Settings", "llm_provider") or "Open WebUI"
        
        if provider == "DeepSeek":
            return DeepSeekProcessor()
        else:
            return OpenWebUIProcessor()


class OpenWebUIProcessor:
    """Process documents using Open WebUI"""
    
    def __init__(self):
        """Initialize Open WebUI processor"""
        self.endpoint = frappe.db.get_single_value("Doc2Sys Settings", "openwebui_endpoint") or "http://localhost:3000/api/v1"
        self.model = frappe.db.get_single_value("Doc2Sys Settings", "openwebui_model") or "llama3"
        self.api_key = frappe.utils.password.get_decrypted_password("Doc2Sys Settings", "Doc2Sys Settings", "openwebui_apikey") or ""
        self.file_cache = {}  # Cache for uploaded file IDs
        
        # Cache token pricing
        self.input_price_per_million = float(frappe.db.get_single_value("Doc2Sys Settings", "input_token_price") or 0.0)
        self.output_price_per_million = float(frappe.db.get_single_value("Doc2Sys Settings", "output_token_price") or 0.0)
    
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
                                     fields=["document_type"],
                                     filters={"enabled": 1})
            
            available_types = [dt.document_type for dt in doc_types]
            
            # Format available types with quotes to clarify they are exact phrases
            formatted_types = [f'"{doc_type}"' for doc_type in available_types]
            
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
            
            api_payload = None
            
            # Process file or text input
            if file_path:
                api_payload, _ = self._prepare_file_content(file_path, prompt)
                
                # If file processing failed, try using text if available
                if api_payload is None and text:
                    api_payload = self._prepare_text_content(text, prompt)
            elif text:
                api_payload = self._prepare_text_content(text, prompt)
                
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
                
                # Add target doctype based on document type
                doc_type = classification.get("document_type", "unknown")
                
                # Add token usage and cost data
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
            
            # Prepare the default prompt text
            default_prompt = f"""
            Identify the JSON structure of an ERPNext {document_type} doctype. 
            Extract the relevant data and present the extracted data in JSON format.
            Only include fields that are present in the document.
            """
            
            # Use custom prompt if available, otherwise use default
            prompt = custom_prompt if custom_prompt else default_prompt
            
            api_payload = None
            
            # Process file or text input
            if file_path:
                api_payload, _ = self._prepare_file_content(file_path, prompt)
                
                # If file processing failed, try using text if available
                if api_payload is None and text:
                    api_payload = self._prepare_text_content(text, prompt)
            elif text:
                api_payload = self._prepare_text_content(text, prompt)
                
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
                
                # Add token usage as metadata
                extracted_data["_token_usage"] = token_cost
                
                return extracted_data
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Open WebUI: {content}")
                return {}
                
        except Exception as e:
            logger.error(f"Data extraction error: {str(e)}")
            return {}

    def extract_text(self, file_path=None):
        """
        Extract text from a document using Open WebUI's capabilities
        
        Args:
            file_path: Path to the document file
            
        Returns:
            dict or str: Extracted text and token usage information
        """
        try:
            # Verify file exists
            if not file_path or not os.path.exists(file_path):
                logger.error(f"File not found or invalid path: {file_path}")
                return ""
            
            # Get file extension and content type
            file_extension = os.path.splitext(file_path)[1].lower()
            content_type = self._get_content_type(file_extension)
            
            # Prompt specifically for text extraction
            prompt = """
            Extract all the text content from this document. 
            Include all readable text, maintaining its logical structure as much as possible.
            Do not analyze or interpret the content, just extract the raw text.
            For tables, preserve their structure using plain text formatting.
            """
            
            # Prepare API payload based on file type
            api_payload, _ = self._prepare_file_content(file_path, prompt)
            if not api_payload:
                logger.error(f"Failed to prepare file content for text extraction: {file_path}")
                return ""
            
            # Remove JSON formatting requirement for text extraction to get full content
            if "response_format" in api_payload:
                del api_payload["response_format"]
            
            # Make the API request
            result = self._make_api_request(
                f"{self.endpoint}/api/chat/completions",
                api_payload
            )
            
            if not result:
                logger.error("API request failed for text extraction")
                return ""
            
            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Calculate token usage costs
            token_cost = self._calculate_token_cost(result.get("usage", {}))
            
            # Return both text and token usage information in a structured format
            return {
                "text": content,
                "token_usage": token_cost
            }
            
        except Exception as e:
            logger.error(f"Text extraction error: {str(e)}")
            return ""

    def _clean_json_response(self, content):
        """Enhanced JSON cleaning with better edge case handling"""
        # Start by finding the first '{' and last '}' for more robust extraction
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return content[start_idx:end_idx+1]
        
        # Fallback to current cleaning logic
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
            
            # Log calculated costs
            logger.debug(f"Token counts - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")
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
            response = requests.post(endpoint, headers=request_headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}, {response.text}")
                return {}
                
            return response.json()
        except Exception as e:
            logger.error(f"API request error: {str(e)}")
            return {}

    def _prepare_file_content(self, file_path, prompt):
        """
        Prepare file content for API request based on file type
        
        Args:
            file_path (str): Path to the file
            prompt (str): Prompt to use with the file
            
        Returns:
            tuple: (api_payload, messages) to use in the request
        """
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
        Prepare text content for API request
        
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
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are an AI language model. Always respond in JSON."},
                {"role": "user", "content": f"{prompt}\n\n{text_for_api}"}
            ]
        }
        
        return api_payload


class DeepSeekProcessor:
    """Process documents using DeepSeek API"""
    
    def __init__(self):
        """Initialize DeepSeek processor"""
        self.endpoint = frappe.db.get_single_value("Doc2Sys Settings", "deepseek_endpoint") or "https://api.deepseek.com/v1/chat/completions"
        self.model = frappe.db.get_single_value("Doc2Sys Settings", "deepseek_model") or "deepseek-chat"
        self.api_key = frappe.utils.password.get_decrypted_password("Doc2Sys Settings", "Doc2Sys Settings", "deepseek_apikey") or ""
        
        # Cache token pricing
        self.input_price_per_million = float(frappe.db.get_single_value("Doc2Sys Settings", "input_token_price") or 0.0)
        self.output_price_per_million = float(frappe.db.get_single_value("Doc2Sys Settings", "output_token_price") or 0.0)
    
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
        Classify document using DeepSeek
        
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
            
            api_payload = None
            
            if file_path:
                # Extract text from file for DeepSeek
                extracted_text = self._extract_text_from_file(file_path)
                if extracted_text:
                    text = extracted_text
                    
            if text:
                api_payload = self._prepare_text_content(text, prompt)
            
            # If we couldn't create a valid payload, return default response
            if not api_payload:
                return {"document_type": "unknown", "confidence": 0.0}
                
            # Make the API request
            result = self._make_api_request(self.endpoint, api_payload)
            
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
                
                # Add token usage and cost data
                classification["token_usage"] = token_cost
                
                return classification
            except json.JSONDecodeError:
                # If we couldn't parse JSON, do basic text analysis
                logger.warning(f"Failed to parse JSON from DeepSeek: {content}")
                
                # Try to extract document type through simple text matching
                return self._extract_document_type_from_text(content, available_types)
                
        except Exception as e:
            logger.error(f"Classification error: {str(e)}")
            return {"document_type": "unknown", "confidence": 0.0}
            
    def extract_data(self, file_path=None, text=None, document_type=None):
        """
        Extract structured data from document using DeepSeek
        
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
            
            # Prepare the default prompt text
            default_prompt = f"""
            Identify the JSON structure of an ERPNext {document_type} doctype. 
            Extract the relevant data and present the extracted data in JSON format.
            Only include fields that are present in the document.
            """
            
            # Use custom prompt if available, otherwise use default
            prompt = custom_prompt if custom_prompt else default_prompt
            
            api_payload = None
            
            if file_path:
                # Extract text from file for DeepSeek
                extracted_text = self._extract_text_from_file(file_path)
                if extracted_text:
                    text = extracted_text
                    
            if text:
                api_payload = self._prepare_text_content(text, prompt)
            
            # If we couldn't create a valid payload, return empty dict
            if not api_payload:
                return {}
                
            # Make the API request
            result = self._make_api_request(self.endpoint, api_payload)
            
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
                
                # Add token usage as metadata
                extracted_data["_token_usage"] = token_cost
                
                return extracted_data
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from DeepSeek: {content}")
                return {}
                
        except Exception as e:
            logger.error(f"Data extraction error: {str(e)}")
            return {}

    def extract_text(self, file_path=None):
        """
        Extract text from a document using DeepSeek capabilities
        
        Args:
            file_path: Path to the document file
            
        Returns:
            dict or str: Extracted text and token usage information
        """
        try:
            # Verify file exists
            if not file_path or not os.path.exists(file_path):
                logger.error(f"File not found or invalid path: {file_path}")
                return ""
            
            # Use built-in text extraction method
            extracted_text = self._extract_text_from_file(file_path)
            if not extracted_text or len(extracted_text.strip()) < 100:
                # If basic extraction failed or produced minimal text,
                # try enhanced extraction with LLM
                return self._enhanced_text_extraction(file_path)
            
            # Return the extracted text (no token usage since we used textract)
            return extracted_text
            
        except Exception as e:
            logger.error(f"Text extraction error: {str(e)}")
            return ""

    def _enhanced_text_extraction(self, file_path):
        """
        Enhanced text extraction using DeepSeek LLM capabilities
        
        Args:
            file_path: Path to the document file
            
        Returns:
            dict: Extracted text and token usage information
        """
        try:
            # Convert file to base64 for API submission
            with open(file_path, 'rb') as f:
                file_content = f.read()
            
            file_extension = os.path.splitext(file_path)[1].lower()
            content_type = self._get_content_type(file_extension)
            base64_file = base64.b64encode(file_content).decode('utf-8')
            
            # Prompt specifically for text extraction
            prompt = """
            Extract all the text content from this document. 
            Include all readable text, maintaining its logical structure as much as possible.
            Do not analyze or interpret the content, just extract the raw text.
            For tables, preserve their structure using plain text formatting.
            """
            
            # Prepare API payload for DeepSeek
            api_payload = {
                "model": self.model,
                "temperature": DEFAULT_TEMPERATURE,
                "messages": [
                    {"role": "system", "content": "You are an AI assistant for document text extraction."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{base64_file}"}}
                    ]}
                ]
            }
            
            # Make the API request
            result = self._make_api_request(self.endpoint, api_payload)
            
            if not result:
                logger.error("API request failed for enhanced text extraction")
                return ""
            
            # Extract content from response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Calculate token usage costs
            token_cost = self._calculate_token_cost(result.get("usage", {}))
            
            # Return both text and token usage information in a structured format
            return {
                "text": content,
                "token_usage": token_cost
            }
            
        except Exception as e:
            logger.error(f"Enhanced text extraction error: {str(e)}")
            return ""

    def _extract_text_from_file(self, file_path):
        """
        Extract text from a file using appropriate extraction method
        
        Args:
            file_path: Path to the file
            
        Returns:
            str: Extracted text content or None on failure
        """
        try:
            import textract
            
            # Extract text using textract library
            text = textract.process(file_path).decode('utf-8')
            
            # Truncate if too long
            return text[:MAX_TEXT_LENGTH] if text else None
        except Exception as e:
            logger.error(f"Text extraction error: {str(e)}")
            return None
    
    def _clean_json_response(self, content):
        """Enhanced JSON cleaning with better edge case handling"""
        # Start by finding the first '{' and last '}' for more robust extraction
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return content[start_idx:end_idx+1]
        
        # Fallback to current cleaning logic
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
            
            # Log calculated costs
            logger.debug(f"Token counts - Input: {input_tokens}, Output: {output_tokens}, Total: {total_tokens}")
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
            response = requests.post(endpoint, headers=request_headers, json=payload, timeout=30)
            
            if response.status_code != 200:
                logger.error(f"API error: {response.status_code}, {response.text}")
                return {}
                
            return response.json()
        except Exception as e:
            logger.error(f"API request error: {str(e)}")
            return {}

    def _prepare_text_content(self, text, prompt):
        """
        Prepare text content for API request
        
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
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "You are an AI language model. Always respond in JSON."},
                {"role": "user", "content": f"{prompt}\n\n{text_for_api}"}
            ]
        }
        
        return api_payload
