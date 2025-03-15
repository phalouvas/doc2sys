import frappe
import importlib
import os
from typing import Dict, Type, List
from doc2sys.integrations.base import BaseIntegration

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


def register_integration(cls):
    """Decorator to register an integration class"""
    IntegrationRegistry.register(cls)
    return cls