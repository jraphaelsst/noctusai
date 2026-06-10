"""HttpxMailchimpClient — real Mailchimp Marketing API v3 adapter.

Uses plain ``httpx.AsyncClient`` with HTTP Basic auth
(username = any string, password = API key) as per the Mailchimp docs.
The base URL is ``https://{dc}.api.mailchimp.com/3.0`` where ``dc`` is
parsed from the key suffix via ``parse_server_prefix``.

Error mapping:
- 401 / 403  → ``MailchimpAuthError``
- 404        → ``MailchimpNotFoundError``
- 429        → ``MailchimpRateLimitedError``
- 400 / 422  → ``MailchimpRejectedError`` (title + detail from body)
- 5xx / network / TLS  → ``MailchimpUnreachableError``

A single ``_request()`` method encapsulates the error mapping; every
public method calls it.  Transport-level exceptions (``httpx.TransportError``,
``httpx.TimeoutException``) are caught and re-raised as
``MailchimpUnreachableError``.
"""

from __future__ import annotations

from typing import Any

import httpx

from noctusai_lib.integrations.mailchimp.mappers import (
    parse_server_prefix,
    raw_to_audience,
    raw_to_campaign,
    raw_to_member,
    raw_to_segment,
    raw_to_template,
    subscriber_hash,
    template_edit_url,
)
from noctusai_lib.integrations.mailchimp.types import (
    Audience,
    Campaign,
    MailchimpAuthError,
    MailchimpError,
    MailchimpNotFoundError,
    MailchimpRateLimitedError,
    MailchimpRejectedError,
    MailchimpUnreachableError,
    Member,
    Page,
    Segment,
    Template,
)


