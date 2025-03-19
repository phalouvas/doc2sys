import frappe
from frappe import _ 
from frappe.model.document import Document

class Doc2SysUserSettings(Document):
    def validate(self):
        """Validate user settings"""
        if self.monitor_interval <= 0:
            frappe.throw(_("Monitor interval must be greater than 0"))
        
        # Ensure at least one OCR language is enabled if OCR is enabled
        if self.ocr_enabled and not any(lang.enabled for lang in self.ocr_languages):
            frappe.throw(_("At least one OCR language must be enabled if OCR is activated."))
        
        self.update_scheduler()

    def get_enabled_languages(self):
        """Return a list of enabled OCR languages"""
        return [lang.language_code for lang in self.ocr_languages if lang.enabled]

    def get_llm_provider_options(self):
        """Return available options for LLM provider"""
        return ["Open WebUI"]  # Add more options as needed

    @frappe.whitelist()
    def update_settings(self, settings):
        """Update user-specific settings"""
        for key, value in settings.items():
            setattr(self, key, value)
        self.save()
        
    def update_scheduler(self):
        """Update the scheduler interval for this specific user"""
        if not self.monitor_interval or not self.monitoring_enabled:
            return
            
        # Schedule logic for this specific user
        # This is just a placeholder - you'll need to implement the actual scheduler logic
        # for individual users. Possibly via a dedicated scheduled job that checks all user settings
        pass
    
    @frappe.whitelist()
    def add_common_languages(self):
        """Add common OCR languages to the user settings"""
        common_languages = [
            {"language_code": "eng", "language_name": "English", "enabled": 1},
            {"language_code": "fra", "language_name": "French", "enabled": 0},
            {"language_code": "deu", "language_name": "German", "enabled": 0},
            {"language_code": "spa", "language_name": "Spanish", "enabled": 0},
            {"language_code": "ita", "language_name": "Italian", "enabled": 0},
            {"language_code": "chi_sim", "language_name": "Chinese (Simplified)", "enabled": 0},
            {"language_code": "jpn", "language_name": "Japanese", "enabled": 0},
            {"language_code": "kor", "language_name": "Korean", "enabled": 0},
            {"language_code": "rus", "language_name": "Russian", "enabled": 0},
            {"language_code": "ara", "language_name": "Arabic", "enabled": 0},
            {"language_code": "hin", "language_name": "Hindi", "enabled": 0},
            {"language_code": "por", "language_name": "Portuguese", "enabled": 0},
            {"language_code": "nld", "language_name": "Dutch", "enabled": 0},
            {"language_code": "tur", "language_name": "Turkish", "enabled": 0},
            {"language_code": "ell", "language_name": "Greek", "enabled": 0}
        ]
        
        # Clear existing languages
        self.ocr_languages = []
        
        # Add common languages
        for lang in common_languages:
            self.append("ocr_languages", lang)
        
        self.save()
        return {"success": True, "message": "Common languages added"}
    
    @frappe.whitelist()
    def download_language_models(self):
        """Check for Tesseract language availability"""
        # This delegates to the global settings method since it's system-wide functionality
        settings = frappe.get_doc("Doc2Sys Settings")
        
        # Get list of enabled languages from user settings
        enabled_langs = self.get_enabled_languages()
        if not enabled_langs:
            return {"success": False, "message": "No languages are enabled"}
            
        # Check availability of each language
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
            results = []
            for lang_code in enabled_langs:
                if lang_code in available_languages:
                    results.append({
                        "language_code": lang_code,
                        "success": True,
                        "message": f"Language {lang_code} is available"
                    })
                else:
                    results.append({
                        "language_code": lang_code,
                        "success": False,
                        "message": f"Language {lang_code} is not installed. Please install the Tesseract language pack."
                    })
        except Exception as e:
            frappe.log_error(f"Error checking Tesseract languages: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": f"Failed to check languages: {str(e)}",
                "results": []
            }
        
        # Update language status
        self.update_language_download_status()
        
        return {
            "success": True,
            "message": "Checked Tesseract languages",
            "results": results
        }
    
    @frappe.whitelist()
    def update_language_download_status(self):
        """Update availability status for all languages in user settings"""
        results = []
        
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
            for lang in self.ocr_languages:
                available = lang.language_code in available_languages
                lang.model_downloaded = 1 if available else 0
                results.append({
                    "language_code": lang.language_code,
                    "language_name": lang.language_name,
                    "downloaded": available
                })
        except Exception as e:
            frappe.log_error(f"Error updating language status: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": str(e),
                "languages": []
            }
        
        # Save changes
        self.save()
        
        return {
            "success": True,
            "message": "Language status updated",
            "languages": results
        }
    
    @frappe.whitelist()
    def list_downloaded_languages(self):
        """List all available Tesseract language models"""
        # This delegates to the global settings functionality since it's system-wide
        settings = frappe.get_doc("Doc2Sys Settings")
        return settings.list_downloaded_languages()
    
    @frappe.whitelist()
    def delete_not_enabled_language_models(self):
        """Display information about deleting Tesseract language models"""
        # This delegates to the global settings functionality since it's system-wide
        settings = frappe.get_doc("Doc2Sys Settings")
        return settings.delete_not_enabled_language_models()


