import frappe
from frappe import _ 
from frappe.model.document import Document
import datetime

class Doc2SysUserSettings(Document):
    def validate(self):
        """Validate user settings"""
        if self.monitor_interval <= 0:
            frappe.throw(_("Monitor interval must be greater than 0"))
        
        # Ensure at least one OCR language is enabled if OCR is enabled
        if self.ocr_enabled and not any(lang.enabled for lang in self.ocr_languages):
            frappe.throw(_("At least one OCR language must be enabled if OCR is activated."))
        
        # Ensure user folder exists if monitoring is enabled
        if self.monitoring_enabled:
            self.ensure_user_folder_exists()
            
        self.update_scheduler()

    def ensure_user_folder_exists(self):
        """Create folder for the user in Doc2Sys directory if it doesn't exist"""
        # Check if Doc2Sys folder exists, create if not
        doc2sys_folder = "Home/Doc2Sys"
        if not frappe.db.exists("File", {"is_folder": 1, "file_name": "Doc2Sys", "folder": "Home"}):
            # Use the frappe API to create the folder
            from frappe.core.api.file import create_new_folder
            create_new_folder("Doc2Sys", "Home")
            frappe.logger().info("Created Doc2Sys folder for file monitoring")
        
        # Check if user-specific folder exists, create if not
        user_folder_name = f"Doc2Sys/{self.user}"
        if not frappe.db.exists("File", {"is_folder": 1, "file_name": self.user, "folder": "Home/Doc2Sys"}):
            # Create user folder
            from frappe.core.api.file import create_new_folder
            create_new_folder(self.user, "Home/Doc2Sys")
            frappe.logger().info(f"Created user folder {user_folder_name} for file monitoring")

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
    def test_llm_ocr_connection(self):
        """Test the connection to the LLM API for OCR functionality"""
        if not self.ocr_enabled or self.ocr_engine != "llm_api":
            return {
                "success": False,
                "message": "LLM OCR is not enabled or selected as the OCR engine"
            }
            
        try:
            # Create an LLM processor instance with current user settings
            from doc2sys.engine.llm_processor import LLMProcessor
            from doc2sys.engine.text_extractor import TextExtractor
            
            # First test basic connectivity with LLM API
            llm_processor = LLMProcessor(user=self.user)
            
            # Check if we have valid endpoint and model
            if not self.llm_ocr_endpoint and not self.openwebui_endpoint:
                return {
                    "success": False,
                    "message": "No LLM API endpoint configured"
                }
                
            # Create a simple test prompt to verify the API works
            test_payload = {
                "model": self.llm_ocr_model or self.openwebui_model or "llama3",
                "temperature": 0.0,
                "messages": [
                    {"role": "system", "content": "You are a test system."},
                    {"role": "user", "content": "Reply with 'CONNECTION_OK' if you receive this message."}
                ]
            }
            
            # Use the appropriate endpoint
            endpoint = (self.llm_ocr_endpoint or self.openwebui_endpoint)
            if not endpoint.endswith("/api/chat/completions"):
                if not endpoint.endswith("/"):
                    endpoint += "/"
                endpoint += "api/chat/completions"
                
            # Make test API call
            result = llm_processor._make_api_request(endpoint, test_payload)
            
            if not result:
                return {
                    "success": False,
                    "message": "Failed to connect to LLM API. Check endpoint and credentials."
                }
                
            # Check if the response has the expected structure
            if "choices" not in result or not result["choices"]:
                return {
                    "success": False,
                    "message": "Connected to API but received unexpected response format."
                }
                
            # Extract content to verify response
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Test if image processing is supported (multimodal)
            has_multimodal = False
            model_info = result.get("model", "").lower()
            
            # Add a note about multimodal capability based on the model name
            multimodal_note = ""
            if any(term in model_info for term in ["gpt-4", "claude-3", "llava", "vision", "multimodal", "gemini"]):
                multimodal_note = " Model appears to support multimodality/images."
                has_multimodal = True
            
            # Test visual capability using a simple image if we detect multimodal support
            visual_test_result = {}
            if has_multimodal:
                try:
                    # Create a TextExtractor to leverage its image handling
                    text_extractor = TextExtractor(user=self.user)
                    
                    # Use a mock image test - create a temporary test image or use system icon
                    import tempfile
                    from PIL import Image, ImageDraw, ImageFont
                    
                    # Create a simple test image with text
                    img = Image.new('RGB', (300, 100), color=(255, 255, 255))
                    d = ImageDraw.Draw(img)
                    
                    # Try to add text (with fallback to simple drawing if font issues)
                    try:
                        d.text((10, 10), "OCR TEST IMAGE", fill=(0, 0, 0))
                    except Exception:
                        d.rectangle(((10, 10), (290, 90)), outline=(0, 0, 0))
                    
                    # Save test image
                    test_img_path = tempfile.mktemp(suffix=".png")
                    img.save(test_img_path)
                    
                    # Try OCR on the test image
                    visual_test_result = {
                        "success": False,
                        "message": "Visual testing failed"
                    }
                    
                    # Attempt OCR with the test image
                    ocr_text = text_extractor._extract_text_using_llm(test_img_path)
                    
                    # Check if we got some text back
                    if ocr_text and "OCR TEST IMAGE" in ocr_text:
                        visual_test_result = {
                            "success": True,
                            "message": f"Successfully OCR'd test image: '{ocr_text.strip()}'"
                        }
                    else:
                        visual_test_result = {
                            "success": False,
                            "message": f"OCR succeeded but couldn't find expected text. Got: '{ocr_text}'"
                        }
                        
                    # Clean up temp file
                    import os
                    if os.path.exists(test_img_path):
                        os.unlink(test_img_path)
                        
                except Exception as e:
                    visual_test_result = {
                        "success": False,
                        "message": f"Visual test error: {str(e)}"
                    }
            
            # Overall result
            if "CONNECTION_OK" in content:
                return {
                    "success": True,
                    "message": f"Successfully connected to LLM API.{multimodal_note}",
                    "visual_test": visual_test_result if has_multimodal else None,
                    "model": model_info,
                    "api_response": content
                }
            else:
                return {
                    "success": True,
                    "message": f"Connected to LLM API but received unexpected response.{multimodal_note}",
                    "visual_test": visual_test_result if has_multimodal else None,
                    "model": model_info,
                    "api_response": content
                }
                
        except Exception as e:
            frappe.log_error(f"Error testing LLM OCR connection: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": f"Failed to test LLM OCR connection: {str(e)}"
            }

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
        
        # Flag to track if we need to save the settings doc
        need_to_save = False
        
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
                
                # Set enabled status based on test result
                if result.get("success"):
                    # Enable integration if test was successful
                    if integration.enabled != 1:
                        integration.enabled = 1
                        need_to_save = True
                        result["message"] += " (Integration automatically enabled)"
                else:
                    # Disable integration if test failed
                    if integration.enabled == 1:
                        integration.enabled = 0
                        need_to_save = True
                        result["message"] += " (Integration automatically disabled)"
                
                # Add result with integration info
                results.append({
                    "integration": display_name,
                    "integration_type": integration.integration_type,
                    "status": "success" if result.get("success") else "error",
                    "message": result.get("message", "No message returned"),
                    "enabled": integration.enabled
                })
                
            except Exception as e:
                # Handle individual integration errors and disable integration
                frappe.log_error(
                    f"Connection test failed for {display_name}: {str(e)}", 
                    "Integration Error"
                )
                
                # Disable integration on exception
                was_enabled = integration.enabled
                integration.enabled = 0
                if was_enabled:
                    need_to_save = True
                
                results.append({
                    "integration": display_name,
                    "integration_type": getattr(integration, "integration_type", "Unknown"),
                    "status": "error",
                    "message": f"{str(e)} (Integration automatically disabled)",
                    "enabled": 0
                })
        
        # Save settings doc if we made any changes
        if need_to_save:
            settings_doc.save()
        
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

