"""KPI pack for one property run: every number a report needs, as markdown tables (pt-BR number format).

Usage: python kpi_pack.py <db.sqlite> <CODE> [--run N] [--window-since YYYY-MM-DD]

- lifetime per ad (funnel + cost + fatigue), deltas vs the previous run of the same property
- video retention (hook, hold, curve points, quartiles, avg watch)
- daily series (spend / impressions / link clicks / leads)
- the "window" = ads that delivered since --window-since (default: day after the previous run) and
  their placement / age×gender breakdowns
- account activity since the previous run (UTC → BRT)

Definitions live in .claude/skills/noc-meta-ads-report/kpis.md. Leads = onsite_conversion.lead_grouped.

# NOC-REMEDIATE[promote-to-mcp-tool]: dev-phase script; folds into the noctus.* meta-ads MCP tool in phase 2
# (roadmap: project-history/roadmaps/meta-ads-analytics-2026-11.md).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timedelta

LEAD = "onsite_conversion.lead_grouped"
CURVE_POINTS = (1, 3, 5, 10, 14)
RANK = {"UNKNOWN": "?", "ABOVE_AVERAGE": "▲", "AVERAGE": "=", "BELOW_AVERAGE_35": "▼35",
        "BELOW_AVERAGE_20": "▼20", "BELOW_AVERAGE_10": "▼10"}


def br(v, d=2):
    if v is None:
        return "—"
    s = f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def pct(n, d, digits=1):
    return None if not d or n is None else 100.0 * n / d


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("code")
    ap.add_argument("--run", type=int)
    ap.add_argument("--window-since")
    a = ap.parse_args()
    con = sqlite3.connect(a.db)
    con.row_factory = sqlite3.Row
    q = lambda s, *p: con.execute(s, p).fetchall()  # noqa: E731

    runs = q("SELECT run_id, fetched_at FROM extraction_run WHERE scope_value=? ORDER BY run_id", a.code)
    if not runs:
        raise SystemExit(f"no extraction_run for {a.code}")
    run = a.run or runs[-1]["run_id"]
    prev = max((r for r in runs if r["run_id"] < run), key=lambda r: r["run_id"], default=None)
    cur_fetched = next(r["fetched_at"] for r in runs if r["run_id"] == run)
    stored = q("SELECT breakdown FROM insight_breakdown WHERE run_id=? AND breakdown LIKE '%@%' LIMIT 1", run)
    since = a.window_since or (stored[0]["breakdown"].split("@")[1] if stored else None) or (
        (datetime.fromisoformat(prev["fetched_at"][:10]) + timedelta(days=1)).date().isoformat() if prev else "0000")

    def life(run_id):
        rows = q("""SELECT i.*, a.name ad_name, a.effective_status st,
                    (SELECT objective FROM campaign c WHERE c.campaign_id=a.campaign_id) objective,
                    (SELECT name FROM campaign c WHERE c.campaign_id=a.campaign_id) campaign_name,
                    (SELECT value FROM insight_action x WHERE x.run_id=i.run_id AND x.level='ad' AND x.granularity='lifetime'
                       AND x.object_id=i.object_id AND x.family='actions' AND x.action_type=?) leads,
                    (SELECT value FROM insight_action x WHERE x.run_id=i.run_id AND x.level='ad' AND x.granularity='lifetime'
                       AND x.object_id=i.object_id AND x.family='actions' AND x.action_type='video_view') v3s,
                    v.play_curve_json curve, v.video_6s v6s
                  FROM insight i JOIN ad a ON a.ad_id=i.object_id
                  LEFT JOIN insight_video v ON v.run_id=i.run_id AND v.level='ad' AND v.object_id=i.object_id
                       AND v.granularity='lifetime'
                  WHERE i.run_id=? AND i.level='ad' AND i.granularity='lifetime' ORDER BY i.spend DESC""", LEAD, run_id)
        out = {r["object_id"]: dict(r) for r in rows}
        names = [v["ad_name"] for v in out.values()]
        for v in out.values():  # identical ad names in several campaigns → label with the campaign
            if names.count(v["ad_name"]) > 1:
                v["ad_name"] = f"{v['ad_name']} ⟨{(v['campaign_name'] or '?')[:22]} · …{v['object_id'][-4:]}⟩"
        return out

    L = life(run)
    P = life(prev["run_id"]) if prev else {}
    print(f"# KPI pack · {a.code} · run #{run} ({cur_fetched})" + (f" vs run #{prev['run_id']} ({prev['fetched_at']})" if prev else ""))
    print(f"\nWindow (recent activity) since: {since}\n")

    print("## Lifetime by objective (never blend objectives)\n")
    by_obj: dict[str, list[float]] = {}
    for r in L.values():
        x = by_obj.setdefault(r["objective"] or "?", [0, 0, 0, 0, 0, 0])
        x[0] += r["spend"] or 0
        x[1] += r["leads"] or 0
        x[2] += r["link_clicks"] or 0
        x[3] += r["impressions"] or 0
        if (r["result_indicator"] or "").startswith("conversion_leads"):
            x[5] += r["result_value"] or 0
        else:
            x[4] += r["result_value"] or 0
    print(table(["Objective", "Spend", "Form leads", "CPL", "Qualified (CRM)", "Cost/qualified", "Impr.", "Link clicks",
                 "Link CTR", "Other results"],
                [[k, br(v[0]), br(v[1], 0), br(v[0] / v[1]) if v[1] else "—", br(v[5], 0) if v[5] else "—",
                  br(v[0] / v[5]) if v[5] else "—", br(v[3], 0), br(v[2], 0), br(pct(v[2], v[3])) + "%", br(v[4], 0)]
                 for k, v in by_obj.items()]))
    print("\nQualified = result `conversion_leads` (CRM events sent back to Meta); only ad sets optimised for it report "
          "it, so cost/qualified divides the objective's whole spend (a lower bound on quality).")
    print()

    print("## Lifetime per ad\n")
    rows = []
    for r in L.values():
        p = P.get(r["object_id"])
        rows.append([r["ad_name"], r["st"], br(r["spend"]), br((r["spend"] or 0) - (p["spend"] or 0)) if p else "new",
                     br(r["leads"], 0), br(r["spend"] / r["leads"]) if r["leads"] else "—",
                     br(r["impressions"], 0), br(r["reach"], 0), br(r["frequency"]), br(r["cpm"]),
                     br(r["link_clicks"], 0), br(r["link_ctr"]) + "%" if r["link_ctr"] else "—",
                     br(r["cost_per_link_click"]),
                     br(pct(r["leads"], r["link_clicks"])) + "%" if r["leads"] and r["link_clicks"] else "—",
                     f"{r['result_indicator']}={br(r['result_value'], 0)}" if r["result_indicator"] else "—",
                     "/".join(RANK.get(x, x or "?") for x in (r["quality_ranking"], r["engagement_rate_ranking"],
                                                               r["conversion_rate_ranking"]))])
    print(table(["Ad", "Status", "Spend", "Δ spend", "Leads", "CPL", "Impr.", "Reach", "Freq.", "CPM", "Link clicks",
                 "Link CTR", "CPC link", "Click→lead", "Other result", "Rank Q/E/C"], rows))

    print("\n## Video retention (lifetime)\n")
    rows = []
    for r in L.values():
        if not r["v3s"] and not r["curve"]:
            continue
        c = json.loads(r["curve"]) if r["curve"] else None
        rows.append([r["ad_name"], br(pct(r["v3s"], r["impressions"])) + "%" if r["v3s"] else "—",
                     br(pct(r["video_thruplays"], r["v3s"])) + "%" if r["v3s"] and r["video_thruplays"] else "—",
                     br(pct(r["v6s"], r["v3s"])) + "%" if r["v6s"] and r["v3s"] else "—",
                     *[f"{c[s]}%" if c else "—" for s in CURVE_POINTS],
                     br(r["video_avg_time_s"], 0) + " s" if r["video_avg_time_s"] else "—",
                     " / ".join(br(r[k], 0) for k in ("video_p25", "video_p50", "video_p75", "video_p100"))])
    print(table(["Ad", "Hook (3s/impr)", "Hold (ThruPlay/3s)", "6s/3s", *[f"Curve {s}s" for s in CURVE_POINTS],
                 "Avg watch", "p25/p50/p75/p100"], rows))

    print("\n## Daily series (all property ads)\n")
    rows = q("""SELECT i.date_start d, SUM(i.spend) s, SUM(i.impressions) im, SUM(i.link_clicks) lc,
                (SELECT SUM(value) FROM insight_action x WHERE x.run_id=i.run_id AND x.level='ad' AND x.granularity='day'
                   AND x.date_start=i.date_start AND x.family='actions' AND x.action_type=?) leads
              FROM insight i WHERE i.run_id=? AND i.level='ad' AND i.granularity='day' AND i.date_start>=?
              GROUP BY i.date_start ORDER BY i.date_start""", LEAD, run, since)
    print(table(["Day", "Spend", "Impr.", "Link clicks", "Leads", "CPM"],
                [[r["d"], br(r["s"]), br(r["im"], 0), br(r["lc"], 0), br(r["leads"], 0), br(1000 * r["s"] / r["im"]) if r["im"] else "—"]
                 for r in rows]))

    win_ads = [r["object_id"] for r in q("""SELECT DISTINCT object_id FROM insight WHERE run_id=? AND level='ad'
                                            AND granularity='day' AND date_start>=? AND spend>0""", run, since)]
    if win_ads:
        ph = ",".join("?" * len(win_ads))
        print(f"\n## Window funnel (since {since}, {len(win_ads)} ads), per objective\n")
        for obj in sorted({L[i]["objective"] for i in win_ads if i in L}):
            ids = [i for i in win_ads if i in L and L[i]["objective"] == obj]
            ph2 = ",".join("?" * len(ids))
            wt = q(f"""SELECT SUM(spend) s, SUM(impressions) im, SUM(link_clicks) lc FROM insight WHERE run_id=? AND level='ad'
                       AND granularity='day' AND date_start>=? AND object_id IN ({ph2})""", run, since, *ids)[0]
            wl = q(f"""SELECT SUM(value) v FROM insight_action WHERE run_id=? AND level='ad' AND granularity='day'
                       AND date_start>=? AND family='actions' AND action_type=? AND object_id IN ({ph2})""",
                   run, since, LEAD, *ids)[0]["v"]
            wq = q(f"""SELECT SUM(result_value) v FROM insight WHERE run_id=? AND level='ad' AND granularity='day'
                       AND date_start>=? AND result_indicator LIKE 'conversion_leads%' AND object_id IN ({ph2})""",
                   run, since, *ids)[0]["v"]
            print(f"- **{obj}** ({len(ids)} ads): R$ {br(wt['s'])} · {br(wt['im'], 0)} impr. · CPM R$ "
                  f"{br(1000 * wt['s'] / wt['im']) if wt['im'] else '—'} · {br(wt['lc'], 0)} link clicks "
                  f"({br(pct(wt['lc'], wt['im']))}% link CTR) · {br(wl, 0)} form leads"
                  + (f" ({br(pct(wl, wt['lc']))}% of clicks · CPL R$ {br(wt['s'] / wl)})" if wl else "")
                  + (f" · **{br(wq, 0)} qualified** (R$ {br(wt['s'] / wq)} each, {br(pct(wq, wl), 0)}% of form leads)"
                     if wq else ""))
        has_win_bd = bool(q("SELECT 1 FROM insight_breakdown WHERE run_id=? AND breakdown LIKE ? LIMIT 1", run, f"%@{since}"))
        for bd, label in (("publisher_platform,platform_position", "Placement"), ("age,gender", "Age × gender")):
            agg: dict[str, list[float]] = {}
            for r in q(f"""SELECT bucket, spend, impressions, link_clicks, actions_json FROM insight_breakdown
                           WHERE run_id=? AND breakdown=? AND object_id IN ({ph})""", run,
                       f"{bd}@{since}" if has_win_bd else bd, *win_ads):
                x = agg.setdefault(r["bucket"], [0, 0, 0, 0])
                x[0] += r["spend"] or 0
                x[1] += r["impressions"] or 0
                x[2] += r["link_clicks"] or 0
                x[3] += sum(float(y["value"]) for y in json.loads(r["actions_json"] or "null") or [] if y["action_type"] == LEAD)
            tot = sum(v[0] for v in agg.values()) or 1
            print(f"\n### {label} (window ads, " + (f"{since} → fetch day" if has_win_bd else
                  "⚠️ LIFETIME of these ads — re-extract with --window-since for window-only numbers") + ")\n")
            print(table([label, "Spend", "Share", "Impr.", "Link clicks", "Leads", "CPM"],
                        [[k, br(v[0]), br(100 * v[0] / tot, 0) + "%", br(v[1], 0), br(v[2], 0), br(v[3], 0),
                          br(1000 * v[0] / v[1]) if v[1] else "—"]
                         for k, v in sorted(agg.items(), key=lambda kv: -kv[1][0]) if v[0] > 0.5]))

    act_from = prev["fetched_at"][:19] if prev else since
    print(f"\n## Activity since {'run #' + str(prev['run_id']) if prev else since} (BRT)\n")
    ids = list(L) + [r["adset_id"] for r in q("SELECT DISTINCT adset_id FROM ad WHERE ad_id IN (%s)" % ",".join("?" * len(L)), *L)] \
        + [r["campaign_id"] for r in q("SELECT DISTINCT campaign_id FROM ad WHERE ad_id IN (%s)" % ",".join("?" * len(L)), *L)]
    if True:
        rows = q(f"""SELECT event_time, translated_event_type, object_type, object_name, actor_name FROM activity
                    WHERE event_time > ? AND event_time <= ? AND object_id IN ({",".join("?" * len(ids))})
                    ORDER BY event_time""", act_from, cur_fetched[:19], *ids)
        conv = lambda t: (datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S") - timedelta(hours=3)).strftime("%m-%d %H:%M")  # noqa: E731
        print(table(["When", "Event", "Level", "Object", "By"],
                    [[conv(r["event_time"]), r["translated_event_type"], r["object_type"], r["object_name"],
                      "Meta" if r["actor_name"] == "Meta" else "operator"] for r in rows]))

    camp = {r["object_id"]: json.loads(r["raw_json"]) for r in
            q("SELECT object_id, raw_json FROM object_snapshot WHERE run_id=? AND level='campaign'", run)}
    sets = q("""SELECT s.adset_id, s.name, o.raw_json FROM adset s JOIN object_snapshot o ON o.object_id=s.adset_id
                AND o.level='adset' AND o.run_id=? WHERE s.adset_id IN
                (SELECT adset_id FROM ad WHERE ad_id IN (SELECT object_id FROM insight WHERE run_id=? AND level='ad'))""", run, run)
    print("\n## Ad set configuration (now)\n")
    rows = []
    for s in sets:
        j = json.loads(s["raw_json"])
        t = j.get("targeting") or {}
        c = camp.get(j.get("campaign_id"), {})
        budget = (br(int(j["daily_budget"]) / 100) if j.get("daily_budget") else
                  (br(int(c["daily_budget"]) / 100) + " (campaign CBO)" if c.get("daily_budget") else "—"))
        sib = (j.get("ads") or {}).get("data") or []
        other = [x for x in sib if a.code.upper() not in (x.get("name") or "").upper()]
        other_on = [x for x in other if x.get("effective_status") == "ACTIVE"]
        pool = ("exclusive" if sib and not other else
                f"SHARED: {len(other)} other ads ({len(other_on)} active)" if sib else "?")
        rows.append([s["name"], j.get("effective_status"), budget, pool,
                     j.get("optimization_goal"), ",".join((j.get("learning_stage_info") or {}).get("attribution_windows") or [])
                     or ",".join(f"{x.get('event_type')}:{x.get('window_days')}d" for x in j.get("attribution_spec") or []),
                     ",".join(t.get("publisher_platforms") or []) + " · " + ",".join(
                         (t.get("instagram_positions") or []) + (t.get("facebook_positions") or [])),
                     f"{t.get('age_min')}–{t.get('age_max')}", {None: "all", "[1]": "men", "[2]": "women"}.get(
                         json.dumps(t.get("genders")) if t.get("genders") not in (None, [0]) else None, "all"),
                     (j.get("learning_stage_info") or {}).get("status", "—")])
    print(table(["Ad set", "Status", "Daily budget", "Pool", "Optimization", "Attribution", "Placements", "Age", "Gender",
                 "Learning"], rows))


if __name__ == "__main__":
    main()
