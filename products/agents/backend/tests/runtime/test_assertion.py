"""``app.runtime.assertion`` — claims shape, canonical hash, and
``verify_assertion``'s §D steps 1-7."""
from uuid import uuid4

import jwt
import pytest

from app.runtime.assertion import (
    AssertionInvalid,
    canonical_body_sha256,
    mint_assertion,
    verify_assertion,
)

_SECRET = "a" * 40
_AUD = "academia-de-reciclagem"


def _mint(**overrides):
    defaults = dict(
        approval_id=uuid4(),
        secret=_SECRET,
        agent_id=uuid4(),
        org_id=uuid4(),
        tool_name="mcp__academia__kb_escrever",
        method="POST",
        path="/api/kb",
        body={"titulo": "t", "corpo_md": "x", "motivo": "m"},
        approved_by=uuid4(),
        requested_by=uuid4(),
        aud=_AUD,
    )
    defaults.update(overrides)
    return defaults


class TestCanonicalBodySha256:
    def test_key_order_does_not_change_the_hash(self):
        a = canonical_body_sha256({"b": 1, "a": 2})
        b = canonical_body_sha256({"a": 2, "b": 1})
        assert a == b

    def test_different_values_hash_differently(self):
        assert canonical_body_sha256({"a": 1}) != canonical_body_sha256({"a": 2})

    def test_matches_manual_canonical_json(self):
        import hashlib
        import json

        body = {"z": 1, "a": [1, 2, 3], "m": "café"}
        expected = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
                "utf-8"
            )
        ).hexdigest()
        assert canonical_body_sha256(body) == expected


class TestMintAssertion:
    def test_claims_shape_is_exactly_contract_d(self):
        params = _mint()
        token = mint_assertion(**params)
        claims = jwt.decode(token, _SECRET, algorithms=["HS256"], audience=_AUD, issuer="agents")
        assert set(claims.keys()) == {
            "jti",
            "iss",
            "aud",
            "sub",
            "org",
            "tool",
            "method",
            "path",
            "body_sha256",
            "approved_by",
            "requested_by",
            "iat",
            "exp",
        }
        assert claims["jti"] == str(params["approval_id"])
        assert claims["sub"] == str(params["agent_id"])
        assert claims["org"] == str(params["org_id"])
        assert claims["tool"] == params["tool_name"]
        assert claims["method"] == params["method"]
        assert claims["path"] == params["path"]
        assert claims["approved_by"] == str(params["approved_by"])
        assert claims["requested_by"] == str(params["requested_by"])
        assert claims["body_sha256"] == canonical_body_sha256(params["body"])
        assert claims["exp"] == claims["iat"] + 60

    def test_ttl_is_configurable(self):
        params = _mint(ttl_seconds=10)
        token = mint_assertion(**params)
        claims = jwt.decode(token, _SECRET, algorithms=["HS256"], audience=_AUD, issuer="agents")
        assert claims["exp"] == claims["iat"] + 10


class TestVerifyAssertion:
    def _verify(self, token, params, **overrides):
        call = dict(
            secret_candidates=[params["secret"]],
            aud=params["aud"],
            org_id=params["org_id"],
            method=params["method"],
            path=params["path"],
            body=params["body"],
            tool_for_route=params["tool_name"],
        )
        call.update(overrides)
        return verify_assertion(token, **call)

    def test_valid_assertion_verifies(self):
        params = _mint()
        token = mint_assertion(**params)
        result = self._verify(token, params)
        assert result.jti == params["approval_id"]
        assert result.approved_by == params["approved_by"]
        assert result.requested_by == params["requested_by"]

    def test_wrong_secret_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, secret_candidates=["b" * 40])

    def test_key_rotation_tries_every_candidate(self):
        params = _mint()
        token = mint_assertion(**params)
        result = self._verify(
            token, params, secret_candidates=["o" * 40, _SECRET]
        )
        assert result.jti == params["approval_id"]

    def test_wrong_org_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, org_id=uuid4())

    def test_wrong_body_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, body={**params["body"], "motivo": "changed"})

    def test_wrong_method_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, method="PUT")

    def test_wrong_path_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, path="/api/kb/other-slug")

    def test_wrong_tool_for_route_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, tool_for_route="mcp__academia__kb_mover")

    def test_wrong_audience_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, aud="some-other-product")

    def test_expired_assertion_is_invalid(self):
        params = _mint(ttl_seconds=-5)
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid, match="expired"):
            self._verify(token, params)

    def test_no_secret_candidates_is_invalid(self):
        params = _mint()
        token = mint_assertion(**params)
        with pytest.raises(AssertionInvalid):
            self._verify(token, params, secret_candidates=[])

    def test_malformed_token_is_invalid(self):
        params = _mint()
        with pytest.raises(AssertionInvalid):
            self._verify("not-a-real-jwt", params)
