"""Graph JSON → dataclass mappers + default field/metric constants.

Pure functions only — no IO. Mirrors the calendar/maps mapper module
posture (testable in isolation, no network). The `FIELDS` constants
encode the `.summary(true).limit(0)` bandwidth trick: ask Graph for an
edge's `summary.total_count` without expanding the edge body (a post
with 5,000 likes returns ~80 bytes instead of ~200KB).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.meta.types import (
    Ad,
    AdAccount,
    AdActivity,
    AdCampaign,
    AdInsightsRow,
    AdSet,
    Conversation,
    DirectMessage,
    FacebookComment,
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramComment,
    InstagramMedia,
    Lead,
    LeadFieldEntry,
    LeadgenForm,
    LeadgenQuestion,
    PageSubscription,
    PostInsights,
)


# ─── Default field selectors (Graph `fields=` query param) ────────────────

PAGE_FIELDS = (
    "id,name,category,access_token,fan_count,followers_count,link,tasks"
)

POST_FIELDS = (
    "id,message,created_time,permalink_url,full_picture,"
    "attachments{title,description,type,media_type,unshimmed_url},"
    "likes.summary(true).limit(0),"
    "comments.summary(true).limit(0),"
    "shares"
)

IG_ACCOUNT_FIELDS = (
    "id,username,name,profile_picture_url,"
    "followers_count,follows_count,media_count,biography,website"
)

IG_MEDIA_FIELDS = (
    "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,"
    "like_count,comments_count"
)

ME_FIELDS = "id,name"

PAGE_IG_FIELD = "instagram_business_account"

# IG comments edge (`instagram_manage_comments` scope). `hidden` /
# `parent_id` were added to the edge after launch — requested
# explicitly since Graph omits fields not asked for (never assumed
# present; the mapper below is None/False-safe regardless).
IG_COMMENT_FIELDS = (
    "id,text,username,timestamp,like_count,hidden,parent_id"
)

# FB Page-post comments edge (`pages_manage_engagement` scope).
# `from`/`parent` are nested objects the mapper below flattens.
FB_COMMENT_FIELDS = (
    "id,message,from,created_time,like_count,is_hidden,parent"
)

# IG Direct conversations list edge (`instagram_manage_messages`
# scope) — `id` is always returned; `participants`/`updated_time` are
# requested explicitly (thin default field surface on this edge).
# Lean field set for the IG conversations edge. `participants` is expanded to
# JUST `{id}` (all `conversation_from_body` uses) — the default expansion pulls
# username/name per participant and, combined with the page size, makes Graph
# reject the whole call with (#1) "Please reduce the amount of data you're
# asking for" on a busy inbox. Scope it to ids to keep the query cheap.
IG_CONVERSATION_FIELDS = "participants{id},updated_time"

# Per-message detail fetch (the conversations `/messages` list edge
# returns bare `{"id": ...}` rows — every field must be re-fetched
# per message id, mirroring `list_instagram_accounts`'s link-probe-
# then-detail-fetch shape).
IG_DM_FIELDS = "id,from,to,message,created_time"


# ─── Default insight metric lists ─────────────────────────────────────────

POST_INSIGHT_METRICS = [
    "post_impressions",
    "post_impressions_unique",  # == reach
    "post_engaged_users",
    "post_clicks",
    "post_reactions_like_total",
    "post_reactions_love_total",
    "post_reactions_wow_total",
    "post_reactions_haha_total",
    "post_reactions_sorry_total",
    "post_reactions_anger_total",
]

# Per-media (`/{media-id}/insights`) metrics. Graph validates the whole metric
# list up front and REJECTS the entire call if ANY name is unsupported, so one
# retired name zeroes every metric on the item. Retirements observed against a
# live token:
#   - `engagement` → `total_interactions`, `video_views` → `views` (2026-07-16)
#   - `impressions` retired for media in Graph v22+ ("the impressions metric is
#     no longer supported for the queried media") — dropped 2026-07-21; it was
#     failing the whole per-post insights call in prod.
# Kept conservative to the names that serve across media product types.
IG_MEDIA_INSIGHT_METRICS = [
    "reach",
    "total_interactions",
    "saved",
    "views",
]

# Account-level (IG User) insights — the `/{ig-user-id}/insights` endpoint,
# distinct from the per-media `/{media-id}/insights` above. Conservative
# default: three `period=day` account metrics needing no extra scope beyond
# `instagram_manage_insights`. `impressions` was retired at the account level
# in Graph v22 (kept only per-media, and even there via `views` in newer
# versions) — deliberately EXCLUDED here so the default call never 400s on a
# current app. Richer metrics (`accounts_engaged`, `total_interactions`,
# `website_clicks`, `views`) are opt-in via the method's `metrics=` param once
# the live account confirms which its app version exposes (calibrate against
# the real token — mirrors the WAHA response-shape-drift discipline). The
# adapter keeps the raw daily series on `PostInsights.raw`, so no metric's
# per-day breakdown is lost even though `metrics` flattens to one number each.
IG_ACCOUNT_INSIGHT_METRICS = [
    "reach",
    "profile_views",
    "follower_count",
]

# The subset of account metrics Graph serves ONLY with
# `metric_type=total_value` — a single summed number over the window, with no
# per-day series. Requesting one of these in the same batched call as a
# time-series metric fails the ENTIRE call with `(#100) The following metrics
# (...) should be specified with parameter metric_type=total_value`, which is
# why `MetaOAuthAdapter.get_instagram_account_insights` splits its request into
# a time-series call + a total-value call and merges the rows. An earlier
# version of this comment asserted the default trio "need no
# `metric_type=total_value` handling" — that was written from the docs and was
# WRONG for `profile_views` against a live token (it 502'd the whole Meta
# overview in prod until 2026-07-16). Calibrated against the real token on
# Graph v21; extend this set the same way — by observing a live rejection, not
# by reading the docs.
IG_TOTAL_VALUE_ACCOUNT_METRICS = frozenset({"profile_views"})

# Facebook Page-level insights — the `/{page-id}/insights` endpoint (distinct
# from the per-post `POST_INSIGHT_METRICS` above). Meta has been actively
# deprecating individual Page Insights metrics on a rolling basis (a wave
# retired 2026-06-15) — this list is a conservative starting point, NOT a
# guarantee every entry is still live on any given app/API version.
# `MetaOAuthAdapter.get_facebook_page_insights` requests each metric
# SEPARATELY (not batched like the lists above) and drops any metric that
# 400s rather than failing the whole call, so a retired name only costs
# itself. Calibrate this default against the live Graph Explorer for the
# connected app before relying on it in production (same "verify against the
# real token" discipline as `IG_ACCOUNT_INSIGHT_METRICS`); pass an explicit
# `metrics=` to the method to override entirely.
PAGE_INSIGHT_METRICS = [
    "page_impressions_unique",
    "page_post_engagements",
    "page_fans",
    "page_views_total",
]


# ─── Datetime ─────────────────────────────────────────────────────────────


def parse_graph_datetime(value: str | None) -> datetime | None:
    """Parse Graph's timestamp formats into an aware ``datetime``.

    Graph emits `2026-05-13T18:30:00+0000` (no colon in the offset),
    which `datetime.fromisoformat` rejects pre-3.11 and still parses
    inconsistently across versions. We normalize the `+HHMM` /
    `-HHMM` tail to `+HH:MM` first, and tolerate a trailing `Z`.
    Returns `None` for falsy input."""

    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # Normalize a `+0000` / `-0530` style offset (no colon) to `+00:00`.
    if len(text) >= 5:
        tail = text[-5:]
        if (tail[0] in "+-") and tail[1:].isdigit():
            text = text[:-5] + tail[0] + tail[1:3] + ":" + tail[3:]
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ─── Edge-summary helper ──────────────────────────────────────────────────


def _summary_count(edge: Any) -> int:
    """Extract `summary.total_count` from a `.summary(true).limit(0)`
    edge, or fall back to `len(data)`. Tolerant of missing keys."""

    if not isinstance(edge, dict):
        return 0
    summary = edge.get("summary")
    if isinstance(summary, dict) and summary.get("total_count") is not None:
        try:
            return int(summary["total_count"])
        except (TypeError, ValueError):
            return 0
    data = edge.get("data")
    if isinstance(data, list):
        return len(data)
    return 0


def _shares_count(value: Any) -> int:
    """`shares` comes back as `{"count": N}` (or absent)."""

    if isinstance(value, dict):
        try:
            return int(value.get("count", 0))
        except (TypeError, ValueError):
            return 0
    return 0


# ─── Body → dataclass mappers ─────────────────────────────────────────────


def page_from_body(body: dict[str, Any]) -> FacebookPage:
    return FacebookPage(
        id=str(body["id"]),
        name=body.get("name", ""),
        category=body.get("category"),
        access_token=body.get("access_token"),
        fan_count=body.get("fan_count"),
        followers_count=body.get("followers_count"),
        link=body.get("link"),
        tasks=list(body.get("tasks") or []),
    )


def post_from_body(body: dict[str, Any]) -> FacebookPost:
    return FacebookPost(
        id=str(body["id"]),
        message=body.get("message"),
        created_time=parse_graph_datetime(body.get("created_time")),
        permalink_url=body.get("permalink_url"),
        full_picture=body.get("full_picture"),
        likes=_summary_count(body.get("likes")),
        comments=_summary_count(body.get("comments")),
        shares=_shares_count(body.get("shares")),
        attachments=list(
            (body.get("attachments") or {}).get("data", [])
            if isinstance(body.get("attachments"), dict)
            else []
        ),
    )


def ig_account_from_body(
    body: dict[str, Any], *, page_id: str | None = None
) -> InstagramAccount:
    return InstagramAccount(
        id=str(body["id"]),
        username=body.get("username", ""),
        name=body.get("name"),
        profile_picture_url=body.get("profile_picture_url"),
        followers_count=body.get("followers_count"),
        follows_count=body.get("follows_count"),
        media_count=body.get("media_count"),
        biography=body.get("biography"),
        website=body.get("website"),
        page_id=page_id,
    )


def ig_media_from_body(body: dict[str, Any]) -> InstagramMedia:
    return InstagramMedia(
        id=str(body["id"]),
        caption=body.get("caption"),
        media_type=body.get("media_type"),
        media_url=body.get("media_url"),
        permalink=body.get("permalink"),
        thumbnail_url=body.get("thumbnail_url"),
        timestamp=parse_graph_datetime(body.get("timestamp")),
        like_count=int(body.get("like_count") or 0),
        comments_count=int(body.get("comments_count") or 0),
    )


def _metric_value(values: Any) -> int:
    """Flatten an insight metric's `values` list into a single int.

    `values` is `[{"value": <int|dict>}]`. Dict-valued payloads
    (`post_reactions_by_type_total`) get summed into a flat int."""

    if not isinstance(values, list) or not values:
        return 0
    raw = values[0].get("value") if isinstance(values[0], dict) else None
    if isinstance(raw, dict):
        total = 0
        for v in raw.values():
            try:
                total += int(v)
            except (TypeError, ValueError):
                continue
        return total
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _total_value_metric(total_value: Any) -> int:
    """Flatten a `metric_type=total_value` row's `total_value` payload
    (`{"value": <int>}`) into a single int.

    A total-value row carries NO `values` list — reading it with
    `_metric_value` would silently yield 0 for every such metric."""

    if not isinstance(total_value, dict):
        return 0
    try:
        return int(total_value.get("value"))
    except (TypeError, ValueError):
        return 0


def insights_from_body(
    object_id: str, body: dict[str, Any]
) -> PostInsights:
    """Map `/{id}/insights` `{"data": [{name, period, values}]}`.

    Rows fetched with `metric_type=total_value` carry a `total_value`
    dict instead of a `values` list (see
    `IG_TOTAL_VALUE_ACCOUNT_METRICS`); both shapes flatten to one int
    here so callers see a uniform `metrics` map regardless of which
    call served the row."""

    rows = body.get("data") or []
    metrics: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if not name:
            continue
        if "total_value" in row:
            metrics[name] = _total_value_metric(row.get("total_value"))
        else:
            metrics[name] = _metric_value(row.get("values"))
    return PostInsights(object_id=object_id, metrics=metrics, raw=list(rows))


# ─── Comments / DMs body → dataclass mappers ──────────────────────────────


def instagram_comment_from_body(body: dict[str, Any]) -> InstagramComment:
    """Map one row of `GET /{ig-media}/comments` (or a comment
    read-back after `reply`/`hide`) to `InstagramComment`."""

    parent_id = body.get("parent_id")
    return InstagramComment(
        id=str(body["id"]),
        text=body.get("text"),
        username=body.get("username"),
        timestamp=parse_graph_datetime(body.get("timestamp")),
        like_count=int(body.get("like_count") or 0),
        hidden=bool(body.get("hidden") or False),
        parent_id=str(parent_id) if parent_id else None,
        raw=dict(body),
    )


def facebook_comment_from_body(body: dict[str, Any]) -> FacebookComment:
    """Map one row of `GET /{post}/comments` (or a comment read-back
    after `reply`/`hide`) to `FacebookComment`. `from`/`parent` are
    nested objects Graph returns as `{"id": ..., "name": ...}`."""

    from_obj = body.get("from")
    from_obj = from_obj if isinstance(from_obj, dict) else {}
    parent_obj = body.get("parent")
    parent_obj = parent_obj if isinstance(parent_obj, dict) else {}
    return FacebookComment(
        id=str(body["id"]),
        message=body.get("message"),
        from_id=from_obj.get("id"),
        from_name=from_obj.get("name"),
        created_time=parse_graph_datetime(body.get("created_time")),
        like_count=int(body.get("like_count") or 0),
        is_hidden=bool(body.get("is_hidden") or False),
        parent_id=parent_obj.get("id"),
        raw=dict(body),
    )


def conversation_from_body(body: dict[str, Any]) -> Conversation:
    """Map one row of `GET /{ig-user}/conversations?platform=instagram`
    to `Conversation`. `participants` is a `{"data": [{"id": ...}]}`
    edge — flattened to a bare id list."""

    participants = body.get("participants")
    participant_ids: list[str] = []
    if isinstance(participants, dict):
        for row in participants.get("data") or []:
            if isinstance(row, dict) and row.get("id"):
                participant_ids.append(str(row["id"]))
    return Conversation(
        id=str(body["id"]),
        participant_ids=participant_ids,
        updated_time=parse_graph_datetime(body.get("updated_time")),
        raw=dict(body),
    )


def direct_message_from_body(
    body: dict[str, Any], *, conversation_id: str | None = None
) -> DirectMessage:
    """Map a per-message detail fetch (`GET /{message-id}`) to
    `DirectMessage`. `conversation_id` is supplied by the caller — the
    message body itself does not carry the parent conversation id
    back. `from`/`to` are nested Graph objects (`to` is a `{"data":
    [...]}` edge even though Direct is 1:1, mirroring the Messenger
    Send API shape)."""

    from_obj = body.get("from")
    from_obj = from_obj if isinstance(from_obj, dict) else {}
    to_obj = body.get("to")
    recipient_id: str | None = None
    if isinstance(to_obj, dict):
        to_rows = to_obj.get("data")
        if isinstance(to_rows, list) and to_rows:
            first = to_rows[0]
            if isinstance(first, dict) and first.get("id"):
                recipient_id = str(first["id"])
    return DirectMessage(
        id=str(body["id"]),
        conversation_id=conversation_id,
        sender_id=from_obj.get("id"),
        recipient_id=recipient_id,
        text=body.get("message"),
        created_time=parse_graph_datetime(body.get("created_time")),
        raw=dict(body),
    )


# ─── Ads-read body → dataclass mappers ─────────────────────────────────────


def _safe_int(value: Any) -> int | None:
    """Best-effort int coercion for Graph numeric-as-string fields
    (`daily_budget`, …). Returns `None` rather than raising or
    silently defaulting to 0 — a missing budget is not the same fact
    as a zero budget."""

    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def ad_account_from_body(body: dict[str, Any]) -> AdAccount:
    """Map one row of `GET me/adaccounts` to `AdAccount`.

    Strips the `act_` prefix Graph returns on `id` — see `AdAccount`'s
    docstring for why (bare-id convention every other
    `ad_account_id`-consuming method in this module expects)."""

    raw_id = str(body.get("id") or "")
    bare_id = raw_id[4:] if raw_id.startswith("act_") else raw_id
    return AdAccount(
        id=bare_id,
        name=body.get("name"),
        currency=body.get("currency"),
        timezone_name=body.get("timezone_name"),
        amount_spent=body.get("amount_spent"),
        balance=body.get("balance"),
        spend_cap=body.get("spend_cap"),
        account_status=_safe_int(body.get("account_status")),
    )


def campaign_from_body(body: dict[str, Any]) -> AdCampaign:
    """Map one row of `GET act_{id}/campaigns` (or a single-campaign
    read) to `AdCampaign`. `daily_budget`/`lifetime_budget` arrive as
    Graph numeric-as-string fields and are present ONLY for
    CBO/Advantage-campaign-budget campaigns; coerced via `_safe_int`
    (`None` on a missing/unparseable value, never a silent 0 — an
    ABO campaign genuinely has no campaign-level budget, and 0 would
    misread as "R$0,00 budget")."""

    return AdCampaign(
        id=str(body["id"]),
        name=body.get("name"),
        objective=body.get("objective"),
        status=body.get("status"),
        effective_status=body.get("effective_status"),
        daily_budget=_safe_int(body.get("daily_budget")),
        lifetime_budget=_safe_int(body.get("lifetime_budget")),
    )


def leadgen_question_from_body(body: dict[str, Any]) -> LeadgenQuestion:
    """Map one entry of a form's `questions` array to `LeadgenQuestion`.
    Graph echoes the answer key back on a lead's `field_data[].name`; we
    fall back to `type` when `key` is absent so a `CUSTOM` question is
    never keyless."""
    return LeadgenQuestion(
        key=body.get("key") or body.get("type"),
        label=body.get("label"),
        type=body.get("type"),
        options=[
            {"key": str(o.get("key", "")), "value": str(o.get("value", ""))}
            for o in (body.get("options") or [])
            if isinstance(o, dict)
        ],
    )


def leadgen_form_from_body(body: dict[str, Any]) -> LeadgenForm:
    """Map one row of `{page_id}/leadgen_forms` (or a single-form read
    with `questions`) to `LeadgenForm`. `leads_count` is a form-level
    metric available without `leads_retrieval`; `questions` is populated
    only when the caller requested that field."""
    return LeadgenForm(
        id=str(body["id"]),
        name=body.get("name"),
        status=body.get("status"),
        locale=body.get("locale"),
        leads_count=_safe_int(body.get("leads_count")),
        created_time=parse_graph_datetime(body.get("created_time")),
        page_id=body.get("_page_id"),
        questions=[
            leadgen_question_from_body(q)
            for q in (body.get("questions") or [])
            if isinstance(q, dict)
        ],
    )


def page_subscription_from_body(body: dict[str, Any]) -> PageSubscription:
    """Map one row of `GET /{page_id}/subscribed_apps` to
    `PageSubscription`. Reads the `_page_id` injected by the caller the
    same way `leadgen_form_from_body` reads it — Graph's row is
    per-app, not per-page, so it never carries the page id itself."""
    return PageSubscription(
        app_id=str(body["id"]),
        app_name=body.get("name"),
        page_id=body.get("_page_id"),
        subscribed_fields=[
            str(f) for f in (body.get("subscribed_fields") or []) if f
        ],
    )


def lead_from_body(body: dict[str, Any]) -> Lead:
    """Map one row of `{form_id}/leads` (or `{ad_id}/leads`) to `Lead`.
    Requires the `leads_retrieval` scope upstream — this mapper only
    shapes the already-fetched body. `field_data` is Graph's
    `[{name, values:[...]}, ...]` answer list."""
    return Lead(
        id=str(body["id"]),
        created_time=parse_graph_datetime(body.get("created_time")),
        form_id=body.get("form_id"),
        ad_id=body.get("ad_id"),
        ad_name=body.get("ad_name"),
        adset_id=body.get("adset_id"),
        adset_name=body.get("adset_name"),
        campaign_id=body.get("campaign_id"),
        campaign_name=body.get("campaign_name"),
        platform=body.get("platform"),
        is_organic=body.get("is_organic"),
        field_data=[
            LeadFieldEntry(
                name=fd.get("name"),
                values=[str(v) for v in (fd.get("values") or [])],
            )
            for fd in (body.get("field_data") or [])
            if isinstance(fd, dict)
        ],
    )


def ad_set_from_body(body: dict[str, Any]) -> AdSet:
    """Map one row of `GET act_{id}/adsets` to `AdSet`. `daily_budget`
    arrives as a Graph numeric-as-string field; coerced via
    `_safe_int` (`None` on a missing/unparseable value, never a
    silent 0)."""

    return AdSet(
        id=str(body["id"]),
        name=body.get("name"),
        status=body.get("status"),
        effective_status=body.get("effective_status"),
        campaign_id=body.get("campaign_id"),
        daily_budget=_safe_int(body.get("daily_budget")),
        billing_event=body.get("billing_event"),
        optimization_goal=body.get("optimization_goal"),
        targeting=dict(body.get("targeting") or {}),
    )


def ad_from_body(body: dict[str, Any]) -> Ad:
    """Map one row of `GET act_{id}/ads` to `Ad`. `creative` is the
    nested `creative{id,thumbnail_url,object_story_spec}` expansion
    `list_ads` requests — flattened here onto `creative_id` /
    `creative_thumbnail_url` / `creative_object_story_spec`."""

    creative = body.get("creative")
    creative = creative if isinstance(creative, dict) else {}
    return Ad(
        id=str(body["id"]),
        name=body.get("name"),
        status=body.get("status"),
        effective_status=body.get("effective_status"),
        adset_id=body.get("adset_id"),
        creative_id=creative.get("id"),
        creative_thumbnail_url=creative.get("thumbnail_url"),
        creative_object_story_spec=dict(
            creative.get("object_story_spec") or {}
        ),
    )


def _actions_to_metrics(actions: Any) -> dict[str, float]:
    """Fold Graph's `actions` / `action_values` shape — a list of
    `{"action_type": str, "value": str}` rows — into a
    `{action_type: float}` map.

    THE fix for gap #4: the old single-row flatten tried
    `float(row["actions"])` directly on the raw list, which always
    raises `TypeError` and was silently `continue`d past — every
    conversion metric vanished with no error. This function instead
    walks the list and converts each row's own `value`."""

    result: dict[str, float] = {}
    if not isinstance(actions, list):
        return result
    for item in actions:
        if not isinstance(item, dict):
            continue
        action_type = item.get("action_type")
        if not action_type:
            continue
        try:
            result[str(action_type)] = float(item.get("value"))
        except (TypeError, ValueError):
            continue
    return result


