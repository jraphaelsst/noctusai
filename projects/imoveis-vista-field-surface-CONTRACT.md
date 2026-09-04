# CONTRACT — Imóveis: full Vista field surface (display-only)

> Authored by the tech-lead 2026-09-04 BEFORE dispatch. All three slices build to THIS.
> Every value shape below is **measured live** against tenant `oneconsu-rest`:
> 107 candidate field names probed on `/imoveis/detalhes` (Vista answers
> `400 "Campo X não está disponível"` for unavailable ones), then the accepted
> fields re-probed across **20 imóveis spanning all 20 categorias**. Nothing here is guessed.

## Scope

**DISPLAY ONLY.** No edit mechanism. Vista rejects writes on this key —
`/imoveis/alterar`, `/imoveis/cadastrar`, `/imoveis/excluir` all return
`404 "No route found"` (probed 2026-09-04). Editing lands only when the platform
leaves Vista. Icon-buttons ARE rendered (see §4) but open a toast, never an editor.

## 1 · New Vista fields → columns

All are `/imoveis/detalhes`-only. Add to `CANDIDATE_IMOVEL_DETAIL_FIELDS`; the
calibrator drops any a tenant rejects, so this is safe by construction.

### Coercion rules (measured)
- **bool**: `"Sim"`→true, `"Nao"`→false, `""`→NULL.
- **money/measure**: `"0"`→**NULL** (zero is not a measurement — matches the existing
  `valor_venda > 0` / `area_construida > 0` CHECK convention).
- **count**: `"0"`→**0** preserved (matches the existing `dormitorios >= 0` convention —
  a real zero is a fact, NULL is unknown).
- **text**: `""`→NULL.

| Vista field | Column | Type | Coercion | Measured (n=20) |
|---|---|---|---|---|
| `DescricaoWeb` | `descricao_web` | TEXT | text | 20/20, 463–1648 chars |
| `Observacoes` | `observacoes` | TEXT | text | 0/20 |
| `ValorCondominio` | `valor_condominio` | NUMERIC | money | 11/20 |
| `ValorIptu` | `valor_iptu` | NUMERIC | money | 18/20 |
| `AnoConstrucao` | `ano_construcao` | INT | measure | 16/20 |
| `Situacao` | `situacao` | TEXT | text | 7/20 (`Usado`) |
| `Ocupacao` | `ocupacao` | TEXT | text | 9/20 (`Proprietário`,`Desocupado`) |
| `Pavimentos` | `pavimentos` | INT | count | 0-valued ×20 |
| `Posicao` | `posicao` | TEXT | text | 1/20 (`Frente`) |
| `Elevador` | `elevador` | BOOL | bool | 2 Sim |
| `Portaria` | `portaria` | BOOL | bool | 9 Sim |
| `Exclusivo` | `exclusivo` | BOOL | bool | 1 Sim |
| `AceitaPermuta` | `aceita_permuta` | BOOL | bool | 7 Sim |
| `AceitaFinanciamento` | `aceita_financiamento` | BOOL | bool | 4 Sim |
| `DestaqueWeb` | `destaque_web` | BOOL | bool | varies (Sim on ONE10107) |
| `SuperDestaqueWeb` | `super_destaque_web` | BOOL | bool | varies (Sim on ONE10107) |
| `ExibirNoSite` | `exibir_no_site` | BOOL | bool | 20/20 Sim |
| `Chave` | `chave` | TEXT | text | 4/20 (`Corretor(a)`,`Agendar`) |
| `Zona` | `zona` | TEXT | text | 5/20 (upstream-truncated ~10 chars) |
| `Regiao` | `regiao` | TEXT | text | 0/20 |
| `AreaTerreno` | `area_terreno` | NUMERIC | measure | 3/20 |
| `Closet` | `closet` | INT | count | 0-valued ×20 |
| `Frente` | `frente` | NUMERIC | measure | 0-valued ×20 |
| `Fundos` | `fundos` | NUMERIC | measure | 0-valued ×20 |
| `Referencia` | `referencia` | TEXT | text | 20/20, always == `codigo` |
| `Matricula` | `matricula_vista` | TEXT | text | 7/20 |
| `InscricaoMunicipal` | `inscricao_municipal` | TEXT | text | 1/20 (holds a CITY name — tenant data-entry noise, store verbatim) |
| `VideoDestaque` | `video_destaque` | TEXT | text | 0/20 |
| `Tour360` | `tour_360` | TEXT | text | 3/20, real 360° tour URLs |

