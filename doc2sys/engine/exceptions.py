"""
Custom exceptions for the document processing engine.
"""

class EngineError(Exception):
    """Base exception for all engine errors"""
    pass

class ProcessingError(EngineError):
    """Exception raised when document processing fails"""
    pass

class UnsupportedDocumentError(ProcessingError):
    """Exception raised when document type is not supported"""
    pass

class DocumentTooLargeError(ProcessingError):
    """Exception raised when document exceeds size limits"""
    pass

class ConfigurationError(EngineError):
    """Exception raised when there's an issue with engine configuration"""
    pass