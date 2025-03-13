"""
Utility functions for the document processing engine.
"""

import os
import logging
import frappe
import importlib.util

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('doc2sys.engine')

def get_file_extension(file_path):
    """Get the extension of a file"""
    import os
    _, extension = os.path.splitext(file_path)
    return extension.lower()[1:] if extension else ""

def is_supported_file_type(file_path, supported_types=None):
    """
    Check if the file type is supported by the engine
    
    Args:
        file_path: Path to the file
        supported_types: List of supported file extensions
        
    Returns:
        bool: True if supported, False otherwise
    """
    if supported_types is None:
        supported_types = ['pdf', 'docx', 'txt', 'jpg', 'png']
        
    ext = get_file_extension(file_path)
    return ext in supported_types
