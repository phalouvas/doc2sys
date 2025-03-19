# Copyright (c) 2025, KAINOTOMO PH LTD and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
import os
from pathlib import Path

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
    def download_language_models(self):
        """Download specified language models for Tesseract OCR"""
        # Get list of user settings with enabled languages
        user_settings = frappe.get_all(
            "Doc2Sys User Settings",
            fields=["name"]
        )
        
        all_enabled_langs = set()
        for settings in user_settings:
            user_doc = frappe.get_doc("Doc2Sys User Settings", settings.name)
            if user_doc.ocr_enabled:
                for lang in user_doc.ocr_languages:
                    if lang.enabled:
                        all_enabled_langs.add(lang.language_code)
        
        if not all_enabled_langs:
            return {"success": False, "message": "No languages are enabled in any user settings"}
            
        # Check availability of each language
        results = []
        try:
            import pytesseract
            for lang_code in all_enabled_langs:
                result = self._download_language_model(lang_code)
                results.append(result)
        except ImportError:
            return {
                "success": False,
                "message": "Pytesseract not installed. Install it first.",
                "results": []
            }
            
        # Update all user settings
        for settings in user_settings:
            try:
                user_doc = frappe.get_doc("Doc2Sys User Settings", settings.name)
                user_doc.update_language_download_status()
            except Exception:
                frappe.log_error("Failed to update language status for user", settings.name)
        
        return {
            "success": True,
            "message": "Language models downloaded",
            "results": results
        }
    
    def _download_language_model(self, lang_code):
        """Check if a Tesseract language model is available"""
        try:
            import pytesseract
            import subprocess
            
            # Check if language is already installed
            available_languages = pytesseract.get_languages()
            if lang_code in available_languages:
                return {
                    "language_code": lang_code,
                    "success": True,
                    "message": f"Language {lang_code} is already installed"
                }
                
            # Try to install the language pack
            # This command may vary depending on the system
            cmd = f"apt-get update && apt-get install -y tesseract-ocr-{lang_code}"
            process = subprocess.Popen(
                cmd, 
                shell=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                return {
                    "language_code": lang_code,
                    "success": True,
                    "message": f"Language {lang_code} installed successfully"
                }
            else:
                return {
                    "language_code": lang_code,
                    "success": False,
                    "message": f"Failed to install {lang_code}: {stderr.decode()}"
                }
                
        except ImportError:
            return {
                "language_code": lang_code,
                "success": False,
                "message": "Pytesseract not installed"
            }
        except Exception as e:
            return {
                "language_code": lang_code,
                "success": False,
                "message": f"Error: {str(e)}"
            }
    
    @frappe.whitelist()
    def update_language_download_status(self):
        """Update language download status for all user settings"""
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
            # Update all user settings
            user_settings = frappe.get_all(
                "Doc2Sys User Settings",
                fields=["name"]
            )
            
            for settings in user_settings:
                try:
                    user_doc = frappe.get_doc("Doc2Sys User Settings", settings.name)
                    for lang in user_doc.ocr_languages:
                        lang.model_downloaded = 1 if lang.language_code in available_languages else 0
                    user_doc.save()
                except Exception:
                    frappe.log_error("Failed to update language status for user", settings.name)
                    
            return {
                "success": True,
                "message": "Updated language status for all users"
            }
            
        except Exception as e:
            frappe.log_error(f"Error updating language status: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": str(e)
            }
    
    def is_language_model_downloaded(self, lang_code):
        """Check if a Tesseract language model is available"""
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            return lang_code in available_languages
        except Exception:
            return False
    
    @frappe.whitelist()
    def list_downloaded_languages(self):
        """List all available Tesseract language models"""
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
            # Try to determine model directory
            model_dir = ""
            try:
                # This will vary depending on the system
                cmd = "find /usr -name tessdata -type d 2>/dev/null | head -1"
                import subprocess
                process = subprocess.Popen(
                    cmd, 
                    shell=True, 
                    stdout=subprocess.PIPE
                )
                stdout, _ = process.communicate()
                if stdout:
                    model_dir = stdout.decode().strip()
            except Exception:
                model_dir = "Unknown (check Tesseract installation)"
                
            return {
                "success": True,
                "languages": available_languages,
                "model_dir": model_dir
            }
        except ImportError:
            return {
                "success": False,
                "message": "Pytesseract not installed",
                "languages": []
            }
        except Exception as e:
            return {
                "success": False,
                "message": str(e),
                "languages": []
            }
    
    @frappe.whitelist()
    def delete_not_enabled_language_models(self):
        """Delete language models that are not enabled in any user settings"""
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
            # Get all enabled languages across all user settings
            user_settings = frappe.get_all(
                "Doc2Sys User Settings",
                fields=["name"]
            )
            
            all_enabled_langs = set()
            for settings in user_settings:
                user_doc = frappe.get_doc("Doc2Sys User Settings", settings.name)
                if user_doc.ocr_enabled:
                    for lang in user_doc.ocr_languages:
                        if lang.enabled:
                            all_enabled_langs.add(lang.language_code)
            
            # Check which languages are installed but not enabled
            languages_to_delete = [
                lang for lang in available_languages
                if lang != "eng" and lang != "osd" and lang not in all_enabled_langs
            ]
            
            if not languages_to_delete:
                return {
                    "success": True,
                    "message": "No unused languages to delete",
                    "results": []
                }
            
            # Try to delete each unused language
            results = []
            for lang in languages_to_delete:
                try:
                    # Command to remove the language package
                    cmd = f"apt-get remove -y tesseract-ocr-{lang}"
                    import subprocess
                    process = subprocess.Popen(
                        cmd, 
                        shell=True, 
                        stdout=subprocess.PIPE, 
                        stderr=subprocess.PIPE
                    )
                    _, stderr = process.communicate()
                    
                    if process.returncode == 0:
                        results.append({
                            "language_code": lang,
                            "success": True,
                            "message": f"Language {lang} deleted successfully"
                        })
                    else:
                        results.append({
                            "language_code": lang,
                            "success": False,
                            "message": f"Failed to delete {lang}: {stderr.decode()}"
                        })
                except Exception as e:
                    results.append({
                        "language_code": lang,
                        "success": False,
                        "message": f"Error deleting {lang}: {str(e)}"
                    })
            
            # Update the language status for all users
            self.update_language_download_status()
            
            return {
                "success": True,
                "message": f"Deleted {len(results)} unused language models",
                "results": results
            }
        except Exception as e:
            frappe.log_error(f"Error deleting language models: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": str(e),
                "results": []
            }

@frappe.whitelist()
def run_folder_monitor():
    """Manually run the folder monitor process"""
    from doc2sys.doc2sys.tasks.folder_monitor import monitor_folders
    monitor_folders()
    return {
        "success": True,
        "message": "Folder monitoring process completed"
    }
