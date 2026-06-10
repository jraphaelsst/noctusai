"""Tests for FakeMailchimpClient + get_mailchimp_client factory.

Covers the full lifecycle of each resource (audiences, members, segments,
templates, campaigns) plus factory switching behaviour.

Pattern mirrors ``tests/integrations/whatsapp/test_fake_adapter.py`` and
``tests/integrations/google_calendar/test_fake_adapter.py``.
"""

from __future__ import annotations

import asyncio

import pytest

from noctusai_lib.integrations.mailchimp import (
    FakeMailchimpClient,
    HttpxMailchimpClient,
    MailchimpClient,
    MailchimpNotFoundError,
    MailchimpRejectedError,
    get_mailchimp_client,
)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_factory_returns_fake_when_no_key() -> None:
    client = get_mailchimp_client()
    assert isinstance(client, FakeMailchimpClient)


def test_factory_returns_fake_when_empty_string() -> None:
    client = get_mailchimp_client("")
    assert isinstance(client, FakeMailchimpClient)


def test_factory_returns_real_when_api_key_given() -> None:
    client = get_mailchimp_client("mykey-us6")
    assert isinstance(client, HttpxMailchimpClient)


def test_factory_accepts_explicit_server_prefix() -> None:
    client = get_mailchimp_client("mykey-us6", server_prefix="eu1")
    assert isinstance(client, HttpxMailchimpClient)
    # The explicitly supplied prefix is used, not parsed from key.
    assert client._server_prefix == "eu1"


def test_factory_raises_on_malformed_key() -> None:
    # No hyphen at all — no dc suffix
    with pytest.raises(ValueError, match="Malformed"):
        get_mailchimp_client("badkeywithoutsuffix")
    # Trailing hyphen only — empty dc suffix
    with pytest.raises(ValueError, match="Malformed"):
        get_mailchimp_client("mytoken-")


def test_protocol_satisfied_by_fake() -> None:
    client = get_mailchimp_client()
    assert isinstance(client, MailchimpClient)


# ---------------------------------------------------------------------------
# Connectivity
# ---------------------------------------------------------------------------


def test_ping_returns_health_status() -> None:
    client = FakeMailchimpClient()
    result = asyncio.run(client.ping())
    assert "health_status" in result


# ---------------------------------------------------------------------------
# Audiences
# ---------------------------------------------------------------------------


def test_list_audiences_returns_seeded_audience() -> None:
    client = FakeMailchimpClient()
    page = asyncio.run(client.list_audiences())
    assert page.total >= 1
    assert any(a.id == "fake-audience-1" for a in page.items)


def test_get_audience_by_id() -> None:
    client = FakeMailchimpClient()
    audience = asyncio.run(client.get_audience("fake-audience-1"))
    assert audience.id == "fake-audience-1"


def test_get_audience_not_found_raises() -> None:
    client = FakeMailchimpClient()
    with pytest.raises(MailchimpNotFoundError):
        asyncio.run(client.get_audience("nonexistent"))


# ---------------------------------------------------------------------------
# Members
# ---------------------------------------------------------------------------


def test_upsert_member_creates_new_member() -> None:
    client = FakeMailchimpClient()
    member = asyncio.run(
        client.upsert_member(
            "fake-audience-1",
            "alice@example.com",
            first_name="Alice",
            last_name="Smith",
        )
    )
    assert member.email == "alice@example.com"
    assert member.first_name == "Alice"
    assert member.status == "subscribed"


def test_upsert_member_updates_existing() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "bob@example.com", first_name="Bob"))
    updated = asyncio.run(
        client.upsert_member(
            "fake-audience-1", "bob@example.com", first_name="Bobby", last_name="Jones"
        )
    )
    assert updated.first_name == "Bobby"
    assert updated.last_name == "Jones"


def test_upsert_member_status_if_new_applied_only_for_new() -> None:
    client = FakeMailchimpClient()
    # First insert: status_if_new used.
    member = asyncio.run(
        client.upsert_member(
            "fake-audience-1",
            "carol@example.com",
            status_if_new="pending",
        )
    )
    assert member.status == "pending"

    # Update: status kwarg used, not status_if_new.
    updated = asyncio.run(
        client.upsert_member(
            "fake-audience-1",
            "carol@example.com",
            status="subscribed",
            status_if_new="pending",
        )
    )
    assert updated.status == "subscribed"


def test_get_member_after_upsert() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "dave@example.com"))
    fetched = asyncio.run(client.get_member("fake-audience-1", "dave@example.com"))
    assert fetched.email == "dave@example.com"


def test_get_member_not_found_raises() -> None:
    client = FakeMailchimpClient()
    with pytest.raises(MailchimpNotFoundError):
        asyncio.run(client.get_member("fake-audience-1", "nobody@example.com"))


def test_list_members_returns_upserted() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "e1@test.com"))
    asyncio.run(client.upsert_member("fake-audience-1", "e2@test.com"))
    page = asyncio.run(client.list_members("fake-audience-1"))
    emails = [m.email for m in page.items]
    assert "e1@test.com" in emails
    assert "e2@test.com" in emails
    assert page.total >= 2


