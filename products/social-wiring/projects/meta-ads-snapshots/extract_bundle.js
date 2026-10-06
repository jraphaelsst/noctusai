// Meta Ads — in-page extraction recipe (run inside a logged-in adsmanager.facebook.com tab).
//
// Run with the browser MCP `javascript_tool` (top-level await works). It reads ONLY — GET requests to
// the same Graph v22 host the Ads Manager UI itself calls (adsmanager-graph.facebook.com), using the
// page's own session token (window.__accessToken). The token never leaves the page:
//   - every returned value goes through __clean() which drops `paging` (its URLs embed the token);
//   - the browser MCP blocks any output containing query-string/cookie data anyway.
//
// Usage (javascript_tool calls):
//   1) paste this file with CODE/ACT set. It STARTS a background job and returns immediately — a full pull
//      takes ~60s and javascript_tool aborts any evaluation at 45s (learned 2026-10-06).
//   1b) poll: `window.__jobStatus`  → 'running' | 'done' | 'error: …'; then `window.__jobSummary`
//   2) download (ASK THE USER FIRST — it is a file download):
//        const b=new Blob([JSON.stringify(__bundle)],{type:'application/json'});const a=document.createElement('a');
//        a.href=URL.createObjectURL(b);a.download=`meta_ads_${CODE}_${new Date().toISOString().slice(0,10)}.json`;a.click();
//   then: python load_bundle.py ~/Downloads/meta_ads_<CODE>_<date>.json <db> --scope-value <CODE>
//
// Why in-page Graph instead of reading the grid DOM: the grid is virtualized (rows/columns outside the
// viewport are not in the DOM), every number is locale-formatted ("R$ 1.586,23"), and the tool returns
// ~1 KB per call. The grid itself is fed by these same endpoints (see META-ADS-MANAGER-MAP.md §Data wiring).

const CODE = 'ONE10449';            // property code — matched against AD NAME (not campaign name)
const ACT = '873947475957808';      // One Consultoria Imobiliaria
const SINCE_ACTIVITY = '2026-01-01';

