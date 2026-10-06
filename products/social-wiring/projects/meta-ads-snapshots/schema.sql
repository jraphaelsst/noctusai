-- Meta Ads snapshot store — SQLite (learning/dev phase; target: dedicated DB later)
-- Hierarchy (Meta naming → UI naming → Graph internal name):
--   account (Conta de anúncios, act_<id>)
--     └ campaign (Campanha; internal "campaign_group")        — objective, buying type, (CBO budget)
--         └ adset (Conjunto de anúncios; internal "campaign") — budget, schedule, optimization, targeting, placement
--             └ ad (Anúncio; internal "adgroup")              — ties ONE creative to the ad set; property code lives in its NAME
--                 └ creative (Criativo)                        — media + copy + CTA; backs an FB post and/or IG media
-- A property (ONExxxxx) is NOT a Meta object: it is parsed from ad.name (and sometimes adset.name).
-- Facts are append-only per extraction_run → each weekly run is a "screenshot" of the data scenario.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS extraction_run (
  run_id            INTEGER PRIMARY KEY AUTOINCREMENT,
  fetched_at        TEXT NOT NULL,              -- ISO-8601 UTC
  source            TEXT NOT NULL,              -- 'graph_in_page' | 'ui_dom' | 'ui_export'
  account_id        TEXT NOT NULL,
  scope_kind        TEXT NOT NULL,              -- 'property' | 'campaign' | 'account'
  scope_value       TEXT NOT NULL,              -- e.g. 'ONE10449'
  date_preset       TEXT NOT NULL,              -- 'maximum' | 'last_7d' | ...
  attribution       TEXT NOT NULL,              -- e.g. '7d_click,1d_view'
  graph_version     TEXT NOT NULL,              -- e.g. 'v22.0'
  raw_path          TEXT,                       -- path of the raw JSON bundle kept for replay
  notes             TEXT
);

-- ── Dimensions (latest state; history lives in object_snapshot) ────────────────────────
CREATE TABLE IF NOT EXISTS account (
  account_id        TEXT PRIMARY KEY,           -- numeric, without 'act_'
  name              TEXT, currency TEXT, timezone_name TEXT,
  business_id       TEXT, business_name TEXT
);

CREATE TABLE IF NOT EXISTS campaign (
  campaign_id       TEXT PRIMARY KEY,
  account_id        TEXT NOT NULL REFERENCES account(account_id),
  name              TEXT NOT NULL,
  objective         TEXT,                       -- OUTCOME_LEADS, LINK_CLICKS, ...
  buying_type       TEXT,
  status            TEXT, effective_status TEXT,
  created_time      TEXT, start_time TEXT, stop_time TEXT,
  daily_budget_cents    INTEGER,                -- set only when budget is at campaign level (CBO)
  lifetime_budget_cents INTEGER,
  bid_strategy      TEXT
);

CREATE TABLE IF NOT EXISTS adset (
  adset_id          TEXT PRIMARY KEY,
  campaign_id       TEXT NOT NULL REFERENCES campaign(campaign_id),
  name              TEXT NOT NULL,
  status            TEXT, effective_status TEXT,
  created_time      TEXT, start_time TEXT, end_time TEXT,
  daily_budget_cents    INTEGER,                -- Graph returns minor units (10000 = R$100,00)
  lifetime_budget_cents INTEGER,
  optimization_goal TEXT,                       -- QUALITY_LEAD, PROFILE_VISIT, ...
  billing_event     TEXT,
  bid_strategy      TEXT,
  destination_type  TEXT,                       -- ON_AD (instant form), INSTAGRAM_PROFILE, ...
  is_shared_pool    INTEGER NOT NULL DEFAULT 0, -- 1 = holds ads of MANY properties (metrics not property-exclusive)
  targeting_json    TEXT, promoted_object_json TEXT, attribution_spec_json TEXT
);

CREATE TABLE IF NOT EXISTS creative (
  creative_id       TEXT PRIMARY KEY,
  name              TEXT, object_type TEXT,     -- VIDEO | SHARE (carousel/link) | PHOTO ...
  title             TEXT, body TEXT, call_to_action_type TEXT,
  video_id          TEXT, image_hash TEXT,
  fb_story_id       TEXT,                       -- effective_object_story_id  (<page_id>_<post_id>)
  ig_media_id       TEXT,                       -- effective_instagram_media_id
  ig_permalink      TEXT
);

