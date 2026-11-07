# Screens — Tours Virtuais (v1, functional spec)

🔴 **Required next step before any FE slice: `product-designer` mockups** (owner-validated, clickable, on real data — `KB § PATTERNS/frontend/prototype-on-real-data.md`). This file lists functions, states and data only; it is not a layout. Our design system, not the reference app's look. The reference's 5 steps are summarised in `[private study: ui/ui-notes.md]` and the screenshots in `[private study: ui/screens/]`; v1 drops its floor-plan step (D-T7) and its MP4/embed/social panels (D-O5, D-O6), giving 4 steps.

Every screen follows the server-state contract (`KB § PATTERNS/common/server-state-family-index.md`): no lying while loading, every write updates every cache entry it touches, a refusal is never silent, an unsaved draft says so.

## 1 · Tours list — `/tours` (nav "Imóveis › Tours virtuais")

- Data: E1. Card/row: thumb (or a placeholder while `fotos_processando > 0`), título, imóvel code (links to `ImovelDetalhes`), photo count, chips `Rascunho | Concluído` and `Publicado | Não publicado`, visits and leads (30 d), last change + who.
- Actions per tour: Editar · Copiar link (when published) · Abrir tour · Estatísticas (S1 drawer) · Copiar tour (E8) · Remover (E7, modal with motivo; `outro` needs text).
- Header: "Criar tour" (E2: modal with imóvel picker over `/api/imoveis/busca` + título prefilled from the imóvel). Quota line "n de N tours" when `cota.limite` is set; 402 shows the limit message, never a silent no-op.
- Filters: status, published, text (título/código). Empty state with one CTA.
- `ImovelDetalhes` gains a "Tour virtual" panel: the tour (thumb, status, link) or "Criar tour para este imóvel".

## 2 · Editor — `/tours/:id` (4 steps, free navigation between steps, each action saved on its own)

Top bar: título (inline edit, E4), imóvel code, status chips, save indicator ("Salvo" / "Salvando…" / "Alterado por outra pessoa — atualizado"), "Ver como visitante" (opens the public viewer when published, else an in-app preview using the same organ), "Concluir tour" (E6; shows blocking pendências).

**Step 1 — Fotos 360º**
- Drop zone + file picker accepting JPEG/PNG; copy says "fotos 360º equiretangulares (2:1) da sua câmera 360". Multi-select; uploads 3 at a time with per-file progress, cancel, retry; per-file states `enviando → processando → pronta | erro` (with the `erro_codigo` message and the seed `UploadErro` organ).
- Warning chips: "não parece 360º (proporção ≠ 2:1)", "foto repetida".
- Grid of photos: drag to reorder (F5), rename cômodo (F4), set as initial photo (E4), replace (F6, with an alignment slider for `deslocamento_yaw` showing old vs new), delete (F7, confirm: "remove também N conexões").
- Start view: select a photo → `PanoramaViewer` in edit mode → "Usar esta vista como inicial" (F4 `vista_inicial`); the thumb refreshes when the job finishes.

**Step 2 — Navegação (pins)**
- Mode selector shows only "Pins" in v1 (arrows/circles not rendered at all, not disabled-teasers).
- Two-pane gesture: left = origin photo, right = target photo (picker of the other `pronta` photos, "mostrar só sem conexão" filter). Click in the left viewer drops pin A (toward the target room), click in the right drops pin B (toward the origin room); "Criar conexão" saves the pair (C1). Both pins draggable afterwards (C2). Per direction: "chegar olhando a vista inicial" toggle.
- List of the pair's connections with delete (C3). Pendência "foto isolada" highlighted on photos without any pair.
- Preview: "Testar navegação" walks the pins in the organ with the server-computed arrival.

**Step 3 — Informações**
- On any photo: "Adicionar informação" → click a point → form `Texto` (title + text) or `Link` (title + https URL). List filtered by photo/type; edit/delete (P1/P2).

**Step 4 — Contato e compartilhamento**
- Contato: WhatsApp number (prefilled from the org default per Q2, editable), name; preview of the pre-filled message.
- Formulário de lead: on/off, fields, trigger (button only / after N% of rooms, per Q3), link to the privacy notice used.
- Identidade: brand kit picker (Q7); autorotation on/off + speed + "avançar ao completar a volta".
- Visibilidade: Publicado / Não publicado (E5), with the blocking pendências listed when refused.
- Link: copy, open, QR code (client-side), "Gerar novo link" (E9, warns the old one stops working).

## 3 · Public viewer — `/t/:token` (in `publicRoutes`, no login, no product chrome)

- Data: V1, then V2 on start, V3 by `sendBeacon` on room change / `visibilitychange` / `pagehide`.
- Full-screen `PanoramaViewer`: preview LQIP → web image; pins with the target room name; info points; arrival per manifest `chegada`.
- Always visible: **WhatsApp button** (floating, thumb-reachable on mobile; opens `wa.me` with the manifest message; records `whatsapp_clicado`). Brand logo + imóvel title/neighbourhood (no street number unless the owner decides).
- Toolbar: room list / thumbnails strip, previous/next, autorotate toggle, fullscreen, gyroscope (mobile; permission asked on the user's tap — iOS requirement), share (Web Share API, fallback copy link).
- "Tenho interesse" button opens the lead form when `lead_form.ativo`; if `gatilho_pct` is set it also opens once after that share of rooms was seen; always dismissible; Turnstile + consent checkbox + privacy link; success state "Recebemos seu contato".
- States: loading (LQIP, never a fake progress), `tour_indisponivel` (one neutral page for every 404 case), WebGL unavailable (static thumbnails gallery fallback), rate-limited (retry later message).
- Performance budget: first panorama visible ≤ 2.5 s on 4G (LQIP immediately); next room's `web` image prefetched for the linked rooms only.
- Accessibility: keyboard arrows rotate, Tab reaches pins and buttons, `aria-label`s on every control, reduced-motion disables autorotation.
