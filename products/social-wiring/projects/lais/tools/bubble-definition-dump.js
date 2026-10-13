// Bubble page definition → compact element texts + API workflows (read-only, app definition only)
(() => {
  const app = window.app; const pageName = window.bubble_page_name;
  const api = app.settings.client_safe.apiconnector2 || {}; const callMap = {};
  for (const [gk, g] of Object.entries(api)) for (const [ck, c] of Object.entries(g.calls || {})) callMap[`apiconnector2-${gk}.${ck}`] = `${(c.method || '').toUpperCase().replace('_METHOD','')} ${String(c.url || '').replace(/^https?:\/\/\[[a-z]+\]/i, '').replace(/\?.*/, '')}`;
  const page = Object.values(app['%p3']).find(x => x['%nm'] === pageName);
  const idName = {}; const idx = (el) => { idName[el.id] = el['%dn'] || el['%nm']; for (const c of Object.values(el['%el'] || {})) idx(c); }; idx(page);
  const texts = (o) => { const out = []; const w = (v) => { if (typeof v === 'string') { if (v.length > 2 && v.length < 300 && /[a-zà-ú]{3}/i.test(v) && / /.test(v) && !/^(%|#|rgba|var\(|http|\/\/|flex-|space-|custom\.|_api_c2|bGFp|material |bootstrap |ionic |phosphor )/.test(v)) out.push(v.replace(/\s+/g, ' ')); } else if (v && typeof v === 'object') for (const x of Object.values(v)) w(x); }; w(o); return [...new Set(out)]; };
  const T = []; const walk = (el) => { const t = texts(el['%p']); if (t.length && !/Group|Shape/.test(el['%x'])) T.push(`${el['%x'].replace(/^\d+x\d+-/, 'plugin-')}«${el['%dn'] || ''}»: ${t.join(' ‖ ').slice(0, 300)}`); for (const c of Object.values(el['%el'] || {})) walk(c); }; walk(page);
  const W = []; for (const wf of Object.values(page['%wf'] || {})) { const acts = Object.values(wf.actions || {}).sort((a, b) => (a['%p']?.['%o'] || 0) - (b['%p']?.['%o'] || 0)); const apis = acts.filter(a => callMap[a['%x']]).map(a => callMap[a['%x']]); if (!apis.length) continue; W.push(`${wf['%x']}«${idName[wf['%p']?.['%ei']] || ''}» → ${apis.join(' → ')}${acts.some(a => /Alert/.test(idName[a['%p']?.['%ei']] || '')) ? ' (+alert ' + acts.flatMap(a => texts(a['%p'])).filter(s => /sucesso|erro/i.test(s)).slice(0, 1).join('') + ')' : ''}`); }
  let pre = document.getElementById('__x'); if (!pre) { pre = document.createElement('pre'); pre.id = '__x'; pre.style.cssText = 'position:fixed;inset:0;z-index:99999;background:#fff;overflow:auto;font-size:10px;white-space:pre-wrap'; document.body.appendChild(pre); }
  pre.textContent = `PAGE ${pageName}\nTEXTS\n${[...new Set(T)].join('\n')}\n\nAPI WORKFLOWS\n${[...new Set(W)].join('\n')}`;
  return pre.textContent.length;
})()
