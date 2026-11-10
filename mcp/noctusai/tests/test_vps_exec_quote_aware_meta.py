"""`_is_read_only` is quote-aware: a metacharacter inside a quoted docker --format template is literal (deploy_verify's
`docker inspect -f '{{.A}}|{{.B}}'` must stay read-only); every active metacharacter still takes a command off the path."""
from __future__ import annotations

import pytest

from tools.noctus.dev.vps_exec import _is_read_only


@pytest.mark.parametrize("cmd", [
    "docker inspect -f '{{.State.Status}}|{{.State.Health.Status}}' noctus-igig",
    'docker inspect -f "{{.A}};{{.B}}" noctus-igig',
])
def test_quoted_metacharacters_are_literal(cmd):
    assert _is_read_only(cmd)


@pytest.mark.parametrize("cmd", [
    "docker inspect noctus-igig | sh",
    "docker inspect noctus-igig; docker rm x",
    "docker inspect 'a' ; rm x",
    'docker inspect "$(rm x)"',
    'docker inspect "`rm x`"',
    "docker inspect 'unterminated",
    "docker inspect noctus-igig > /tmp/x",
])
def test_active_metacharacters_still_refused(cmd):
    assert not _is_read_only(cmd)


@pytest.mark.parametrize("cmd", [
    # ANSI-C / locale quoting end their spans by bash's own rules (`\'` does not close `$'…'`): refused, never parsed.
    "docker inspect $'a\\' ; rm -rf x ; \\'' noctus-igig",
    "docker inspect $'{{.A}}|{{.B}}' noctus-igig",
    'docker inspect $"{{.A}}|{{.B}}" noctus-igig',
    # a trailing backslash is unparseable
    "docker inspect noctus-igig \\",
])
def test_ansi_c_and_locale_quoting_and_trailing_backslash_are_refused(cmd):
    assert not _is_read_only(cmd)
