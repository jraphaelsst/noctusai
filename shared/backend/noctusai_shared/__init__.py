"""
NoctusAI Shared Backend — Common utilities for all NoctusAI backends.

Consolidates duplicated code (exceptions, responses, middleware, logging,
auth helpers, database factory, config base, and app bootstrap) so that
each product backend imports from a single source of truth.
"""
