# Regrouped menus — active products (recommended, approved 2026-10-05)

Rules applied to every product:
- **No item is added, removed or renamed**; only grouping changes. Routes, icons and `status_pagina` keys stay exactly as they are today.
- Groups are nested up to 4 levels (seed `Sidebar` change). Accordion per level, closable; the top-level group holding the current page is highlighted and the current leaf is marked.
- A group of one item is avoided: the item goes into its closest group.
- In-page tabs stay in-page for now (moving tabs into the menu changes pages, not menus).
- Products with 7 items or fewer that already read well are left as they are.

Labels below are verbatim from each product's `NAV_GROUPS`; `›` marks nesting.

## social-wiring (51 items, today 9 groups)

- **Principal**: Dashboard · Contatos · Agendamentos
- **Imóveis**: Imóveis · Permutas
- **Leads**: Leads · Funil de Vendas · Processos de Venda · ROI por Portal
- **Clientes**: Clientes · Revisão de Duplicados
- **Edição de Fotos**
  - **Operação**: Lotes · Novo Lote · Painel · Processamento
  - **Configuração**: Configurações · Referências · Guias de Estilo · Regras · Curadores · Modelos
- **Criação de mídia**: Criação de mídia (`/media-creation`). The CoreStudio tree is added here when the Criação de Mídia module is built (see `DECISIONS.md`); it sits directly below Edição de Fotos. The 2026-10-06 re-crawl confirmed CoreStudio's sidebar is unchanged (`core-studio/specs/page-map-v2.md` §0.4). Its newly mapped routes are not menu items: Minha conta's **Meu Perfil · Instagram · Integrações** are in-page tabs (they stay in-page under the rule above), and `Gerar Headlines` lands on a 3-card page that opens `/headlines?who=me|public|viral`.
- **Marketing**
  - **Email**: Painel · Campanhas · Contatos · Listas · Templates · Automações · Domínios
  - **Mailchimp**: Membros · Listas · Templates · Campanhas · Configuração
- **Emissões**: Certidões · Extrator de Matrículas · Agentes Financeiros
- **Conexões**: Marcas · Monitor · YouTube · Meta · WhatsApp · n8n
- **Configuração**: Configurações · Testemunhas · Equipe · Custos

## core (20 items, today 2 groups)

- **Administracao**
  - **Visão geral**: Dashboard · Analytics · Digest de auditoria · Fleet Control
  - **Clientes**: Usuarios · Organizacoes
  - **Comercial**: Produtos · Planos · Assinaturas · Faturamento
  - **Plataforma**: Chaves API · Chaves LLM · Webhooks · Templates · Logout Behavior · Configuracoes · Segurança
- **Website**: Documentação · Configurações · Leads

The `marketing` role still sees only Website.

## orbity (15 items, today 7 groups, 4 of them single-item)

- **Principal**: Dashboard · Equipe · Financeiro
- **CRM**: Clientes · Funil
- **Operações**: Tarefas · Agenda · Rotinas
- **Marketing**: Conteúdo · Tráfego · Automacao · Relatórios

## igig (13 items, today 1 group)

- **Principal**: Dashboard · Equipe
- **Comercial**: Comercial · Clientes · Orçamentos · Produtos e Serviços
- **Operação**: Esteira · Calendário · Distribuição
- **Financeiro**: Financeiro · Custos
- **Integrações**: Integrações · Automações

## community — staff layout (12 items, today 1 group)

- **Principal**: Dashboard · Membros · Planos · Inscrições · Financeiro · Grupoterapia
- **WhatsApp**: WhatsApp · Sincronização · Transmissões · Moderação
- **Configuração**: Equipe · Configurações

Member layout (Minha área: Minha conta · Grupoterapia) is unchanged.

## p-studio (10 items, today 1 group)

- **Principal**: Dashboard · Agenda
- **Comercial**: CRM Comercial · Clientes
- **Operação**: Produção · Imóveis · Serviços · Equipamentos
- **Gestão**: Financeiro · Integrações

## agents (8 items, today 1 group)

- **Principal**: Dashboard · Julia · Agentes · Agent Studio · Aprovações
- **Configuração**: Equipe · Configurações do agente · Credenciais

## academia-de-reciclagem (7 items, today 1 group)

- **Principal**: Dashboard · Interessados · Equipe
- **Conhecimento**: Base de conhecimento · Decisões · Perguntas abertas · Roadmap e tarefas

## store (2 items)

Unchanged: **Loja**: Página de vendas · Vendas.

## Known issues fixed with the seed change

- Prefix double highlight: a parent route (e.g. `/admin`, `/edicao-fotos`, `/email`, `/clientes`) no longer highlights together with its children; only the most specific match is the current page.
