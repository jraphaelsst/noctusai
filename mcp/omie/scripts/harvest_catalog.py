"""Harvest the complete Omie API catalog from the official developer portal.

Each service URL (https://app.omie.com.br/api/v1/<family>/<resource>/) serves
its own HTML documentation on GET. We parse:
  - methods:       id/name, description, param type, return type, live JSON example
  - complexTypes:  field name, required/optional, type, maxlen, docs, array-of

Output: catalog.json  { endpoints: [ {path, family, resource, methods[], types{}} ] }
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


def strip(x: str) -> str:
    x = re.sub(r"<BR\s*/?>", "\n", x, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", " ", x)).replace("\xa0", " ").strip()


def squash(x: str) -> str:
    return re.sub(r"[ \t]+", " ", strip(x)).strip()


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")


def parse_methods(s: str) -> list[dict]:
    out = []
    for blk in re.findall(r'<div id="([^"]+)" class="methodItem">(.*?)(?=<div id="[^"]+" class="methodItem">|<h2>Tipos Complexos</h2>|\Z)', s, re.S):
        mid, body = blk
        desc = ""
        m = re.search(r'<h3 class="method-name">.*?</h3>\s*<p>(.*?)</p>', body, re.S)
        if m:
            desc = squash(m.group(1))
        params = []
        for row in re.findall(r"<tr>(.*?)(?=<tr>|</table>)", body, re.S):
            t = re.search(r'method-parameter-type"><a href="#([^"]+)"', row)
            n = re.search(r'method-parameter-name">([^<]*)<', row)
            d = re.search(r'method-parameter-docs">(.*?)</td>', row, re.S)
            if t:
                params.append({"type": t.group(1), "name": squash(n.group(1)) if n else "", "docs": squash(d.group(1)) if d else ""})
        ret, retdoc = None, ""
        m = re.search(r'<div class="panel-footer">\s*Retorno.*?<a href="#([^"]+)">.*?</a></span>:?(.*?)</div>', body, re.S)
        if m:
            ret, retdoc = m.group(1), squash(m.group(2))
        ex = None
        m = re.search(r'<pre class="method-example-code">(.*?)</pre>', body, re.S)
        if m:
            raw = strip(m.group(1))
            try:
                ex = json.loads(raw)
            except Exception:
                ex = raw or None
        out.append({"name": mid, "description": desc, "params": params, "returns": ret, "returns_doc": retdoc, "example": ex})
    return out


def parse_types(s: str) -> dict:
    out = {}
    tail = s.split("<h2>Tipos Complexos</h2>", 1)
    if len(tail) < 2:
        return out
    for body in re.findall(r'<div class="complexTypeItem">(.*?)</div>\s*(?=<div class="complexTypeItem">|\Z)', tail[1], re.S):
        nm = re.search(r'<a name="([^"]+)"', body)
        if not nm:
            continue
        name = nm.group(1)
        entry: dict = {"description": "", "array_of": None, "fields": []}
        arr = re.search(r'array do tipo\s*<span class="pre"><a href="#([^"]+)"', body)
        if arr:
            entry["array_of"] = arr.group(1)
        ps = re.findall(r"<p>(.*?)</p>", body, re.S)
        descs = [squash(p) for p in ps if squash(p) and "array do tipo" not in squash(p)]
        if descs:
            entry["description"] = descs[-1]
        for row in re.findall(r"<tr>(.*?)(?=<tr>|</table>)", body, re.S):
            n = re.search(r'parameter-name ([^"]*)">([^<]*)<', row)
            if not n:
                continue
            t = re.search(r'parameter-type">([^<]*)(?:<span class="parameter-lenght">([^<]*)</span>)?', row)
            link = re.search(r'parameter-type"><a href="#([^"]+)"', row)
            d = re.search(r'parameter-docs">(.*?)</td>', row, re.S)
            entry["fields"].append({
                "name": squash(n.group(2)),
                "required": "parameter-required" in n.group(1),
                "type": (link.group(1) if link else (squash(t.group(1)) if t else "")),
                "maxlen": (t.group(2) if t and t.group(2) else None),
                "docs": squash(d.group(1)) if d else "",
            })
        out[name] = entry
    return out


def one(url: str) -> dict | None:
    # Path is stored RELATIVE to base_url (`.../api/v1`) — storing the
    # `/api/v1` prefix too would double it at request time.
    raw = url.replace("https://app.omie.com.br", "").strip("/")
    parts = [p for p in raw.split("/") if p][2:]  # drop api, v1
    path = "/" + "/".join(parts) + "/"
    try:
        s = fetch(url)
    except Exception as e:
        print(f"  !! {path}: {e}", file=sys.stderr)
        return None
    methods = parse_methods(s)
    types = parse_types(s)
    if not methods:
        print(f"  ?? {path}: no methods parsed", file=sys.stderr)
    return {
        "path": path,
        "family": parts[0] if parts else "",
        "resource": parts[-1] if parts else "",
        "url": url,
        "methods": methods,
        "types": types,
    }


def main() -> None:
    urls = [u.strip() for u in (HERE / "endpoints.txt").read_text().splitlines() if u.strip()]
    print(f"harvesting {len(urls)} endpoints ...", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=6) as ex:
        results = [r for r in ex.map(one, urls) if r]
    catalog = {
        "source": "https://developer.omie.com.br/service-list/",
        "base_url": "https://app.omie.com.br/api/v1",
        "endpoints": sorted(results, key=lambda r: r["path"]),
    }
    (HERE / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1))
    nm = sum(len(r["methods"]) for r in results)
    nt = sum(len(r["types"]) for r in results)
    print(f"OK  endpoints={len(results)}  methods={nm}  complexTypes={nt}", file=sys.stderr)


if __name__ == "__main__":
    main()
