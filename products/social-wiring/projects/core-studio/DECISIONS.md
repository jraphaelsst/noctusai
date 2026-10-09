# Decisions log (owner interview)

Rule for this project: the owner is interviewed for every specification; nothing is guessed, assumed or inferred.

## Decided — 2026-10-05

### Scope
- Study first, build later. The CoreStudio tree is recreated in-home, keeping its structure, mechanisms and labels, because its users already know CoreStudio and asked that it not change.
- Biblioteca de Virais, the Pesquisa mechanism and the content-creating AI conversations get their own deeper discussion before building.

### Sidebar
- A new **Criação de Mídia** group below **Edição de Fotos** in social-wiring holds CoreStudio's tree exactly. That makes the seed sidebar **4 levels** deep (Criação de Mídia › Configurações › Headlines › Gerar / Favoritas / Sugeridas).
- Groups behave as an **accordion that can be closed** (one open per level; clicking the open header closes it).
- Highlight: CoreStudio's top-item highlight **plus** a mark on the current leaf link.
- It is a **seed `Sidebar` change** (approved). Every **active** product gets it: academia-de-reciclagem, agents, community, core, igig, orbity, p-studio, social-wiring, store. Asleep products are untouched.
- Active products get the new behaviour **and regrouped menus**; a proposed tree per product comes back for approval before building.
- Screens use **our design system**, not CoreStudio's look.

### Pesquisa variables
- One **merged list**: CoreStudio's UI variables plus the classifier-only ones. All of them are kept, and each needs a documented "where and how it is used" (see `specs/variables-usage.md`).

### Branding (evolves social-wiring's "Kits de marca")
- Kits de marca becomes **Branding**, supporting several clients and several design systems.
- The **Branding Template** (merged from Gilson's and Mônica's systems) is the canonical model for creating brandings from scratch.
- Validation order: add **Mônica's (Nós no Limiar)** first to validate, fix and refine; then add **Gilson's** on the fixed code for a second round.
- The table uses the **richer model** (tokens, brand-book sections, components, logos, references), **not** a link to an artifact (deleting an artifact must not break anything).
- **Owners are brands**, not only people: Gilson Tangerino is a personal/professional brand of his own, separate from ONE Consultoria's brand; the same holds for Mônica. Mônica's personal branding does not exist yet; only Nós no Limiar does.
- The **Store Visual Identity is Gilson's**. The **Nós no Limiar Identity is Mônica's**.
- A **NoctusAI** design system is built from the website's tokens as they are (bootstrap, pre-rebrand) and must also be available in Branding inside social-wiring.

### Product and storage
- CoreStudio's rebuild is the **Criação de Mídia module inside social-wiring** for now; it will probably become its own product later. Reference material lives in `products/social-wiring/projects/core-studio/`.
- This folder is committed whole, captures included.
- Brandings and the Branding Template live in the **database only**, edited in the app (no repo catalog, no artifact link).
- The old catalog entry "Wilson — Granja Viana" was Gilson's (mis-named; he is @gilson_tangerino). Its two looks (premium dark + gold, educational lilac + navy + yellow) are **retired**.

## Decided — 2026-10-05, round 4

### Branding data
- The **Store Visual Identity is Gilson Tangerino's** (his personal/professional brand).
- The repo brand catalog (`branding/catalog/`, its loader, the seed-catalog endpoint and the "Carregar catálogo" button) is **deleted**. Its only entry ("Wilson", really Gilson) is retired, so nothing moves to the database.
- Brands live in `social_wiring.marcas`: today One Consultoria (empresa), João Raphael (pessoa_fisica), Mônica Tangerino (pessoa_fisica). New: **Gilson Tangerino** (pessoa_fisica), **Nós no Limiar** (empresa), **NoctusAI** (empresa).
- The empty brand kit "One Design" is **attached to One Consultoria**, to be filled from the template later.
- Import order: Nós no Limiar first (validate, fix, refine), then Gilson's Store Visual Identity, then NoctusAI. The Branding Template is stored in the database too.

### Existing media creation
- **Keep everything**: Biblioteca, Novo post and Kits de marca (renamed Branding). Biblioteca and Novo post overlap with CoreStudio's flow and get **merged** when the Criação de Mídia module is built. CoreStudio's extracted methodology must be **aligned with our in-home Método Audience** (`prompts/methodology.py`), since the two are complementary.

### Menus
- Regroup the active products' menus following the recommended trees in `MENUS.md`, no further approval round.

### Research variables
- Correction: the merged list has **40 distinct concepts and no overlaps**. Only the 5 exact slug matches and one spelling variant (Pessoas e personagens conhecidos) are identities. Everything previously flagged as "overlap" (e.g. Crenças do meu público vs crenças limitantes) is a different concept. See `specs/variables-usage.md` §6.

## Decided — 2026-10-05, round 5

- The CoreStudio tree is added to the sidebar **one link per page, as each page is ready**. The current "Criação de mídia" page (3 tabs) stays as one link until it is merged.
- First module: **Pesquisa** (Minha Pesquisa, then Extrair Pesquisa).
- Pesquisa is scoped **per marca**, with a brand switcher on the page. All **40 variables**; the unclear ones are refined later from real use ("first a fully working prototype, then refine").
- Approval like CoreStudio: manual add = approved, AI-produced = pending, rejected = hidden.
- Item sources v1: **our own content** already in the platform, plus the **Instagram integration** (profile KPIs, charts, post cards newest first, post modal with insights over time).

## Decided — 2026-10-09, round 7

- **Headline system prompt** (hidden in CoreStudio): rebuild it by **merging** what the reverse engineering found (`prompts/headline-engenharia-reversa-DRAFT.md`) with our Método Audience (`backend/app/modules/media_creation/prompts/methodology.py`).
- **Núcleo de Influência source**: the profile **bio**.
- **Fetch 2–3 of the owner's own auto suggestions** (ids 201486–201503, confirmed the owner's): approved, read-only.
- **Viral library source**: deferred. It will come from high-performing Instagram posts; where those come from (e.g. accounts the owner registers in a list and we monitor for viral posts) is still open.
- Build contract for Minha Pesquisa v1: `specs/pesquisa-contract.md`.

## Open — to ask before building

- Fill the headline blueprint `{{DB-SLUG}}` slots from approved Pesquisa items? Owner unsure (2026-10-09) — revisit when the headline module starts, with a worked example.
- Rebuild or drop: Assuntos Virais pane, AI validation of brain answers, voice answers, the hidden "Minhas extrações" page.
- Viral library source (see round 7).
- Approval for checks that change the CoreStudio account (study spec §7), including one live generation (1 credit) to read the real HEADLINE/ROTEIRO prompts.
