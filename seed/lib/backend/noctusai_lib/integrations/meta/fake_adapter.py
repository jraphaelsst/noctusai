"""`FakeMetaAdapter` — deterministic in-memory adapter (dev/test default).

Mirrors the Graph response shapes so consumer code swaps real/fake
transparently. `auth_mode` is `"none"` (no real credentials) — but
`status()` reports `configured=False, adapter="fake"` so a consumer
can still introspect. Seeded via `seed(...)`; `limit` truncation
mirrors the real adapter's paging cap.

Write/ads surface: the Fake simulates publish + ads deterministically
in memory (no network) so MCP / consumer tests exercise the real
handler path. Published posts/media are recorded on
`.published_posts` / `.published_media`; ad campaigns / insights are
served from `seed(...)`. The Fake never raises the App-Review
permission error — that gate lives on the live adapter only; the Fake
is the "scope already approved" path."""

from __future__ import annotations

from noctusai_lib.integrations.meta._meta_api import MetaGraphError
from noctusai_lib.integrations.meta.types import (
    Ad,
    AdAccount,
    AdActivity,
    AdCampaign,
    AdCreative,
    AdCreativeSpec,
    AdInsights,
    AdInsightsSeries,
    AdSet,
    AdSetSpec,
    AdSpec,
    CampaignSpec,
    Conversation,
    DirectMessage,
    FacebookComment,
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramComment,
    InstagramMedia,
    Lead,
    LeadgenForm,
    MetaConnectionStatus,
    PageSubscription,
    PostInsights,
    PublishedMedia,
    PublishedPost,
    )