@frappe.whitelist()
def delete_old_doc2sys_files(user_settings):
    """Delete old files from Doc2Sys Item documents based on user settings."""
    settings = frappe.get_doc("Doc2Sys User Settings", user_settings)
    
    if not settings.delete_old_files or settings.days_to_keep_files <= 0:
        return {
            "success": False,
            "message": "File deletion is not enabled or days to keep is not properly configured"
        }
    
    try:
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=settings.days_to_keep_files)
        
        # Find Doc2Sys Items older than the cutoff date that belong to this user
        old_items = frappe.get_all(
            "Doc2Sys Item",
            filters={
                "user": settings.user,
                "creation": ["<", cutoff_date]
            },
            fields=["name", "single_file"]
        )
        
        if not old_items:
            return {
                "success": True,
                "message": f"No documents older than {settings.days_to_keep_files} days found"
            }
        
        # Import the attachment removal function
        from frappe.desk.form.utils import remove_attach
        
        deleted_count = 0
        files_not_found = 0
        items_processed = 0
        
        for item in old_items:
            items_processed += 1
            
            # Skip if no file attached
            if not item.single_file:
                continue
            
            try:
                # Get the file ID based on attachment relationship
                file_doc = frappe.get_all(
                    "File", 
                    filters={
                        "attached_to_doctype": "Doc2Sys Item",
                        "attached_to_name": item.name
                    },
                    fields=["name"]
                )

                if not file_doc or len(file_doc) == 0:
                    files_not_found += 1
                    continue
                
                frappe.form_dict["dn"] = item.name
                frappe.form_dict["dt"] = "Doc2Sys Item"
                frappe.form_dict["fid"] = file_doc[0].name
                
                # Remove the attachment using the file ID
                remove_attach()
                
                # Update the document to clear the file field
                doc = frappe.get_doc("Doc2Sys Item", item.name)
                doc.single_file = ""
                doc.save()
                
                deleted_count += 1
                
            except Exception as e:
                frappe.log_error(f"Error deleting file from {item.name}: {str(e)}", "Doc2Sys File Cleanup")
                files_not_found += 1
        
        return {
            "success": True,
            "message": f"Processed {items_processed} documents, deleted {deleted_count} files, {files_not_found} files not found or had errors",
            "details": {
                "items_processed": items_processed,
                "files_deleted": deleted_count,
                "files_not_found": files_not_found
            }
        }
        
    except Exception as e:
        frappe.log_error(f"Error during Doc2Sys file cleanup: {str(e)}", "Doc2Sys File Cleanup")
        return {
            "success": False,
            "message": f"Error during file cleanup: {str(e)}"
        }