window.__jobStatus = 'running';
window.__job = (async () => {
window.__g = async (path, params = {}) => {
  const u = new URL('https://adsmanager-graph.facebook.com/v22.0/' + path);
  u.searchParams.set('access_token', window.__accessToken);
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, typeof v === 'string' ? v : JSON.stringify(v));
  return (await fetch(u, { credentials: 'include' })).json();
};
window.__gAll = async (path, params = {}) => {
  const out = []; let r = await __g(path, params); if (r.error) return r;
  out.push(...(r.data || []));
  while (r.paging && r.paging.next) { r = await (await fetch(r.paging.next, { credentials: 'include' })).json(); out.push(...(r.data || [])); }
  return { data: out };
};
window.__clean = (o) => JSON.parse(JSON.stringify(o, (k, v) =>
  (k === 'paging' || k === 'next' || k === 'previous') ? undefined
  : (typeof v === 'string' && /access_token/.test(v)) ? '[url]' : v));

const B = window.__bundle = { fetched_at: new Date().toISOString(), scope: CODE, errors: [] };
const ads0 = await __gAll(`act_${ACT}/ads`, {
  fields: 'id,campaign{id},adset{id},creative{id}',
  filtering: [{ field: 'ad.name', operator: 'CONTAIN', value: CODE.replace(/^ONE/i, '') }], limit: 200,
});
if (ads0.error) throw new Error(ads0.error.message);
const adIds = ads0.data.map(a => a.id);
const campIds = [...new Set(ads0.data.map(a => a.campaign.id))];
const setIds = [...new Set(ads0.data.map(a => a.adset.id))];
const crIds = [...new Set(ads0.data.map(a => a.creative.id))];
const one = async (id, fields) => __clean(await __g(id, { fields }));

B.account = await one(`act_${ACT}`, 'id,account_id,name,currency,timezone_name,business{id,name},amount_spent,account_status');
B.campaigns = await Promise.all(campIds.map(id => one(id, 'id,name,objective,status,effective_status,configured_status,created_time,updated_time,start_time,stop_time,buying_type,daily_budget,lifetime_budget,budget_remaining,bid_strategy,special_ad_categories')));
B.adsets = await Promise.all(setIds.map(id => one(id, 'id,name,campaign_id,status,effective_status,configured_status,created_time,updated_time,start_time,end_time,daily_budget,lifetime_budget,budget_remaining,optimization_goal,billing_event,bid_strategy,bid_amount,destination_type,attribution_spec,promoted_object,targeting,learning_stage_info')));
B.ads = await Promise.all(adIds.map(id => one(id, 'id,name,adset_id,campaign_id,status,effective_status,configured_status,created_time,updated_time,creative{id},ad_review_feedback,issues_info')));
B.creatives = await Promise.all(crIds.map(id => one(id, 'id,name,object_type,status,title,body,link_url,call_to_action_type,video_id,image_hash,effective_object_story_id,effective_instagram_media_id,instagram_permalink_url,object_story_spec,asset_feed_spec')));

const F = 'account_id,campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name,objective,optimization_goal,date_start,date_stop,spend,impressions,reach,frequency,cpm,cpp,clicks,ctr,cpc,unique_clicks,unique_ctr,inline_link_clicks,inline_link_click_ctr,cost_per_inline_link_click,unique_inline_link_clicks,outbound_clicks,outbound_clicks_ctr,inline_post_engagement,cost_per_inline_post_engagement,actions,unique_actions,action_values,cost_per_action_type,cost_per_unique_action_type,video_play_actions,video_thruplay_watched_actions,video_p25_watched_actions,video_p50_watched_actions,video_p75_watched_actions,video_p95_watched_actions,video_p100_watched_actions,video_avg_time_watched_actions,video_30_sec_watched_actions,cost_per_thruplay,quality_ranking,engagement_rate_ranking,conversion_rate_ranking,results,cost_per_result';
const base = { fields: F, level: 'ad', date_preset: 'maximum', limit: 500,
  filtering: [{ field: 'ad.id', operator: 'IN', value: adIds }], action_attribution_windows: ['7d_click', '1d_view'] };
const setBase = { ...base, level: 'adset', filtering: [{ field: 'adset.id', operator: 'IN', value: setIds }] };
const ins = async (p) => { const r = __clean(await __gAll(`act_${ACT}/insights`, p)); if (r.error) B.errors.push([JSON.stringify(p).slice(0, 80), r.error.message]); return r; };
B.ins_lifetime_ad = await ins(base);
B.ins_daily_ad = await ins({ ...base, time_increment: 1 });
B.ins_lifetime_adset = await ins(setBase);
B.ins_daily_adset = await ins({ ...setBase, time_increment: 1 });

const bf = 'ad_id,ad_name,date_start,date_stop,spend,impressions,reach,clicks,inline_link_clicks,actions,cost_per_action_type';
B.breakdowns = {};
for (const bd of ['age,gender', 'publisher_platform,platform_position', 'region', 'device_platform', 'hourly_stats_aggregated_by_advertiser_time_zone'])
  B.breakdowns[bd] = await ins({ fields: bf, level: 'ad', date_preset: 'maximum', limit: 500, filtering: base.filtering, breakdowns: bd });

const since = Math.floor(new Date(SINCE_ACTIVITY).getTime() / 1000);
const act = await __gAll(`act_${ACT}/activities`, { fields: 'event_time,event_type,translated_event_type,object_id,object_name,object_type,extra_data,actor_name', since, limit: 500 });
if (act.error) B.errors.push(['activities', act.error.message]);
const ids = new Set([...adIds, ...setIds, ...campIds]);
B.activities = act.data ? __clean(act.data.filter(e => ids.has(String(e.object_id)) || (e.object_name || '').includes(CODE.replace(/^ONE/i, '')))) : [];

B.posts = [];
for (const c of B.creatives) {
  const sid = c.effective_object_story_id, ig = c.effective_instagram_media_id;
  B.posts.push({ creative_id: c.id, fb_story_id: sid, ig_media_id: ig,
    fb: sid ? await one(sid, 'id,created_time,permalink_url,comments.summary(total_count).limit(0),reactions.summary(total_count).limit(0),shares') : null,
    ig: ig ? await one(ig, 'id,timestamp,permalink,comments_count,like_count,media_type') : null });
}

const s = JSON.stringify(B);
window.__jobSummary = { ads: adIds.length, campaigns: campIds.length, adsets: setIds.length, daily_rows: (B.ins_daily_ad.data || []).length,
   activities: B.activities.length, errors: B.errors, kb: Math.round(s.length / 1024),
   tokenFree: !s.includes(window.__accessToken.slice(0, 24)) };
window.__jobStatus = 'done';
})().catch(e => { window.__jobStatus = 'error: ' + e.message; });
'started';