**Store all 32 even where n=20 shows empty.** n=20 of 2057 is weak evidence for
dropping — `Escritorio` reads empty across the sample yet is `Sim` on ONE10107.
Columns are cheap; `vista_raw` already retains everything. The UI renders
conditionally (§3), so an always-empty field costs nothing on screen.

🔴 `matricula_vista`, NOT `matricula` — `social_wiring.imovel_dados` (migration 075)
already owns a cartório-authored `matricula`. Two `matricula`s in one schema, one
Vista-sourced and one ours, is the exact `origem` collision the 2026-08 roadmap
called out. Keep them namespaced and distinct.


### 🔴 CORRECTION 2026-09-04 — `Lavabo` / `Copa` / `Escritorio` REMOVED (32 → 29 fields)

Measured live, not inferred. Vista **shadows** these three: they are also keys inside
`Caracteristicas`, and when `Caracteristicas` is in the same `fields` request Vista
returns `null` for all three at top level.

```
fields=[Codigo,Escritorio,Lavabo,Copa]                  -> "Sim" / "Sim" / "Nao"
fields=[Codigo,Escritorio,Lavabo,Copa,Caracteristicas]  -> null  / null  / null
fields=[Codigo,Escritorio,Lavabo,Copa,ValorIptu,...]    -> "Sim" / "Sim" / "Nao"
Caracteristicas{Escritorio,Lavabo,Copa}                 -> "Sim" / "Sim" / "Nao"
```

Our sync ALWAYS requests `Caracteristicas`, so these three columns would be
**permanently NULL in production** while the same values sit in `caracteristicas_raw`.

**Therefore:** no `lavabo` / `copa` / `escritorio` columns, no model fields, no UI
facts. Source them from the amenity list, where they already are. `Elevador` and
`Portaria` are NOT shadowed (verified live) and keep their columns.

Only these three of the 32 overlap the ~75 `Caracteristicas` keys — checked against
the full live key set.

## 2 · Fields deliberately NOT added

- **Photo gallery — unobtainable.** `Fotos`/`Foto`/`Imagens`/`Galeria`/`FotoGrande`/
  `FotoMedia`/`FotoPequena`/`Planta` are ALL rejected by this tenant, and
  `/imoveis/fotos` is write-only (405 on GET). Only `FotoDestaque` (one URL) exists.
  `imovel_normalizer.py:127` reads `payload.get("Fotos")` — a key Vista never sends,
  which is why `fotos` is empty on all 2057 rows. **Leave `fotos` in place, do NOT
  delete it, do NOT fake it.** Add a code comment recording the probe result so the
  next reader does not re-investigate.
- `Descricao`, `Slug`, `PalavrasChave`, `Banheiros`, `Andar`, `AreaUtil`,
  `Proprietario`, `Captador`, `Agencia` and 64 others: probed, rejected by tenant.

## 3 · Derived / presentation-only (no columns)

- `DataAtualizacaoDias` — already inside `vista_raw`, never surfaced. Expose as
  `dias_desde_atualizacao: int | null` computed in the service from `vista_raw`.
- **Solar orientation is NOT an amenity.** `caracteristicas_raw` mixes `Norte`/`Sul`/
  `Leste`/`Oeste` in with real amenities. Split them into their own
  `orientacao_solar: string[]` and remove them from the amenity list.
