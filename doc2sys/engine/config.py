"""
Configuration settings for the document processing engine.
"""

import frappe

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
        
    def from_settings(cls):
        """
        Load configuration from Frappe site settings.
        
        Returns:
            EngineConfig: Configuration instance
        """
        config = {}
        
        # Try to get configuration from Frappe settings
        try:
            doc2sys_settings = frappe.get_doc('Doc2Sys Settings')
            if doc2sys_settings:
                config['temp_dir'] = doc2sys_settings.get('temp_dir') or config.get('temp_dir')
                config['ocr_enabled'] = doc2sys_settings.get('ocr_enabled', 1) == 1
                # Add other settings as needed
        except Exception:
            pass
            
        return cls(**config)