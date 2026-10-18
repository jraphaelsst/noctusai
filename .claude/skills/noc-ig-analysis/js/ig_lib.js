// noc-ig-analysis — in-page helpers. Paste the whole file into javascript_tool ONCE per
// page load (instagram.com tab, logged in); then call window.IG.* from later snippets.
// Rules baked in: pace with fetch('/robots.txt') (background-tab timers are throttled),
// never return CDN URLs (the tool output filter blocks them), persist to localStorage.
window.IG = (() => {
  const H = { headers: { 'X-IG-App-ID': '936619743392459' } };
  const A = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_';
  const pace = () => fetch('/robots.txt');
  const toId = (code) => { let id = 0n; for (const c of code.slice(0, 11)) id = id * 64n + BigInt(A.indexOf(c)); return id.toString(); };
  const status = {};
  const save = (k, v) => localStorage.setItem(k, JSON.stringify(v));
  const load = (k, d = null) => JSON.parse(localStorage.getItem(k) || 'null') ?? d;
  const dash = {};

  async function info(code) {
    const r = await fetch(`/api/v1/media/${toId(code)}/info/`, H);
    if (r.status !== 200) return { code, err: r.status };
    const it = (await r.json()).items[0];
    dash[code] = it.video_dash_manifest || null;
    return {
      code, t: it.taken_at, plays: it.play_count || it.ig_play_count || 0, likes: it.like_count,
      com: it.comment_count, dur: it.video_duration || 0, user: it.user?.username,
      pinned: !!(it.timeline_pinned_user_ids?.length || it.clips_tab_pinned_user_ids?.length),
      cap: it.caption?.text || '', music: it.clips_metadata?.music_info?.music_asset_info?.title || null,
      orig: it.clips_metadata?.original_sound_info ? 1 : 0, carousel: (it.carousel_media || []).length,
    };
  }

  // Grid is virtualized: accumulate codes WHILE scrolling, never read the DOM once at the end.
  function gridCodes(key, want = 60, kind = 'reel') {
    status[key] = { n: 0, done: false };
    const acc = new Set(load(key, []));
    (async () => {
      const grab = () => document.querySelectorAll(`a[href*="/${kind}/"]`).forEach(a => acc.add(a.getAttribute('href').split(`/${kind}/`)[1].split('/')[0]));
      window.scrollTo(0, 0); await pace(); grab();
      let last = 0, still = 0;
      for (let i = 0; i < 300 && acc.size < want; i++) {
        window.scrollBy(0, 700); await pace(); await pace(); grab();
        status[key].n = acc.size;
        if (acc.size === last) { if (++still > 25) break; } else { still = 0; last = acc.size; }
      }
      save(key, [...acc]); status[key].done = true;
    })();
    return 'started';
  }

  function infoAll(codesKey, metaKey) {
    status[metaKey] = { n: 0, done: false };
    (async () => {
      const meta = load(metaKey, []); const have = new Set(meta.filter(m => !m.err).map(m => m.code));
      for (const c of load(codesKey, [])) {
        if (have.has(c)) continue;
        meta.push(await info(c)); status[metaKey].n++; save(metaKey, meta); await pace();
      }
      status[metaKey].done = true;
    })();
    return 'started';
  }

  // All top-level comments + every reply thread, deduped by pk.
  function comments(code, key) {
    status[key] = { n: 0, done: false, err: null };
    (async () => {
      try {
        const id = toId(code), out = [], seen = new Set();
        const m = (c, parent) => ({ pk: String(c.pk), user: c.user?.username, t: c.created_at, text: c.text, likes: c.comment_like_count, nchild: c.child_comment_count || 0, parent: parent || null });
        const push = (c, parent) => { if (!seen.has(String(c.pk))) { seen.add(String(c.pk)); out.push(m(c, parent)); } };
        let min = null;
        for (let pg = 0; pg < 200; pg++) {
          const j = await (await fetch(`/api/v1/media/${id}/comments/?can_support_threading=true&permalink_enabled=false` + (min ? `&min_id=${encodeURIComponent(min)}` : ''), H)).json();
          for (const c of j.comments || []) { push(c); for (const p of c.preview_child_comments || []) push(p, String(c.pk)); }
          status[key].n = out.length; if (!j.next_min_id) break; min = j.next_min_id; await pace();
        }
        for (const c of out.filter(c => !c.parent && c.nchild > 0)) {
          let mx = null;
          for (let pg = 0; pg < 50; pg++) {
            const j = await (await fetch(`/api/v1/media/${id}/comments/${c.pk}/child_comments/` + (mx ? `?max_id=${encodeURIComponent(mx)}` : ''), H)).json();
            for (const ch of j.child_comments || []) push(ch, c.pk);
            status[key].n = out.length; await pace();
            if (j.has_more_tail_child_comments && j.next_max_child_cursor) mx = j.next_max_child_cursor; else break;
          }
        }
        save(key, out); status[key].done = true;
      } catch (e) { status[key].err = String(e); }
    })();
    return 'started';
  }

  // Downloads (ASK THE USER FIRST): kind 'audio' = the audio AdaptationSet, 'video' = the lowest video rep.
  function download(codes, prefix, kind = 'audio', key = 'dl') {
    status[key] = { n: 0, bytes: 0, err: [], done: false };
    (async () => {
      for (let i = 0; i < codes.length; i++) {
        const c = codes[i];
        try {
          if (!dash[c]) await info(c);
          const doc = new DOMParser().parseFromString(dash[c], 'text/xml');
          const sets = [...doc.querySelectorAll('AdaptationSet')];
          const set = sets.find(s => s.getAttribute('contentType') === kind);
          const reps = [...set.querySelectorAll('Representation')].sort((a, b) => +a.getAttribute('bandwidth') - +b.getAttribute('bandwidth'));
          const b = await (await fetch(reps[0].querySelector('BaseURL').textContent)).blob();
          const a = document.createElement('a'); a.href = URL.createObjectURL(b);
          a.download = `${prefix}_${String(i + 1).padStart(2, '0')}_${c}.${kind === 'audio' ? 'm4a' : 'mp4'}`;
          document.body.appendChild(a); a.click(); status[key].n++; status[key].bytes += b.size;
        } catch (e) { status[key].err.push(`${c}: ${e}`); }
        await pace(); await pace();
      }
      status[key].done = true;
    })();
    return 'started';
  }

  // Wait <= ~25 s for a background job (keep each tool call under ~30 s or the extension drops).
  async function wait(key) {
    for (let i = 0; i < 25 && !status[key]?.done && !status[key]?.err; i++) await pace().then(() => new Promise(r => setTimeout(r, 1000)));
    return JSON.stringify(status[key]);
  }

  // Export: render text into <article><pre>, then read it with get_page_text.
  function exportText(text) { document.body.innerHTML = '<article><pre id="x"></pre></article>'; document.getElementById('x').textContent = text; return text.length; }

  function cleanup(prefix) { Object.keys(localStorage).filter(k => k.startsWith(prefix)).forEach(k => localStorage.removeItem(k)); return 'cleaned'; }

  return { toId, info, gridCodes, infoAll, comments, download, wait, exportText, cleanup, load, save, status, dash };
})();
'IG ready';