class HttpxMailchimpClient:
    """Real Mailchimp Marketing API v3 client backed by ``httpx.AsyncClient``.

    Instantiate via the ``get_mailchimp_client(api_key, server_prefix=...)``
    factory; don't construct directly in product code.

    Thread-safety: the underlying ``httpx.AsyncClient`` is not
    thread-safe; use one instance per request or per coroutine chain.
    """

    def __init__(self, api_key: str, *, server_prefix: str) -> None:
        self._api_key = api_key
        self._server_prefix = server_prefix
        self._base_url = f"https://{server_prefix}.api.mailchimp.com/3.0"

    # ------------------------------------------------------------------
    # Internal HTTP primitive
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        body_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """Execute one authenticated request and return the parsed JSON body.

        Empty 2xx responses (e.g. DELETE 204) return ``{}``.
        All non-2xx responses are translated to the error hierarchy.
        """
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient() as http:
                kwargs: dict[str, Any] = {
                    "auth": ("anystring", self._api_key),
                    "params": params,
                }
                if body_bytes is not None:
                    kwargs["content"] = body_bytes
                    kwargs["headers"] = {"Content-Type": "application/json"}
                elif json is not None:
                    kwargs["json"] = json

                response = await http.request(method, url, **kwargs)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            raise MailchimpUnreachableError(
                str(exc), status=0
            ) from exc

        return self._translate(response)

    @staticmethod
    def _translate(response: httpx.Response) -> dict[str, Any]:
        """Map an httpx Response to a dict or raise the appropriate error."""
        status = response.status_code

        if status in (200, 201, 204) or (200 <= status < 300):
            # 204 No Content — empty body; other 2xx return JSON.
            body = response.content
            if not body or not body.strip():
                return {}
            try:
                parsed = response.json()
            except ValueError:
                return {}
            return parsed if isinstance(parsed, dict) else {"raw": parsed}

        # Parse problem+json title/detail for structured errors.
        title = ""
        detail = ""
        try:
            err_body = response.json()
            if isinstance(err_body, dict):
                title = err_body.get("title", "")
                detail = err_body.get("detail", "")
        except ValueError:
            pass

        message = detail or title or f"HTTP {status}"

        if status in (401, 403):
            raise MailchimpAuthError(message, status=status, title=title, detail=detail)
        if status == 404:
            raise MailchimpNotFoundError(message, status=status, title=title, detail=detail)
        if status == 429:
            raise MailchimpRateLimitedError(message, status=status, title=title, detail=detail)
        if status in (400, 422):
            raise MailchimpRejectedError(message, status=status, title=title, detail=detail)
        if status >= 500:
            raise MailchimpUnreachableError(message, status=status, title=title, detail=detail)

        # Unexpected 3xx / other — wrap generically.
        raise MailchimpError(message, status=status, title=title, detail=detail)

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    async def ping(self) -> dict[str, Any]:
        return await self._request("GET", "/ping")

    # ------------------------------------------------------------------
    # Audiences
    # ------------------------------------------------------------------

    async def list_audiences(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Audience]:
        data = await self._request(
            "GET", "/lists", params={"count": count, "offset": offset}
        )
        return Page(
            items=[raw_to_audience(a) for a in data.get("lists", [])],
            total=data.get("total_items", 0),
            raw=data,
        )

    async def get_audience(self, audience_id: str) -> Audience:
        data = await self._request("GET", f"/lists/{audience_id}")
        return raw_to_audience(data)

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def list_members(
        self,
        audience_id: str,
        *,
        status: str | None = None,
        count: int = 25,
        offset: int = 0,
    ) -> Page[Member]:
        params: dict[str, Any] = {"count": count, "offset": offset}
        if status:
            params["status"] = status
        data = await self._request(
            "GET", f"/lists/{audience_id}/members", params=params
        )
        return Page(
            items=[raw_to_member(m) for m in data.get("members", [])],
            total=data.get("total_items", 0),
            raw=data,
        )

    async def get_member(self, audience_id: str, email: str) -> Member:
        h = subscriber_hash(email)
        data = await self._request("GET", f"/lists/{audience_id}/members/{h}")
        return raw_to_member(data)

    async def upsert_member(
        self,
        audience_id: str,
        email: str,
        *,
        status: str = "subscribed",
        first_name: str = "",
        last_name: str = "",
        status_if_new: str = "subscribed",
    ) -> Member:
        h = subscriber_hash(email)
        payload: dict[str, Any] = {
            "email_address": email,
            "status": status,
            "status_if_new": status_if_new,
            "merge_fields": {"FNAME": first_name, "LNAME": last_name},
        }
        data = await self._request(
            "PUT", f"/lists/{audience_id}/members/{h}", json=payload
        )
        return raw_to_member(data)

    async def set_member_tags(
        self,
        audience_id: str,
        email: str,
        *,
        active_tags: list[str],
        inactive_tags: list[str] | None = None,
    ) -> None:
        h = subscriber_hash(email)
        tags_payload: list[dict[str, str]] = [
            {"name": t, "status": "active"} for t in active_tags
        ]
        if inactive_tags:
            tags_payload.extend(
                {"name": t, "status": "inactive"} for t in inactive_tags
            )
        await self._request(
            "POST",
            f"/lists/{audience_id}/members/{h}/tags",
            json={"tags": tags_payload},
        )

    async def archive_member(self, audience_id: str, email: str) -> None:
        h = subscriber_hash(email)
        await self._request("DELETE", f"/lists/{audience_id}/members/{h}")

    # ------------------------------------------------------------------
    # Segments
    # ------------------------------------------------------------------

    async def list_segments(
        self, audience_id: str, *, count: int = 25, offset: int = 0
    ) -> Page[Segment]:
        data = await self._request(
            "GET",
            f"/lists/{audience_id}/segments",
            params={"count": count, "offset": offset},
        )
        return Page(
            items=[raw_to_segment(s) for s in data.get("segments", [])],
            total=data.get("total_items", 0),
            raw=data,
        )

    async def create_static_segment(
        self, audience_id: str, *, name: str
    ) -> Segment:
        data = await self._request(
            "POST",
            f"/lists/{audience_id}/segments",
            json={"name": name, "static_segment": [], "options": {"match": "any", "conditions": []}},
        )
        return raw_to_segment(data)

    async def update_segment(
        self, audience_id: str, segment_id: int, *, name: str
    ) -> Segment:
        data = await self._request(
            "PATCH",
            f"/lists/{audience_id}/segments/{segment_id}",
            json={"name": name},
        )
        return raw_to_segment(data)

    async def delete_segment(self, audience_id: str, segment_id: int) -> None:
        await self._request("DELETE", f"/lists/{audience_id}/segments/{segment_id}")

    async def list_segment_members(
        self, audience_id: str, segment_id: int, *, count: int = 25, offset: int = 0
    ) -> Page[Member]:
        data = await self._request(
            "GET",
            f"/lists/{audience_id}/segments/{segment_id}/members",
            params={"count": count, "offset": offset},
        )
        return Page(
            items=[raw_to_member(m) for m in data.get("members", [])],
            total=data.get("total_items", 0),
            raw=data,
        )

    async def add_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        await self._request(
            "POST",
            f"/lists/{audience_id}/segments/{segment_id}/members",
            json={"email_address": email},
        )

    async def remove_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        h = subscriber_hash(email)
        await self._request(
            "DELETE",
            f"/lists/{audience_id}/segments/{segment_id}/members/{h}",
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    async def list_templates(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Template]:
        data = await self._request(
            "GET",
            "/templates",
            params={"type": "user", "count": count, "offset": offset},
        )
        return Page(
            items=[
                raw_to_template(t, server_prefix=self._server_prefix)
                for t in data.get("templates", [])
            ],
            total=data.get("total_items", 0),
            raw=data,
        )

    async def get_template(self, template_id: int) -> Template:
        data = await self._request("GET", f"/templates/{template_id}")
        return raw_to_template(data, server_prefix=self._server_prefix)

    async def create_template(self, *, name: str, html: str) -> Template:
        data = await self._request(
            "POST", "/templates", json={"name": name, "html": html}
        )
        return raw_to_template(data, server_prefix=self._server_prefix)

    async def update_template(
        self, template_id: int, *, name: str | None = None, html: str | None = None
    ) -> Template:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if html is not None:
            payload["html"] = html
        data = await self._request(
            "PATCH", f"/templates/{template_id}", json=payload
        )
        return raw_to_template(data, server_prefix=self._server_prefix)

    async def delete_template(self, template_id: int) -> None:
        await self._request("DELETE", f"/templates/{template_id}")

    async def get_template_default_content(self, template_id: int) -> dict[str, Any]:
        return await self._request("GET", f"/templates/{template_id}/default-content")

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    async def list_campaigns(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Campaign]:
        data = await self._request(
            "GET", "/campaigns", params={"count": count, "offset": offset}
        )
        return Page(
            items=[raw_to_campaign(c) for c in data.get("campaigns", [])],
            total=data.get("total_items", 0),
            raw=data,
        )

    async def get_campaign(self, campaign_id: str) -> Campaign:
        data = await self._request("GET", f"/campaigns/{campaign_id}")
        return raw_to_campaign(data)

    async def create_campaign(
        self,
        *,
        title: str,
        subject_line: str,
        preview_text: str = "",
        from_name: str,
        reply_to: str,
        audience_id: str,
        segment_id: int | None = None,
        template_id: int | None = None,
    ) -> Campaign:
        recipients: dict[str, Any] = {"list_id": audience_id}
        if segment_id is not None:
            recipients["segment_opts"] = {"saved_segment_id": segment_id}

        payload: dict[str, Any] = {
            "type": "regular",
            "recipients": recipients,
            "settings": {
                "title": title,
                "subject_line": subject_line,
                "preview_text": preview_text,
                "from_name": from_name,
                "reply_to": reply_to,
            },
        }
        data = await self._request("POST", "/campaigns", json=payload)
        campaign = raw_to_campaign(data)
        if template_id is not None:
            await self.set_campaign_content(campaign.id, template_id=template_id)
            # Re-read to get updated campaign with template_id in settings.
            campaign = await self.get_campaign(campaign.id)
        return campaign

    async def update_campaign(
        self,
        campaign_id: str,
        *,
        title: str | None = None,
        subject_line: str | None = None,
        preview_text: str | None = None,
        from_name: str | None = None,
        reply_to: str | None = None,
        segment_id: int | None = None,
        template_id: int | None = None,
    ) -> Campaign:
        settings: dict[str, Any] = {}
        if title is not None:
            settings["title"] = title
        if subject_line is not None:
            settings["subject_line"] = subject_line
        if preview_text is not None:
            settings["preview_text"] = preview_text
        if from_name is not None:
            settings["from_name"] = from_name
        if reply_to is not None:
            settings["reply_to"] = reply_to

        payload: dict[str, Any] = {}
        if settings:
            payload["settings"] = settings
        if segment_id is not None:
            payload["recipients"] = {
                "segment_opts": {"saved_segment_id": segment_id}
            }
        if template_id is not None:
            settings["template_id"] = template_id

        data = await self._request(
            "PATCH", f"/campaigns/{campaign_id}", json=payload
        )
        return raw_to_campaign(data)

    async def delete_campaign(self, campaign_id: str) -> None:
        await self._request("DELETE", f"/campaigns/{campaign_id}")

    async def set_campaign_content(
        self, campaign_id: str, *, template_id: int | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if template_id is not None:
            payload["template"] = {"id": template_id}
        return await self._request(
            "PUT", f"/campaigns/{campaign_id}/content", json=payload
        )

    async def send_campaign(self, campaign_id: str) -> Campaign:
        await self._request("POST", f"/campaigns/{campaign_id}/actions/send")
        return await self.get_campaign(campaign_id)

    async def schedule_campaign(
        self, campaign_id: str, *, schedule_time: str
    ) -> Campaign:
        await self._request(
            "POST",
            f"/campaigns/{campaign_id}/actions/schedule",
            json={"schedule_time": schedule_time},
        )
        return await self.get_campaign(campaign_id)

    async def unschedule_campaign(self, campaign_id: str) -> Campaign:
        await self._request(
            "POST", f"/campaigns/{campaign_id}/actions/unschedule"
        )
        return await self.get_campaign(campaign_id)

    async def send_test(
        self, campaign_id: str, *, test_emails: list[str]
    ) -> dict[str, Any]:
        await self._request(
            "POST",
            f"/campaigns/{campaign_id}/actions/test",
            json={"test_emails": test_emails, "send_type": "html"},
        )
        return {"ok": True}
