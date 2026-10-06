"""Instagram API **with Instagram Login** — read adapter for IG Direct.

The agency-model sibling of ``MetaOAuthAdapter`` (which is the Facebook-Login /
Page-token model). This adapter talks to ``graph.instagram.com`` with a
**per-client Instagram User access token** and needs **no Facebook Page** — the
model Meta recommends for agencies reading many clients' inboxes (see roadmap
``ig-login-messaging-migration-2026-07`` + memory
``reference_meta_ig_dm_facebook_login_model``).

Model contrast (do NOT cross the two):

| | Facebook-Login (``MetaOAuthAdapter``) | Instagram-Login (this) |
|---|---|---|
| Host | ``graph.facebook.com`` | ``graph.instagram.com`` (``IG_GRAPH_BASE``) |
| Token | Page access token | IG **User** access token |
| FB Page | required | not required |
| Conversations node | ``/{PAGE-ID}/conversations`` | ``/me/conversations`` |
| Permissions | ``instagram_manage_messages`` + ``pages_manage_metadata`` | ``instagram_business_basic`` + ``instagram_business_manage_messages`` |

S1 (this file) covers the **read** surface — list conversations + list
messages. Send (``POST /me/messages``) is roadmap S4.

**Insights surface** (``InstagramLoginInsightsAdapter``, 2026-10-06):
``get_profile`` / ``get_user_insights`` / ``list_media`` (paged) /
``list_stories`` / ``get_media_insights`` — needs
``instagram_business_manage_insights``. Metric catalogs, value objects and
parsers live in ``instagram_insights`` (with the Meta doc URLs). Factory:
``get_instagram_login_adapter``. The conversation/message
JSON shapes match the Facebook-Login model, so the same ``conversation_from_body``
/ ``direct_message_from_body`` mappers + ``Conversation`` / ``DirectMessage``
dataclasses are reused (no second copy).
"""
from __future__ import annotations

import logging
from typing import Any, Protocol
from urllib.parse import parse_qs, urlparse

from noctusai_lib.integrations.meta import _meta_api
from noctusai_lib.integrations.meta._meta_api import IG_GRAPH_BASE, MetaGraphError
from noctusai_lib.integrations.meta.instagram_insights import (
    IG_MEDIA_LIST_CORE_FIELDS,
    IG_MEDIA_LIST_FIELDS,
    IG_PROFILE_CORE_FIELDS,
    IG_PROFILE_FIELDS,
    IG_USER_TOTAL_VALUE_METRICS,
    IgMediaItem,
    IgMediaPage,
    IgMetricsResult,
    IgProfile,
    IgUserInsights,
    ig_media_item_from_body,
    ig_profile_from_body,
    media_metrics_for,
    metric_series_from_body,
    metric_values_from_body,
)
from noctusai_lib.integrations.meta.mappers import (
    IG_CONVERSATION_FIELDS,
    IG_DM_FIELDS,
    conversation_from_body,
    direct_message_from_body,
)
from noctusai_lib.integrations.meta.types import Conversation, DirectMessage

logger = logging.getLogger(__name__)

__all__ = [
    "InstagramLoginAdapter",
    "InstagramLoginInsightsAdapter",
    "InstagramLoginMessagingAdapter",
    "InstagramLoginOAuthAdapter",
    "FakeInstagramLoginAdapter",
    "get_instagram_login_adapter",
]

# Graph "invalid parameter" — what an unknown field / a metric unsupported for
# this object (or this API version) returns. The ONLY code the insights read
# path degrades on (field-set fallback, per-metric retry). Everything else —
# auth (190), permission (10/200: scope not granted, or a Story under 5
# viewers), rate-limit — raises to the caller.
_INVALID_PARAM_CODE = 100


