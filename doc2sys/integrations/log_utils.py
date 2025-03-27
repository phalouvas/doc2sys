# NEW FILE: Contains logging functionality with no imports from other integration modules
import frappe
from typing import Dict, Any, Optional

def create_integration_log(integration_type: str, status: str, message: str, 
                           data: Optional[Dict] = None, 
                           doc_reference: Optional[str] = None,
                           user: Optional[str] = None) -> Dict[str, Any]:
    """Create a log entry for integration activity"""
    try:
        log_data = {
            "integration_type": integration_type,
            "status": status,
            "message": message[:140] if message else "",  # Truncate if too long
            "data": frappe.as_json(data) if data else None,
            "reference_doctype": "Doc2Sys Item",
            "reference_name": doc_reference,
            "user": user or frappe.session.user
        }
        
        # Create log entry in the database
        log = frappe.get_doc({
            "doctype": "Integration Log",
            **log_data
        })
        log.insert(ignore_permissions=True)
        frappe.db.commit()
        
        return {"success": True, "log_id": log.name}
    except Exception as e:
        frappe.log_error(f"Failed to create integration log: {str(e)}")
        return {"success": False, "error": str(e)}