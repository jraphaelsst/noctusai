"""Load a Meta Ads raw bundle (JSON produced in-page from Ads Manager) into the SQLite snapshot store.

Usage: python load_bundle.py <bundle.json> <db.sqlite> --scope-kind property --scope-value ONE10449

Each invocation creates ONE extraction_run; facts are keyed by run_id so weekly runs never overwrite
each other (append-only "screenshots"). Dimensions (campaign/adset/ad/creative) are upserted to latest
state, and their raw JSON is kept per run in object_snapshot.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).with_name("schema.sql")
UI_COLUMNS = Path(__file__).with_name("ui_columns.sql")
PROPERTY_RE = re.compile(r"\b(ONE\d{3,6})\b\s*(.*)$", re.IGNORECASE)
ACTION_FAMILIES = ("actions", "unique_actions", "cost_per_action_type", "cost_per_unique_action_type", "action_values")
VIDEO_FIELDS = {
    "video_play_actions": "video_plays", "video_thruplay_watched_actions": "video_thruplays",
    "video_p25_watched_actions": "video_p25", "video_p50_watched_actions": "video_p50",
    "video_p75_watched_actions": "video_p75", "video_p95_watched_actions": "video_p95",
    "video_p100_watched_actions": "video_p100", "video_avg_time_watched_actions": "video_avg_time_s",
    "video_30_sec_watched_actions": "video_30s", "cost_per_thruplay": "cost_per_thruplay",
}


def _num(v):
    if v is None or v == "":
        return None
    return float(v)


def _int(v):
    return None if v in (None, "") else int(float(v))


def _first_action_value(lst):
    """Video fields come as [{'action_type': 'video_view', 'value': 'N'}] — take the summed value."""
    if not lst:
        return None
    return sum(float(x["value"]) for x in lst)


def _only(obj: dict, what: str) -> dict:
    if "error" in obj:
        raise RuntimeError(f"{what} came back with a Graph error: {obj['error']}")
    return obj


def parse_property(name: str) -> tuple[str | None, str | None]:
    m = PROPERTY_RE.search(name or "")
    if not m:
        return None, None
    variant = m.group(2).strip() or None
    return m.group(1).upper(), variant


def load(bundle_path: Path, db_path: Path, scope_kind: str, scope_value: str) -> int:
    b = json.loads(bundle_path.read_text())
    if b.get("errors"):
        raise RuntimeError(f"bundle carries extraction errors, refusing to load partial data: {b['errors']}")
    con = sqlite3.connect(db_path)
    con.executescript(SCHEMA.read_text())
    con.executescript(UI_COLUMNS.read_text())
    cur = con.cursor()

    acct = _only(b["account"], "account")
    account_id = acct["account_id"]
    cur.execute(
        "INSERT INTO extraction_run(fetched_at, source, account_id, scope_kind, scope_value, date_preset, attribution, graph_version, raw_path)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (b["fetched_at"], "graph_in_page", account_id, scope_kind, scope_value, "maximum", "7d_click,1d_view", "v22.0", str(bundle_path)),
    )
    run_id = cur.lastrowid

    biz = acct.get("business") or {}
    cur.execute(
        "INSERT INTO account VALUES (?,?,?,?,?,?) ON CONFLICT(account_id) DO UPDATE SET name=excluded.name, currency=excluded.currency,"
        " timezone_name=excluded.timezone_name, business_id=excluded.business_id, business_name=excluded.business_name",
        (account_id, acct.get("name"), acct.get("currency"), acct.get("timezone_name"), biz.get("id"), biz.get("name")),
    )
    cur.execute("INSERT INTO object_snapshot VALUES (?,?,?,?)", (run_id, "account", account_id, json.dumps(acct)))

    for c in b["campaigns"]:
        _only(c, "campaign")
        cur.execute(
            "INSERT OR REPLACE INTO campaign VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (c["id"], account_id, c["name"], c.get("objective"), c.get("buying_type"), c.get("status"), c.get("effective_status"),
             c.get("created_time"), c.get("start_time"), c.get("stop_time"), _int(c.get("daily_budget")), _int(c.get("lifetime_budget")),
             c.get("bid_strategy")),
        )
        cur.execute("INSERT INTO object_snapshot VALUES (?,?,?,?)", (run_id, "campaign", c["id"], json.dumps(c)))

    # An ad set is a "shared pool" when its name carries no property code (it hosts ads of many properties).
    for s in b["adsets"]:
        _only(s, "adset")
        shared = 0 if parse_property(s["name"])[0] else 1
        cur.execute(
            "INSERT OR REPLACE INTO adset VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s["id"], s["campaign_id"], s["name"], s.get("status"), s.get("effective_status"), s.get("created_time"),
             s.get("start_time"), s.get("end_time"), _int(s.get("daily_budget")), _int(s.get("lifetime_budget")),
             s.get("optimization_goal"), s.get("billing_event"), s.get("bid_strategy"), s.get("destination_type"), shared,
             json.dumps(s.get("targeting")), json.dumps(s.get("promoted_object")), json.dumps(s.get("attribution_spec"))),
        )
        cur.execute("INSERT INTO object_snapshot VALUES (?,?,?,?)", (run_id, "adset", s["id"], json.dumps(s)))

    for cr in b["creatives"]:
        _only(cr, "creative")
        cur.execute(
            "INSERT OR REPLACE INTO creative VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (cr["id"], cr.get("name"), cr.get("object_type"), cr.get("title"), cr.get("body"), cr.get("call_to_action_type"),
             cr.get("video_id"), cr.get("image_hash"), cr.get("effective_object_story_id"), cr.get("effective_instagram_media_id"),
             cr.get("instagram_permalink_url")),
        )
        cur.execute("INSERT INTO object_snapshot VALUES (?,?,?,?)", (run_id, "creative", cr["id"], json.dumps(cr)))

    for a in b["ads"]:
        _only(a, "ad")
        code, variant = parse_property(a["name"])
        cur.execute(
            "INSERT OR REPLACE INTO ad VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (a["id"], a["adset_id"], a["campaign_id"], (a.get("creative") or {}).get("id"), a["name"], code, variant,
             a.get("status"), a.get("effective_status"), a.get("created_time"), a.get("updated_time")),
        )
        cur.execute("INSERT INTO object_snapshot VALUES (?,?,?,?)", (run_id, "ad", a["id"], json.dumps(a)))

    def put_insights(rows: list[dict], level: str, granularity: str) -> None:
        id_key = f"{level}_id"
        for r in rows:
            res = (r.get("results") or [{}])[0]
            res_val = (res.get("values") or [{}])[0].get("value")
            cpr = (r.get("cost_per_result") or [{}])[0]
            cpr_val = (cpr.get("values") or [{}])[0].get("value")
            link_cpc = r.get("cost_per_inline_link_click")
            video = {col: (_num(r.get(src)) if src == "cost_per_thruplay" and not isinstance(r.get(src), list)
                           else _first_action_value(r.get(src))) for src, col in VIDEO_FIELDS.items()}
            key = (run_id, level, r[id_key], granularity, r["date_start"], r["date_stop"])
            cur.execute(
                "INSERT INTO insight VALUES (" + ",".join("?" * 40) + ")",
                key + (
                    _num(r.get("spend")), _int(r.get("impressions")), _int(r.get("reach")), _num(r.get("frequency")),
                    _num(r.get("cpm")), _num(r.get("cpp")),
                    _int(r.get("clicks")), _int(r.get("unique_clicks")), _num(r.get("ctr")), _num(r.get("unique_ctr")), _num(r.get("cpc")),
                    _int(r.get("inline_link_clicks")), _int(r.get("unique_inline_link_clicks")), _num(r.get("inline_link_click_ctr")),
                    _num(link_cpc),
                    _first_action_value(r.get("outbound_clicks")),
                    _int(r.get("inline_post_engagement")), _num(r.get("cost_per_inline_post_engagement")),
                    res.get("indicator"), _num(res_val), _num(cpr_val),
                    r.get("quality_ranking"), r.get("engagement_rate_ranking"), r.get("conversion_rate_ranking"),
                    video["video_plays"], video["video_thruplays"], video["video_p25"], video["video_p50"], video["video_p75"],
                    video["video_p95"], video["video_p100"], video["video_avg_time_s"], video["video_30s"], video["cost_per_thruplay"],
                ),
            )
            for fam in ACTION_FAMILIES:
                for x in r.get(fam) or []:
                    cur.execute("INSERT INTO insight_action VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                key + (fam, x["action_type"], _num(x.get("value")), _num(x.get("7d_click")), _num(x.get("1d_view"))))

    put_insights(b["ins_lifetime_ad"]["data"], "ad", "lifetime")
    put_insights(b["ins_daily_ad"]["data"], "ad", "day")
    put_insights(b["ins_lifetime_adset"]["data"], "adset", "lifetime")
    put_insights(b["ins_daily_adset"]["data"], "adset", "day")

    for bd, payload in b["breakdowns"].items():
        if "error" in payload:
            raise RuntimeError(f"breakdown {bd} errored: {payload['error']}")
        dims = bd.split(",")
        for r in payload["data"]:
            bucket = "|".join(str(r.get(d)) for d in dims)
            cur.execute(
                "INSERT INTO insight_breakdown VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, "ad", r["ad_id"], bd, bucket, _num(r.get("spend")), _int(r.get("impressions")), _int(r.get("reach")),
                 _int(r.get("clicks")), _int(r.get("inline_link_clicks")), json.dumps(r.get("actions"))),
            )

    for p in b["posts"]:
        fb, ig = p.get("fb") or {}, p.get("ig") or {}
        cur.execute(
            "INSERT INTO post_engagement VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, p["creative_id"], p.get("fb_story_id"),
             None if "error" in fb else ((fb.get("comments") or {}).get("summary") or {}).get("total_count"),
             None if "error" in fb else ((fb.get("reactions") or {}).get("summary") or {}).get("total_count"),
             None if "error" in fb else (fb.get("shares") or {}).get("count", 0),
             p.get("ig_media_id"),
             None if "error" in ig else ig.get("comments_count"),
             None if "error" in ig else ig.get("like_count")),
        )

    for e in b["activities"]:
        cur.execute(
            "INSERT OR IGNORE INTO activity VALUES (?,?,?,?,?,?,?,?)",
            (e["event_time"], e["event_type"], str(e["object_id"]), e.get("object_type"), e.get("object_name"),
             e.get("translated_event_type"), e.get("actor_name"), e.get("extra_data")),
        )

    con.commit()
    con.close()
    return run_id


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle", type=Path)
    ap.add_argument("db", type=Path)
    ap.add_argument("--scope-kind", default="property")
    ap.add_argument("--scope-value", required=True)
    a = ap.parse_args()
    print("run_id", load(a.bundle, a.db, a.scope_kind, a.scope_value))
