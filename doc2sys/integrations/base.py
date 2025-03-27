import frappe
from abc import ABC, abstractmethod  # Add this import
from typing import Dict, Any, Optional

from doc2sys.integrations.log_utils import create_integration_log

class BaseIntegration(ABC):
    """Base class for all integration connectors"""
    
    def __init__(self, settings: Dict[str, Any]) -> None:
        self.settings = settings or {}
        self.integration_type = self.__class__.__name__
        self.is_authenticated = False
        self.current_document = None
    
    def log_activity(self, status: str, message: str, data: Optional[Dict] = None) -> None:
        """Log integration activity"""
        create_integration_log(
            integration_type=self.integration_type,
            status=status,
            message=message,
            data=data,
            doc_reference=self.current_document,
            user=self.settings.get("user")
        )

    # These should be abstract methods
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the external system"""
        pass
        
    @abstractmethod
    def sync_document(self, doc2sys_item: Dict[str, Any]) -> Dict[str, Any]:
        """Sync a document to the external system"""
        pass