def ad_insights_row_from_body(
    row: dict[str, Any], *, breakdown_keys: list[str] | None = None
) -> AdInsightsRow:
    """Map ONE row of `GET /{object-id}/insights` `data` to
    `AdInsightsRow` — the per-row twin of `insights_from_body` above,
    used by `ad_insights_series` to preserve every row (not just the
    first, see `AdInsightsRow`'s docstring).

    `breakdown_keys` — the `breakdowns` dimension names the caller
    requested (e.g. `["publisher_platform"]`) — are pulled off the row
    into `breakdown` rather than left to fall into `metrics` (their
    values are dimension labels, e.g. `"instagram"`, not numbers, so a
    plain `float()` flatten would silently drop them anyway; here
    they're explicitly preserved instead)."""

    if not isinstance(row, dict):
        row = {}
    breakdown_names = set(breakdown_keys or [])
    breakdown = {k: row[k] for k in breakdown_names if k in row}
    excluded = breakdown_names | {
        "date_start", "date_stop", "actions", "action_values",
    }
    metrics: dict[str, float] = {}
    for key, val in row.items():
        if key in excluded:
            continue
        try:
            metrics[key] = float(val)
        except (TypeError, ValueError):
            continue
    return AdInsightsRow(
        date_start=row.get("date_start"),
        date_stop=row.get("date_stop"),
        breakdown=breakdown,
        metrics=metrics,
        actions=_actions_to_metrics(row.get("actions")),
        action_values=_actions_to_metrics(row.get("action_values")),
        raw=dict(row),
    )


