# Branding import runbook

Brandings live in the database only (`mc_brand_kits` + `mc_brand_components` + `mc_brand_references` + private bucket `social-wiring-branding`). Nothing here has been run: migrations 204/205 are unapplied and no import has been executed.

## Order (owner decision 2026-10-05)

1. Apply migrations `204_branding_model.sql` (schema) then `205_branding_marcas_data.sql` (marcas Gilson Tangerino / Nós no Limiar / NoctusAI + "One Design" attached to One Consultoria), via `noctus.dev.migrate_product` with explicit consent. Deploy the backend + frontend.
2. Import the **Branding Template** (folder `design-systems/branding-template`) with "Importar como Branding Template".
3. Import **Nós no Limiar only** (folder `design-systems/nos-no-limiar-monica`), marca "Nós no Limiar". Validate, fix, refine. Gilson's (`store-visual-identity-gilson`, marca "Gilson Tangerino") and NoctusAI (`noctusai`, marca "NoctusAI") come in later rounds.

## Via the UI

Mídia → **Branding** → **Importar design system** → pick the folder → choose the marca (or tick "Branding Template") → Importar. The dialog lists every rejection reason, the counts, warnings and the files that were not imported. Re-importing the same folder updates the branding in place (idempotent; also the repair path after a partial failure).

## Via the API (same endpoint)

`POST /api/media-creation/branding/import` with a bearer token; body `{marca_id | null, is_template, name?, files:[{path, content_base64}]}`; paths are relative to the folder root.

```bash
FOLDER=products/social-wiring/projects/core-studio/design-systems/nos-no-limiar-monica
python3 - "$FOLDER" <<'PY' > /tmp/limiar-import.json
import base64, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
files = [{"path": p.relative_to(root).as_posix(),
          "content_base64": base64.b64encode(p.read_bytes()).decode()}
         for p in sorted(root.rglob("*")) if p.is_file() and p.name != ".DS_Store"]
print(json.dumps({"marca_id": "<id of Nós no Limiar from GET /api/marcas>", "files": files}))
PY
curl -sS -X POST "$BASE_URL/api/media-creation/branding/import" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  --data @/tmp/limiar-import.json
```

For the template use `{"is_template": true, "files": [...]}` (no `marca_id`).

## What the folder maps to

`tokens.json` (validated) · `README.md` (brand book) · `design-system.json` `title` (name) · `sections/*.md` · `components/<Name>/README.md` + `preview.html` (validated, never rendered in the page DOM) · `assets/Logos/*` → logos · `assets/References/*` → post models · `fonts/*` → fonts · `assets/<Group>/README.md` → extra section. `source/**` and other files are reported as not imported. Assets are checked by magic bytes (PNG/JPEG/WebP/GIF, WOFF/WOFF2/TTF/OTF; SVG refused), 5 MB each, 25 MB total.
