"""
E2E tests for the Seed Product — validates the seed framework's standard
routers work as complete user journeys.

These tests prove the framework itself works. If these fail, every product
that inherits from the framework is affected.

Inherits from `noctusai_lib.testing` framework-test suites (lifted from N=4
byte-identical copies; see `seed/lib/backend/noctusai_lib/testing/
framework_test_suites.py`).
"""
from noctusai_lib.testing import (
    FrameworkEndpointsSuite,
    TeamFlowSuite,
    NotificationFlowSuite,
    AuthBoundarySuite,
)


class TestFrameworkEndpoints(FrameworkEndpointsSuite):
    expected_product_name = "Seed Product"


class TestTeamFlow(TeamFlowSuite):
    pass


class TestNotificationFlow(NotificationFlowSuite):
    pass


class TestAuthBoundary(AuthBoundarySuite):
    pass