class InstagramLoginMessagingAdapter(Protocol):
    """Read-only IG Direct contract for the Instagram-Login model.

    Concrete: ``InstagramLoginOAuthAdapter`` (live ``graph.instagram.com``),
    ``FakeInstagramLoginAdapter`` (deterministic in-memory; dev/test)."""

    def me(self) -> dict[str, Any]: ...

    def list_instagram_conversations(self, limit: int = ...) -> list[Conversation]: ...

    def list_instagram_messages(
        self, conversation_id: str, limit: int = ...
    ) -> list[DirectMessage]: ...

    def send_instagram_message(
        self, recipient_id: str, text: str
    ) -> DirectMessage: ...


class InstagramLoginInsightsAdapter(Protocol):
    """Profile + insights + media-catalog read contract for the
    Instagram-Login model (scope ``instagram_business_manage_insights`` on
    top of ``instagram_business_basic``).

    Sources (Meta, Instagram API with Instagram Login):
    - https://developers.facebook.com/docs/instagram-platform/api-reference/instagram-user/insights
    - https://developers.facebook.com/docs/instagram-platform/reference/instagram-media
    - https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/insights
    Metric catalogs + parsers: ``noctusai_lib.integrations.meta.instagram_insights``."""

    def get_profile(self) -> IgProfile: ...

    def get_user_insights(
        self,
        ig_user_id: str,
        metrics: "tuple[str, ...] | list[str] | None" = ...,
        *,
        metric_type: str = ...,
        period: str = ...,
        since: int | None = ...,
        until: int | None = ...,
    ) -> IgUserInsights: ...

    def list_media(self, *, cursor: str | None = ..., limit: int = ...) -> IgMediaPage: ...

    def list_stories(self) -> list[IgMediaItem]: ...

    def get_media_insights(
        self,
        media_id: str,
        media_product_type: str | None = ...,
        *,
        media_type: str | None = ...,
    ) -> IgMetricsResult: ...


class InstagramLoginAdapter(
    InstagramLoginMessagingAdapter, InstagramLoginInsightsAdapter, Protocol
):
    """The full Instagram-Login adapter surface (messaging + insights)."""


