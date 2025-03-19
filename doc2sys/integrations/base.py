import frappe
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from doc2sys.integrations.utils import create_integration_log  # Add this import

class BaseIntegration(ABC):
    """Abstract base class for all integrations in doc2sys.
    
    All integration connectors must inherit from this class and implement
    its abstract methods.
    """
    
    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        self.name = self.__class__.__name__
        self.is_authenticated = False
        
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the external system"""
        pass
        
    @abstractmethod
    def test_connection(self) -> Dict[str, Any]:
        """Test the connection to the external system"""
        pass
        
    @abstractmethod
    def sync_document(self, doc2sys_item: Dict[str, Any]) -> Dict[str, Any]:
        """Sync a processed doc2sys_item to the external system"""
        pass
        
    @abstractmethod
    def get_mapping_fields(self) -> List[Dict[str, Any]]:
        """Return a list of fields available for mapping in the external system"""
        pass
    
    def log_activity(self, status, message, data=None):
        """Log integration activity"""
        integration_type = getattr(self, "integration_type", self.__class__.__name__)
        
        # Extract document reference from data if available
        document = None
        if isinstance(data, dict) and data.get("doc_name"):
            document = data.get("doc_name")
            
        create_integration_log(
            integration_type=integration_type,
            status=status,
            message=message,
            data=data,
            user=self.settings.get("user"),
            integration_reference=self.settings.get("name"),
            document=document
        )