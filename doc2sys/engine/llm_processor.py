import frappe
import requests
import json
import os
import base64
import time  # Add time module import
from .utils import logger
from .exceptions import ProcessingError, LLMProcessingError  # Import the LLMProcessingError

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
        
        if provider != "Open WebUI":
            logger.warning(f"Only Open WebUI provider is supported, got: {provider}, using Open WebUI")
            
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
            1. **Translate non-English text to English** (for analysis), but retain **original text** for JSON output.  
            2. **Extract & Validate**:  
               - **Supplier**:  
                 - Extract original name/country using translated labels (e.g., "Supplier/Proveedor").  
               - **Invoice**:  
                 - **Number**: Extract from labels like "Factura N°", "Rechnung Nr." (original text).  
                 - **Date**: Extract and convert to `YYYY-MM-DD` for both `posting_date` and `bill_date`.  
               - **Items**:  
                 - Extract original names, quantities (integer), rates (float).  
               - **Totals**:  
                 - Validate `net_total + tax = grand_total` (reject mismatches).  
            3. **Generate ERPNext JSON**:  
               ```json  
               [  
                 {  
                   "doc": {  
                     "doctype": "Purchase Invoice",  
                     "supplier": "[Original_Supplier_Name]",  
                     "bill_no": "[Extracted_Invoice_Number]",  
                     "posting_date": "YYYY-MM-DD",  
                     "bill_date": "YYYY-MM-DD",
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
                         "tax_amount": [Tax]  
                       }  
                     ],  
                     "company": "KAINOTOMO PH LTD"  
                   }  
                 }  
               ]
               """
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
            total_duration = usage.get("total_duration", 0)
            
            # Convert duration from nanoseconds to seconds (1 second = 1,000,000,000 nanoseconds)
            total_duration_seconds = total_duration / 1_000_000_000 if total_duration else 0.0
            
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
                "total_cost": total_cost,
                "total_duration": total_duration_seconds  # Now in seconds
            }
        except Exception as e:
            logger.error(f"Error calculating token cost: {str(e)}")
            return {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "input_cost": 0.0,
                "output_cost": 0.0,
                "total_cost": 0.0,
                "total_duration": 0.0
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