class InstagramLoginOAuthAdapter:
    """Live Instagram-Login read adapter over ``graph.instagram.com``.

    Bound to ONE client's Instagram User access token — there is no Page and
    no ``/me/accounts`` fan-out here; ``/me`` IS the IG professional account.
    Needs ``instagram_business_basic`` + ``instagram_business_manage_messages``
    on the token (granted via Instagram Business Login — roadmap S2)."""

    def __init__(
        self,
        ig_user_token: str,
        *,
        version: str = _meta_api.DEFAULT_GRAPH_VERSION,
    ) -> None:
        self._token = ig_user_token
        self._version = version
        # The media field set Graph accepted on the first page (see
        # `_get_with_field_fallback`) — pinned so later pages skip the retry.
        self._media_fields: tuple[str, ...] = IG_MEDIA_LIST_FIELDS

    def me(self) -> dict[str, Any]:
        """The authenticated IG professional account (`/me`): `id`,
        `username`. Used as a best-effort label probe after OAuth (or to
        validate a manually-pasted token) — never the primary auth
        boundary (Graph itself is the source of truth on token validity;
        a probe failure raises `MetaGraphError`, never a silent pass)."""

        return _meta_api.graph_get(
            "me",
            access_token=self._token,
            params={"fields": "id,username"},
            version=self._version,
            base=IG_GRAPH_BASE,
        )

    def list_instagram_conversations(self, limit: int = 25) -> list[Conversation]:
        """List IG Direct threads — ``GET /me/conversations?platform=instagram``
        with the IG User token. Lean fields (``participants{id}``) to keep the
        query cheap, same as the Facebook-Login path."""
        rows = _meta_api.graph_paged(
            "me/conversations",
            access_token=self._token,
            params={
                "platform": "instagram",
                "fields": IG_CONVERSATION_FIELDS,
                "limit": limit,
            },
            version=self._version,
            base=IG_GRAPH_BASE,
            limit=limit,
        )
        return [conversation_from_body(r) for r in rows]

    def list_instagram_messages(
        self, conversation_id: str, limit: int = 25
    ) -> list[DirectMessage]:
        """Messages inside one thread. ``GET /{conversation}/messages`` returns
        bare ``{"id": ...}`` rows, so each is re-fetched for its body — the same
        link-probe-then-detail shape the Facebook-Login adapter uses."""
        rows = _meta_api.graph_paged(
            f"{conversation_id}/messages",
            access_token=self._token,
            params={"limit": limit},
            version=self._version,
            base=IG_GRAPH_BASE,
            limit=limit,
        )
        messages: list[DirectMessage] = []
        for row in rows:
            msg_id = str(row.get("id") or "")
            if not msg_id:
                continue
            detail = _meta_api.graph_get(
                msg_id,
                access_token=self._token,
                params={"fields": IG_DM_FIELDS},
                version=self._version,
                base=IG_GRAPH_BASE,
            )
            messages.append(
                direct_message_from_body(detail, conversation_id=conversation_id)
            )
        return messages

    def send_instagram_message(self, recipient_id: str, text: str) -> DirectMessage:
        """Send an IG Direct message — ``POST /me/messages`` on
        ``graph.instagram.com`` with the IG User token.

        The Instagram-Login twin of ``MetaOAuthAdapter.send_instagram_message``
        (which posts to ``/{PAGE-ID}/messages`` with a Page token). Same Send-API
        body shape — nested ``recipient``/``message`` objects are JSON-encoded
        form fields — but there is **no page id**: ``/me`` IS the professional
        account, which is the whole point of this model.

        ``sender_id`` on the returned message is the IG user id resolved from
        ``me()``, NOT a page id, so the read path's
        ``direction = outbound if sender_id == self_id`` comparison stays true
        for a just-sent message on this model.

        **Production gate:** ``instagram_business_manage_messages`` needs
        Advanced Access to message people who hold no role on the app. Absent
        it, Graph returns a permission error and this raises ``MetaGraphError``
        with ``requires_app_review`` true — never a faked success."""

        import json

        # Resolved BEFORE the send, deliberately. Graph's send response carries
        # no sender, so the id has to come from `/me` — and doing that first
        # means a token/permission failure raises with NOTHING sent, instead of
        # leaving a delivered message behind an error the caller will retry.
        sender_id = str(self.me().get("id") or "")

        created = _meta_api.graph_post(
            "me/messages",
            access_token=self._token,
            data={
                "recipient": json.dumps({"id": recipient_id}),
                "message": json.dumps({"text": text}),
            },
            version=self._version,
            base=IG_GRAPH_BASE,
        )
        message_id = str(created.get("message_id") or created.get("id") or "")
        if not message_id:
            raise MetaGraphError(
                f"IG Direct send to {recipient_id} returned no message id",
                code=200,
            )
        return DirectMessage(
            id=message_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            text=text,
        )

    # ─── Insights / catalog read surface ────────────────────────────────
    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        return _meta_api.graph_get(
            path,
            access_token=self._token,
            params=params,
            version=self._version,
            base=IG_GRAPH_BASE,
        )

    def _get_with_field_fallback(
        self,
        path: str,
        fields: tuple[str, ...],
        core: tuple[str, ...],
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        """GET with the FULL field set; on a Graph field rejection (code 100)
        retry ONCE with the CORE set, logging which optional fields were
        dropped. Returns ``(body, fields_used)`` so a pager can pin the set."""
        base = dict(params or {})
        try:
            return self._get(path, {**base, "fields": ",".join(fields)}), fields
        except MetaGraphError as exc:
            if exc.code != _INVALID_PARAM_CODE or fields == core:
                raise
            dropped = [f for f in fields if f not in core]
            logger.warning(
                "instagram_login: %s rejected optional fields %s (%s) — "
                "retrying with the core field set; those fields will be null",
                path, dropped, exc,
            )
            return self._get(path, {**base, "fields": ",".join(core)}), core

    def _fetch_metrics(
        self, path: str, metrics: list[str], params: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Request ``metrics`` in ONE call; if Graph rejects the batch with
        code 100 (one metric unsupported for this object rejects the whole
        call), retry metric-by-metric so the supported ones still land.
        Returns ``(merged_body_rows, errors_by_metric)``."""
        try:
            body = self._get(path, {**params, "metric": ",".join(metrics)})
            return {"data": list(body.get("data") or [])}, {}
        except MetaGraphError as exc:
            if exc.code != _INVALID_PARAM_CODE:
                raise
            if len(metrics) == 1:
                return {"data": []}, {metrics[0]: str(exc)}
            logger.info(
                "instagram_login: %s batch rejected (%s) — retrying %d metrics one by one",
                path, exc, len(metrics),
            )
        rows: list[dict[str, Any]] = []
        errors: dict[str, str] = {}
        for metric in metrics:
            try:
                body = self._get(path, {**params, "metric": metric})
                rows.extend(body.get("data") or [])
            except MetaGraphError as exc:
                if exc.code != _INVALID_PARAM_CODE:
                    raise
                errors[metric] = str(exc)
        return {"data": rows}, errors

    def get_profile(self) -> IgProfile:
        """``GET /me`` with the profile field set (``IG_PROFILE_FIELDS``)."""
        body, _ = self._get_with_field_fallback(
            "me", IG_PROFILE_FIELDS, IG_PROFILE_CORE_FIELDS
        )
        return ig_profile_from_body(body)

    def get_user_insights(
        self,
        ig_user_id: str,
        metrics: "tuple[str, ...] | list[str] | None" = None,
        *,
        metric_type: str = "total_value",
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> IgUserInsights:
        """``GET /<IG_ID>/insights`` — account-level metrics.

        ``metric_type="total_value"`` → one number per metric for the
        ``since``/``until`` window (Graph's default window is the last 24h);
        ``"time_series"`` → per-day points (only ``reach`` supports it on this
        API). Unsupported metrics come back ``None`` + named in
        ``unsupported`` — never 0. Needs ``instagram_business_manage_insights``;
        without it Graph answers a permission error, raised as
        ``MetaGraphError`` (``is_permission``)."""
        requested = list(metrics or IG_USER_TOTAL_VALUE_METRICS)
        params: dict[str, Any] = {"period": period, "metric_type": metric_type}
        if since is not None:
            params["since"] = since
        if until is not None:
            params["until"] = until
        body, errors = self._fetch_metrics(f"{ig_user_id}/insights", requested, params)
        if metric_type == "time_series":
            series = metric_series_from_body(body)
            unsupported = tuple(m for m in requested if m not in series)
            for m in unsupported:
                errors.setdefault(m, "not returned by Graph")
            return IgUserInsights(
                totals={}, series=series, unsupported=unsupported, errors=errors
            )
        got = metric_values_from_body(body)
        totals = {m: got.get(m) for m in requested}
        unsupported = tuple(m for m in requested if m not in got)
        for m in unsupported:
            errors.setdefault(m, "not returned by Graph")
        if unsupported:
            logger.warning(
                "instagram_login: user insights unsupported for %s: %s",
                ig_user_id, list(unsupported),
            )
        return IgUserInsights(totals=totals, unsupported=unsupported, errors=errors)

    def _paged_items(
        self,
        path: str,
        *,
        cursor: str | None,
        limit: int,
        default_product_type: str | None = None,
    ) -> IgMediaPage:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            if cursor.startswith("until:"):
                params["until"] = cursor[len("until:"):]
            else:
                params["after"] = cursor
        body, used = self._get_with_field_fallback(
            path, self._media_fields, IG_MEDIA_LIST_CORE_FIELDS, params
        )
        # Pin the accepted field set so later pages don't re-pay the fallback.
        self._media_fields = used
        items = [
            ig_media_item_from_body(r, default_product_type=default_product_type)
            for r in (body.get("data") or [])
            if isinstance(r, dict) and r.get("id")
        ]
        return IgMediaPage(items=items, next_cursor=_next_cursor(body.get("paging")))

    def list_media(self, *, cursor: str | None = None, limit: int = 50) -> IgMediaPage:
        """ONE page of ``GET /me/media`` (newest first; Graph serves at most
        the 10K most recent; Stories are NOT on this edge — see
        ``list_stories``). ``cursor`` is the opaque ``next_cursor`` of the
        previous page."""
        return self._paged_items("me/media", cursor=cursor, limit=limit)

    def list_stories(self) -> list[IgMediaItem]:
        """``GET /me/stories`` — the account's currently-live Stories (24h
        window). Every item is ``media_product_type="STORY"``."""
        out: list[IgMediaItem] = []
        cursor: str | None = None
        for _ in range(_meta_api.DEFAULT_MAX_PAGES):
            page = self._paged_items(
                "me/stories", cursor=cursor, limit=100, default_product_type="STORY"
            )
            out.extend(page.items)
            cursor = page.next_cursor
            if not cursor:
                break
        return out

    def get_media_insights(
        self,
        media_id: str,
        media_product_type: str | None = None,
        *,
        media_type: str | None = None,
    ) -> IgMetricsResult:
        """``GET /<IG_MEDIA_ID>/insights`` with the metric set for this media's
        product type (``IG_MEDIA_METRICS_BY_PRODUCT_TYPE``). A metric Graph
        rejects for this object → ``None`` + ``unsupported``; any non-code-100
        error (expired token, missing scope, Story under 5 viewers = code 10)
        raises ``MetaGraphError``."""
        requested = list(media_metrics_for(media_product_type, media_type))
        body, errors = self._fetch_metrics(f"{media_id}/insights", requested, {})
        got = metric_values_from_body(body)
        values = {m: got.get(m) for m in requested}
        unsupported = tuple(m for m in requested if m not in got)
        for m in unsupported:
            errors.setdefault(m, "not returned by Graph")
        if unsupported:
            logger.info(
                "instagram_login: media %s (%s) unsupported metrics: %s",
                media_id, media_product_type or media_type, list(unsupported),
            )
        return IgMetricsResult(
            object_id=media_id, values=values, unsupported=unsupported, errors=errors
        )


def _next_cursor(paging: Any) -> str | None:
    """Opaque next-page cursor from a Graph ``paging`` envelope: the
    ``cursors.after`` token when Graph uses cursor paging, ``until:<ts>`` when
    it uses time-based paging (the IG User media edge documents both). No
    ``paging.next`` → last page → ``None``."""
    if not isinstance(paging, dict) or not paging.get("next"):
        return None
    after = (paging.get("cursors") or {}).get("after")
    if after:
        return str(after)
    query = parse_qs(urlparse(str(paging["next"])).query)
    if query.get("after"):
        return query["after"][0]
    if query.get("until"):
        return f"until:{query['until'][0]}"
    raise MetaGraphError(
        f"Graph returned paging.next without a usable cursor: {paging['next']!r}"
    )


class FakeInstagramLoginAdapter:
    """Deterministic in-memory Instagram-Login adapter (dev/test default).

    Mirrors ``FakeMetaAdapter``'s seed-then-serve shape but for the single
    IG-user (no page) model: conversations are keyed by nothing (one inbox per
    token), messages by conversation id."""

    def __init__(self) -> None:
        self._conversations: list[Conversation] = []
        self._messages_by_conversation: dict[str, list[DirectMessage]] = {}
        self._me: dict[str, Any] = {"id": "FAKE_IG_USER", "username": "fake_ig_user"}
        self._counter = 0
        # Insights surface — empty-but-valid by default (a fresh account).
        self._profile: IgProfile | None = None
        self._media: list[IgMediaItem] = []
        self._stories: list[IgMediaItem] = []
        self._media_insights: dict[str, dict[str, float | int]] = {}
        self._media_errors: dict[str, MetaGraphError] = {}
        self._user_insights: dict[str, float | int] = {}
        self._user_series: dict[str, list[tuple[str, float | int | None]]] = {}
        self._user_insights_error: MetaGraphError | None = None
        # Every insights call, for tests asserting what was asked of Graph.
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def seed(
        self,
        *,
        conversations: list[Conversation] | None = None,
        messages_by_conversation: dict[str, list[DirectMessage]] | None = None,
        me: dict[str, Any] | None = None,
        profile: IgProfile | None = None,
        media: list[IgMediaItem] | None = None,
        stories: list[IgMediaItem] | None = None,
        media_insights: dict[str, dict[str, float | int]] | None = None,
        media_errors: dict[str, MetaGraphError] | None = None,
        user_insights: dict[str, float | int] | None = None,
        user_series: dict[str, list[tuple[str, float | int | None]]] | None = None,
        user_insights_error: MetaGraphError | None = None,
    ) -> "FakeInstagramLoginAdapter":
        """Seed any subset of the surface. ``media`` is served in the given
        order (seed it newest-first, as Graph does). A metric ABSENT from
        ``media_insights[id]`` / ``user_insights`` is served as unsupported
        (``None`` + named) — the Fake honours the no-silent-zero contract."""
        if profile is not None:
            self._profile = profile
        if media is not None:
            self._media = list(media)
        if stories is not None:
            self._stories = list(stories)
        if media_insights is not None:
            self._media_insights = {k: dict(v) for k, v in media_insights.items()}
        if media_errors is not None:
            self._media_errors = dict(media_errors)
        if user_insights is not None:
            self._user_insights = dict(user_insights)
        if user_series is not None:
            self._user_series = {k: list(v) for k, v in user_series.items()}
        if user_insights_error is not None:
            self._user_insights_error = user_insights_error
        if conversations is not None:
            self._conversations = list(conversations)
        if messages_by_conversation is not None:
            self._messages_by_conversation = {
                k: list(v) for k, v in messages_by_conversation.items()
            }
        if me is not None:
            self._me = dict(me)
        return self

    def me(self) -> dict[str, Any]:
        return dict(self._me)

    def list_instagram_conversations(self, limit: int = 25) -> list[Conversation]:
        return list(self._conversations)[:limit]

    def list_instagram_messages(
        self, conversation_id: str, limit: int = 25
    ) -> list[DirectMessage]:
        return list(self._messages_by_conversation.get(conversation_id, []))[:limit]

    def send_instagram_message(self, recipient_id: str, text: str) -> DirectMessage:
        """Append an outbound message to the recipient's thread and return it.

        The thread is keyed by ``recipient_id`` — on this model a conversation
        IS the other participant, so a send with no prior thread creates one
        (which is what Graph does too). Sent messages are readable back through
        ``list_instagram_messages``, so a test can assert the round trip rather
        than just the return value."""
        self._counter += 1
        message = DirectMessage(
            id=f"FAKE_IG_SENT_{self._counter}",
            sender_id=str(self._me.get("id") or ""),
            recipient_id=recipient_id,
            text=text,
        )
        self._messages_by_conversation.setdefault(recipient_id, []).append(message)
        return message

    # ─── Insights / catalog read surface ────────────────────────────────
    def get_profile(self) -> IgProfile:
        self.calls.append(("get_profile", {}))
        if self._profile is not None:
            return self._profile
        me_id = str(self._me.get("id") or "FAKE_IG_USER")
        return IgProfile(
            id=me_id,
            user_id=me_id,
            username=str(self._me.get("username") or "fake_ig_user"),
            media_count=len(self._media),
        )

    def get_user_insights(
        self,
        ig_user_id: str,
        metrics: "tuple[str, ...] | list[str] | None" = None,
        *,
        metric_type: str = "total_value",
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> IgUserInsights:
        requested = list(metrics or IG_USER_TOTAL_VALUE_METRICS)
        self.calls.append((
            "get_user_insights",
            {"ig_user_id": ig_user_id, "metrics": requested, "metric_type": metric_type,
             "period": period, "since": since, "until": until},
        ))
        if self._user_insights_error is not None:
            raise self._user_insights_error
        if metric_type == "time_series":
            series = {m: list(self._user_series[m]) for m in requested if m in self._user_series}
            unsupported = tuple(m for m in requested if m not in series)
            return IgUserInsights(
                totals={}, series=series, unsupported=unsupported,
                errors={m: "not seeded" for m in unsupported},
            )
        totals = {m: self._user_insights.get(m) for m in requested}
        unsupported = tuple(m for m in requested if m not in self._user_insights)
        return IgUserInsights(
            totals=totals, unsupported=unsupported,
            errors={m: "not seeded" for m in unsupported},
        )

    def list_media(self, *, cursor: str | None = None, limit: int = 50) -> IgMediaPage:
        """Index-cursor pagination over the seeded list (opaque to callers,
        like Graph's ``after`` token)."""
        self.calls.append(("list_media", {"cursor": cursor, "limit": limit}))
        start = int(cursor) if cursor else 0
        page = self._media[start:start + limit]
        nxt = start + limit
        return IgMediaPage(
            items=list(page), next_cursor=str(nxt) if nxt < len(self._media) else None
        )

    def list_stories(self) -> list[IgMediaItem]:
        self.calls.append(("list_stories", {}))
        return list(self._stories)

    def get_media_insights(
        self,
        media_id: str,
        media_product_type: str | None = None,
        *,
        media_type: str | None = None,
    ) -> IgMetricsResult:
        requested = list(media_metrics_for(media_product_type, media_type))
        self.calls.append((
            "get_media_insights",
            {"media_id": media_id, "media_product_type": media_product_type,
             "media_type": media_type, "metrics": requested},
        ))
        if media_id in self._media_errors:
            raise self._media_errors[media_id]
        seeded = self._media_insights.get(media_id, {})
        values = {m: seeded.get(m) for m in requested}
        unsupported = tuple(m for m in requested if m not in seeded)
        return IgMetricsResult(
            object_id=media_id, values=values, unsupported=unsupported,
            errors={m: "not seeded" for m in unsupported},
        )


def get_instagram_login_adapter(
    access_token: str | None,
    *,
    version: str | None = None,
    allow_fake: bool = False,
) -> "InstagramLoginOAuthAdapter | FakeInstagramLoginAdapter":
    """Canonical factory for the Instagram-Login adapter.

    A token → ``InstagramLoginOAuthAdapter`` (live ``graph.instagram.com``,
    pinned to ``version`` when given). No token → ``FakeInstagramLoginAdapter``
    ONLY when the caller opts in with ``allow_fake=True`` (dev/test);
    otherwise ``ValueError`` — a production path that lost its token must fail
    loud as a named config gap, never serve fake numbers."""
    if access_token:
        if version:
            return InstagramLoginOAuthAdapter(access_token, version=version)
        return InstagramLoginOAuthAdapter(access_token)
    if allow_fake:
        return FakeInstagramLoginAdapter()
    raise ValueError(
        "get_instagram_login_adapter: no access_token — reconnect the "
        "Instagram account (pass allow_fake=True only in dev/test)"
    )


# Re-export MetaGraphError so consumers importing from this module have the
# error type without reaching into `_meta_api` (same failure contract).
__all__.append("MetaGraphError")