@frappe.whitelist()
def process_user_folder(user_settings):
    """Process the monitored folder for a specific user"""
    settings = frappe.get_doc("Doc2Sys User Settings", user_settings)
    
    if not settings.monitoring_enabled or not settings.folder_to_monitor:
        return {
            "success": False,
            "message": "Folder monitoring is not properly configured"
        }
    
    try:
        # Import the folder monitor module
        from doc2sys.doc2sys.tasks.folder_monitor import process_folder
        
        # Process the user's specific folder
        result = process_folder(settings.folder_to_monitor, settings)
        
        return {
            "success": True,
            "message": f"Processed {result['processed']} files from {settings.folder_to_monitor}",
            "details": result
        }
    except Exception as e:
        frappe.log_error(f"Error processing folder for {settings.user}: {str(e)}", "Doc2Sys")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }

@frappe.whitelist()
def test_integration_connection(user_settings, selected):
    """Test the connection for selected user integrations"""
    try:
        # Parse the selected parameter
        if isinstance(selected, str):
            import json
            selected = json.loads(selected)
            
        if not selected or not selected.get('user_integrations'):
            return {"status": "error", "message": "No integration selected"}
            
        # Get all selected integration names
        integration_names = selected['user_integrations']
        settings_doc = frappe.get_doc("Doc2Sys User Settings", user_settings)
        
        # Import the registry
        from doc2sys.integrations.registry import IntegrationRegistry
        
        # Track results for all tested integrations
        results = []
        
        # Test each selected integration
        for integration_name in integration_names:
            # Find the integration by name
            integration = None
            for idx, integ in enumerate(settings_doc.user_integrations):
                if integ.name == integration_name:
                    integration = integ
                    break
                    
            if not integration:
                results.append({
                    "integration": integration_name,
                    "integration_type": "Unknown",
                    "status": "error", 
                    "message": "Integration not found"
                })
                continue
            
            # Get display name for the integration
            display_name = getattr(integration, "integration_name", None) or integration.integration_type
            if getattr(integration, "base_url", None):
                display_name += f" ({integration.base_url})"
                
            try:
                # Create integration instance
                integration_instance = IntegrationRegistry.create_instance(
                    integration.integration_type, 
                    settings=integration.as_dict()
                )
                
                # Test connection
                result = integration_instance.test_connection()
                
                # Add result with integration info
                results.append({
                    "integration": display_name,
                    "integration_type": integration.integration_type,
                    "status": "success" if result.get("success") else "error",
                    "message": result.get("message", "No message returned")
                })
                
            except Exception as e:
                # Handle individual integration errors
                frappe.log_error(
                    f"Connection test failed for {display_name}: {str(e)}", 
                    "Integration Error"
                )
                results.append({
                    "integration": display_name,
                    "integration_type": getattr(integration, "integration_type", "Unknown"),
                    "status": "error",
                    "message": str(e)
                })
        
        # Determine overall status
        overall_status = "success" if all(r["status"] == "success" for r in results) else "error"
        
        # Return consolidated results
        return {
            "status": overall_status,
            "results": results,
            "message": f"Tested {len(results)} integration(s)"
        }
            
    except Exception as e:
        frappe.log_error(f"Connection test failed: {str(e)}", "Integration Error")
        return {"status": "error", "message": str(e)}