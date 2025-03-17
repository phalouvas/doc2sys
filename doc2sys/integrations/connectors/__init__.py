"""
Connectors module for Doc2Sys integrations.
This module automatically discovers and registers all integration connectors.
"""
from doc2sys.integrations.registry import IntegrationRegistry

# Discover and register all integrations
IntegrationRegistry.discover_integrations()