import frappe
import requests
import json
import os
from .utils import logger

class LLMProcessor:
    """Process documents using various LLM providers"""
    
    @staticmethod
    def create():
        """Factory method to create the appropriate LLM processor based on settings"""
        provider = frappe.db.get_single_value("Doc2Sys Settings", "llm_provider") or "DeepSeek"
        
        if provider == "Ollama":
            return OllamaProcessor()
        elif provider == "DeepSeek":
            return DeepSeekProcessor()
        else:
            logger.warning(f"Unsupported LLM provider: {provider}, falling back to DeepSeek")
            return DeepSeekProcessor()


class OllamaProcessor:
    """Process documents using locally-hosted Ollama LLM"""
    
    def __init__(self):
        """Initialize Ollama processor"""
        self.endpoint = frappe.db.get_single_value("Doc2Sys Settings", "ollama_endpoint") or "http://localhost:11434"
        self.model = frappe.db.get_single_value("Doc2Sys Settings", "ollama_model") or "llama3"
        
    def classify_document(self, text):
        """
        Classify document using Ollama
        
        Args:
            text: Document text content
            
        Returns:
            dict: Classification result with document type and confidence
        """
        # Truncate text if too long
        text_for_api = text[:10000]  # Adjust based on model capabilities
        
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
            
            # Call Ollama API
            response = requests.post(
                f"{self.endpoint}/api/chat",
                headers={ "Content-Type": "application/json" },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are a document classification assistant. Always respond in JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "format": "json" # Request JSON output if the model supports it
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.text}")
                return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
                
            # Parse response
            result = response.json()
            content = result.get("message", {}).get("content", "{}")
            
            try:
                # Try to parse the JSON response
                # Strip any markdown code blocks if present
                cleaned_content = content.strip()
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]
                    
                cleaned_content = cleaned_content.strip()
                classification = json.loads(cleaned_content)
                
                # Add target doctype based on document type
                doc_type = classification.get("document_type", "unknown")
                classification["target_doctype"] = type_to_doctype.get(doc_type)
                
                return classification
            except json.JSONDecodeError:
                # If we couldn't parse JSON, do basic text analysis
                logger.warning(f"Failed to parse JSON from Ollama: {content}")
                
                # Try to extract document type through simple text matching
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
                
        except Exception as e:
            logger.error(f"Ollama processing error: {str(e)}")
            return {"document_type": "unknown", "confidence": 0.0, "target_doctype": None}
            
    def extract_data(self, text, document_type):
        """
        Extract structured data from document using Ollama
        
        Args:
            text: Document text content
            document_type: Type of document
            
        Returns:
            dict: Extracted data fields
        """
        # Truncate text if too long
        text_for_api = text[:10000]
        
        try:
            # Get the custom prompt from the document type
            custom_prompt = frappe.db.get_value(
                "Doc2Sys Document Type", 
                {"document_type": document_type}, 
                "extract_data_prompt"
            )
            
            # Use custom prompt if available, otherwise use default
            if custom_prompt:
                prompt = f"{custom_prompt}\n\n{text_for_api}"
            else:
                # Fallback to default prompt
                prompt = f"""
                Identify the json structure of an erpnext {document_type} doctype. Then based on below text extract the relevant data and present to me only the extracted data.
                
                {text_for_api}
                """
            
            # Call Ollama API
            response = requests.post(
                f"{self.endpoint}/api/chat",
                headers={ "Content-Type": "application/json" },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "You are an AI language model. Always respond in JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False,
                    "format": "json" # Request JSON output if the model supports it
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Ollama API error: {response.text}")
                return {}
                
            # Parse response
            result = response.json()
            content = result.get("message", {}).get("content", "{}")
            
            try:
                # Try to parse the JSON response
                # Strip any markdown code blocks if present
                cleaned_content = content.strip()
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]
                    
                cleaned_content = cleaned_content.strip()
                extracted_data = json.loads(cleaned_content)

                return extracted_data
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Ollama: {content}")
                return {}
                
        except Exception as e:
            logger.error(f"Ollama processing error: {str(e)}")
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


class DeepSeekProcessor:
    """Process documents using DeepSeek LLM"""
    
    def __init__(self):
        """Initialize DeepSeek processor"""
        self.api_key = frappe.db.get_single_value("Doc2Sys Settings", "deepseek_api_key")
        self.api_url = "https://api.deepseek.com/v1/chat/completions"  # Replace with actual DeepSeek API endpoint
        
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
        
        # Truncate text if too long
        text_for_api = text[:8000]
        
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
            # Get the custom prompt from the document type
            custom_prompt = frappe.db.get_value(
                "Doc2Sys Document Type", 
                {"document_type": document_type}, 
                "extract_data_prompt"
            )
            
            # Use custom prompt if available, otherwise use default
            if custom_prompt:
                prompt = f"{custom_prompt}\n\n{text_for_api}"
            else:
                # Fallback to default prompt
                prompt = f"""
                Extract all relevant information from the following {document_type} document.
                
                Document text:
                {text_for_api}
                
                Respond in JSON format only with the extracted fields.
                For example:
                {{
                    "field1": "value1",
                    "field2": "value2",
                    ...
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