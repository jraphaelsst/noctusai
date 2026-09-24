// Install in the portal page via javascript_tool AFTER it loads. Survives in-app (SPA)
// navigation; lost on full reload. Records method, path, param NAMES, status, request-body
// keys and top-level response keys — never values. Read back with:
//   [...new Set(window.__nocLog)].join('\n')
if (!window.__nocHook) {
  window.__nocLog = [];
  const norm = (u) => {
    try {
      const x = new URL(u, location.href);
      if (!/apigw/.test(x.host)) return null;
      return x.pathname
        .replace(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g, ':uuid')
        .replace(/\d{5,}/g, ':id')
        .replace(/\/[A-Z0-9]{8}\//g, '/:code/')
        + (x.search ? ' ?' + [...new Set(x.searchParams.keys())].join(',') : '');
    } catch (e) { return null; }
  };
  const shape = (o) => {
    if (Array.isArray(o)) return '[' + (o[0] && typeof o[0] === 'object' ? Object.keys(o[0]).join(',') : typeof o[0]) + ']';
    if (o && typeof o === 'object') return '{' + Object.entries(o).map(([k, v]) => k + (Array.isArray(v) ? '[]' : v && typeof v === 'object' ? '{}' : '')).join(',') + '}';
    return typeof o;
  };
  const bodyKeys = (b) => { try { return Object.keys(JSON.parse(b)).join(','); } catch (e) { return b ? '(non-json)' : ''; } };
  const push = (m, u, s, b, t) => {
    const p = norm(u); if (!p) return;
    let sh = ''; try { sh = shape(JSON.parse(t)); } catch (e) { sh = t ? '(non-json)' : ''; }
    const page = location.pathname.replace(/\d{5,}/g, ':id').replace(/[0-9a-f-]{36}/, ':uuid');
    window.__nocLog.push(`${page} :: ${m} ${p} -> ${s}${b ? ' req{' + bodyKeys(b) + '}' : ''} res${sh.slice(0, 400)}`);
  };
  const of = window.fetch;
  window.fetch = async function (i, o) {
    const r = await of.apply(this, arguments);
    try {
      const u = typeof i === 'string' ? i : i.url;
      const m = ((o && o.method) || (i && i.method) || 'GET').toUpperCase();
      r.clone().text().then((t) => push(m, u, r.status, o && o.body, t));
    } catch (e) { window.__nocLogErrors = (window.__nocLogErrors || 0) + 1; }
    return r;
  };
  const oo = XMLHttpRequest.prototype.open, os = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__m = m; this.__u = u; return oo.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) {
    this.addEventListener('load', () => {
      let t = '';
      try { t = (this.responseType === '' || this.responseType === 'text') ? this.responseText : JSON.stringify(this.response); } catch (e) { window.__nocLogErrors = (window.__nocLogErrors || 0) + 1; }
      push(String(this.__m).toUpperCase(), this.__u, this.status, b, t);
    });
    return os.apply(this, arguments);
  };
  window.__nocHook = 1;
}
'hook ok';
