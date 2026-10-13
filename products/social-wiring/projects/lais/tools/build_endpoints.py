"""Build endpoints.json + endpoints.md from endpoints_src.py, mapping chunks -> routes statically."""
import os, re, json, sys, collections
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, 'tools'))
from endpoints_src import E  # noqa

JS = os.path.join(BASE, 'js')
files = {}
for dp, _, fs in os.walk(JS):
    for f in fs:
        p = os.path.join(dp, f)
        files[os.path.relpath(p, JS)] = open(p, encoding='utf-8', errors='replace').read()

def route_of(rel):
    if rel.startswith('app/'):
        d = os.path.dirname(rel)[4:]
        return '/' + d if d else ('/' if 'page-' in rel else '(layout)')
    return None

# page -> dependency chunk ids
deps = {}
for rel, s in files.items():
    if rel.startswith('app/') and ('/page-' in rel or rel.startswith('app/page-') or 'layout-' in rel):
        m = re.search(r'e\.O\(0,\[([0-9,]+)\]', s)
        ids = set(m.group(1).split(',')) if m else set()
        r = route_of(rel) if 'layout-' not in rel else '(layout)'
        deps[r] = ids

def chunk_id(rel):
    return re.match(r'([0-9a-f]+)[-.]', os.path.basename(rel)).group(1)

out = []
for row in E:
    hits = [rel for rel, s in files.items() if row['sig'] and re.search(row['sig'], s)]
    hits = [h for h in hits if not h.startswith('9707.')]  # exclude mocks chunk from caller mapping
    routes = set(); shared = []
    for h in hits:
        r = route_of(h)
        if r:
            routes.add(r)
        else:
            cid = chunk_id(h); shared.append(h)
            for pr, ids in deps.items():
                if cid in ids:
                    routes.add(pr)
    mock = any(re.search(re.escape(row['path'].split('?')[0].split(' ')[0].replace(':id', 'X')).replace('X', ':[a-zA-Z]+'), files[k]) for k in files if k.startswith('9707.'))
    r2 = dict(row); r2.pop('sig')
    r2['chunks'] = sorted(hits)
    r2['routes'] = sorted(routes)
    r2['hasMswMock'] = mock
    out.append(r2)

os.makedirs(os.path.join(BASE, 'analysis'), exist_ok=True)
json.dump(out, open(os.path.join(BASE, 'analysis', 'endpoints.json'), 'w'), ensure_ascii=False, indent=1)

cnt = collections.Counter(r['safety'] for r in out)
L = ['# Lais / Lastro BFF — endpoint catalogue (static, from bundle)', '',
     'Base URL: `https://bff.lastro.services/api/v1` (C 5138 `let t="https://bff.lastro.services/api/v1"` in UrlBuilder). Relative paths below are appended to it.',
     'Every BFF call gets `Authorization: Bearer <keycloak access token>` and `x-agency-id: <selected REA id>` unless `skipAgencyId` (C 5138 `injectAuthHeaders`).',
     'Client retries 3x with exp. backoff (1s,2s,4s) on HTTP>=500 or 429 — for ALL verbs incl. POST (C 5138 `DEFAULT_RETRY_CONFIG={retries:3,delay:1e3,backoff:2}`); only catalog product-set writes pass `retries:0`. => a live POST that 5xx\'s may be replayed.',
     'HTTP 402 with code `premium_module_required` => `window.location.replace("/add-ons/pro")` except on /add-ons/pro, /acessos and for /agency/details, /subscription/premium (C 5138).',
     '',
     'Safety classes: **READ** GET no side effect · **WRITE** create/update/delete · **SEND** sends WhatsApp/broadcast, schedules outreach, or changes AI-vs-human answering · **SIDE-EFFECT-GET** (none found) · **AUTH** auth/session flows.',
     'Counts: ' + ', '.join(f'{k}={v}' for k, v in sorted(cnt.items())) + f', total={len(out)}.', '',
     'Columns: method · path · caller · request · response · routes (page chunks that load the defining chunk; `(layout)` = global shell) · ev (C code / I inferred / C(mock) only in MSW) · mock = MSW handler exists.', '']
by = collections.defaultdict(list)
for r in out:
    by[r['domain']].append(r)
for d, rows in by.items():
    L.append(f'## {d}')
    L.append('')
    L.append('| safety | method | path | caller | request | response | routes | ev | mock | note |')
    L.append('|---|---|---|---|---|---|---|---|---|---|')
    for r in rows:
        routes = ', '.join(r['routes']) if r['routes'] else '—'
        if len(routes) > 140:
            routes = routes[:137] + '…'
        cells = [('**%s**' % r['safety']) if r['safety'] == 'SEND' else r['safety'], r['method'], '`%s`' % r['path'], r['caller'], r['request'], r['response'], routes, r['evidence'], 'y' if r['hasMswMock'] else '', r['note']]
        L.append('| ' + ' | '.join(str(c).replace('|', '\\|') for c in cells) + ' |')
    L.append('')
open(os.path.join(BASE, 'analysis', 'endpoints.md'), 'w').write('\n'.join(L))
print(cnt, len(out))
for r in out:
    if not r['chunks']:
        print('NOCHUNK', r['method'], r['path'])
