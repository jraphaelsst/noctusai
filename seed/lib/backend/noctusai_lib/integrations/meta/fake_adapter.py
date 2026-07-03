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

from noctusai_lib.integrations.meta.types import (
    Ad,
    AdCampaign,
    AdCreative,
    AdCreativeSpec,
    AdInsights,
    AdSet,
    AdSetSpec,
    AdSpec,
    CampaignSpec,
    FacebookPage,
    FacebookPost,
    InstagramAccount,
    InstagramMedia,
    MetaConnectionStatus,
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
        self._media_insights: dict[str, PostInsights] = {}
        self._account_insights: dict[str, PostInsights] = {}
        self._me: dict[str, str] = {}
        # Write-side recorders — deterministic in-memory simulation so
        # consumer/MCP tests exercise the real publish handler path.
        self.published_posts: list[PublishedPost] = []
        self.published_media: list[PublishedMedia] = []
        self._ad_campaigns_by_account: dict[str, list[AdCampaign]] = {}
        self._ad_insights: dict[str, AdInsights] = {}
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

    def seed(
        self,
        *,
        pages: list[FacebookPage] | None = None,
        posts_by_page: dict[str, list[FacebookPost]] | None = None,
        ig_accounts: list[InstagramAccount] | None = None,
        media_by_ig_user: dict[str, list[InstagramMedia]] | None = None,
        post_insights: dict[str, PostInsights] | None = None,
        media_insights: dict[str, PostInsights] | None = None,
        account_insights: dict[str, PostInsights] | None = None,
        me: dict[str, str] | None = None,
        ad_campaigns_by_account: dict[str, list[AdCampaign]] | None = None,
        ad_insights: dict[str, AdInsights] | None = None,
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


__all__ = ["FakeMetaAdapter"]