def test_list_members_filter_by_status() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "sub@test.com", status="subscribed"))
    asyncio.run(client.upsert_member("fake-audience-1", "unsub@test.com", status="unsubscribed"))
    page = asyncio.run(client.list_members("fake-audience-1", status="subscribed"))
    assert all(m.status == "subscribed" for m in page.items)


def test_set_member_tags_adds_tags() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "tagged@test.com"))
    asyncio.run(
        client.set_member_tags(
            "fake-audience-1",
            "tagged@test.com",
            active_tags=["newsletter", "vip"],
        )
    )
    member = asyncio.run(client.get_member("fake-audience-1", "tagged@test.com"))
    assert "newsletter" in member.tags
    assert "vip" in member.tags


def test_set_member_tags_removes_inactive_tags() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "tagtest@test.com"))
    asyncio.run(
        client.set_member_tags(
            "fake-audience-1", "tagtest@test.com", active_tags=["a", "b"]
        )
    )
    asyncio.run(
        client.set_member_tags(
            "fake-audience-1",
            "tagtest@test.com",
            active_tags=[],
            inactive_tags=["a"],
        )
    )
    member = asyncio.run(client.get_member("fake-audience-1", "tagtest@test.com"))
    assert "a" not in member.tags
    assert "b" in member.tags


def test_archive_member_sets_status_archived() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "archive@test.com"))
    asyncio.run(client.archive_member("fake-audience-1", "archive@test.com"))
    member = asyncio.run(client.get_member("fake-audience-1", "archive@test.com"))
    assert member.status == "archived"


def test_archive_member_not_found_raises() -> None:
    client = FakeMailchimpClient()
    with pytest.raises(MailchimpNotFoundError):
        asyncio.run(client.archive_member("fake-audience-1", "ghost@test.com"))


def test_audience_member_count_reflects_active_members() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "a@test.com"))
    asyncio.run(client.upsert_member("fake-audience-1", "b@test.com"))
    asyncio.run(client.archive_member("fake-audience-1", "b@test.com"))
    audience = asyncio.run(client.get_audience("fake-audience-1"))
    assert audience.member_count == 1


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


def test_create_segment_returns_segment_with_id() -> None:
    client = FakeMailchimpClient()
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="VIPs"))
    assert seg.id >= 1
    assert seg.name == "VIPs"
    assert seg.member_count == 0


def test_list_segments_returns_created() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.create_static_segment("fake-audience-1", name="S1"))
    asyncio.run(client.create_static_segment("fake-audience-1", name="S2"))
    page = asyncio.run(client.list_segments("fake-audience-1"))
    names = [s.name for s in page.items]
    assert "S1" in names
    assert "S2" in names


def test_update_segment_renames_it() -> None:
    client = FakeMailchimpClient()
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="Old"))
    updated = asyncio.run(
        client.update_segment("fake-audience-1", seg.id, name="New")
    )
    assert updated.name == "New"


def test_delete_segment_removes_it() -> None:
    client = FakeMailchimpClient()
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="ToDelete"))
    asyncio.run(client.delete_segment("fake-audience-1", seg.id))
    page = asyncio.run(client.list_segments("fake-audience-1"))
    assert seg.id not in [s.id for s in page.items]


def test_add_segment_member_requires_audience_membership() -> None:
    client = FakeMailchimpClient()
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="X"))
    with pytest.raises(MailchimpRejectedError):
        asyncio.run(
            client.add_segment_member("fake-audience-1", seg.id, "stranger@test.com")
        )


def test_add_segment_member_succeeds_for_audience_member() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "member@test.com"))
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="Y"))
    asyncio.run(client.add_segment_member("fake-audience-1", seg.id, "member@test.com"))
    page = asyncio.run(client.list_segment_members("fake-audience-1", seg.id))
    assert any(m.email == "member@test.com" for m in page.items)


def test_segment_member_count_updates_on_add_remove() -> None:
    client = FakeMailchimpClient()
    asyncio.run(client.upsert_member("fake-audience-1", "cnt@test.com"))
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="Count"))
    asyncio.run(client.add_segment_member("fake-audience-1", seg.id, "cnt@test.com"))
    page = asyncio.run(client.list_segments("fake-audience-1"))
    seg_refreshed = next(s for s in page.items if s.id == seg.id)
    assert seg_refreshed.member_count == 1
    asyncio.run(client.remove_segment_member("fake-audience-1", seg.id, "cnt@test.com"))
    page2 = asyncio.run(client.list_segments("fake-audience-1"))
    seg_refreshed2 = next(s for s in page2.items if s.id == seg.id)
    assert seg_refreshed2.member_count == 0


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_create_template_returns_template() -> None:
    client = FakeMailchimpClient()
    tmpl = asyncio.run(
        client.create_template(name="Welcome", html="<h1>Hello</h1>")
    )
    assert tmpl.id >= 1
    assert tmpl.name == "Welcome"
    assert tmpl.type == "user"
    assert tmpl.drag_and_drop is False
    assert "admin.mailchimp.com" in tmpl.edit_url


