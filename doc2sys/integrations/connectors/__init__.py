"""
Connectors module for Doc2Sys integrations.
This module automatically discovers and registers all integration connectors.
"""
from doc2sys.integrations.registry import IntegrationRegistry
from doc2sys.integrations.registry import load_connectors

# Discover and register all integrations
load_connectors()