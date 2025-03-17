import frappe
import json
import requests
from typing import Dict, Any, Optional

def get_integration_settings(integration_name: str) -> Dict[str, Any]:
    """Get settings for a specific integration"""
    settings = frappe.get_doc("Doc2Sys Integration Settings", integration_name)
    return settings.as_dict() if settings else {}

def execute_webhook(url: str, data: Dict[str, Any], 
                   headers: Optional[Dict[str, str]] = None, 
                   method: str = "POST") -> Dict[str, Any]:
    """Execute a webhook to an external system"""
    try:
        headers = headers or {"Content-Type": "application/json"}
        
        if method == "POST":
            response = requests.post(url, json=data, headers=headers)
        elif method == "PUT":
            response = requests.put(url, json=data, headers=headers)
        else:
            response = requests.get(url, params=data, headers=headers)
            
        response.raise_for_status()
        return {"success": True, "data": response.json()}
    except Exception as e:
        return {"success": False, "error": str(e)}
