# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class Doc2SysSettings(Document):
    def validate(self):
        """Validate settings"""
        if self.max_file_size_mb <= 0:
            frappe.throw("Maximum file size must be greater than 0")
            
    def get_supported_file_extensions(self):
        """Return list of supported file extensions"""
        return [ft.file_extension.lower().strip() for ft in self.supported_file_types if ft.file_extension]
    
    def get_max_file_size_bytes(self):
        """Return max file size in bytes"""
        return self.max_file_size_mb * 1024 * 1024

@frappe.whitelist()
def test_ollama_connection():
    """Test connection to Ollama server"""
    import requests
    
    try:
        endpoint = frappe.db.get_single_value("Doc2Sys Settings", "ollama_endpoint") or "http://localhost:11434"
        model = frappe.db.get_single_value("Doc2Sys Settings", "ollama_model") or "llama3"
        
        # First check models endpoint to see if server is up
        response = requests.get(f"{endpoint}/api/tags")
        
        if response.status_code != 200:
            return {
                "success": False,
                "message": f"Failed to connect to Ollama server: {response.text}"
            }
            
        # Get list of models
        models = response.json().get("models", [])
        model_names = [m["name"] for m in models]
        
        # Check if specified model is available
        if model not in model_names:
            return {
                "success": False,
                "message": f"Model '{model}' not found. Available models: {', '.join(model_names)}"
            }
            
        # Test simple completion
        chat_response = requests.post(
            f"{endpoint}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": "Hello, can you respond with a simple JSON? {'test': 'successful'}"}
                ],
                "stream": False
            }
        )
        
        if chat_response.status_code != 200:
            return {
                "success": False,
                "message": f"Failed to get response from model: {chat_response.text}"
            }
            
        return {
            "success": True,
            "message": "Successfully connected to Ollama server",
            "available_models": model_names,
            "response_sample": chat_response.json().get("message", {}).get("content", "")
        }
            
    except Exception as e:
        frappe.log_error(f"Error testing Ollama connection: {str(e)}")
        return {
            "success": False,
            "message": f"Error connecting to Ollama: {str(e)}"
        }
