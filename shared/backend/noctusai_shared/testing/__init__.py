"""
NoctusAI Shared Testing Infrastructure.

Provides mock classes for Supabase that mirror the real SDK's type hierarchy,
preventing "works in tests, breaks in production" bugs. All products import
these instead of defining their own mock classes.

Usage in a product's conftest.py::

    from noctusai_shared.testing import (
        MockSupabaseResponse,
        MockSelectBuilder,
        MockFilterBuilder,
        MockQueryBuilder,
        MockRequestBuilder,
        MockSupabaseClient,
        MockUser,
        MockUserResponse,
        AuthClient,
    )
"""
from __future__ import annotations

from noctusai_shared.testing.mocks import (
    MockSupabaseResponse,
    _MockExecuteMixin,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
)
from noctusai_shared.testing.clients import (
    MockUser,
    MockUserResponse,
    AuthClient,
)

__all__ = [
    "MockSupabaseResponse",
    "MockSelectBuilder",
    "MockFilterBuilder",
    "MockQueryBuilder",
    "MockRequestBuilder",
    "MockSupabaseClient",
    "MockUser",
    "MockUserResponse",
    "AuthClient",
]
