"""
Configuration settings for the document processing engine.
"""

import frappe
import os

class EngineConfig:
    """
    Configuration class for the document processing engine.
    """
    
    def __init__(self, **kwargs):
        """
        Initialize engine configuration with defaults or provided values.
        
        Args:
            **kwargs: Configuration parameters
        """
        # Default settings
        self.temp_dir = kwargs.get('temp_dir', '/tmp/doc2sys')
        self.output_format = kwargs.get('output_format', 'json')
        self.supported_file_types = kwargs.get(
            'supported_file_types', 
            ['pdf', 'docx', 'txt', 'jpg', 'png']
        )
        self.ocr_enabled = kwargs.get('ocr_enabled', True)
        self.max_file_size = kwargs.get('max_file_size', 10 * 1024 * 1024)  # 10MB
        
        # Create temp directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            try:
                os.makedirs(self.temp_dir, exist_ok=True)
            except Exception as e:
                frappe.log_error(f"Failed to create temp directory: {str(e)}")
        
    @classmethod
    def from_settings(cls):
        """
        Load configuration from Frappe site settings.
        
        Returns:
            EngineConfig: Configuration instance
        """
        config = {}
        
        # Try to get configuration from Frappe settings
        try:
            doc2sys_settings = frappe.get_single('Doc2Sys Settings')
            if doc2sys_settings:
                config['temp_dir'] = doc2sys_settings.temp_dir
                config['ocr_enabled'] = doc2sys_settings.ocr_enabled
                config['output_format'] = doc2sys_settings.output_format
                config['max_file_size'] = doc2sys_settings.get_max_file_size_bytes()
                
                # Get supported file types
                supported_types = doc2sys_settings.get_supported_file_extensions()
                if supported_types:
                    config['supported_file_types'] = supported_types
        except Exception as e:
            frappe.log_error(f"Error loading Doc2Sys settings: {str(e)}")
            
        return cls(**config)