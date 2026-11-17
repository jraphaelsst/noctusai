"""`check_http_call_without_timeout` -- AST ratchet keeper tests (synthetic trees; red + green fixtures)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import compliance as c  # noqa: E402

DEV = "mcp/noctusai/tools/noctus/dev"
T = f"{DEV}/x.py"


def _tree(tmp_path, files: dict[str, str], baseline: dict | None = None):
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    if baseline is not None:
        b = tmp_path.joinpath(*c._HTTP_BASELINE_REL)
        b.parent.mkdir(parents=True, exist_ok=True)
        b.write_text(json.dumps({"files": baseline}))
    return tmp_path


def _flag(tmp_path, src: str):
    return c.check_http_call_without_timeout(_tree(tmp_path, {T: src}))


class TestHttpCallWithoutTimeout:
    """Red: every unbounded shape. Green: timeout present, helper, suppression with a reason."""

    def test_clean_tree_no_issues(self, tmp_path):
        assert c.check_http_call_without_timeout(tmp_path) == []

    def test_urlopen_without_timeout_flagged(self, tmp_path):
        issues = _flag(tmp_path, "import urllib.request\nurllib.request.urlopen(req)\n")
        assert len(issues) == 1 and issues[0]["severity"] == "high" and issues[0]["file"] == T

    def test_bare_urlopen_flagged(self, tmp_path):
        assert len(_flag(tmp_path, "from urllib.request import urlopen\nurlopen(req)\n")) == 1

    def test_httpx_client_and_verbs_flagged(self, tmp_path):
        src = "import httpx\nhttpx.Client()\nhttpx.AsyncClient(base_url='x')\nhttpx.get(u)\nhttpx.post(u)\nhttpx.request('GET', u)\n"
        assert len(_flag(tmp_path, src)) == 1  # one file issue
        hits = c._http_scan(tmp_path)[T]
        assert len(hits) == 5

    def test_requests_verbs_and_session_flagged(self, tmp_path):
        src = "import requests\nrequests.get(u)\nrequests.post(u)\nrequests.Session().get(u)\nrequests.Session().request('GET', u)\n"
        _tree(tmp_path, {T: src})
        assert len(c._http_scan(tmp_path)[T]) == 4

    def test_timeout_none_is_still_unbounded(self, tmp_path):
        assert len(_flag(tmp_path, "import httpx\nhttpx.Client(timeout=None)\n")) == 1

    def test_explicit_timeout_passes(self, tmp_path):
        src = ("import httpx, requests, urllib.request\nhttpx.Client(timeout=30)\nhttpx.get(u, timeout=httpx.Timeout(5))\n"
               "requests.get(u, timeout=(3, 9))\nurllib.request.urlopen(req, timeout=15)\n")
        assert _flag(tmp_path, src) == []

    def test_positional_urlopen_timeout_passes(self, tmp_path):
        assert _flag(tmp_path, "import urllib.request\nurllib.request.urlopen(u, None, 12)\n") == []

    def test_going_through_the_helper_passes(self, tmp_path):
        assert _flag(tmp_path, "from . import _http\n_http.urlopen_read(req, call_site='x')\n") == []

    def test_unrelated_get_calls_are_not_http(self, tmp_path):
        assert _flag(tmp_path, "d = {}\nd.get('k')\nclient.post(u)\nfoo.request(1)\n") == []

    def test_suppression_with_reason_passes_without_reason_flags(self, tmp_path):
        ok = "import httpx\nhttpx.get(u)  # noc-allow: http-timeout -- streaming download bounded by the caller\n"
        bad = "import httpx\nhttpx.get(u)  # noc-allow: http-timeout\n"
        assert _flag(tmp_path, ok) == []
        assert len(_flag(tmp_path, bad)) == 1

    def test_multiline_call_suppression_on_any_line(self, tmp_path):
        src = ("import httpx\nhttpx.Client(\n    base_url=b,  # noc-allow: http-timeout -- per-request timeouts set below\n)\n")
        assert _flag(tmp_path, src) == []

    def test_helper_module_and_tests_are_out_of_scope(self, tmp_path):
        body = "import urllib.request\nurllib.request.urlopen(req)\n"
        root = _tree(tmp_path, {f"{DEV}/_http.py": body, "mcp/noctusai/tools/noctus/tests/t.py": body})
        assert c.check_http_call_without_timeout(root) == []

    def test_ratchet_baselined_passes_grown_count_blocks(self, tmp_path):
        two = "import httpx\nhttpx.get(a)\nhttpx.get(b)\n"
        root = _tree(tmp_path, {T: two}, baseline={T: 2})
        assert c.check_http_call_without_timeout(root) == []
        root = _tree(tmp_path, {T: two + "httpx.get(c)\n"}, baseline={T: 2})
        assert len(c.check_http_call_without_timeout(root)) == 1

    def test_new_file_not_in_baseline_blocks(self, tmp_path):
        root = _tree(tmp_path, {T: "import httpx\nhttpx.get(a)\n"}, baseline={f"{DEV}/other.py": 1})
        assert len(c.check_http_call_without_timeout(root)) == 1

    def test_paths_narrows_reporting(self, tmp_path):
        root = _tree(tmp_path, {T: "import httpx\nhttpx.get(a)\n"})
        assert c.check_http_call_without_timeout(root, paths=[f"{DEV}/other.py"]) == []
        assert len(c.check_http_call_without_timeout(root, paths=[T])) == 1

    def test_baseline_refresh_is_shrink_only(self, tmp_path):
        root = _tree(tmp_path, {T: "import httpx\nhttpx.get(a)\nhttpx.get(b)\n"})
        assert c.refresh_http_timeout_baseline(root) == {T: 2}
        _tree(tmp_path, {T: "import httpx\nhttpx.get(a)\n"})
        assert c.refresh_http_timeout_baseline(root) == {T: 1}
        _tree(tmp_path, {T: "import httpx\nhttpx.get(a)\nhttpx.get(b)\nhttpx.get(c)\n"})
        assert c.refresh_http_timeout_baseline(root) == {T: 1}  # never grows

    def test_live_tree_is_clean(self):
        """The toolkit itself: every call is bounded (baseline is empty)."""
        assert c.check_http_call_without_timeout() == []
