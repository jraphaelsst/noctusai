"""In-memory deterministic Mailchimp client for dev + tests.

Satisfies the ``MailchimpClient`` Protocol structurally.  Seeds one
audience ``"fake-audience-1"`` on construction; all entity ids are
deterministic sequential integers / short strings so tests can assert
exact values.

Lifecycle semantics that mirror the real API:
- ``upsert_member``: creates or updates; ``status_if_new`` applied only
  for new members.
- ``archive_member``: sets ``status = "archived"`` (member stays in
  the store — real Mailchimp keeps archived members).
- ``add_segment_member``: raises ``MailchimpRejectedError`` when the
  email is not present in the audience (real-API parity).
- ``send_campaign``: flips campaign status ``"save"`` → ``"sent"``
  (one-shot; subsequent calls leave it ``"sent"``).
- ``schedule_campaign``: flips to ``"schedule"``.
- ``unschedule_campaign``: reverts to ``"save"``.

Use ``client.members["fake-audience-1"]`` etc. to inspect or seed state
in tests.

Same shape as ``FakeCalendarAdapter`` and ``FakeWahaClient`` per
``KB § PATTERNS/seed-fake-real-adapter.md``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from noctusai_lib.integrations.mailchimp.mappers import subscriber_hash, template_edit_url
from noctusai_lib.integrations.mailchimp.types import (
    Audience,
    Campaign,
    MailchimpNotFoundError,
    MailchimpRejectedError,
    Member,
    Page,
    Segment,
    Template,
)

_FAKE_SERVER_PREFIX = "us1"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


class FakeMailchimpClient:
    """In-memory Mailchimp stand-in.  Records state in plain dicts;
    all operations return the correct Protocol shapes.

    Test pattern::

        client = FakeMailchimpClient()
        await client.upsert_member("fake-audience-1", "alice@example.com")
        page = await client.list_members("fake-audience-1")
        assert page.items[0].email == "alice@example.com"
    """

    def __init__(self) -> None:
        # audiences: {audience_id: Audience}
        self.audiences: dict[str, Audience] = {
            "fake-audience-1": Audience(
                id="fake-audience-1",
                name="Fake Audience",
                member_count=0,
                raw={"id": "fake-audience-1", "name": "Fake Audience", "stats": {"member_count": 0}},
            )
        }
        # members: {audience_id: {email: Member}}
        self.members: dict[str, dict[str, Member]] = {
            "fake-audience-1": {}
        }
        # segments: {audience_id: {segment_id: Segment}}
        self.segments: dict[str, dict[int, Segment]] = {
            "fake-audience-1": {}
        }
        # segment_members: {audience_id: {segment_id: set[email]}}
        self.segment_members: dict[str, dict[int, set[str]]] = {
            "fake-audience-1": {}
        }
        # templates: {template_id: Template}
        self.templates: dict[int, Template] = {}
        # campaigns: {campaign_id: Campaign}
        self.campaigns: dict[str, Campaign] = {}

        self._next_segment_id = 1
        self._next_template_id = 1
        self._next_campaign_serial = 1

    # ------------------------------------------------------------------
    # Connectivity
    # ------------------------------------------------------------------

    async def ping(self) -> dict[str, Any]:
        return {"health_status": "Everything's Chimpy!"}

    # ------------------------------------------------------------------
    # Audiences
    # ------------------------------------------------------------------

    async def list_audiences(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Audience]:
        items = list(self.audiences.values())
        sliced = items[offset: offset + count]
        return Page(items=sliced, total=len(items))

    async def get_audience(self, audience_id: str) -> Audience:
        if audience_id not in self.audiences:
            raise MailchimpNotFoundError(
                f"Audience {audience_id!r} not found", status=404
            )
        return self.audiences[audience_id]

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
        self._require_audience(audience_id)
        all_members = list(self.members[audience_id].values())
        if status:
            all_members = [m for m in all_members if m.status == status]
        sliced = all_members[offset: offset + count]
        return Page(items=sliced, total=len(all_members))

    async def get_member(self, audience_id: str, email: str) -> Member:
        self._require_audience(audience_id)
        key = email.strip().lower()
        member = self.members[audience_id].get(key)
        if member is None:
            raise MailchimpNotFoundError(
                f"Member {email!r} not found in audience {audience_id!r}", status=404
            )
        return member

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
        self._require_audience(audience_id)
        key = email.strip().lower()
        existing = self.members[audience_id].get(key)
        effective_status = status if existing else status_if_new
        member = Member(
            email=email,
            status=effective_status,
            first_name=first_name,
            last_name=last_name,
            tags=list(existing.tags) if existing else [],
            vip=existing.vip if existing else False,
            last_changed=_now(),
            raw={
                "email_address": email,
                "status": effective_status,
                "merge_fields": {"FNAME": first_name, "LNAME": last_name},
                "tags": [],
                "vip": False,
            },
        )
        self.members[audience_id][key] = member
        self._sync_audience_count(audience_id)
        return member

    async def set_member_tags(
        self,
        audience_id: str,
        email: str,
        *,
        active_tags: list[str],
        inactive_tags: list[str] | None = None,
    ) -> None:
        self._require_audience(audience_id)
        key = email.strip().lower()
        existing = self.members[audience_id].get(key)
        if existing is None:
            raise MailchimpNotFoundError(
                f"Member {email!r} not found in audience {audience_id!r}", status=404
            )
        current_tags: set[str] = set(existing.tags)
        current_tags.update(active_tags)
        if inactive_tags:
            current_tags.difference_update(inactive_tags)
        updated = Member(
            email=existing.email,
            status=existing.status,
            first_name=existing.first_name,
            last_name=existing.last_name,
            tags=sorted(current_tags),
            vip=existing.vip,
            last_changed=_now(),
            raw={**existing.raw, "tags": [{"name": t} for t in sorted(current_tags)]},
        )
        self.members[audience_id][key] = updated

    async def archive_member(self, audience_id: str, email: str) -> None:
        self._require_audience(audience_id)
        key = email.strip().lower()
        existing = self.members[audience_id].get(key)
        if existing is None:
            raise MailchimpNotFoundError(
                f"Member {email!r} not found", status=404
            )
        archived = Member(
            email=existing.email,
            status="archived",
            first_name=existing.first_name,
            last_name=existing.last_name,
            tags=existing.tags,
            vip=existing.vip,
            last_changed=_now(),
            raw={**existing.raw, "status": "archived"},
        )
        self.members[audience_id][key] = archived
        self._sync_audience_count(audience_id)

    # ------------------------------------------------------------------
    # Segments
    # ------------------------------------------------------------------

    async def list_segments(
        self, audience_id: str, *, count: int = 25, offset: int = 0
    ) -> Page[Segment]:
        self._require_audience(audience_id)
        items = list(self.segments[audience_id].values())
        sliced = items[offset: offset + count]
        return Page(items=sliced, total=len(items))

    async def create_static_segment(
        self, audience_id: str, *, name: str
    ) -> Segment:
        self._require_audience(audience_id)
        seg_id = self._next_segment_id
        self._next_segment_id += 1
        now = _now()
        segment = Segment(
            id=seg_id,
            name=name,
            member_count=0,
            created_at=now,
            updated_at=now,
            raw={"id": seg_id, "name": name, "member_count": 0},
        )
        self.segments[audience_id][seg_id] = segment
        self.segment_members[audience_id][seg_id] = set()
        return segment

    async def update_segment(
        self, audience_id: str, segment_id: int, *, name: str
    ) -> Segment:
        self._require_segment(audience_id, segment_id)
        existing = self.segments[audience_id][segment_id]
        updated = Segment(
            id=existing.id,
            name=name,
            member_count=existing.member_count,
            created_at=existing.created_at,
            updated_at=_now(),
            raw={**existing.raw, "name": name},
        )
        self.segments[audience_id][segment_id] = updated
        return updated

    async def delete_segment(self, audience_id: str, segment_id: int) -> None:
        self._require_segment(audience_id, segment_id)
        del self.segments[audience_id][segment_id]
        self.segment_members[audience_id].pop(segment_id, None)

    async def list_segment_members(
        self, audience_id: str, segment_id: int, *, count: int = 25, offset: int = 0
    ) -> Page[Member]:
        self._require_segment(audience_id, segment_id)
        emails = list(self.segment_members[audience_id][segment_id])
        all_members = [
            self.members[audience_id][e]
            for e in emails
            if e in self.members[audience_id]
        ]
        sliced = all_members[offset: offset + count]
        return Page(items=sliced, total=len(all_members))

    async def add_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        self._require_segment(audience_id, segment_id)
        key = email.strip().lower()
        # Real API parity: email must be a subscribed/active audience member.
        audience_member = self.members[audience_id].get(key)
        if audience_member is None or audience_member.status not in (
            "subscribed", "pending", "unsubscribed"
        ):
            raise MailchimpRejectedError(
                f"Email {email!r} is not a member of audience {audience_id!r}. "
                "Create the contact first.",
                status=400,
                detail=f"{email} is not subscribed to list {audience_id}.",
            )
        self.segment_members[audience_id][segment_id].add(key)
        # Update segment member_count.
        existing = self.segments[audience_id][segment_id]
        self.segments[audience_id][segment_id] = Segment(
            id=existing.id,
            name=existing.name,
            member_count=len(self.segment_members[audience_id][segment_id]),
            created_at=existing.created_at,
            updated_at=_now(),
            raw=existing.raw,
        )

    async def remove_segment_member(
        self, audience_id: str, segment_id: int, email: str
    ) -> None:
        self._require_segment(audience_id, segment_id)
        key = email.strip().lower()
        self.segment_members[audience_id][segment_id].discard(key)
        existing = self.segments[audience_id][segment_id]
        self.segments[audience_id][segment_id] = Segment(
            id=existing.id,
            name=existing.name,
            member_count=len(self.segment_members[audience_id][segment_id]),
            created_at=existing.created_at,
            updated_at=_now(),
            raw=existing.raw,
        )

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    async def list_templates(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Template]:
        items = list(self.templates.values())
        sliced = items[offset: offset + count]
        return Page(items=sliced, total=len(items))

    async def get_template(self, template_id: int) -> Template:
        if template_id not in self.templates:
            raise MailchimpNotFoundError(
                f"Template {template_id} not found", status=404
            )
        return self.templates[template_id]

    async def create_template(self, *, name: str, html: str) -> Template:
        tid = self._next_template_id
        self._next_template_id += 1
        now = _now()
        tmpl = Template(
            id=tid,
            name=name,
            category="",
            type="user",
            drag_and_drop=False,
            preview_image="",
            date_created=now,
            date_edited=now,
            edit_url=template_edit_url(_FAKE_SERVER_PREFIX, tid),
            raw={"id": tid, "name": name, "type": "user", "drag_and_drop": False},
        )
        self.templates[tid] = tmpl
        return tmpl

    async def update_template(
        self, template_id: int, *, name: str | None = None, html: str | None = None
    ) -> Template:
        if template_id not in self.templates:
            raise MailchimpNotFoundError(
                f"Template {template_id} not found", status=404
            )
        existing = self.templates[template_id]
        updated = Template(
            id=existing.id,
            name=name if name is not None else existing.name,
            category=existing.category,
            type=existing.type,
            drag_and_drop=existing.drag_and_drop,
            preview_image=existing.preview_image,
            date_created=existing.date_created,
            date_edited=_now(),
            edit_url=existing.edit_url,
            raw={**existing.raw, **({"name": name} if name else {})},
        )
        self.templates[template_id] = updated
        return updated

    async def delete_template(self, template_id: int) -> None:
        if template_id not in self.templates:
            raise MailchimpNotFoundError(
                f"Template {template_id} not found", status=404
            )
        del self.templates[template_id]

    async def get_template_default_content(self, template_id: int) -> dict[str, Any]:
        if template_id not in self.templates:
            raise MailchimpNotFoundError(
                f"Template {template_id} not found", status=404
            )
        return {"sections": {}, "archive_html": ""}

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    async def list_campaigns(
        self, *, count: int = 25, offset: int = 0
    ) -> Page[Campaign]:
        items = list(self.campaigns.values())
        sliced = items[offset: offset + count]
        return Page(items=sliced, total=len(items))

    async def get_campaign(self, campaign_id: str) -> Campaign:
        if campaign_id not in self.campaigns:
            raise MailchimpNotFoundError(
                f"Campaign {campaign_id!r} not found", status=404
            )
        return self.campaigns[campaign_id]

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
        cid = f"fake-campaign-{self._next_campaign_serial}"
        self._next_campaign_serial += 1
        now = _now()
        campaign = Campaign(
            id=cid,
            web_id=self._next_campaign_serial,
            title=title,
            status="save",
            subject_line=subject_line,
            preview_text=preview_text,
            from_name=from_name,
            reply_to=reply_to,
            segment_id=segment_id,
            template_id=template_id,
            send_time=None,
            create_time=now,
            emails_sent=None,
            opens=None,
            clicks=None,
            archive_url="",
            raw={
                "id": cid,
                "status": "save",
                "settings": {
                    "title": title,
                    "subject_line": subject_line,
                    "preview_text": preview_text,
                    "from_name": from_name,
                    "reply_to": reply_to,
                    "template_id": template_id,
                },
                "recipients": {
                    "list_id": audience_id,
                    **(
                        {"segment_opts": {"saved_segment_id": segment_id}}
                        if segment_id is not None
                        else {}
                    ),
                },
            },
        )
        self.campaigns[cid] = campaign
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
        existing = await self.get_campaign(campaign_id)
        updated = Campaign(
            id=existing.id,
            web_id=existing.web_id,
            title=title if title is not None else existing.title,
            status=existing.status,
            subject_line=subject_line if subject_line is not None else existing.subject_line,
            preview_text=preview_text if preview_text is not None else existing.preview_text,
            from_name=from_name if from_name is not None else existing.from_name,
            reply_to=reply_to if reply_to is not None else existing.reply_to,
            segment_id=segment_id if segment_id is not None else existing.segment_id,
            template_id=template_id if template_id is not None else existing.template_id,
            send_time=existing.send_time,
            create_time=existing.create_time,
            emails_sent=existing.emails_sent,
            opens=existing.opens,
            clicks=existing.clicks,
            archive_url=existing.archive_url,
            raw=existing.raw,
        )
        self.campaigns[campaign_id] = updated
        return updated

    async def delete_campaign(self, campaign_id: str) -> None:
        if campaign_id not in self.campaigns:
            raise MailchimpNotFoundError(
                f"Campaign {campaign_id!r} not found", status=404
            )
        del self.campaigns[campaign_id]

    async def set_campaign_content(
        self, campaign_id: str, *, template_id: int | None = None
    ) -> dict[str, Any]:
        # Fake: just update template_id if given.
        if template_id is not None:
            existing = await self.get_campaign(campaign_id)
            updated = Campaign(
                id=existing.id,
                web_id=existing.web_id,
                title=existing.title,
                status=existing.status,
                subject_line=existing.subject_line,
                preview_text=existing.preview_text,
                from_name=existing.from_name,
                reply_to=existing.reply_to,
                segment_id=existing.segment_id,
                template_id=template_id,
                send_time=existing.send_time,
                create_time=existing.create_time,
                emails_sent=existing.emails_sent,
                opens=existing.opens,
                clicks=existing.clicks,
                archive_url=existing.archive_url,
                raw=existing.raw,
            )
            self.campaigns[campaign_id] = updated
        return {}

    async def send_campaign(self, campaign_id: str) -> Campaign:
        existing = await self.get_campaign(campaign_id)
        now = _now()
        sent = Campaign(
            id=existing.id,
            web_id=existing.web_id,
            title=existing.title,
            status="sent",
            subject_line=existing.subject_line,
            preview_text=existing.preview_text,
            from_name=existing.from_name,
            reply_to=existing.reply_to,
            segment_id=existing.segment_id,
            template_id=existing.template_id,
            send_time=now,
            create_time=existing.create_time,
            emails_sent=0,
            opens=0,
            clicks=0,
            archive_url=f"https://mailchi.mp/fake/{campaign_id}",
            raw={**existing.raw, "status": "sent", "send_time": now.isoformat()},
        )
        self.campaigns[campaign_id] = sent
        return sent

    async def schedule_campaign(
        self, campaign_id: str, *, schedule_time: str
    ) -> Campaign:
        existing = await self.get_campaign(campaign_id)
        scheduled = Campaign(
            id=existing.id,
            web_id=existing.web_id,
            title=existing.title,
            status="schedule",
            subject_line=existing.subject_line,
            preview_text=existing.preview_text,
            from_name=existing.from_name,
            reply_to=existing.reply_to,
            segment_id=existing.segment_id,
            template_id=existing.template_id,
            send_time=existing.send_time,
            create_time=existing.create_time,
            emails_sent=existing.emails_sent,
            opens=existing.opens,
            clicks=existing.clicks,
            archive_url=existing.archive_url,
            raw={**existing.raw, "status": "schedule"},
        )
        self.campaigns[campaign_id] = scheduled
        return scheduled

    async def unschedule_campaign(self, campaign_id: str) -> Campaign:
        existing = await self.get_campaign(campaign_id)
        unscheduled = Campaign(
            id=existing.id,
            web_id=existing.web_id,
            title=existing.title,
            status="save",
            subject_line=existing.subject_line,
            preview_text=existing.preview_text,
            from_name=existing.from_name,
            reply_to=existing.reply_to,
            segment_id=existing.segment_id,
            template_id=existing.template_id,
            send_time=None,
            create_time=existing.create_time,
            emails_sent=existing.emails_sent,
            opens=existing.opens,
            clicks=existing.clicks,
            archive_url=existing.archive_url,
            raw={**existing.raw, "status": "save"},
        )
        self.campaigns[campaign_id] = unscheduled
        return unscheduled

    async def send_test(
        self, campaign_id: str, *, test_emails: list[str]
    ) -> dict[str, Any]:
        # Validate campaign exists.
        await self.get_campaign(campaign_id)
        return {"ok": True}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_audience(self, audience_id: str) -> None:
        if audience_id not in self.audiences:
            raise MailchimpNotFoundError(
                f"Audience {audience_id!r} not found", status=404
            )
        # Ensure sub-dicts exist (handles newly added audiences).
        self.members.setdefault(audience_id, {})
        self.segments.setdefault(audience_id, {})
        self.segment_members.setdefault(audience_id, {})

    def _require_segment(self, audience_id: str, segment_id: int) -> None:
        self._require_audience(audience_id)
        if segment_id not in self.segments[audience_id]:
            raise MailchimpNotFoundError(
                f"Segment {segment_id} not found in audience {audience_id!r}", status=404
            )

    def _sync_audience_count(self, audience_id: str) -> None:
        """Recompute member_count for the audience (excludes archived)."""
        active_count = sum(
            1
            for m in self.members[audience_id].values()
            if m.status != "archived"
        )
        existing = self.audiences[audience_id]
        self.audiences[audience_id] = Audience(
            id=existing.id,
            name=existing.name,
            member_count=active_count,
            raw={**existing.raw, "stats": {"member_count": active_count}},
        )
