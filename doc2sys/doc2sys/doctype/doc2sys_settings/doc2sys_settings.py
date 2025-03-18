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
        self.update_scheduler()
        
        # Check if OCR is enabled and validate language selections
        if self.ocr_enabled:
            # Verify that at least one language is enabled
            if not any(lang.enabled for lang in self.ocr_languages):
                # Enable English by default if no language is enabled
                for lang in self.ocr_languages:
                    if lang.language_code == "en":
                        lang.enabled = 1
                        break
            
    def get_supported_file_extensions(self):
        """Return list of supported file extensions"""
        return [ft.file_extension.lower().strip() for ft in self.supported_file_types if ft.file_extension]
    
    def get_max_file_size_bytes(self):
        """Return max file size in bytes"""
        return self.max_file_size_mb * 1024 * 1024

    def update_scheduler(self):
        """Update the scheduler interval based on settings"""
        if not self.monitor_interval or not self.monitoring_enabled:
            return
            
        # Get the current job
        job = frappe.get_all(
            "Scheduled Job Type",
            filters={"method": "doc2sys.doc2sys.tasks.folder_monitor.monitor_folders"},
            fields=["name", "cron_format"]
        )
        
        if not job:
            return
            
        # Create the new cron format based on settings
        new_cron = f"*/{self.monitor_interval} * * * *"
        
        # Update the job if needed
        if job[0].cron_format != new_cron:
            frappe.db.set_value("Scheduled Job Type", job[0].name, "cron_format", new_cron)
            frappe.db.commit()
    
    @frappe.whitelist()
    def add_common_languages(self):
        """Add common OCR languages to the settings"""
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
            {"language_code": "ell", "language_name": "Greek", "enabled": 1}  # Enable Greek by default
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
        if not self.ocr_enabled:
            return {"success": False, "message": "OCR is not enabled"}
        
        # Get list of enabled languages
        enabled_langs = [lang.language_code for lang in self.ocr_languages if lang.enabled]
        if not enabled_langs:
            return {"success": False, "message": "No languages are enabled"}
        
        # Check availability of each language
        results = []
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
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
    
    def _download_language_model(self, lang_code):
        """Check if a Tesseract language model is available"""
        try:
            import pytesseract
            available_languages = pytesseract.get_languages()
            
            if lang_code in available_languages:
                return True, f"Language {lang_code} is available"
            else:
                return False, f"Language {lang_code} is not installed. Please install the Tesseract language pack."
        except ImportError:
            return False, "Pytesseract is not installed"
        except Exception as e:
            frappe.log_error(f"Error checking language {lang_code}: {str(e)}", "Doc2Sys")
            return False, str(e)
    
    @frappe.whitelist()
    def update_language_download_status(self):
        """Update availability status for all languages in settings"""
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
            languages = pytesseract.get_languages()
            
            # Try to get the tessdata directory
            import subprocess
            try:
                result = subprocess.run(
                    ["tesseract", "--list-langs"], 
                    capture_output=True, 
                    text=True
                )
                output_lines = result.stdout.strip().split('\n')
                # First line is typically "List of available languages (xxx):"
                tessdata_dir = output_lines[0].split('(')[-1].split(')')[0] if '(' in output_lines[0] else None
            except:
                tessdata_dir = "Unknown (check 'tesseract --list-langs')"
            
            return {
                "success": True,
                "message": f"Found {len(languages)} available languages",
                "languages": languages,
                "model_dir": tessdata_dir
            }
        except ImportError:
            return {
                "success": False,
                "message": "Pytesseract is not installed",
                "languages": []
            }
        except Exception as e:
            frappe.log_error(f"Error listing languages: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": str(e),
                "languages": []
            }
    
    @frappe.whitelist()
    def delete_not_enabled_language_models(self):
        """
        Display information about deleting Tesseract language models
        
        Note: Tesseract language models are system-wide and cannot be deleted
        through Python code for security reasons. This method provides guidance.
        """
        return {
            "success": True,
            "message": "Tesseract language management notice",
            "results": [{
                "language_code": "info",
                "success": True,
                "message": "Tesseract language packs are managed at the system level. To remove languages, use your system's package manager."
            }]
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
