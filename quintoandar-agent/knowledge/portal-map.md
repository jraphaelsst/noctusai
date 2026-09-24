# Portal map — QuintoAndar partner portal

Observed 2026-09-24 on `https://listings.quintoandar.com.br/` (account: ONE Consultoria,
admin user). UI labels are quoted **verbatim in pt-BR**. All facts `[observado]` unless
tagged `[confirmado pelo usuário]`. Counts are a snapshot — they moved during the session.

## 0 · Shell

- Header: "Marketplace QuintoAndar" logo · user button (initial + first name) → menu:
  "Gerenciar usuários" (`/members`) · "Perfil da Imobiliária" (`/company-profile`) ·
  "Sair da conta" (logs out — never click).
- Left sidebar, collapsible groups (˄), "‹" at the bottom collapses it.
- Next.js app. Full route list is in the build manifest (`self.__BUILD_MANIFEST`,
  snippet `playbook/snippets/manifest-routes.js`) — 48 routes.
- Paginated lists carry `?page=N&perPage=N` in the URL.
- Two IDs per property: **QA code** (numeric, 9 digits, e.g. `8957xxxxx`) and **CRM code**
  (the agency's Vista code, prefixes seen: `ONE`, `CA`, `AP`). Both have "Copiar" buttons.

## 1 · Sidebar → routes

| Group | Item | Route | Sidebar badge |
|---|---|---|---|
| — | Início | `/` | — |
| Oportunidades | Desempenho dos anúncios | `/listing-performance` | blue dot |
| Oportunidades | Publicar mais anúncios | `/status/pending` | blue dot |
| Imóveis | Em processamento | `/status/processing` | count |
| Imóveis | Anunciados | `/status/published` | count |
| Imóveis | Desativados | `/status/unpublished` | count |
| Imóveis | Não-elegíveis | `/status/notEligible` | count |
| Imóveis | Descartados | `/status/discarded` | count |
| Imóveis | Todos os imóveis | `/status/all` | count |
| — | Visitas | `/visits` | — |
| Propostas de venda | Minhas propostas | `/sale-offers/internal/in-negotiation` | — |
| Propostas de venda | Propostas externas | `/sale-offers/in-negotiation` | — |
| — | Performance | `/reports/pos` | — |
| — | Calculadora | `/price-calculator` | — |

**Counter quirk:** sidebar "Todos os imóveis" = sum of the other five status counters +
the pending count (held twice: 2066, 2075). The `/status/all` list itself showed a lower
total (1966, later 1972). Cause unknown `[confirmado pelo usuário: sem explicação]`.

## 2 · Routes outside the menu

| Route | Result |
|---|---|
| `/photos` | Works — "Sessões de Fotos" (§13). No link found anywhere in the UI |
| `/search/:term` | Search results (§3) |
| `/lead/:uuid/:RENT\|SALE\|HYBRID?crmId=:crm` | Lead page (§5B) |
| `/listing/:qaId/:RENT\|SALE` | Listing page (§5C) — works but is NOT in the manifest |
| `/listing-performance/report-setup/:qaId` | "Personalizar relatório" (§2) |
| `/user-profile/:uuid` | "Perfil do usuário" (§11) |
| `/operation-areas[?contextType=COMPANY\|AGENT&personUuid=…&isEditMode=true]` | Area editor (§11/§12) |
| `/status` → `/status/all` · `/integration` → `/status/pending` | redirects |
| `/house-registration`, `/contract-renewal`, `/rent-offers/in-negotiation` | redirect to `/` |

Not opened: `/drafts/[draftSection]`, `/rent-offer/…` (4), `/sale-offer/details[/tic]`,
`/pricing-report/[...hash]`, `/listing-performance/report/[...hash]`,
`/price-calculator/results`, `/house-registration/success`, and all auth/onboarding routes
(`/login`, `/first-access`, `/first-login`, `/confirm-user-data`, `/verify-email`,
`/esqueci-minha-senha`, `/nova-senha`, `/reset-password`, `/create-new-password`,
`/profile-conflict[/unsuported]`, `/forbidden`).

## 3 · Início `/`

- "Boas-vindas à carteira de <imobiliária>" / "Acompanhe aqui o status dos seus imóveis no QuintoAndar".
- "Principais atividades" cards: **Visitas "N para confirmar"** → `/visits`; **Imóveis "N para revisar"** → `/status/pending`.
- "Visitas agendadas" table (next ~3–5) + "Ver todas as visitas agendadas".
  Columns: Data (weekday, `DD/MM/AAAA`, `HH:MM`) · Imóvel (QA code+Copiar, CRM code+Copiar,
  address link → property in new tab) · Captador ("-" if none) · Corretor ("Corretor
  externo", short name, phone) · Status (Confirmada green / Não confirmada yellow) · action.
- Status filter here: "Não confirmada", "Confirmada" + "Limpar"/"Filtrar".
- Row action: "Responder" (unconfirmed) or "Detalhes" (confirmed) + "⋮".

### Visit panels (shared by Início and Visitas)
- **"⋮" menu:** "Baixar autorização de entrada" · "Editar horários disponíveis" ·
  "Cancelar visita" (absent on cancelled visits) · "Abrir anúncio no QuintoAndar".
- **"Horários para visita" modal:** "Selecione abaixo os horários nos quais o seu imóvel
  pode receber visitas. Isso irá refletir no site do QuintoAndar." Tabs Seg…Dom; 1-hour
  checkbox slots, set differs per day (Mon 08–19 = 11 slots; Sun 09–14 = 5); some slots
  tagged "Alta Procura". "Voltar" / "Confirmar horários" (write).
- **"Confirmar visita" drawer** (Responder): business-type tag, address, codes; "Dia e
  horário" long form; "Corretor externo" name · CRECI, phone (WhatsApp icon) + reason
  text; "Captador"; "Entrada no imóvel" + "Editar entrada"; "Informações importantes"
  incl. deadline ("Confirme a visita com o proprietário até … para ela não ser cancelada
  automaticamente"). Buttons "Cancelar visita" / "Confirmar visita" (writes). ← closes.
- **"Visita confirmada"** drawer: same minus deadline, only "Cancelar visita".
- **"Visita cancelada"** drawer: same blocks, no action buttons.
- Corretor-externo reasons seen: "…sua imobiliária não participa do Programa Clientes
  QuintoAndar, ou não possui corretor na região desse imóvel ou com disponibilidade de
  agenda." · "…por preferência do interessado."

### Entry-access wizard ("Editar entrada" / "Editar entrada no imóvel" / pencils)
1. "Qual é o local de chaves?": "Chaves com o proprietário" ("O proprietário precisa abrir
   a porta e garantir a autorização de entrada dos parceiros.") · "Chaves com outro
   responsável" ("Um vizinho, familiar ou amigo fica com as chaves e é responsável por abrir
   o imóvel em todas as visitas."). Current one tagged "Entrada atual". "Continuar".
2. "Tem alguma observação de entrada?": textarea "Informe a orientação de entrada
   (opcional)", max 200 (`name=accessDetails`). "Confirmar alteração" (write).

## 4 · Publicar mais anúncios — "Imóveis com pendência" `/status/pending`

- Text: "Imóveis com algum tipo de pendência a ser resolvida antes da publicação." + the
  standard CRM notice: "Os ajustes devem ser feitos diretamente em seu CRM. Após o envio,
  estes ajustes podem levar entre 24 e 48h para ser refletidos…"
- Columns: Imóvel (CRM code, address → `/lead/…`) · Status ("Com pendências", sometimes +
  "Não elegível") · Pendências · Anúncio (Aluguel/Venda/both) · Valor (one per type).
- Pendência texts seen (23 items): "Erro ao processar as fotos. Atualize o anúncio no CRM e
  envie novamente" (8) · "Faltam informações da pessoa proprietária" (5) · empty (5) ·
  "Análise de fotos não aprovada" (2) · "Número de quartos ou banheiros inválido" (1) ·
  "Endereço incompleto: complemento não informado" (1) · "Poucas fotos disponíveis" (1).

### Shared list controls (all `/status/*`)
- "Anúncio" column filter: "Aluguel" · "Venda" · "Aluguel e Venda" → `businessContext=RENT|SALE|HYBRID`.
- Page size 10/20/30 (`perPage`); numbered pagination.
- Search box: placeholder "Buscar por id (código de seu CRM)" (Desativados: "Buscar por
  endereço ou código"); "Buscar" button appears once text is typed → `/search/:term`.
- **Search** (`/search/:term`): "Resultados da busca", "N imóvel para "<term>"", "‹ Voltar";
  columns Imóvel · Status · Detalhamento · Anúncio · Valor. Accepts CRM code AND QA code;
  searches across all statuses.

## 5 · Status lists `/status/:status`

| Item | Route | Page description | Columns | Status tags | Row link |
|---|---|---|---|---|---|
| Em processamento | processing | "Imóveis que estão em processamento, na fila de publicação ou que tiveram pendências marcadas como resolvidas." | Imóvel·Status·Motivo·Anúncio·Valor | Em processamento; Com pendências+Não elegível | `/lead` |
| Anunciados | published | "Imóveis atualmente anunciados no QuintoAndar." | Imóvel·Status·Anúncio·Valor | Anunciado; Anunciado+Não elegível | `/property/:qaId/summary` |
| Desativados | unpublished | "Imóveis que foram publicados um dia e agora estão desativados." | +Motivo | Desativado; +Não elegível | `/property` (verified via search) |
| Não-elegíveis | notEligible | "Imóveis que não foram publicados por estarem fora das regras de negócio do Marketplace QuintoAndar." | +Motivo | Não elegível | `/lead` |
| Descartados | discarded | "Imóveis que foram descartados por escolha da imobiliária." | Imóvel·Status·Anúncio·Valor | Descartado; Desativado | `/lead` |
| Todos | all | "Imóveis enviados para o Marketplace QuintoAndar, independente do status." | +Detalhamento | all | per status |

Motivos seen (first page only — sample): processing: "Imóvel aguardando liberação no CRM",
"Análise de imagem em andamento" · unpublished: "Proprietário não concorda com os termos do
QuintoAndar", "Proprietário desistiu de alugar o imóvel", "Falta de confirmação de
disponibilidade", "Gestão de Consequências Proprietário", "Imóvel indisponível" ·
notEligible: "Fora da área de atuação do QuintoAndar", "Fora do preço de atuação do
QuintoAndar", "Imóvel já existente no QuintoAndar", "Imóveis de outras parcerias".

## 6 · Property detail — three page types

### A) `/property/:qaId/summary|details|visits` (Anunciado, Desativado)
- Header: ← back; cover photo; "Código: <QA> CRM: <CRM>"; title (complement); full address;
  owner line: first name · phone (wa.me link) · e-mail shaped
  `3p-<agency CNPJ>-+55<phone>@owner3p.quintoandar.com.br`.
- **Resumo:** price card — business type + status tag, value, price-rating tag ("Preço
  certo" green dot / "Preço muito acima"), Condomínio, IPTU "12x R$ …", links "Editar" and
  "Acessar anúncio" (→ public `quintoandar.com.br/imovel/<QA>/alugar`, new tab), "Anunciado
  em DD/MM/AAAA". Only ONE price card seen, even for a HYBRID property.
  Status card: Anunciado → "O imóvel está anunciado — Interessados já podem encontrar…";
  Desativado → "O anúncio foi desativado pelo motivo de: <motivo>. Se quiser, você pode
  voltar reativar o anúncio agora." + **"Reativar anúncio"** (write).
  "Consiga mais visitas" card (published) + "Editar entrada no imóvel" (→ entry wizard).
- **"Editar" → "Revisar anúncio" drawer:** "Caso note algo diferente, corrija abaixo as
  informações do imóvel"; summary (m², dorms, vagas, "Valor do aluguel|Valor de venda");
  **Condomínio** Sim/Não: Academia, Área verde, Brinquedoteca, Churrasqueira, Elevador,
  Lavanderia, Playground, Quadra esportiva, Salão de festas, Salão de jogos, Sauna, Piscina;
  **Portaria**: 24 horas · Noturna · Diurna · Não há portaria; **Comodidades** Sim/Não:
  Apartamento cobertura, Ar condicionado, Banheira, Chuveiro a gás, Churrasqueira privativa,
  Closet, Piscina privativa, Tanque, Ventilador de teto. "Enviar correções" (write).
- **Detalhes:** Características (quartos (suítes), m², vagas, banheiros, andar, Mobiliado,
  Vista livre, Aceita pet) · Descrição · Itens "Disponível" / "Indisponível".
- **Visitas:** 4 cards — Entrada no imóvel (pencil → wizard step 1) · Observações de entrada
  (pencil → step 2) · Horários de visitas (pencil → horários modal) · Autorização de entrada
  (download icon). No visit list was shown on the one property checked.

### B) `/lead/:uuid/:type?crmId=:crm` (Com pendências, Em processamento, Não elegível, Descartado)
- Server-rendered (no client API calls). Tab title "<CRM> - <tipo> para locação | à venda
  [com <m²>, <n> quartos e <n> vagas] - QuintoAndar".
- Header: photo or "Imóvel sem fotos"; address; "<tipo> • Código: <CRM>".
- Status card (sometimes): **"Anúncio com pendências"** + reason + **"Marcar pendências
  como resolvidas"** + **"Descartar anúncio"** (both writes). Seen on single-context leads
  (e.g. "Imóvel aguardando liberação no CRM. Para completar o anúncio e garantir a sua
  publicação, comunique ao proprietário e autorize envio do seu imóvel." / "Imóvel em
  processamento: a análise das imagens ainda está em andamento."). "Imóvel descartado —
  Imóvel descartado pela imobiliária durante o processo de integração" (no buttons).
  NOT shown on two HYBRID pending leads nor on a Não-elegível one (open question).
- "Informações do imóvel": 8 icons — quartos(+suítes), m² (+R$/m²), vagas, banheiros,
  andar, then sun / muted-speaker / picture icons with "–" (their labels, per §5C, are
  "Sol da manhã", "Rua silenciosa", "Vista livre").
- "Expandir informações" (sometimes needs a 2nd click): "Descrição do imóvel" (or "A
  descrição ainda não está disponível.") + "Imóvel" Disponível/Indisponível item lists.
- Price cards on the right: one per business type, each with its own status tag.

### C) `/listing/:qaId/:type` (reached from Desempenho dos anúncios)
- Header: address, "<tipo> • Publicado em DD/MM/AAAA", links "Editar anúncio" (→ same
  "Revisar anúncio" drawer) and "Editar horários de visitas".
- Same 8 icons, **labelled**: … "Sol da manhã" · "Rua silenciosa" · "Vista livre".
- Expandable description + items (extra item seen: "somente uma casa no terreno").
- Price card: type, "Anunciado", value, Condomínio, IPTU (here "1x R$ …"), "Mostrar anúncio".

## 7 · Desempenho dos anúncios `/listing-performance`

- "Analise do desempenho do anúncio" + count badge; "Imóveis atualmente publicados no
  QuintoAndar e que não tem resultados suficientes para gerar um negócio aparecem aqui com
  um desempenho de anúncio baixo…"
- Chips: Todos · Problemas de desempenho · Bom desempenho. Search "Buscar por código ou
  endereço". Filter on "Desempenho do anúncio": Avaliando desempenho · Sem desempenho ·
  Desempenho baixo · Pouco desempenho · Bom desempenho · Ótimo desempenho.
- Columns: score in a semicircle gauge (seen 1, 3) · Imóvel · Valor de venda · Proprietário
  (name + phone) · "⋮" · expand ⌄.
- "⋮": "Personalizar relatório" · "Editar preço" · "Editar imóvel".
- Expanded row: diagnosis sentence; "Atividades do anúncio" (last 30 days: Visualizações,
  Visitas agendadas, each "% maior que um similar"); "Novo valor sugerido" + "O imóvel está
  bem precificado" + "Mais rápido — Negocie mais descontos…" + **"Editar valor"**; warning
  "Melhore o desempenho do seu anúncio…"; buttons "Disponibilidade do imóvel" / "Cadastro do
  imóvel" (→ `/listing/…`) / **"Compartilhar relatório"**.
- "Editar valor" → drawer "Alteração de preço": "Alterações feitas aqui são somente para o
  QuintoAndar. Caso queira alterar em todos os seus canais faça esse ajuste diretamente no
  seu CRM."; "Análise de preço" text + coloured scale with current value and two values
  below; "Dados do proprietário" (name/phone/e-mail); R$ input; "Cancelar" / **"Salvar"**.
- **Report setup** `/listing-performance/report-setup/:qaId`: header (status, address, m²,
  quartos, vaga, banheiro); "Nota de desempenho" (score + class e.g. "Pouco desempenho";
  ⓘ "A nota de desempenho é referente a um conjunto de ações que impactam a visibilidade do
  imóvel."); "Atividades do anúncio" (ⓘ "…últimos 30 dias, comparando a imóveis
  similares."); "Valor atual"; "Valor sugerido" + R$/m² + confidence tag ("Alta confiança —
  Já negociamos muitos imóveis parecidos no mesmo bairro."); pencil → "Por quanto o imóvel
  será vendido?" input + live feedback ("Excelente — Preços dentro da faixa recomendada
  geram mais visitas") + **"Alterar valor"**; "Outras sugestões": Mais rápido · Valor
  máximo; share block "Envie esta avaliação do imóvel para o proprietário" with a
  `quin.to/…` short link + copy + **"Compartilhar no WhatsApp"**; "Vendidos no QuintoAndar"
  comparables (Vendido/Próximo tags, price + month/year, R$/m², m², quartos, vagas, street,
  neighbourhood, city).

## 8 · Visitas `/visits`

- Chips: Todas · Meus imóveis (`visitType=MY_SUPPLY`) · Meus clientes (`MY_CLIENTS`) ·
  Clientes QuintoAndar (`LEAD_GEN`). Empty state: "Sem visitas — Quando você tiver visitas
  marcadas, você vai poder acompanhá-las aqui."
- Same columns/panels as Início. Status filter: Não confirmada · Confirmada · Cancelada.
- API also requests status `DONE`, never seen as a UI tag.

## 9 · Propostas de venda (all empty on 2026-09-24)

- **Minhas propostas** — "Gerencie e negocie as propostas de venda feitas pelos seus
  corretores nos imóveis do Marketplace." Tabs/chips → routes under `/sale-offers/internal/`:
  Em andamento: Todas `in-negotiation` · Recebidas `ongoing` · Aceitas `accepted` · TIC
  emitida `tic-created` · Assinadas `post-ccv`; Concluídas `finished`; Canceladas `canceled`.
  Columns: Imóvel ↓ · Comprador (filter) · Valor · Status ↓ (Concluídas/Canceladas: "Concluída
  em"/"Cancelada em"). Empty: "Sem propostas <x> — Quando você tiver propostas <x>, vai poder
  acompanhá-las aqui."
- **Propostas externas** — "Acompanhe as propostas de venda realizadas por corretores
  externos para os imóveis da sua imobiliária." Same under `/sale-offers/`, **no "TIC
  emitida"** chip.

## 10 · Performance — "Pós-Publicação" `/reports/pos`

Banner "Esta visualização apresenta o desempenho dos seus imóveis disponíveis para compra e
venda no QuintoAndar."; "Última atualização: <data e hora>"; period select: Este mês · Mês
anterior (default) · Últimos três meses · Últimos seis meses; tabs (`?tab=<name>`): Anúncios
publicados · Visitas · Propostas · Compromissos de compra e venda. All showed "Sem
informações para exibir" — no charts ever seen.

## 11 · Calculadora `/price-calculator`

Landing ("Calcule o valor do aluguel e da venda"; cards "Como calculamos os valores?" —
"Usamos a base de imóveis vendidos no QuintoAndar, dados públicos de transações imobiliárias
e inteligência artificial." / "Relatório de precificação"); "Quero calcular" (first click
only scrolled). 5-step form, subtitle "Descubra o valor correto para o imóvel":
1. Características — tipo (Apartamento · Kitnet/Studio · Casa · Casa em condomínio);
   cobertura Sim/Não; área m²; vagas (0); banheiros (1, "Não incluir lavabo e serviço");
   quartos (1, "Incluindo suites"); suítes (0); items staying (Armário na cozinha,
   Fogão/cooktop, Geladeira, Armário no quarto, Microondas: Sim/Não/Não sei).
2. Condições — "Como está o imóvel?": perfeito estado · precisa de alguns ajustes ·
   recém-construído ou sem itens básicos · mal conservado · antigo bem conservado.
3. Endereço — "Endereço e número", "Preencher com CEP".
4. Custos — valor do condomínio (R$/mês); "O imóvel está sujeito ao pagamento de IPTU?".
5. Informações — Nome do corretor, Nome da Imobiliária, "Qual sugestão de preço você
   precisa?" Aluguel · Venda · Venda e Aluguel.
Never submitted.

## 12 · Gerenciar usuários `/members`

- Columns: Informações da conta (name, phone) · Perfil · Status · actions. Paginated.
- Perfis: Corretor de aluguel · Corretor de venda · Administrador. Status: Acesso liberado ·
  Convidado · Conta desativada.
- Actions: Acesso liberado → pencil → `/user-profile/:uuid`; Convidado → **"Reenviar
  convite"** + trash; Conta desativada → greyed trash.
- **"Adicionar usuários"** → drawer "Adicionar novo usuário": perfil select (with
  descriptions — broker: "Terá acesso à visualização da carteira de imóveis captados por
  ele, à calculadora de preços e ao aplicativo de corretores do QuintoAndar."; admin:
  "Terão acesso à visualização de todos os imóveis, ao agendamento de visitas, à gestão de
  propostas e ao gerenciamento de perfis de usuários."), Nome (max 30), E-mail, Telefone
  (+55 default, "(00) 9 0000-0000"), **"Adicionar usuário"** (sends invite).
- **Perfil do usuário:** Dados pessoais (name, e-mail, CRECI); Acessos ("Perfil: <x>"
  "Ativo"; "Programa Cliente QuintoAndar" "Não habilitado"); Áreas de atuação + "Gerenciar
  bairros" → `/operation-areas?contextType=AGENT&personUuid=…&isEditMode=true`: map of
  neighbourhood polygons, "Bairros selecionados" per-city tabs, "Desfazer a última edição",
  "Desmarcar todos os bairros", "Cancelar", **"Salvar área de atuação"**. No edit for
  name/profile/status on this page.

## 13 · Perfil da Imobiliária `/company-profile`

Read-only: Endereço · Dados da imobiliária (name ×2, CNPJ) · Áreas de atuação (cities) +
"Gerenciar bairros" (needed a 2nd click) → `/operation-areas?contextType=COMPANY`: "Área de
atuação de <imobiliária>", **"Editar áreas selecionadas"**, per-city tabs with counts and
neighbourhood-name lists.

## 14 · Sessões de Fotos `/photos` (hidden)

"Agende a sessão de fotos para o imóvel ser publicado." Chips: Todas · Para agendar
(`status=PENDING`) · Agendadas (`SCHEDULED`) · Aguardando publicação (`WAITING_PUBLICATION`).
Columns: Sessão · Imóvel (→ `/property`) · Entrada · Status ("Agendamento pendente") ·
"Agendar fotos". Drawer (progress bar): step 1 entry block + "Como você prefere que seja a
sessão de fotos?" — "Sem hora marcada" (greyed; "O fotógrafo vai sozinho no imóvel, em
horário comercial (8h às 18h)") / "Com hora marcada" ("Alguém acompanha o fotógrafo…");
step 2 "Escolha uma data" (e.g. "Sexta, 25/09/2026") + "Escolha um horário" ("As sessões
duram em média 30 minutos"). Later steps unseen.

## 15 · Glossary (portal's own definitions; "—" = not defined by the portal)

| Term | Definition shown |
|---|---|
| Com pendências / Em processamento / Anunciado / Desativado / Não elegível / Descartado | Page descriptions in §4–§5 |
| Confirmada · Não confirmada · Cancelada | — ("Visitas não confirmadas pelo proprietário podem ser canceladas…") |
| Corretor externo | reasons in §3 |
| Captador · Alta Procura · Preço certo · Preço muito acima · Mais rápido · Valor máximo | — |
| Programa Cliente(s) QuintoAndar | — (both spellings appear) |
| Nota de desempenho | "…conjunto de ações que impactam a visibilidade do imóvel." |
| Alta confiança | "Já negociamos muitos imóveis parecidos no mesmo bairro." |
| TIC emitida · Assinadas (`post-ccv`) · Compromissos de compra e venda | — |
| Perfis | descriptions in §12 |
| Acesso liberado · Convidado · Conta desativada · Agendamento pendente | — |

## 16 · Flows walked (final write step never executed)

| Flow | Path | Final (write) step |
|---|---|---|
| Answer a visit | Início/Visitas → "Responder" → "Confirmar visita" drawer | Confirmar / Cancelar visita |
| Change entry access | "Editar entrada" → keys → "Continuar" → observation | "Confirmar alteração" |
| Visit hours | "⋮" → "Editar horários disponíveis" or property Visitas tab | "Confirmar horários" |
| Correct listing data | Resumo "Editar" / listing "Editar anúncio" → "Revisar anúncio" | "Enviar correções" |
| Send price report to owner | Desempenho → "⋮" → "Personalizar relatório" | "Alterar valor" / copy `quin.to` / WhatsApp |
| Invite a user | Gerenciar usuários → "Adicionar usuários" | "Adicionar usuário" |
| Schedule photos | `/photos` → "Agendar fotos" → type → date/time | later steps |

Portal-stated rule: pendências and listing data are fixed **in the CRM**; changes take
24–48h to reflect in the Marketplace.
