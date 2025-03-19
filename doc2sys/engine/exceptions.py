"""
Custom exceptions for the document processing engine.
"""

class ProcessingError(Exception):
    """Base exception for all document processing errors"""
    pass

class UnsupportedDocumentError(ProcessingError):
    """Exception raised when an unsupported document type is processed"""
    pass

class LLMProcessingError(ProcessingError):
    """Exception raised when there's an error interacting with LLM services"""
    pass