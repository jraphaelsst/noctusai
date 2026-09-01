"""The test double must never be LOOSER than the client it stands in for.

`ContractFakeMailchimpClient` (conftest) is what every mailchimp router test
runs against. On 2026-09-01 its `list_templates` accepted a `type=` kwarg that
the Protocol, the seed Fake and the real `HttpxMailchimpClient` all rejected.
The router called `list_templates(type="user", ...)`, the suite stayed green,
and `GET /api/mailchimp/templates` returned 500 in production.

A double that accepts arguments the real thing refuses cannot fail on the code
path that breaks in prod — so the drift is invisible until a user finds it.
This asserts signature parity for every Protocol method, which closes the whole
class rather than the one method that happened to bite.
"""
from __future__ import annotations

import inspect

import pytest

from noctusai_lib.integrations.mailchimp.client import HttpxMailchimpClient
from noctusai_lib.integrations.mailchimp.types import MailchimpClient

from .conftest import ContractFakeMailchimpClient


def _kwargs(fn) -> set[str]:
    return {
        name
        for name, p in inspect.signature(fn).parameters.items()
        if name != "self" and p.kind is not inspect.Parameter.VAR_KEYWORD
    }


PROTOCOL_METHODS = sorted(
    name
    for name in dir(MailchimpClient)
    if not name.startswith("_") and callable(getattr(MailchimpClient, name))
)


@pytest.mark.parametrize("method", PROTOCOL_METHODS)
def test_double_accepts_no_argument_the_real_client_rejects(method: str) -> None:
    fake = getattr(ContractFakeMailchimpClient, method, None)
    if fake is None:
        pytest.skip(f"double does not implement {method}")
    real = getattr(HttpxMailchimpClient, method)
    extra = _kwargs(fake) - _kwargs(real)
    assert not extra, (
        f"ContractFakeMailchimpClient.{method} accepts {sorted(extra)}, which "
        f"HttpxMailchimpClient.{method} does not. A router calling with that "
        f"argument passes the suite and 500s in production."
    )


@pytest.mark.parametrize("method", PROTOCOL_METHODS)
def test_real_client_satisfies_the_protocol_signature(method: str) -> None:
    real = getattr(HttpxMailchimpClient, method, None)
    if real is None:
        pytest.skip(f"real client does not implement {method}")
    proto = getattr(MailchimpClient, method)
    missing = _kwargs(proto) - _kwargs(real)
    assert not missing, (
        f"MailchimpClient Protocol declares {sorted(missing)} on {method} that "
        f"HttpxMailchimpClient does not accept."
    )
