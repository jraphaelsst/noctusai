"""
NoctusAI Shared Testing Infrastructure.

Provides mock classes for Supabase that mirror the real SDK's type hierarchy,
preventing "works in tests, breaks in production" bugs. All products import
these instead of defining their own mock classes.

Usage in a product's conftest.py::

    from noctusai_lib.testing import (
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

from noctusai_lib.testing.mocks import (
    MockSupabaseResponse,
    _MockExecuteMixin,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
)
from noctusai_lib.testing.clients import (
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_user_metadata,
)
from noctusai_lib.testing.schema_errors import MockSchemaError, MockUnknownTableError
from noctusai_lib.testing._schema_cache import (
    get_schema_map,
    reset_cache,
    set_cache_for_tests,
)
from noctusai_lib.testing.consent import bind_consent_module_to_mock
from noctusai_lib.testing.assertions import assert_error_contains
from noctusai_lib.testing.conftest_helpers import purge_shadowing_editable_finders
from noctusai_lib.testing.framework_test_suites import (
    HealthCheckSuite,
    TeamRouterListMembersSuite,
    TeamRouterInviteSuite,
    TeamRouterRemoveMemberSuite,
    FrameworkEndpointsSuite,
    TeamFlowSuite,
    NotificationFlowSuite,
    AuthBoundarySuite,
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
    "bind_user_metadata",
    "MockSchemaError",
    "MockUnknownTableError",
    "get_schema_map",
    "reset_cache",
    "set_cache_for_tests",
    "bind_consent_module_to_mock",
    "assert_error_contains",
    "purge_shadowing_editable_finders",
    "HealthCheckSuite",
    "TeamRouterListMembersSuite",
    "TeamRouterInviteSuite",
    "TeamRouterRemoveMemberSuite",
    "FrameworkEndpointsSuite",
    "TeamFlowSuite",
    "NotificationFlowSuite",
    "AuthBoundarySuite",
]