def test_get_template_after_create() -> None:
    client = FakeMailchimpClient()
    created = asyncio.run(client.create_template(name="T", html="<p>x</p>"))
    fetched = asyncio.run(client.get_template(created.id))
    assert fetched.id == created.id


def test_update_template_renames() -> None:
    client = FakeMailchimpClient()
    tmpl = asyncio.run(client.create_template(name="Old", html="<p/>"))
    updated = asyncio.run(client.update_template(tmpl.id, name="New"))
    assert updated.name == "New"


def test_delete_template_removes_it() -> None:
    client = FakeMailchimpClient()
    tmpl = asyncio.run(client.create_template(name="Del", html="<p/>"))
    asyncio.run(client.delete_template(tmpl.id))
    with pytest.raises(MailchimpNotFoundError):
        asyncio.run(client.get_template(tmpl.id))


def test_list_templates_pagination() -> None:
    client = FakeMailchimpClient()
    for i in range(5):
        asyncio.run(client.create_template(name=f"T{i}", html=""))
    page = asyncio.run(client.list_templates(count=2, offset=0))
    assert len(page.items) == 2
    page2 = asyncio.run(client.list_templates(count=2, offset=2))
    assert len(page2.items) == 2


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


def test_create_campaign_returns_campaign_with_save_status() -> None:
    client = FakeMailchimpClient()
    campaign = asyncio.run(
        client.create_campaign(
            title="My Campaign",
            subject_line="Hello",
            from_name="Sender",
            reply_to="reply@example.com",
            audience_id="fake-audience-1",
        )
    )
    assert campaign.id.startswith("fake-campaign-")
    assert campaign.status == "save"
    assert campaign.title == "My Campaign"


def test_campaign_ids_increment() -> None:
    client = FakeMailchimpClient()
    c1 = asyncio.run(
        client.create_campaign(
            title="C1",
            subject_line="S1",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    c2 = asyncio.run(
        client.create_campaign(
            title="C2",
            subject_line="S2",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    assert c1.id != c2.id


def test_get_campaign_after_create() -> None:
    client = FakeMailchimpClient()
    created = asyncio.run(
        client.create_campaign(
            title="X",
            subject_line="Sub",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    fetched = asyncio.run(client.get_campaign(created.id))
    assert fetched.id == created.id


def test_send_campaign_flips_status_to_sent() -> None:
    client = FakeMailchimpClient()
    campaign = asyncio.run(
        client.create_campaign(
            title="SendMe",
            subject_line="Sub",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    sent = asyncio.run(client.send_campaign(campaign.id))
    assert sent.status == "sent"
    assert sent.send_time is not None


def test_schedule_campaign_flips_status_to_schedule() -> None:
    client = FakeMailchimpClient()
    campaign = asyncio.run(
        client.create_campaign(
            title="Sched",
            subject_line="S",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    scheduled = asyncio.run(
        client.schedule_campaign(campaign.id, schedule_time="2025-12-01T10:00:00+00:00")
    )
    assert scheduled.status == "schedule"


def test_unschedule_campaign_reverts_to_save() -> None:
    client = FakeMailchimpClient()
    campaign = asyncio.run(
        client.create_campaign(
            title="Unsched",
            subject_line="S",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    asyncio.run(
        client.schedule_campaign(campaign.id, schedule_time="2025-12-01T10:00:00+00:00")
    )
    unscheduled = asyncio.run(client.unschedule_campaign(campaign.id))
    assert unscheduled.status == "save"


def test_delete_campaign() -> None:
    client = FakeMailchimpClient()
    campaign = asyncio.run(
        client.create_campaign(
            title="Del",
            subject_line="S",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    asyncio.run(client.delete_campaign(campaign.id))
    with pytest.raises(MailchimpNotFoundError):
        asyncio.run(client.get_campaign(campaign.id))


def test_send_test_returns_ok() -> None:
    client = FakeMailchimpClient()
    campaign = asyncio.run(
        client.create_campaign(
            title="TestCamp",
            subject_line="S",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
        )
    )
    result = asyncio.run(
        client.send_test(campaign.id, test_emails=["tester@example.com"])
    )
    assert result == {"ok": True}


def test_create_campaign_with_segment_and_template() -> None:
    client = FakeMailchimpClient()
    seg = asyncio.run(client.create_static_segment("fake-audience-1", name="Seg"))
    tmpl = asyncio.run(client.create_template(name="T", html="<p/>"))
    campaign = asyncio.run(
        client.create_campaign(
            title="Full",
            subject_line="S",
            from_name="F",
            reply_to="r@r.com",
            audience_id="fake-audience-1",
            segment_id=seg.id,
            template_id=tmpl.id,
        )
    )
    assert campaign.segment_id == seg.id
    assert campaign.template_id == tmpl.id


def test_list_campaigns_pagination() -> None:
    client = FakeMailchimpClient()
    for i in range(4):
        asyncio.run(
            client.create_campaign(
                title=f"C{i}",
                subject_line="S",
                from_name="F",
                reply_to="r@r.com",
                audience_id="fake-audience-1",
            )
        )
    page = asyncio.run(client.list_campaigns(count=2, offset=0))
    assert len(page.items) == 2
    assert page.total == 4
