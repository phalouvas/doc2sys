import frappe
import importlib
import os
from typing import Dict, Type, List, Optional
from doc2sys.integrations.base import BaseIntegration

# Dictionary to store integration classes
INTEGRATION_REGISTRY = {}

def register_integration(cls):
    """Decorator to register integration classes"""
    INTEGRATION_REGISTRY[cls.__name__] = cls
    return cls

def get_integration_class(integration_name: str) -> Optional[Type]:
    """Get an integration class by name"""
    # Check if we need to load connectors first
    if not INTEGRATION_REGISTRY:
        load_connectors()
        
    return INTEGRATION_REGISTRY.get(integration_name)

def load_connectors():
    """Dynamically import all connector modules to register integrations"""
    try:
        # Import connectors modules dynamically
        import doc2sys.integrations.connectors.quickbooks
        import doc2sys.integrations.connectors.erpnext
        # Add other connectors here as needed
    except Exception as e:
        frappe.logger().error(f"Error loading integration connectors: {str(e)}")

class IntegrationRegistry:
    """Registry for available integrations in doc2sys."""
    
    _integrations: Dict[str, Type[BaseIntegration]] = {}
    
    @classmethod
    def register(cls, integration_cls: Type[BaseIntegration]) -> None:
        """Register an integration class"""
        cls._integrations[integration_cls.__name__] = integration_cls
        
    @classmethod
    def get_integration(cls, integration_name: str) -> Type[BaseIntegration]:
        """Get integration class by name"""
        if integration_name not in cls._integrations:
            frappe.throw(f"Integration '{integration_name}' not found")
        return cls._integrations[integration_name]
        
    @classmethod
    def get_all_integrations(cls) -> List[str]:
        """Get a list of all registered integration names"""
        return list(cls._integrations.keys())
    
    @classmethod
    def create_instance(cls, integration_name: str, settings=None):
        """Create an instance of the integration with settings"""
        integration_cls = cls.get_integration(integration_name)
        return integration_cls(settings=settings)
        
    @classmethod
    def discover_integrations(cls) -> None:
        """Auto-discover and register all integrations"""
        connectors_dir = os.path.join(os.path.dirname(__file__), "connectors")
        for filename in os.listdir(connectors_dir):
            if filename.endswith(".py") and filename != "__init__.py":
                module_name = filename[:-3]  # Remove .py extension
                module_path = f"doc2sys.integrations.connectors.{module_name}"
                
                try:
                    importlib.import_module(module_path)
                except Exception as e:
                    frappe.log_error(f"Error loading integration: {module_path}\n{str(e)}")