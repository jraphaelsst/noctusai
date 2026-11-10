# Instagram bot shell vs Meta docs (noc-research run 2, read 2026-11-09, docs on v27.0)
Short (high on API facts, medium on policy edges): Instagram API with Instagram Login (graph.instagram.com, instagram_business_* scopes) needs a professional (Business/Creator) account, no Facebook Page. Standard Access (no App Review) for owned/managed accounts added to the app: profile, media, insights, comments (read/reply/hide/delete), DMs (read/send), publishing, mentions/tags. Exception: webhooks for IG Login need Advanced Access + Live app → shell polls in dev mode. business_discovery is Facebook-Login only → competitor checks via Apify. "Use Facebook Login or Instagram Login, not both."

Seed adapter instagram_login_adapter.py implements: me, list_instagram_conversations, list_instagram_messages, send_instagram_message (raises requires_app_review, no fake success), get_profile, get_user_insights, list_media (paged), list_stories, get_media_insights; Fake + factory (fake only allow_fake=True); _meta_api: authorize URL, code exchange, long-lived exchange. MISSING: refresh (ig_refresh_token), comments, publishing, mentions, private replies, webhooks. Drift: docstring says "Send is roadmap S4" though implemented.

| Job | API scope (IG Login) | Apify | Residual (browser) | Seed |
|---|---|---|---|---|
| Insights | instagram_business_manage_insights | – | – | ✅ |
| Recent posts/stories | instagram_business_basic | public | – | ✅ |
| Comments read/reply/hide/delete | instagram_business_manage_comments | read public | – | ❌ (FB-Login MetaOAuthAdapter has it) |
| Private reply to commenter | manage_comments, ≤7 days, one message | – | – | ❌ |
| Read DMs | instagram_business_manage_messages (polling) | – | Requests >30d, groups | ✅ |
| Answer DMs | same, user-initiated, 24h window | – | groups, >7d | ✅ |
| Human-agent 7-day | human_agent, App Review | – | – | ❌ |
| Publish feed/reel/story/carousel (≤20) | instagram_business_content_publish, JPEG, public media URL | – | shopping tags, filters, music | ❌ (FB-Login has it) |
| Schedule | no API param; own scheduler + publish | – | native scheduler | ❌ |
| Mentions/tags | GET /<IG_ID>/tags, POST /mentions; no story mentions | – | story mentions | ❌ |
| Competitor/public profile | business_discovery FB-Login only | ✅ scrape_profile | private accounts | Apify ✅ |
| Likes/follows | not offered | – | browser only, policy-risky | – |

Key claims (T1 verified unless noted): Standard Access for owned accounts added in dashboard, App Review not required; testers need app role + IG account role. Webhooks need published/Live + Advanced Access + public media owners; story_insights not on IG Login. Tokens: code 1h, short 1h, long-lived 60d, refresh after ≥24h → 60d. BUC: 4800 × impressions / 24h (messaging excluded), header X-Business-Use-Case-Usage; Conversations API 2/s, Send text 100/s, audio/video 10/s, private replies 750/h. Publishing limit 100 vs 50 per 24h CONTESTED (same page) → runtime GET content_publishing_limit. Insights: some need ≥100 followers, 90-day retention, missing = empty not 0; `impressions` deprecation unverified. Developer Policies (2026-02-03): §1.7 consent, §5.2(a) no contact without consent, §5.2(b) honour stop at once, §5.6.1 24h, §5.6.2(b) no spam/high-frequency bot, (c) no promo in tags, (d) no pre-filled content, §5.6.4 minimisation. Messaging policy: disclose automation where law requires; human-agent for manual replies. Community Standards: no high-frequency posting manual or automatic, repetitive content, engagement exchange. IG ToU automated-collection ban: via legal-advisor's same-day read (Terms page unreachable, JS-rendered).

Shell constraints: no DM unless user messaged first; refuse sends outside 24h, human-agent off; one private reply per comment ≤7d; publishing capped by content_publishing_limit, no bursts, no likes/follows; automated-reply disclosure string; opt-out at once; minimise DM data.
Shell design: Protocols + Fakes: IgProfileReader, IgInsightsReader, IgMediaReader, IgCommentModerator, IgMessenger, IgPublisher, IgMentionsReader, IgTokenKeeper, PublicProfileScraper (Apify). Config from real account via GET only: ig_user_id, username, account_type, granted scopes, access_level, app_mode, token expires_at, followers_count, Graph version pin. DryRunInstagramAdapter wraps real: reads pass, writes → action journal `planned` + policy verdict, synthetic id dry_run=True, never graph_post/graph_delete; factory default mode=dry_run until explicit per-account flag; keeper test asserts zero POST/DELETE in dry run.
Register: developers.facebook.com graded T1 + contested + unreachable; transparency.meta.com T1; help.instagram.com unreachable.
What would change it: Advanced Access; Meta fixing publishing cap; newer doc dates; whether Live app on Standard Access gets webhooks for role holders (spare accounts settle it).
