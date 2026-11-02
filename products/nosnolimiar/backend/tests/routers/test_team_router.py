"""
Tests for Team Management router — provided by seed framework.

Inherits from `noctusai_lib.testing` framework-test suites (lifted from N=4
byte-identical copies; see `seed/lib/backend/noctusai_lib/testing/
framework_test_suites.py`).
"""
from noctusai_lib.testing import (
    TeamRouterListMembersSuite,
    TeamRouterInviteSuite,
    TeamRouterRemoveMemberSuite,
)


class TestListMembers(TeamRouterListMembersSuite):
    pass


class TestInvite(TeamRouterInviteSuite):
    pass


class TestRemoveMember(TeamRouterRemoveMemberSuite):
    pass
