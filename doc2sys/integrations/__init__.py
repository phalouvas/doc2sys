"""
Doc2Sys Integrations package that provides connectivity to external systems.
"""
# Import registry first to ensure it's initialized before connectors
from doc2sys.integrations.registry import IntegrationRegistry

# Import connectors package to trigger discovery
from doc2sys.integrations import connectors