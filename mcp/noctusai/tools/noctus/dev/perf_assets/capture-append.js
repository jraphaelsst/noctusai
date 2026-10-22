// noc perf capture v1 — APPEND the current page load to localStorage['__noc_perf'].
// Run once per page, after the page has settled (network idle). A full navigation resets
// the Resource Timing buffer, so pages accumulate in localStorage across loads.
// Records only paths (ids are templated later by the tool) and query KEYS, never values,
// never bodies or headers — safe to run on third-party apps.
(() => {
  const K = '__noc_perf';
  const r = (x) => Math.round(x * 10) / 10;
  const nav = performance.getEntriesByType('navigation')[0];
  const api = [];
  const assets = {};
  for (const e of performance.getEntriesByType('resource')) {
    let u;
    try { u = new URL(e.name); } catch { continue; }
    const kind = (e.initiatorType === 'fetch' || e.initiatorType === 'xmlhttprequest') ? 'api' : e.initiatorType;
    const where = (u.host === location.host ? '' : u.host) + u.pathname
      + (u.search ? '?' + [...u.searchParams.keys()].join('&') : '');
    if (kind === 'api') {
      const app = (e.serverTiming || []).find((s) => s.name === 'app');
      api.push([where, r(e.startTime), r(e.duration),
        e.responseStart > 0 ? r(e.responseStart - e.startTime) : null,
        app ? r(app.duration) : null, e.transferSize || 0, e.responseStatus || 0]);
    } else {
      const a = (assets[kind] ||= { n: 0, bytes: 0, end: 0 });
      a.n += 1; a.bytes += e.transferSize || 0; a.end = Math.max(a.end, r(e.responseEnd));
    }
  }
  const page = {
    path: location.pathname,
    at: new Date().toISOString(),
    nav: nav ? { ttfb: r(nav.responseStart), dcl: r(nav.domContentLoadedEventEnd), load: r(nav.loadEventEnd), bytes: nav.transferSize || 0 } : null,
    api, assets,
  };
  let cap;
  try { cap = JSON.parse(localStorage.getItem(K) || 'null'); } catch { cap = null; }
  if (!cap || cap.host !== location.host) cap = { v: 1, host: location.host, ua: navigator.userAgent, pages: [] };
  cap.pages.push(page);
  localStorage.setItem(K, JSON.stringify(cap));
  return { page: page.path, api_calls: api.length, slowest_ms: Math.max(0, ...api.map((x) => x[2])), pages_so_far: cap.pages.length };
})();
