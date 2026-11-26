"""API extractor: same bundle shape as extract_bundle.js, via the system-user token (no browser).

# NOC-REMEDIATE[promote-to-mcp-tool]: dev-phase script; becomes a noctus.* MCP tool + seed MetaAdapter
# ad-level insights in phase 2 of the meta-ads-report work (roadmap: project-history/roadmaps/meta-ads-analytics-2026-11.md).

Usage: python extract_api.py <CODE> <out.json> [--env <path/.env>] [--window-since YYYY-MM-DD]

--window-since also pulls every breakdown for [since, today] (breakdowns_window), so the report can
read placement / age for the recent burst instead of the ads' whole lifetime.
Read-only GETs on graph.facebook.com. Token never written to the bundle.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

ACT = "873947475957808"
VER = "v27.0"  # v22 is silently served as v25 (expired versions auto-upgrade); pin the current one
SINCE_ACTIVITY = "2026-01-01"


def _token(env_path: str) -> str:
    for line in open(env_path):
        if line.startswith("META_SYSTEM_USER_TOKEN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("META_SYSTEM_USER_TOKEN missing")


TOKEN = ""


def g(path: str, params: dict | None = None) -> dict:
    p = {k: (v if isinstance(v, str) else json.dumps(v)) for k, v in (params or {}).items()}
    p["access_token"] = TOKEN
    url = f"https://graph.facebook.com/{VER}/{path}?" + urllib.parse.urlencode(p)
    for attempt in range(4):
        try:
            return json.load(urllib.request.urlopen(url, timeout=120))
        except urllib.error.HTTPError as e:
            body = json.load(e)
            code = body.get("error", {}).get("code")
            if code in (4, 17, 32, 613, 80004) and attempt < 3:  # throttling
                time.sleep(20 * (attempt + 1))
                continue
            return body
    return {"error": {"message": "retries exhausted"}}


def g_all(path: str, params: dict | None = None) -> dict:
    out, r = [], g(path, params)
    if "error" in r:
        return r
    out += r.get("data", [])
    while r.get("paging", {}).get("next"):
        nxt = r["paging"]["next"]
        r = json.load(urllib.request.urlopen(nxt, timeout=120))
        out += r.get("data", [])
    return {"data": out}


def clean(o):
    return json.loads(json.dumps(o, default=str).replace(TOKEN, "[token]")) if TOKEN else o


def main() -> None:
    global TOKEN
    code, out = sys.argv[1], sys.argv[2]
    env = sys.argv[sys.argv.index("--env") + 1] if "--env" in sys.argv else ".env"
    TOKEN = _token(env)
    digits = code.upper().removeprefix("ONE")
    B: dict = {"fetched_at": datetime.now(timezone.utc).isoformat(), "scope": code, "errors": [],
               "source": "graph_api_system_user", "graph_version": VER}
    ads0 = g_all(f"act_{ACT}/ads", {"fields": "id,name,campaign{id},adset{id},creative{id}",
                                     "filtering": [{"field": "ad.name", "operator": "CONTAIN", "value": digits}],
                                     "limit": 200})
    if "error" in ads0:
        raise SystemExit(ads0["error"])
    # CONTAIN '10449' also matches '104490' etc. Keep exact property-code matches only.
    rx = re.compile(rf"\bONE{digits}\b", re.I)
    ads0["data"] = [a for a in ads0["data"] if rx.search(a.get("name", ""))]
    ad_ids = [a["id"] for a in ads0["data"]]
    camp_ids = sorted({a["campaign"]["id"] for a in ads0["data"]})
    set_ids = sorted({a["adset"]["id"] for a in ads0["data"]})
    cr_ids = sorted({a["creative"]["id"] for a in ads0["data"]})

    def one(i, f):
        return clean({k: v for k, v in g(i, {"fields": f}).items() if k != "paging"})

    with ThreadPoolExecutor(8) as ex:
        B["account"] = one(f"act_{ACT}", "id,account_id,name,currency,timezone_name,business{id,name},amount_spent,account_status")
        B["campaigns"] = list(ex.map(lambda i: one(i, "id,name,objective,status,effective_status,configured_status,created_time,updated_time,start_time,stop_time,buying_type,daily_budget,lifetime_budget,budget_remaining,bid_strategy,special_ad_categories"), camp_ids))
        B["adsets"] = list(ex.map(lambda i: one(i, "id,name,campaign_id,status,effective_status,configured_status,created_time,updated_time,start_time,end_time,daily_budget,lifetime_budget,budget_remaining,optimization_goal,billing_event,bid_strategy,bid_amount,destination_type,attribution_spec,promoted_object,targeting,learning_stage_info,ads.limit(300){name,effective_status}"), set_ids))
        B["ads"] = list(ex.map(lambda i: one(i, "id,name,adset_id,campaign_id,status,effective_status,configured_status,created_time,updated_time,creative{id},ad_review_feedback,issues_info"), ad_ids))
        B["creatives"] = list(ex.map(lambda i: one(i, "id,name,object_type,status,title,body,link_url,call_to_action_type,video_id,image_hash,effective_object_story_id,effective_instagram_media_id,instagram_permalink_url,object_story_spec,asset_feed_spec,thumbnail_url"), cr_ids))

    F = ("account_id,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,objective,optimization_goal,date_start,date_stop,"
         "spend,impressions,reach,frequency,cpm,cpp,clicks,ctr,cpc,unique_clicks,unique_ctr,inline_link_clicks,inline_link_click_ctr,"
         "cost_per_inline_link_click,unique_inline_link_clicks,outbound_clicks,outbound_clicks_ctr,inline_post_engagement,"
         "cost_per_inline_post_engagement,actions,unique_actions,action_values,cost_per_action_type,cost_per_unique_action_type,"
         "video_play_actions,video_thruplay_watched_actions,video_p25_watched_actions,video_p50_watched_actions,"
         "video_p75_watched_actions,video_p95_watched_actions,video_p100_watched_actions,video_avg_time_watched_actions,"
         "video_30_sec_watched_actions,video_6_sec_watched_actions,video_continuous_2_sec_watched_actions,video_play_curve_actions,cost_per_thruplay,"
         "quality_ranking,engagement_rate_ranking,conversion_rate_ranking,results,cost_per_result")
    base = {"fields": F, "level": "ad", "date_preset": "maximum", "limit": 500,
            "filtering": [{"field": "ad.id", "operator": "IN", "value": ad_ids}],
            "action_attribution_windows": ["7d_click", "1d_view"]}
    set_base = {**base, "level": "adset", "filtering": [{"field": "adset.id", "operator": "IN", "value": set_ids}]}

    def ins(p):
        r = clean(g_all(f"act_{ACT}/insights", p))
        if "error" in r:
            B["errors"].append([json.dumps(p)[:80], r["error"].get("message")])
        return r

    B["ins_lifetime_ad"] = ins(base)
    B["ins_daily_ad"] = ins({**base, "time_increment": 1})
    B["ins_lifetime_adset"] = ins(set_base)
    B["ins_daily_adset"] = ins({**set_base, "time_increment": 1})

    bf = ("ad_id,ad_name,date_start,date_stop,spend,impressions,reach,clicks,inline_link_clicks,actions,cost_per_action_type,"
          "video_p25_watched_actions,video_thruplay_watched_actions")
    B["breakdowns"] = {}
    for bd in ["age,gender", "publisher_platform,platform_position", "region", "device_platform",
               "hourly_stats_aggregated_by_advertiser_time_zone"]:
        B["breakdowns"][bd] = ins({"fields": bf, "level": "ad", "date_preset": "maximum", "limit": 500,
                                   "filtering": base["filtering"], "breakdowns": bd})

    if "--window-since" in sys.argv:
        ws = sys.argv[sys.argv.index("--window-since") + 1]
        tr = {"since": ws, "until": datetime.now(timezone.utc).date().isoformat()}
        B["breakdowns_window"] = {"since": ws, "data": {}}
        for bd in B["breakdowns"]:
            B["breakdowns_window"]["data"][bd] = ins({"fields": bf, "level": "ad", "time_range": tr, "limit": 500,
                                                      "filtering": base["filtering"], "breakdowns": bd})

    since = int(datetime.fromisoformat(SINCE_ACTIVITY).replace(tzinfo=timezone.utc).timestamp())
    act = g_all(f"act_{ACT}/activities", {"fields": "event_time,event_type,translated_event_type,object_id,object_name,object_type,extra_data,actor_name",
                                         "since": since, "limit": 500})
    if "error" in act:
        B["errors"].append(["activities", act["error"].get("message")])
    ids = set(ad_ids + set_ids + camp_ids)
    B["activities"] = clean([e for e in act.get("data", []) if str(e.get("object_id")) in ids or digits in (e.get("object_name") or "")])

    B["posts"] = []
    for c in B["creatives"]:
        sid, ig = c.get("effective_object_story_id"), c.get("effective_instagram_media_id")
        B["posts"].append({"creative_id": c["id"], "fb_story_id": sid, "ig_media_id": ig,
                           "fb": one(sid, "id,created_time,permalink_url,comments.summary(total_count).limit(0),reactions.summary(total_count).limit(0),shares") if sid else None,
                           "ig": one(ig, "id,timestamp,permalink,comments_count,like_count,media_type") if ig else None})
    s = json.dumps(B)
    assert TOKEN not in s, "token leaked into bundle"
    open(out, "w").write(s)
    print(json.dumps({"ads": len(ad_ids), "campaigns": len(camp_ids), "adsets": len(set_ids),
                      "daily_rows": len(B["ins_daily_ad"].get("data", [])), "activities": len(B["activities"]),
                      "errors": B["errors"], "kb": len(s) // 1024}))


if __name__ == "__main__":
    main()
