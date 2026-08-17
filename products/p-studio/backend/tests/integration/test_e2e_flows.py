"""
E2E tests for P Studio — validates the seed framework's standard routers
work as complete user journeys.

These tests prove the framework itself works. If these fail, every product
that inherits from the framework is affected.

Inherits from `noctusai_lib.testing` framework-test suites (lifted from N=4
byte-identical copies; see `seed/lib/backend/noctusai_lib/testing/
framework_test_suites.py`). Uses the `client` fixture defined in this
directory's own `conftest.py` — NOT the product-wide `tests/conftest.py`
fixture (P Studio's own routers use a hand-rolled single-tenant auth layer
that predates absorption; the framework's standard routers use the seed's
own `DatabaseModule`/`ProductDependencies` instead — see that conftest's
docstring for the full story).
"""
from noctusai_lib.testing import (
    FrameworkEndpointsSuite,
    TeamFlowSuite,
    NotificationFlowSuite,
    AuthBoundarySuite,
)


class TestFrameworkEndpoints(FrameworkEndpointsSuite):
    expected_product_name = "P Studio"


class TestTeamFlow(TeamFlowSuite):
    pass


class TestNotificationFlow(NotificationFlowSuite):
    pass


class TestAuthBoundary(AuthBoundarySuite):
    pass
