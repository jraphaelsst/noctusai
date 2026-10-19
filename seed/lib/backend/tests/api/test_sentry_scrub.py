from noctusai_lib.api.sentry_scrub import REDACTED, before_send


def test_scrubber_drops_body_headers_query_and_pii():
    ev = {
        "request": {
            "url": "https://x.test/api/a?token=abc&x=1",
            "query_string": "token=abc",
            "data": {"cpf": "123"},
            "headers": {"Authorization": "Bearer z", "Cookie": "s=1"},
            "cookies": {"s": "1"},
        },
        "extra": {"prompt": "secret", "ok": 1, "nested": {"email": "a@b.c", "n": 2}},
        "breadcrumbs": {"values": [{"data": {"texto": "t", "k": 1}, "message": "GET /x?access_token=abc"}]},
        "user": {"id": "1", "email": "a@b.c", "ip_address": "1.1.1.1"},
    }
    out = before_send(ev)
    assert "data" not in out["request"] and "headers" not in out["request"]
    assert "cookies" not in out["request"] and "query_string" not in out["request"]
    assert out["request"]["url"] == "https://x.test/api/a"
    assert out["extra"]["prompt"] == REDACTED and out["extra"]["ok"] == 1
    assert out["extra"]["nested"] == {"email": REDACTED, "n": 2}
    crumb = out["breadcrumbs"]["values"][0]
    assert crumb["data"] == {"texto": REDACTED, "k": 1}
    assert "abc" not in crumb["message"]
    assert out["user"] == {"id": "1"}