@frappe.whitelist()
def test_azure_connection(user_settings):
    """Test the Azure Document Intelligence connection using SDK"""
    settings = frappe.get_doc("Doc2Sys User Settings", user_settings)
    
    if settings.llm_provider != "Azure AI Document Intelligence":
        return {
            "success": False,
            "message": "The selected LLM provider is not Azure AI Document Intelligence"
        }
    
    try:
        # Get API key securely
        api_key = frappe.utils.password.get_decrypted_password(
            "Doc2Sys User Settings", 
            user_settings, 
            "azure_key"
        )
        
        if not settings.azure_endpoint or not api_key:
            return {
                "success": False,
                "message": "Azure endpoint URL or API key not configured"
            }
        
        # Import Azure SDK components
        from azure.core.credentials import AzureKeyCredential
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.exceptions import HttpResponseError
        
        # Initialize the client
        credential = AzureKeyCredential(api_key)
        client = DocumentIntelligenceClient(
            endpoint=settings.azure_endpoint,
            credential=credential
        )
        
        # Test the connection by getting available models
        models = client.list_document_models()
        
        # Check if we can retrieve models
        model_list = list(models)
        model_count = len(model_list)
        
        # Look for the selected model
        selected_model = settings.azure_model
        model_exists = any(model.model_id == selected_model for model in model_list)
        
        if model_exists:
            return {
                "success": True,
                "message": f"Successfully connected to Azure Document Intelligence. Found {model_count} available models including the selected model '{selected_model}'."
            }
        else:
            return {
                "success": True,
                "message": f"Connected to Azure Document Intelligence ({model_count} models available), but the selected model '{selected_model}' was not found. You may need to use a prebuilt model."
            }
            
    except HttpResponseError as error:
        frappe.log_error(f"Azure API error: {str(error)}", "Azure Connection Test")
        return {
            "success": False,
            "message": f"Azure API error: {str(error)}"
        }
    except Exception as e:
        frappe.log_error(f"Error testing Azure connection: {str(e)}", "Azure Connection Test")
        return {
            "success": False,
            "message": f"Connection error: {str(e)}"
        }