CREATE TABLE IF NOT EXISTS ad (
  ad_id             TEXT PRIMARY KEY,
  adset_id          TEXT NOT NULL REFERENCES adset(adset_id),
  campaign_id       TEXT NOT NULL REFERENCES campaign(campaign_id),
  creative_id       TEXT REFERENCES creative(creative_id),
  name              TEXT NOT NULL,
  property_code     TEXT,                       -- parsed: 'ONE10449'
  variant           TEXT,                       -- suffix after the code: 'Larissa','Tour','Carrossel','MESCLADO', NULL = base
  status            TEXT, effective_status TEXT,
  created_time      TEXT, updated_time TEXT
);
CREATE INDEX IF NOT EXISTS ix_ad_property ON ad(property_code);

-- Every run also stores the raw object JSON → cheap history of budget/status/targeting changes.
CREATE TABLE IF NOT EXISTS object_snapshot (
  run_id            INTEGER NOT NULL REFERENCES extraction_run(run_id),
  level             TEXT NOT NULL,              -- account|campaign|adset|ad|creative
  object_id         TEXT NOT NULL,
  raw_json          TEXT NOT NULL,
  PRIMARY KEY (run_id, level, object_id)
);

-- ── Facts ───────────────────────────────────────────────────────────────────────────────
-- One row per (run, level, object, period). granularity='lifetime' (date_preset window) or 'day'.
CREATE TABLE IF NOT EXISTS insight (
  run_id            INTEGER NOT NULL REFERENCES extraction_run(run_id),
  level             TEXT NOT NULL,              -- ad | adset | campaign
  object_id         TEXT NOT NULL,
  granularity       TEXT NOT NULL,              -- lifetime | day
  date_start        TEXT NOT NULL, date_stop TEXT NOT NULL,
  spend             REAL, impressions INTEGER, reach INTEGER, frequency REAL,
  cpm REAL, cpp REAL,
  clicks INTEGER, unique_clicks INTEGER, ctr REAL, unique_ctr REAL, cpc REAL,
  link_clicks INTEGER, unique_link_clicks INTEGER, link_ctr REAL, cost_per_link_click REAL,
  outbound_clicks INTEGER,
  post_engagement INTEGER, cost_per_post_engagement REAL,
  result_indicator  TEXT,                       -- e.g. 'profile_visit_view', 'leadgen_grouped'
  result_value      REAL,
  cost_per_result   REAL,
  quality_ranking TEXT, engagement_rate_ranking TEXT, conversion_rate_ranking TEXT,
  video_plays INTEGER, video_thruplays INTEGER,
  video_p25 INTEGER, video_p50 INTEGER, video_p75 INTEGER, video_p95 INTEGER, video_p100 INTEGER,
  video_avg_time_s REAL, video_30s INTEGER, cost_per_thruplay REAL,
  PRIMARY KEY (run_id, level, object_id, granularity, date_start, date_stop)
);

-- The long tail: every action_type Meta reports (lead, comment, post_reaction, onsite_conversion.*, ...).
CREATE TABLE IF NOT EXISTS insight_action (
  run_id            INTEGER NOT NULL,
  level             TEXT NOT NULL,
  object_id         TEXT NOT NULL,
  granularity       TEXT NOT NULL,
  date_start        TEXT NOT NULL, date_stop TEXT NOT NULL,
  family            TEXT NOT NULL,              -- actions | unique_actions | cost_per_action_type | cost_per_unique_action_type | action_values
  action_type       TEXT NOT NULL,
  value             REAL,                       -- under the object's OWN attribution setting (what the UI shows); NULL if 0 there
  value_7d_click    REAL,                       -- requested window, comparable across objects
  value_1d_view     REAL,
  PRIMARY KEY (run_id, level, object_id, granularity, date_start, date_stop, family, action_type),
  FOREIGN KEY (run_id, level, object_id, granularity, date_start, date_stop)
    REFERENCES insight(run_id, level, object_id, granularity, date_start, date_stop)
);