class FakeMetaAdapter:
    """In-memory `MetaAdapter`. Default when no creds are configured."""

    auth_mode = "none"

    def __init__(self) -> None:
        self._pages: list[FacebookPage] = []
        self._posts_by_page: dict[str, list[FacebookPost]] = {}
        self._ig_accounts: list[InstagramAccount] = []
        self._media_by_ig_user: dict[str, list[InstagramMedia]] = {}
        self._post_insights: dict[str, PostInsights] = {}
        self._page_insights: dict[str, PostInsights] = {}
        self._media_insights: dict[str, PostInsights] = {}
        self._account_insights: dict[str, PostInsights] = {}
        self._me: dict[str, str] = {}
        # Write-side recorders — deterministic in-memory simulation so
        # consumer/MCP tests exercise the real publish handler path.
        self.published_posts: list[PublishedPost] = []
        self.published_media: list[PublishedMedia] = []
        self._ad_campaigns_by_account: dict[str, list[AdCampaign]] = {}
        self._ad_insights: dict[str, AdInsights] = {}
        # Ads-read surface, W1 completion — seedable state, same
        # "deterministic, never raises the App-Review gate" posture as
        # the ads-read/-management recorders above.
        self._ad_accounts: list[AdAccount] = []
        self._ad_sets_by_account: dict[str, list[AdSet]] = {}
        self._ads_by_account: dict[str, list[Ad]] = {}
        self._ad_insights_series: dict[str, AdInsightsSeries] = {}
        self._activities_by_account: dict[str, list[AdActivity]] = {}
        self._leadgen_forms_by_page: dict[str, list[LeadgenForm]] = {}
        self._leads_by_form: dict[str, list[Lead]] = {}
        # Lead-ads webhook surface — `_leads_by_id` is the flattened
        # `leads_by_form` index (rebuilt whenever `leads_by_form` is
        # (re-)seeded) merged with any explicit `leads_by_id=` override;
        # `get_lead` reads from here, never from `_leads_by_form`
        # directly (a webhook delivers a bare `leadgen_id`, not a
        # `form_id`, so the by-form index alone can't serve it).
        self._leads_by_id: dict[str, Lead] = {}
        self._page_subscribed_apps: dict[str, list[PageSubscription]] = {}
        self.subscribed_pages: list[tuple[str, tuple[str, ...]]] = []
        self.unsubscribed_pages: list[str] = []
        self._post_seq = 0
        self._media_seq = 0
        # Ads-management recorders — deterministic in-memory CRUD so
        # MCP/consumer tests exercise the real handler graph with no
        # network. The Fake NEVER raises the App-Review gate — that
        # gate lives on the live adapter only; the Fake is the
        # "scope already approved" path.
        self.created_campaigns: list = []
        self.created_ad_sets: list = []
        self.created_ad_creatives: list = []
        self.created_ads: list = []
        self._campaigns_by_id: dict = {}
        self._ad_sets_by_id: dict = {}
        self._camp_seq = 0
        self._adset_seq = 0
        self._creative_seq = 0
        self._ad_seq = 0
        # Comments / DMs / Stories — seedable read state + write
        # recorders, same deterministic-in-memory posture as the rest
        # of the write surface. The Fake NEVER raises the App-Review
        # gate here either.
        self._ig_comments_by_media: dict[str, list[InstagramComment]] = {}
        self._fb_comments_by_post: dict[str, list[FacebookComment]] = {}
        self._conversations_by_page: dict[str, list[Conversation]] = {}
        self._messages_by_conversation: dict[str, list[DirectMessage]] = {}
        self.created_instagram_comments: list[InstagramComment] = []
        self.replied_instagram_comments: list[InstagramComment] = []
        self.hidden_instagram_comments: list[tuple[str, bool]] = []
        self.deleted_instagram_comment_ids: list[str] = []
        self.sent_instagram_messages: list[DirectMessage] = []
        self.published_stories: list[PublishedMedia] = []
        self.created_facebook_comments: list[FacebookComment] = []
        self.replied_facebook_comments: list[FacebookComment] = []
        self.hidden_facebook_comments: list[tuple[str, bool]] = []
        self.deleted_facebook_comment_ids: list[str] = []
        self._ig_comment_seq = 0
        self._fb_comment_seq = 0
        self._dm_seq = 0

    def seed(
        self,
        *,
        pages: list[FacebookPage] | None = None,
        posts_by_page: dict[str, list[FacebookPost]] | None = None,
        ig_accounts: list[InstagramAccount] | None = None,
        media_by_ig_user: dict[str, list[InstagramMedia]] | None = None,
        post_insights: dict[str, PostInsights] | None = None,
        page_insights: dict[str, PostInsights] | None = None,
        media_insights: dict[str, PostInsights] | None = None,
        account_insights: dict[str, PostInsights] | None = None,
        me: dict[str, str] | None = None,
        ad_campaigns_by_account: dict[str, list[AdCampaign]] | None = None,
        ad_insights: dict[str, AdInsights] | None = None,
        ad_accounts: list[AdAccount] | None = None,
        ad_sets_by_account: dict[str, list[AdSet]] | None = None,
        ads_by_account: dict[str, list[Ad]] | None = None,
        ad_insights_series: dict[str, AdInsightsSeries] | None = None,
        activities_by_account: dict[str, list[AdActivity]] | None = None,
        leadgen_forms_by_page: dict[str, list[LeadgenForm]] | None = None,
        leads_by_form: dict[str, list[Lead]] | None = None,
        leads_by_id: dict[str, Lead] | None = None,
        page_subscribed_apps: dict[str, list[PageSubscription]] | None = None,
        ig_comments_by_media: dict[str, list[InstagramComment]] | None = None,
        fb_comments_by_post: dict[str, list[FacebookComment]] | None = None,
        conversations_by_page: dict[str, list[Conversation]] | None = None,
        messages_by_conversation: dict[str, list[DirectMessage]] | None = None,
    ) -> "FakeMetaAdapter":
        if pages is not None:
            self._pages = list(pages)
        if posts_by_page is not None:
            self._posts_by_page = {k: list(v) for k, v in posts_by_page.items()}
        if ig_accounts is not None:
            self._ig_accounts = list(ig_accounts)
        if media_by_ig_user is not None:
            self._media_by_ig_user = {
                k: list(v) for k, v in media_by_ig_user.items()
            }
        if post_insights is not None:
            self._post_insights = dict(post_insights)
        if page_insights is not None:
            self._page_insights = dict(page_insights)
        if media_insights is not None:
            self._media_insights = dict(media_insights)
        if account_insights is not None:
            self._account_insights = dict(account_insights)
        if me is not None:
            self._me = dict(me)
        if ad_campaigns_by_account is not None:
            self._ad_campaigns_by_account = {
                k: list(v) for k, v in ad_campaigns_by_account.items()
            }
        if ad_insights is not None:
            self._ad_insights = dict(ad_insights)
        if ad_accounts is not None:
            self._ad_accounts = list(ad_accounts)
        if ad_sets_by_account is not None:
            self._ad_sets_by_account = {
                k: list(v) for k, v in ad_sets_by_account.items()
            }
        if ads_by_account is not None:
            self._ads_by_account = {
                k: list(v) for k, v in ads_by_account.items()
            }
        if ad_insights_series is not None:
            self._ad_insights_series = dict(ad_insights_series)
        if activities_by_account is not None:
            self._activities_by_account = {
                k: list(v) for k, v in activities_by_account.items()
            }
        if leadgen_forms_by_page is not None:
            self._leadgen_forms_by_page = {
                k: list(v) for k, v in leadgen_forms_by_page.items()
            }
        if leads_by_form is not None:
            self._leads_by_form = {
                k: list(v) for k, v in leads_by_form.items()
            }
            self._leads_by_id = {
                lead.id: lead
                for leads in self._leads_by_form.values()
                for lead in leads
            }
        if leads_by_id is not None:
            self._leads_by_id.update(dict(leads_by_id))
        if page_subscribed_apps is not None:
            self._page_subscribed_apps = {
                k: list(v) for k, v in page_subscribed_apps.items()
            }
        if ig_comments_by_media is not None:
            self._ig_comments_by_media = {
                k: list(v) for k, v in ig_comments_by_media.items()
            }
        if fb_comments_by_post is not None:
            self._fb_comments_by_post = {
                k: list(v) for k, v in fb_comments_by_post.items()
            }
        if conversations_by_page is not None:
            self._conversations_by_page = {
                k: list(v) for k, v in conversations_by_page.items()
            }
        if messages_by_conversation is not None:
            self._messages_by_conversation = {
                k: list(v) for k, v in messages_by_conversation.items()
            }
        return self

    def status(self) -> MetaConnectionStatus:
        return MetaConnectionStatus(
            configured=False,
            adapter="fake",
            auth_mode="none",
            consent_required=True,
            user_id=self._me.get("id"),
            user_name=self._me.get("name"),
            pages_count=len(self._pages),
            instagram_accounts_count=len(self._ig_accounts),
        )

    def me(self) -> dict:
        return dict(self._me)

    def list_facebook_pages(self) -> list[FacebookPage]:
        return list(self._pages)

    def get_page(self, page_id: str) -> FacebookPage | None:
        for page in self._pages:
            if page.id == page_id:
                return page
        return None

    def list_facebook_posts(
        self, page_id: str, limit: int = 25
    ) -> list[FacebookPost]:
        return list(self._posts_by_page.get(page_id, []))[:limit]

    def get_facebook_post_insights(
        self, post_id: str, page_id: str | None = None
    ) -> PostInsights:
        return self._post_insights.get(
            post_id, PostInsights(object_id=post_id)
        )

    def get_facebook_page_insights(
        self,
        page_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights:
        # Deterministic: period/since/until/metrics are accepted for
        # Protocol parity but ignored — serves whatever was seeded for
        # this page (or an empty insight object). The per-metric-degrade
        # behavior is a live-adapter-only concern (Graph's actual
        # deprecated-metric 400s); the Fake has nothing to degrade from.
        return self._page_insights.get(
            page_id, PostInsights(object_id=page_id)
        )

    def list_instagram_accounts(self) -> list[InstagramAccount]:
        return list(self._ig_accounts)

    def list_instagram_media(
        self, ig_user_id: str, limit: int = 25
    ) -> list[InstagramMedia]:
        return list(self._media_by_ig_user.get(ig_user_id, []))[:limit]

    def get_instagram_media_insights(self, media_id: str) -> PostInsights:
        return self._media_insights.get(
            media_id, PostInsights(object_id=media_id)
        )

    def get_instagram_account_insights(
        self,
        ig_user_id: str,
        *,
        metrics: list[str] | None = None,
        period: str = "day",
        since: int | None = None,
        until: int | None = None,
    ) -> PostInsights:
        # Deterministic: the window/period/metric args are accepted for
        # Protocol parity but ignored — the Fake serves whatever was
        # seeded for this account (or an empty insight object).
        return self._account_insights.get(
            ig_user_id, PostInsights(object_id=ig_user_id)
        )

    # ─── Write / ads surface (deterministic in-memory simulation) ──────

    def publish_facebook_post(
        self,
        page_id: str,
        message: str,
        link: str | None = None,
        photo_url: str | None = None,
    ) -> PublishedPost:
        self._post_seq += 1
        post = PublishedPost(
            id=f"{page_id}_{self._post_seq}",
            page_id=page_id,
            message=message,
            permalink_url=f"https://facebook.com/{page_id}_{self._post_seq}",
        )
        self.published_posts.append(post)
        return post

    def publish_instagram_media(
        self,
        ig_user_id: str,
        image_url: str,
        caption: str | None = None,
    ) -> PublishedMedia:
        self._media_seq += 1
        media = PublishedMedia(
            id=f"{ig_user_id}_media_{self._media_seq}",
            ig_user_id=ig_user_id,
            container_id=f"{ig_user_id}_container_{self._media_seq}",
            caption=caption,
            permalink=f"https://instagram.com/p/{ig_user_id}_{self._media_seq}",
        )
        self.published_media.append(media)
        return media

    def publish_instagram_carousel(
        self,
        ig_user_id: str,
        image_urls: list[str],
        caption: str | None = None,
    ) -> PublishedMedia:
        if not image_urls:
            raise ValueError("publish_instagram_carousel requires at least one image_url")
        if len(image_urls) > 10:
            raise ValueError("Instagram carousels accept at most 10 children")
        self._media_seq += 1
        media = PublishedMedia(
            id=f"{ig_user_id}_carousel_{self._media_seq}",
            ig_user_id=ig_user_id,
            container_id=f"{ig_user_id}_carousel_container_{self._media_seq}",
            caption=caption,
            permalink=f"https://instagram.com/p/{ig_user_id}_carousel_{self._media_seq}",
        )
        self.published_media.append(media)
        return media
    def publish_instagram_reel(
        self,
        ig_user_id: str,
        video_url: str,
        caption: str | None = None,
    ) -> PublishedMedia:
        """Deterministic Reel publish — mirrors the Real 3-step async flow
        but instant-ready (no transcode wait). ``processing_duration_ms``
        is a small fixed value so consumer code that logs / asserts the
        field has a stable non-None number. The Fake NEVER raises the
        App-Review gate — that lives on the live adapter only; the Fake is
        the "scope already approved + transcode done" path."""

        if not video_url:
            raise ValueError(
                "publish_instagram_reel requires a non-empty video_url"
            )
        self._media_seq += 1
        media = PublishedMedia(
            id=f"{ig_user_id}_reel_{self._media_seq}",
            ig_user_id=ig_user_id,
            container_id=f"{ig_user_id}_reel_container_{self._media_seq}",
            caption=caption,
            permalink=f"https://instagram.com/reel/{ig_user_id}_{self._media_seq}",
            processing_duration_ms=0,
        )
        self.published_media.append(media)
        return media

    def publish_facebook_video(
        self,
        page_id: str,
        video_url: str,
        description: str | None = None,
        *,
        as_reel: bool = False,
    ) -> PublishedPost:
        """Deterministic FB Page video / Reel publish — mirrors the Real
        method's ``as_reel`` discriminator, instant-ready. Records on
        ``published_posts``. The Fake never raises the App-Review gate."""

        if not video_url:
            raise ValueError(
                "publish_facebook_video requires a non-empty video_url"
            )
        self._post_seq += 1
        kind = "reel" if as_reel else "video"
        post = PublishedPost(
            id=f"{page_id}_{kind}_{self._post_seq}",
            page_id=page_id,
            message=description,
            permalink_url=(
                f"https://facebook.com/{page_id}/{kind}/{self._post_seq}"
            ),
            processing_duration_ms=0,
        )
        self.published_posts.append(post)
        return post

    def list_ad_campaigns(self, ad_account_id: str) -> list[AdCampaign]:
        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        return list(
            self._ad_campaigns_by_account.get(
                acct, self._ad_campaigns_by_account.get(ad_account_id, [])
            )
        )

    def ad_insights(
        self,
        object_id: str,
        level: str,
        date_preset: str | None = None,
    ) -> AdInsights:
        return self._ad_insights.get(
            object_id, AdInsights(object_id=object_id, level=level)
        )

    # ─── Ads-read surface, W1 completion (deterministic, seeded) ───────

    def list_ad_accounts(self) -> list[AdAccount]:
        return list(self._ad_accounts)

    def list_ad_sets(
        self, ad_account_id: str, campaign_id: str | None = None
    ) -> list[AdSet]:
        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        rows = list(
            self._ad_sets_by_account.get(
                acct, self._ad_sets_by_account.get(ad_account_id, [])
            )
        )
        if campaign_id:
            rows = [r for r in rows if r.campaign_id == campaign_id]
        return rows

    def list_ads(
        self, ad_account_id: str, adset_id: str | None = None
    ) -> list[Ad]:
        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        rows = list(
            self._ads_by_account.get(
                acct, self._ads_by_account.get(ad_account_id, [])
            )
        )
        if adset_id:
            rows = [r for r in rows if r.adset_id == adset_id]
        return rows

    def ad_insights_series(
        self,
        object_id: str,
        level: str,
        *,
        time_range=None,
        date_preset: str | None = None,
        time_increment: int | str = 1,
        breakdowns: list[str] | None = None,
        action_attribution_windows: list[str] | None = None,
        fields: list[str] | None = None,
    ) -> AdInsightsSeries:
        # Deterministic: every filter/window arg is accepted for
        # Protocol parity but ignored — same "seeded, not computed"
        # posture as ad_insights / get_instagram_account_insights
        # above. Serves whatever multi-row series was seeded for this
        # object_id.
        return self._ad_insights_series.get(
            object_id, AdInsightsSeries(object_id=object_id, level=level)
        )

    def list_activities(
        self, ad_account_id: str, since: int, until: int
    ) -> list[AdActivity]:
        # Deterministic: since/until accepted for Protocol parity but
        # ignored — serves whatever activity sequence was seeded for
        # this account (in seeded order — the Fake never reorders).
        acct = (
            ad_account_id
            if ad_account_id.startswith("act_")
            else f"act_{ad_account_id}"
        )
        return list(
            self._activities_by_account.get(
                acct, self._activities_by_account.get(ad_account_id, [])
            )
        )

    def list_leadgen_forms(
        self, page_id: str, *, with_questions: bool = False
    ) -> list[LeadgenForm]:
        # `with_questions` accepted for Protocol parity; the Fake serves
        # whatever forms were seeded (a seeded form may already carry its
        # questions). Deterministic, never raises the leads_retrieval gate.
        return list(self._leadgen_forms_by_page.get(page_id, []))

    def get_leadgen_form(
        self, form_id: str, *, page_id: str | None = None
    ) -> LeadgenForm:
        for forms in self._leadgen_forms_by_page.values():
            for f in forms:
                if f.id == form_id:
                    return f
        return LeadgenForm(id=form_id)

    def list_leads(
        self, form_id: str, *, page_id: str | None = None, limit: int = 100
    ) -> list[Lead]:
        # The Fake is the "scope already granted" path — it NEVER raises
        # the leads_retrieval gate (that lives on the live adapter only),
        # so consumer/endpoint tests can exercise the records path.
        return list(self._leads_by_form.get(form_id, []))[:limit]

    def get_lead(self, leadgen_id: str, *, page_id: str | None = None) -> Lead:
        # Unlike `get_leadgen_form`'s return-empty-object-on-miss, a
        # miss here MUST raise: an empty `Lead` would silently upsert a
        # PII-less row into production (the caller can't tell "no such
        # lead" from "here's an empty one"). Seeded via `leads_by_form`
        # (flattened into `_leads_by_id`) or the explicit `leads_by_id=`
        # kwarg.
        lead = self._leads_by_id.get(leadgen_id)
        if lead is None:
            raise MetaGraphError(
                f"No lead seeded for leadgen_id={leadgen_id!r} "
                "(FakeMetaAdapter.seed(leads_by_form=...) or "
                "seed(leads_by_id=...) first)",
            )
        return lead

    def subscribe_page_to_leadgen(
        self, page_id: str, *, fields: tuple[str, ...] = ("leadgen",)
    ) -> bool:
        # Deterministic in-memory record — the Fake never raises the
        # App-Review gate (that lives on the live adapter only).
        self.subscribed_pages.append((page_id, tuple(fields)))
        self._page_subscribed_apps[page_id] = [
            PageSubscription(
                app_id="fake_app",
                app_name="Fake App",
                page_id=page_id,
                subscribed_fields=list(fields),
            )
        ]
        return True

    def list_page_subscribed_apps(self, page_id: str) -> list[PageSubscription]:
        return list(self._page_subscribed_apps.get(page_id, []))

    def unsubscribe_page_from_leadgen(self, page_id: str) -> bool:
        self.unsubscribed_pages.append(page_id)
        self._page_subscribed_apps.pop(page_id, None)
        return True

    def create_ad_campaign(self, ad_account_id, spec):
        self._camp_seq += 1
        camp = AdCampaign(
            id=f"camp_{self._camp_seq}",
            name=spec.name,
            objective=spec.objective,
            status=spec.status,
        )
        self.created_campaigns.append(camp)
        self._campaigns_by_id[camp.id] = camp
        return camp

    def create_ad_set(self, ad_account_id, spec):
        self._adset_seq += 1
        ad_set = AdSet(
            id=f"adset_{self._adset_seq}",
            name=spec.name,
            status=spec.status,
            campaign_id=spec.campaign_id,
            daily_budget=spec.daily_budget,
            billing_event=spec.billing_event,
            optimization_goal=spec.optimization_goal,
            targeting=dict(spec.targeting),
        )
        self.created_ad_sets.append(ad_set)
        self._ad_sets_by_id[ad_set.id] = ad_set
        return ad_set

    def create_ad_creative(self, ad_account_id, spec):
        self._creative_seq += 1
        creative = AdCreative(
            id=f"creative_{self._creative_seq}",
            name=spec.name,
            object_story_spec=dict(spec.object_story_spec),
        )
        self.created_ad_creatives.append(creative)
        return creative

    def create_ad(self, ad_account_id, spec):
        self._ad_seq += 1
        ad = Ad(
            id=f"ad_{self._ad_seq}",
            name=spec.name,
            status=spec.status,
            adset_id=spec.adset_id,
            creative_id=spec.creative_id,
        )
        self.created_ads.append(ad)
        return ad

    def update_campaign_status(self, campaign_id, status):
        prev = self._campaigns_by_id.get(campaign_id)
        updated = AdCampaign(
            id=campaign_id,
            name=prev.name if prev else None,
            objective=prev.objective if prev else None,
            status=status,
            effective_status=status,
        )
        self._campaigns_by_id[campaign_id] = updated
        return updated

    def update_ad_set_budget(self, ad_set_id, daily_budget):
        prev = self._ad_sets_by_id.get(ad_set_id)
        updated = AdSet(
            id=ad_set_id,
            name=prev.name if prev else None,
            status=prev.status if prev else None,
            effective_status=prev.effective_status if prev else None,
            campaign_id=prev.campaign_id if prev else None,
            daily_budget=daily_budget,
            billing_event=prev.billing_event if prev else None,
            optimization_goal=prev.optimization_goal if prev else None,
            targeting=dict(prev.targeting) if prev else {},
        )
        self._ad_sets_by_id[ad_set_id] = updated
        return updated

    # ─── IG comments (deterministic in-memory simulation) ──────────────

    def list_instagram_comments(
        self, media_id: str, limit: int = 25
    ) -> list[InstagramComment]:
        return list(self._ig_comments_by_media.get(media_id, []))[:limit]

    def create_instagram_comment(
        self, media_id: str, message: str
    ) -> InstagramComment:
        self._ig_comment_seq += 1
        comment = InstagramComment(
            id=f"{media_id}_comment_{self._ig_comment_seq}",
            text=message,
        )
        self.created_instagram_comments.append(comment)
        return comment

    def reply_instagram_comment(
        self, comment_id: str, message: str
    ) -> InstagramComment:
        self._ig_comment_seq += 1
        reply = InstagramComment(
            id=f"{comment_id}_reply_{self._ig_comment_seq}",
            text=message,
            parent_id=comment_id,
        )
        self.replied_instagram_comments.append(reply)
        return reply

    def hide_instagram_comment(
        self, comment_id: str, hide: bool = True
    ) -> None:
        self.hidden_instagram_comments.append((comment_id, hide))

    def delete_instagram_comment(self, comment_id: str) -> None:
        self.deleted_instagram_comment_ids.append(comment_id)

    # ─── IG Direct messages (deterministic in-memory simulation) ───────

    def list_instagram_conversations(
        self, page_id: str, limit: int = 25
    ) -> list[Conversation]:
        return list(
            self._conversations_by_page.get(page_id, [])
        )[:limit]

    def list_instagram_messages(
        self, conversation_id: str, page_id: str, limit: int = 25
    ) -> list[DirectMessage]:
        # `page_id` accepted for Protocol parity (the Facebook-Login
        # model reads messages with the Page token) — the Fake keys by
        # conversation_id.
        return list(
            self._messages_by_conversation.get(conversation_id, [])
        )[:limit]

    def send_instagram_message(
        self, page_id: str, recipient_id: str, text: str
    ) -> DirectMessage:
        self._dm_seq += 1
        msg = DirectMessage(
            id=f"{page_id}_dm_{self._dm_seq}",
            sender_id=page_id,
            recipient_id=recipient_id,
            text=text,
        )
        self.sent_instagram_messages.append(msg)
        return msg

    # ─── IG Stories (deterministic in-memory simulation) ───────────────

    def publish_instagram_story(
        self,
        ig_user_id: str,
        media_url: str,
        *,
        is_video: bool = False,
    ) -> PublishedMedia:
        self._media_seq += 1
        kind = "video" if is_video else "image"
        media = PublishedMedia(
            id=f"{ig_user_id}_story_{kind}_{self._media_seq}",
            ig_user_id=ig_user_id,
            container_id=f"{ig_user_id}_story_container_{self._media_seq}",
            permalink=(
                f"https://instagram.com/stories/{ig_user_id}/"
                f"{self._media_seq}"
            ),
        )
        self.published_stories.append(media)
        return media

    # ─── FB comment moderation (deterministic in-memory simulation) ────

    def list_facebook_comments(
        self, post_id: str, limit: int = 25
    ) -> list[FacebookComment]:
        return list(self._fb_comments_by_post.get(post_id, []))[:limit]

    def create_facebook_comment(
        self, post_id: str, message: str
    ) -> FacebookComment:
        self._fb_comment_seq += 1
        comment = FacebookComment(
            id=f"{post_id}_comment_{self._fb_comment_seq}",
            message=message,
        )
        self.created_facebook_comments.append(comment)
        return comment

    def reply_facebook_comment(
        self, comment_id: str, message: str
    ) -> FacebookComment:
        self._fb_comment_seq += 1
        reply = FacebookComment(
            id=f"{comment_id}_reply_{self._fb_comment_seq}",
            message=message,
            parent_id=comment_id,
        )
        self.replied_facebook_comments.append(reply)
        return reply

    def hide_facebook_comment(
        self, comment_id: str, hide: bool = True
    ) -> None:
        self.hidden_facebook_comments.append((comment_id, hide))

    def delete_facebook_comment(self, comment_id: str) -> None:
        self.deleted_facebook_comment_ids.append(comment_id)


__all__ = ["FakeMetaAdapter"]