def ad_activity_from_body(body: dict[str, Any]) -> AdActivity:
    """Map one row of `GET act_{id}/activities` to `AdActivity`.

    `extra_data` arrives as a JSON-ENCODED STRING (not a nested
    object) on the live edge; parsed here and, when it carries an
    `old_value`/`new_value` pair (status-flip / budget-change event
    types), those are lifted onto the typed fields — see
    `AdActivity`'s docstring for why other event types leave them
    `None` while still preserving the parsed dict on `raw`.

    `id` — Graph does not return a stable row id on this edge (it's
    an audit log, not a Graph node); a locally-synthesized composite
    key is used instead. See `AdActivity`'s docstring — this is
    asserted from documentation, not confirmed live (`ads_read` not
    yet granted)."""

    extra_raw = body.get("extra_data")
    extra: dict[str, Any] = {}
    if isinstance(extra_raw, str) and extra_raw:
        try:
            parsed = json.loads(extra_raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            extra = parsed
    elif isinstance(extra_raw, dict):
        extra = extra_raw

    row_id = body.get("id")
    if not row_id:
        row_id = (
            f"{body.get('object_id')}:{body.get('event_time')}:"
            f"{body.get('event_type')}"
        )

    return AdActivity(
        id=str(row_id),
        object_id=body.get("object_id"),
        object_level=body.get("object_type"),
        event_type=body.get("event_type") or body.get("translated_event_type"),
        occurred_at=parse_graph_datetime(body.get("event_time")),
        actor_name=body.get("actor_name"),
        actor_id=body.get("actor_id"),
        old_value=extra.get("old_value"),
        new_value=extra.get("new_value"),
        raw=dict(body),
    )


__all__ = [
    "FB_COMMENT_FIELDS",
    "IG_ACCOUNT_FIELDS",
    "IG_ACCOUNT_INSIGHT_METRICS",
    "IG_COMMENT_FIELDS",
    "IG_CONVERSATION_FIELDS",
    "IG_DM_FIELDS",
    "IG_MEDIA_FIELDS",
    "IG_MEDIA_INSIGHT_METRICS",
    "ME_FIELDS",
    "PAGE_FIELDS",
    "PAGE_IG_FIELD",
    "PAGE_INSIGHT_METRICS",
    "POST_FIELDS",
    "POST_INSIGHT_METRICS",
    "ad_account_from_body",
    "ad_activity_from_body",
    "ad_from_body",
    "ad_insights_row_from_body",
    "ad_set_from_body",
    "campaign_from_body",
    "conversation_from_body",
    "direct_message_from_body",
    "facebook_comment_from_body",
    "ig_account_from_body",
    "ig_media_from_body",
    "instagram_comment_from_body",
    "insights_from_body",
    "lead_from_body",
    "leadgen_form_from_body",
    "leadgen_question_from_body",
    "page_from_body",
    "parse_graph_datetime",
    "post_from_body",
]
