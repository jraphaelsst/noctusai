"""`TrelloClient` DI seam — every live `trello.*` tool builds its client
through `get_client()` (the FastAPI-dep-factory module-slot convention: a
private override slot, default `None`, populated by an explicit
`configure_client(...)` call — mirrors `mcp/n8n/client.py`).

`TrelloClient` is a thin, connector-owned wrapper around `api.request_json`
— domain-shaped methods (`get_card`, `list_board_cards`, `update_card`, …)
instead of every tool module remembering raw Trello paths. It is NOT a
seed adapter: no product consumes Trello, so there is no Fake+Real+factory
seam to ship (`settings.py`'s module docstring; `README.md` § Architecture).

**Test seam (dependency injection, NOT monkeypatching).**
`configure_client(_FakeTrelloClient(...))` lets a test exercise the REAL
handler path — confirm-gate + client call + Out shaping — without a
network round-trip. Tests that need to inspect the RAW HTTP call (query
params, method, URL shape) instead patch the external boundary
`trello.api.request_json` or `_kit.transport.urlopen` — our own code
(`TrelloClient`, `api.require_configured`) is never patched.
"""
from __future__ import annotations

from typing import Any, Optional

from . import api
from .settings import get_settings

_client_override: Optional["TrelloClient"] = None


class TrelloClient:
    """Domain-shaped Trello REST calls. Every method raises
    `api.TrelloApiError` (typed `status`) on failure — never a partial or
    fabricated result."""

    def __init__(self, *, api_key: str, token: str, base_url: str, timeout_seconds: float):
        self._api_key = api_key
        self._token = token
        self._base_url = base_url
        self._timeout = timeout_seconds

    def _get(self, path: str, params: Optional[dict] = None) -> Any:
        return api.request_json(
            "GET", path,
            api_key=self._api_key, token=self._token, base_url=self._base_url,
            params=params, timeout=self._timeout,
        )

    def _post(self, path: str, params: Optional[dict] = None) -> Any:
        return api.request_json(
            "POST", path,
            api_key=self._api_key, token=self._token, base_url=self._base_url,
            params=params, timeout=self._timeout,
        )

    def _put(self, path: str, params: Optional[dict] = None) -> Any:
        return api.request_json(
            "PUT", path,
            api_key=self._api_key, token=self._token, base_url=self._base_url,
            params=params, timeout=self._timeout,
        )

    # ── reads ────────────────────────────────────────────────────────

    def get_member_boards(self, member_id: str = "me") -> Any:
        return self._get(f"/members/{member_id}/boards")

    def get_board_lists(self, board_id: str) -> Any:
        return self._get(f"/boards/{board_id}/lists")

    def get_board_cards(self, board_id: str) -> Any:
        return self._get(f"/boards/{board_id}/cards")

    def get_list_cards(self, list_id: str) -> Any:
        return self._get(f"/lists/{list_id}/cards")

    def get_card(self, card_id: str, *, include: Optional[list[str]] = None) -> Any:
        """`include` names extra nested resources to expand — a subset of
        `attachments` / `checklists` / `actions` / `members`. Each maps to
        the corresponding Trello query param (`attachments=true`, etc.);
        `actions` additionally sets `actions=commentCard,createCard`."""
        params: dict[str, Any] = {}
        wanted = set(include or [])
        if "attachments" in wanted:
            params["attachments"] = "true"
        if "checklists" in wanted:
            params["checklists"] = "all"
        if "members" in wanted:
            params["members"] = "true"
        if "actions" in wanted:
            params["actions"] = "commentCard,createCard,updateCard:idList"
        return self._get(f"/cards/{card_id}", params=params or None)

    def get_checklist(self, checklist_id: str) -> Any:
        return self._get(f"/checklists/{checklist_id}")

    def get_board_labels(self, board_id: str) -> Any:
        return self._get(f"/boards/{board_id}/labels")

    def get_card_actions(self, card_id: str, *, filter_: Optional[str] = None) -> Any:
        return self._get(f"/cards/{card_id}/actions", params={"filter": filter_} if filter_ else None)

    def get_me(self) -> Any:
        """Cheap identity probe — `trello.diagnostics.probe`."""
        return self._get("/members/me")

    # ── writes ───────────────────────────────────────────────────────

    def create_card(self, *, id_list: str, name: str, desc: Optional[str] = None,
                     due: Optional[str] = None, id_members: Optional[list[str]] = None,
                     id_labels: Optional[list[str]] = None) -> Any:
        params: dict[str, Any] = {"idList": id_list, "name": name}
        if desc is not None:
            params["desc"] = desc
        if due is not None:
            params["due"] = due
        if id_members:
            params["idMembers"] = ",".join(id_members)
        if id_labels:
            params["idLabels"] = ",".join(id_labels)
        return self._post("/cards", params=params)

    def update_card(self, card_id: str, **fields: Any) -> Any:
        """`fields` keys must be from the vendor's documented `PUT
        /cards/{id}` writable-param list (`trello.contract.card_surface`
        publishes it) — the tool layer validates this, not the client."""
        return self._put(f"/cards/{card_id}", params=fields)

    def add_comment(self, card_id: str, text: str) -> Any:
        return self._post(f"/cards/{card_id}/actions/comments", params={"text": text})

    def create_checklist(self, card_id: str, name: str) -> Any:
        return self._post("/checklists", params={"idCard": card_id, "name": name})


def configure_client(client: Optional[TrelloClient]) -> None:
    """Inject the `TrelloClient` every live `trello.*` tool builds through
    (tests only). `None` restores the settings-resolved production path."""
    global _client_override
    _client_override = client


def get_client() -> TrelloClient:
    """The DI override when set (tests); otherwise the settings-resolved
    client — raises `api.TrelloApiError` (424) when unconfigured."""
    if _client_override is not None:
        return _client_override
    s = get_settings()
    api.require_configured(s)
    return TrelloClient(
        api_key=s.api_key or "", token=s.token or "",
        base_url=s.base_url, timeout_seconds=s.timeout_seconds,
    )


__all__ = ["TrelloClient", "configure_client", "get_client"]