- **~20 amenities render as ugly fallback labels** because `CARACTERISTICA_LABEL` in
  `useImoveis.ts` covers 55 of the ~75 live keys. Missing at minimum: `Cerca Eletrica`,
  `Alarme`, `Antena Parabolica`, `Aquecimento Eletrico`, `Calefacao`, `Porao`, `Sotao`,
  `Patio`, `Gabinete`, `Sala`, `Sala Estar`, `Estar Intimo`, `Banheiro Auxiliar`,
  `Cozinha Montada`, `Cozinha Com Tanque`, `Construcao Alvenaria`, `Living`,
  `Dependenciade Empregada` (upstream typo — distinct key from `Dependencia De Empregada`).
  Derive the full key set from the live `caracteristicas_raw`, do not hand-guess.

## 4 · Icon-buttons (display-only placeholders)

Reuse the EXISTING component — do not fork one:
`products/social-wiring/frontend/src/components/card/TooltipIconButton.tsx`
(`variant="ghost"`, `size="icon"`, lucide icon, Radix tooltip, `label` drives both
tooltip and `aria-label`; the props type forbids children and `aria-label`).

Render `Pencil` (editar) on each section header and on each listing card. On click:
`toast.info("Edição via plataforma ainda não disponível — o Vista não expõe rota de escrita. Chega quando migrarmos para o sistema próprio.")`

A button that silently does nothing is a silent no-op and violates no-silent-errors.
The toast is what makes the placeholder honest. Do NOT wire any mutation, do NOT add
a PATCH route, do NOT add an editing dialog.

## 5 · Detail-page sections (organized display)

1. **Cabeçalho** — código · título · status · categoria · badges (`Exclusivo`, `Destaque`, `Super destaque`, `Tour 360°`) · endereço · valores
2. **Descrição** — `descricao_web`, clamped with "ver mais"
3. **Valores e custos** — venda · locação · condomínio · IPTU · *custo mensal derivado (condomínio + IPTU/12) when both present*
4. **Cômodos** — dormitórios · suítes · vagas · banheiro social · lavabo · copa · escritório · closet
5. **Áreas** — total · privativa · construída · terreno · frente · fundos
6. **Construção e estado** — ano · situação · ocupação · pavimentos · posição · elevador · portaria
7. **Condições comerciais** — permuta · financiamento · exclusivo · chave · finalidades · exibir no site · destaques
8. **Comodidades** — amenity chips (`Sim` only, prominent) + `Orientação solar` as its own group + a collapsed "não possui" list
9. **Mídia** — `foto_destaque` · `tour_360` (link out, labelled 360°) · `video_destaque`
10. **Localização** — endereço · CEP · bairro · cidade · UF · zona · região · empreendimento · construtora · map link
11. **Corretores** — existing block, unchanged
12. **Registro** — `matricula_vista` · `inscricao_municipal` · `codigo_imobiliaria` · `referencia`; keep the existing `ImovelCartorioCard` beneath it
13. **Metadados** — cadastro · atualização (+ `dias_desde_atualizacao`) · sincronizado em

Every section renders only when it has ≥1 non-null value. Reuse the existing `Fact`
component and `formatCount`/`formatValor`/`formatArea` helpers — a genuine `0` must
read "0" and only NULL renders "—".

## 6 · Listing-page additions

Card gains: condomínio + IPTU compactly, and badges for `Exclusivo` / `Destaque` /
`Aceita permuta` / `Aceita financiamento` / `Tour 360°`. Keep the card scannable —
badges only when true. Add the `Pencil` icon-button per §4.

## 7 · Non-negotiables

- Loading states: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`. Never bare `isLoading`, never bare `isFetching`.
- Auth tests assert strict `== 401`.
- Migration is forward-only + idempotent; header cites this contract. It is a FILE ONLY — the tech-lead applies it.
- No `--no-verify`. Commit only your own branch.
