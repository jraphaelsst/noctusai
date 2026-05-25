"""Canonical test-identity constants are public, single-source, and match the
seed-default ``MockUser``.

These constants are the structural cure for the ``"test-user-id"`` vs
``"test-user-123"`` mock-fixture drift (N=2 daily-life + erp): a mock row whose
``user_id`` / ``org_id`` is hand-typed can silently diverge from the
``MockUser`` default and then fail every ``.eq(user_id|org_id, …)`` predicate
once ``MockRequestBuilder`` filtering is accurate. Promoting the pair to a
shared seed feature means future products import the constant, never a literal.
"""
from __future__ import annotations

from noctusai_lib.testing import TEST_ORG_ID, TEST_USER_ID, MockUser
from noctusai_lib.testing import clients, framework_test_suites


def test_constants_have_canonical_values():
    assert TEST_USER_ID == "test-user-123"
    assert TEST_ORG_ID == "test-org-123"


def test_mock_user_default_id_is_the_constant():
    # The whole point: a mock row may reference TEST_USER_ID and it will always
    # match MockUser()'s default id — they cannot drift apart.
    assert MockUser().id == TEST_USER_ID


def test_constants_are_publicly_exported():
    import noctusai_lib.testing as t

    assert "TEST_USER_ID" in t.__all__
    assert "TEST_ORG_ID" in t.__all__
    assert t.TEST_USER_ID is clients.TEST_USER_ID
    assert t.TEST_ORG_ID is clients.TEST_ORG_ID


def test_framework_suites_consume_the_constants_single_source():
    # framework_test_suites derives from the constants, not its own literal.
    assert framework_test_suites._DEFAULT_USER_ID is TEST_USER_ID
    assert framework_test_suites.TEST_USER_ID is TEST_USER_ID
    assert framework_test_suites.TEST_ORG_ID is TEST_ORG_ID