-- Breakdowns (Detalhamento): age×gender, platform×position, region, device, hour.
CREATE TABLE IF NOT EXISTS insight_breakdown (
  run_id            INTEGER NOT NULL REFERENCES extraction_run(run_id),
  level             TEXT NOT NULL,
  object_id         TEXT NOT NULL,
  breakdown         TEXT NOT NULL,              -- 'age,gender' | 'publisher_platform,platform_position' | ...
  bucket            TEXT NOT NULL,              -- e.g. '35-44|female', 'instagram|reels'
  spend REAL, impressions INTEGER, reach INTEGER, clicks INTEGER, link_clicks INTEGER,
  actions_json      TEXT,
  PRIMARY KEY (run_id, level, object_id, breakdown, bucket)
);

-- Organic-side counters of the post behind each creative (NOT the same as ad-attributed actions).
CREATE TABLE IF NOT EXISTS post_engagement (
  run_id            INTEGER NOT NULL REFERENCES extraction_run(run_id),
  creative_id       TEXT NOT NULL REFERENCES creative(creative_id),
  fb_story_id TEXT, fb_comments INTEGER, fb_reactions INTEGER, fb_shares INTEGER,
  ig_media_id TEXT, ig_comments INTEGER, ig_likes INTEGER,
  PRIMARY KEY (run_id, creative_id)
);

-- Change history (Histórico de atividades) — dedups naturally across runs.
CREATE TABLE IF NOT EXISTS activity (
  event_time        TEXT NOT NULL,
  event_type        TEXT NOT NULL,
  object_id         TEXT NOT NULL,
  object_type       TEXT,                       -- CAMPAIGN_GROUP | CAMPAIGN | ADGROUP (internal names!)
  object_name       TEXT,
  translated_event_type TEXT,
  actor_name        TEXT,
  extra_json        TEXT,
  PRIMARY KEY (event_time, event_type, object_id)
);

-- Column dictionary: UI label (pt-BR) ↔ API field ↔ meaning. Seeded by load script.
CREATE TABLE IF NOT EXISTS ui_column (
  ui_label_pt       TEXT NOT NULL,
  api_field         TEXT NOT NULL,
  presets           TEXT,                       -- which UI presets show it
  levels            TEXT,                       -- campaign,adset,ad
  unit              TEXT,
  meaning           TEXT,
  gotcha            TEXT,
  PRIMARY KEY (ui_label_pt, api_field)
);

-- ── Views ───────────────────────────────────────────────────────────────────────────────
CREATE VIEW IF NOT EXISTS v_latest_run AS
  SELECT scope_kind, scope_value, MAX(run_id) AS run_id FROM extraction_run GROUP BY scope_kind, scope_value;

CREATE VIEW IF NOT EXISTS v_ad_lifetime AS
  SELECT a.property_code, a.variant, a.name AS ad_name, c.objective, s.name AS adset_name, s.is_shared_pool,
         i.*
  FROM insight i JOIN ad a ON a.ad_id = i.object_id
  JOIN adset s ON s.adset_id = a.adset_id JOIN campaign c ON c.campaign_id = a.campaign_id
  WHERE i.level = 'ad' AND i.granularity = 'lifetime';

CREATE VIEW IF NOT EXISTS v_action_pivot AS
  SELECT run_id, level, object_id, granularity, date_start,
    SUM(CASE WHEN family='actions' AND action_type='lead' THEN value END)                         AS leads,
    SUM(CASE WHEN family='actions' AND action_type='onsite_conversion.lead_grouped' THEN value END) AS form_leads,
    SUM(CASE WHEN family='actions' AND action_type='link_click' THEN value END)                   AS link_clicks,
    SUM(CASE WHEN family='actions' AND action_type='post_reaction' THEN value END)                AS reactions,
    SUM(CASE WHEN family='actions' AND action_type='comment' THEN value END)                      AS comments,
    SUM(CASE WHEN family='actions' AND action_type='onsite_conversion.post_save' THEN value END)  AS saves,
    SUM(CASE WHEN family='actions' AND action_type='post' THEN value END)                         AS shares,
    SUM(CASE WHEN family='actions' AND action_type='like' THEN value END)                         AS page_likes,
    SUM(CASE WHEN family='actions' AND action_type='video_view' THEN value END)                   AS video_views_3s,
    SUM(CASE WHEN family='actions' AND action_type='post_engagement' THEN value END)              AS post_engagement,
    SUM(CASE WHEN family='actions' AND action_type='onsite_conversion.messaging_conversation_started_7d' THEN value END) AS msg_started
  FROM insight_action GROUP BY run_id, level, object_id, granularity, date_start;
