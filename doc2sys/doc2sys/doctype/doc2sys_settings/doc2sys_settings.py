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
            {"language_code": "en", "language_name": "English", "enabled": 1},
            {"language_code": "fr", "language_name": "French", "enabled": 0},
            {"language_code": "de", "language_name": "German", "enabled": 0},
            {"language_code": "es", "language_name": "Spanish", "enabled": 0},
            {"language_code": "it", "language_name": "Italian", "enabled": 0},
            {"language_code": "zh", "language_name": "Chinese (Simplified)", "enabled": 0},
            {"language_code": "ja", "language_name": "Japanese", "enabled": 0},
            {"language_code": "ko", "language_name": "Korean", "enabled": 0},
            {"language_code": "ru", "language_name": "Russian", "enabled": 0},
            {"language_code": "ar", "language_name": "Arabic", "enabled": 0},
            {"language_code": "hi", "language_name": "Hindi", "enabled": 0},
            {"language_code": "pt", "language_name": "Portuguese", "enabled": 0},
            {"language_code": "nl", "language_name": "Dutch", "enabled": 0},
            {"language_code": "tr", "language_name": "Turkish", "enabled": 0},
            {"language_code": "el", "language_name": "Greek", "enabled": 0}
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
        """Download language models for enabled languages"""
        if not self.ocr_enabled:
            return {"success": False, "message": "OCR is not enabled"}
        
        # Get list of enabled languages
        enabled_langs = [lang.language_code for lang in self.ocr_languages if lang.enabled]
        if not enabled_langs:
            return {"success": False, "message": "No languages are enabled"}
        
        # Try to download each language model
        results = []
        for lang_code in enabled_langs:
            try:
                frappe.publish_progress(
                    title=f"Downloading language model for {lang_code}",
                    percent=0,
                    description="Starting download..."
                )
                
                # Download the model
                success, message = self._download_language_model(lang_code)
                
                frappe.publish_progress(
                    percent=100,
                    description=f"{'Success' if success else 'Failed'}: {message}"
                )
                
                results.append({
                    "language_code": lang_code,
                    "success": success,
                    "message": message
                })
                
            except Exception as e:
                frappe.log_error(f"Error downloading language model for {lang_code}: {str(e)}", "Doc2Sys")
                results.append({
                    "language_code": lang_code,
                    "success": False,
                    "message": str(e)
                })
        
        # Update download status of languages
        self.update_language_download_status()
        
        return {
            "success": True,
            "message": f"Processed {len(enabled_langs)} language models",
            "results": results
        }
    
    def _download_language_model(self, lang_code):
        """Download an individual language model"""
        try:
            import easyocr
            
            # Initialize reader with language to trigger download
            frappe.log_error(f"Downloading model for language: {lang_code}", "Doc2Sys")
            reader = easyocr.Reader([lang_code], verbose=True)
            
            # Verify the download was successful
            if self.is_language_model_downloaded(lang_code):
                return True, f"Language model for {lang_code} downloaded successfully"
            else:
                return False, f"Language model for {lang_code} could not be verified after download"
                
        except ImportError:
            return False, "EasyOCR is not installed. Please install dependencies first."
        except Exception as e:
            frappe.log_error(f"Error downloading language model: {str(e)}", "Doc2Sys")
            return False, str(e)
    
    @frappe.whitelist()
    def update_language_download_status(self):
        """Update download status for all languages in settings"""
        results = []
        
        for lang in self.ocr_languages:
            downloaded = self.is_language_model_downloaded(lang.language_code)
            lang.model_downloaded = 1 if downloaded else 0
            results.append({
                "language_code": lang.language_code,
                "language_name": lang.language_name,
                "downloaded": downloaded
            })
        
        # Save changes
        self.save()
        
        return {
            "success": True,
            "message": "Language download status updated",
            "languages": results
        }
    
    def is_language_model_downloaded(self, lang_code):
        """Check if a specific language model is downloaded"""
        try:
            # Get the EasyOCR model directory
            home = str(Path.home())
            model_dir = os.path.join(home, '.EasyOCR')
            
            if not os.path.exists(model_dir):
                return False
            
            # Check for recognition model (language specific)
            recognition_model = os.path.join(model_dir, f'{lang_code}_g2.pth')
            return os.path.exists(recognition_model)
            
        except Exception as e:
            frappe.log_error(f"Error checking language model: {str(e)}", "Doc2Sys")
            return False
    
    @frappe.whitelist()
    def list_downloaded_languages(self):
        """List all downloaded language models"""
        try:
            # Get the EasyOCR model directory
            home = str(Path.home())
            model_dir = os.path.join(home, '.EasyOCR')
            
            if not os.path.exists(model_dir):
                return {
                    "success": False,
                    "message": "EasyOCR model directory not found",
                    "languages": []
                }
            
            # List all files in the model directory
            files = os.listdir(model_dir)
            
            # Filter out language model files
            languages = [f.split('_')[0] for f in files if f.endswith('_g2.pth')]
            
            return {
                "success": True,
                "message": f"Found {len(languages)} downloaded language models",
                "languages": languages,
                "model_dir": model_dir
            }
            
        except Exception as e:
            frappe.log_error(f"Error listing language models: {str(e)}", "Doc2Sys")
            return {
                "success": False,
                "message": str(e),
                "languages": []
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
