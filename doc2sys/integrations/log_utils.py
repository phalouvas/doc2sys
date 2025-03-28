import frappe
import json
import logging
from typing import Dict, Any, Optional

# Get a logger specific to integrations
logger = logging.getLogger("frappe.integrations")

def create_integration_log(integration_type: str, status: str, message: str, 
                           data: Optional[Dict] = None, 
                           doc_reference: Optional[str] = None,
                           user: Optional[str] = None) -> Dict[str, Any]:
    """Log integration activity to file instead of database"""
    try:
        # Get current user if not provided
        current_user = user or frappe.session.user
        
        # Format the message with key details
        log_prefix = f"[{integration_type}] [{status.upper()}]"
        log_reference = f"[Doc: {doc_reference}]" if doc_reference else ""
        log_user = f"[User: {current_user}]" if current_user else ""
        
        # Format the main log message
        log_message = f"{log_prefix} {message} {log_user} {log_reference}"
        
        # Determine log level based on status
        if status.lower() == "error":
            log_func = logger.error
        elif status.lower() == "warning":
            log_func = logger.warning
        elif status.lower() == "success":
            log_func = logger.info
        else:
            log_func = logger.info
            
        # Log the message
        log_func(log_message)
        
        # If additional data is provided, log it as JSON (at debug level)
        if data:
            try:
                data_str = json.dumps(data, default=str)
                logger.debug(f"{log_prefix} Additional data: {data_str}")
            except Exception as data_err:
                logger.warning(f"{log_prefix} Could not serialize log data: {str(data_err)}")
        
        return {"success": True}
    except Exception as e:
        # Don't use frappe.log_error as it might create a database entry
        print(f"Failed to log integration activity: {str(e)}")
        return {"success": False, "error": str(e)}