"""
Data models used by the document processing engine.
"""

from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class ProcessedDocument:
    """Represents a processed document with extracted data"""
    
    document_id: str
    filename: str
    processed_at: datetime
    metadata: Dict[str, Any]
    extracted_text: str
    structured_data: Dict[str, Any]
    confidence_score: float
    processing_time: float  # in seconds
    status: str
    error_message: Optional[str] = None

@dataclass
class ProcessingJob:
    """Represents a document processing job"""
    
    job_id: str
    document_path: str
    created_at: datetime
    status: str
    options: Dict[str, Any]
    result: Optional[ProcessedDocument] = None
    error: Optional[str] = None