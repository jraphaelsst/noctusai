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

## Open — to ask before building

- Which brand the Store Visual Identity attaches to: Gilson Tangerino (personal) or ONE Consultoria.
- What happens to the existing repo catalog mechanism (`branding/catalog/` + "Carregar catálogo") now that brandings are database-only.
- Per-product regrouped menus (proposal pending).
- Rebuild or drop: Assuntos Virais pane, AI validation of brain answers, voice answers, the hidden "Minhas extrações" page.
- Viral library source (our own scraped corpus or user references only).
- Approval for checks that change the CoreStudio account (study spec §7), including one live generation (1 credit) to read the real HEADLINE/ROTEIRO prompts.
