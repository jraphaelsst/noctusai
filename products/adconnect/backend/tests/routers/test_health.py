"""
Tests for Health check endpoint — provided by seed framework.

Inherits from `noctusai_lib.testing.HealthCheckSuite` (lifted from N=4
byte-identical copies; see `seed/lib/backend/noctusai_lib/testing/
framework_test_suites.py`).
"""
from noctusai_lib.testing import HealthCheckSuite


class TestHealthCheck(HealthCheckSuite):
    expected_product_name = "AdConnect"
