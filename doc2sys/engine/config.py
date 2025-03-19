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
        self.supported_file_types = kwargs.get(
            'supported_file_types', 
            ['pdf', 'docx', 'txt', 'jpg', 'png']
        )
        self.ocr_enabled = kwargs.get('ocr_enabled', True)
        self.ocr_languages = kwargs.get('ocr_languages', ['eng'])  # Default to English
        self.max_file_size = kwargs.get('max_file_size', 10 * 1024 * 1024)  # 10MB
        
        # LLM settings
        self.llm_provider = kwargs.get('llm_provider', 'Open WebUI')
        self.openwebui_endpoint = kwargs.get('openwebui_endpoint', 'http://localhost:3000/api/chat/completions')
        self.openwebui_model = kwargs.get('openwebui_model', 'llama3')
        self.openwebui_apikey = kwargs.get('openwebui_apikey', '')
        
        # Folder monitoring settings
        self.monitoring_enabled = kwargs.get('monitoring_enabled', False)
        self.folder_to_monitor = kwargs.get('folder_to_monitor', '')
        self.monitor_interval = kwargs.get('monitor_interval', 15)  # Default 15 minutes
        
        # User reference
        self.user = kwargs.get('user', None)
        
        # Create temp directory if it doesn't exist
        if not os.path.exists(self.temp_dir):
            try:
                os.makedirs(self.temp_dir, exist_ok=True)
            except Exception as e:
                frappe.log_error(f"Failed to create temp directory: {str(e)}")
        
    @classmethod
    def from_settings(cls, user=None):
        """
        Load configuration from global and user-specific settings.
        
        Args:
            user (str, optional): User for whom to load settings. 
                                  If None, uses current user.
                                  
        Returns:
            EngineConfig: Configuration instance
        """
        config = {}
        
        # Get current user if not specified
        if not user:
            user = frappe.session.user
        
        # Try to get global configuration from Doc2Sys Settings
        try:
            doc2sys_settings = frappe.get_single('Doc2Sys Settings')
            if doc2sys_settings:
                # Get global settings
                config['temp_dir'] = doc2sys_settings.temp_dir
                config['max_file_size'] = doc2sys_settings.get_max_file_size_bytes()
                
                # Get supported file types
                supported_types = doc2sys_settings.get_supported_file_extensions()
                if supported_types:
                    config['supported_file_types'] = supported_types
        except Exception as e:
            frappe.log_error(f"Error loading Doc2Sys global settings: {str(e)}")
        
        # Try to get user-specific configuration
        try:
            # Find settings for the specified user
            user_settings_list = frappe.get_all(
                'Doc2Sys User Settings',
                filters={'user': user},
                fields=['name']
            )
            
            if user_settings_list:
                user_settings = frappe.get_doc('Doc2Sys User Settings', user_settings_list[0].name)
                
                # OCR settings
                config['ocr_enabled'] = user_settings.ocr_enabled
                
                # Get OCR languages
                languages = []
                if hasattr(user_settings, 'ocr_languages') and user_settings.ocr_languages:
                    for lang in user_settings.ocr_languages:
                        if lang.enabled and lang.language_code:
                            languages.append(lang.language_code.strip())
                
                # If no languages specified, default to English
                if not languages:
                    languages = ['eng']
                    
                config['ocr_languages'] = languages
                
                # Folder monitoring settings
                config['monitoring_enabled'] = user_settings.monitoring_enabled
                config['folder_to_monitor'] = user_settings.folder_to_monitor
                config['monitor_interval'] = user_settings.monitor_interval
                
                # LLM settings
                config['llm_provider'] = user_settings.llm_provider
                config['openwebui_endpoint'] = user_settings.openwebui_endpoint
                config['openwebui_model'] = user_settings.openwebui_model
                config['openwebui_apikey'] = user_settings.openwebui_apikey
                
                # Store user reference
                config['user'] = user
            else:
                frappe.log_error(f"No Doc2Sys User Settings found for user {user}")
        except Exception as e:
            frappe.log_error(f"Error loading Doc2Sys user settings for {user}: {str(e)}")
            
        return cls(**config)
    
    @classmethod
    def for_user(cls, user):
        """
        Load configuration for a specific user.
        
        Args:
            user (str): The user for whom to load settings
            
        Returns:
            EngineConfig: Configuration instance for the specified user
        """
        return cls.from_settings(user=user)