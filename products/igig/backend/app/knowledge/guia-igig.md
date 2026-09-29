# Guia IgIg — manual de instruções e especificação da plataforma

> **Para quem é este documento.** (1) O Assistente IgIg (o chat de ajuda disponível em todas as telas) usa este guia como TODO o seu conhecimento da plataforma. (2) A equipe da agência e o dono do produto usam-no como manual de instruções e especificação oficial de cada página e funcionalidade.
>
> **Regra de manutenção.** Este arquivo descreve o comportamento REAL do código. Toda mudança de página, regra, mensagem ou fluxo atualiza este guia no MESMO commit (`products/igig/backend/app/knowledge/guia-igig.md`). Um guia desatualizado faz o assistente afirmar com confiança um comportamento que não existe mais.
>
> **Como ler.** Capítulo 0 = visão geral, acesso, papéis, navegação, rotas, endpoints, modelo de dados, ciclo de vida, jobs, configuração, erros, IA e glossário. Capítulos 1–4 = uma especificação por página/funcionalidade, sempre com as mesmas 11 seções: 1. Propósito · 2. Acesso · 3. Layout · 4. Campos · 5. Ações · 6. Estados · 7. Regras de negócio e por quê · 8. Fluxo de dados · 9. Dependências de configuração · 10. Limitações conhecidas · 11. Perguntas frequentes. Capítulo 5 = limitações globais e itens que dependem de fornecedor ou de decisão do dono do produto.

## Sumário
- Capítulo 0 — Plataforma (visão geral, acesso, papéis, navegação, rotas, endpoints, dados, ciclo de vida, jobs, configuração, erros, IA, glossário)
- Capítulo 1 — Comercial e Clientes (Dashboard, Comercial, Card do negócio, Pré-qualificação, Clientes, Automações, Fontes de lead, Equipe)
- Capítulo 2 — Orçamentos, Produtos e Serviços, Custos, Contrato, E-mail
- Capítulo 3 — Esteira, Calendário, Central da Marca e Cofre, Portal de Aprovação
- Capítulo 4 — Distribuição, Financeiro, Integrações, Relatórios
- Capítulo 5 — Limitações globais e itens dependentes de fornecedor/decisão


---

# Capítulo 0 — Plataforma

## IgIg — Guia da Plataforma (visão geral, acesso, papéis, navegação, rotas, API, dados, ciclo de vida, configuração, erros, IA e glossário)

> Camada TRANSVERSAL do manual do IgIg. Público: (1) o assistente de ajuda do IgIg, que responde usuários a partir deste texto; (2) o dono do produto, como especificação durável. Conferido no código final do IgIg (frontend React, backend FastAPI, migrations SQL) e, onde o IgIg delega, no seed da plataforma NoctusAI. Textos entre aspas "assim" são os rótulos/mensagens EXATOS (alguns textos da plataforma base aparecem sem acento no código, ex.: "Pagina nao encontrada", "Sem permissao" — mantidos como estão). "(não confirmado no código)" marca o que não foi possível confirmar. As especificações por página estão nos Capítulos 1 a 4 deste mesmo arquivo; o Capítulo 5 consolida as limitações globais.

---

## 1. Visão geral e propósito do IgIg

O IgIg é o "ERP para agências de comunicação" da NoctusAI. Organiza a agência inteira num só lugar, do primeiro contato do lead à fatura paga. O público é a equipe da agência, muitas vezes usando pelo celular (as telas são "mobile-first"). Página de apresentação: "O ERP da sua agência de comunicação" — "Do lead ao contrato assinado, da pauta à peça aprovada pelo cliente, do apontamento de horas à margem real por conta — em um só lugar."

Módulos (na ordem do menu):
1. **Dashboard** — indicadores da carteira, produção, financeiro do mês e funil Comercial.
2. **Comercial** — funil (kanban) de negócios. Leads chegam pelo formulário público de pré-qualificação, pelo WhatsApp (WAHA), pelo Meta Lead Ads ou pelo botão "Novo lead". Perdidos ficam arquivados e podem ser reabertos. Card do negócio com lembretes e Assistente IA.
3. **Clientes** — carteira; o card do cliente reúne dados, marcas (Central da Marca + Cofre de Acessos), orçamentos e contratos, calendário, lembretes, esteira e financeiro.
4. **Orçamentos** e **Produtos e Serviços** — proposta mensal montada do catálogo, com totais e margem estimada, PDF, envio por e-mail, versões, aceite/recusa.
5. **Esteira** — produção: tarefas por etapa (roteiro → design → revisão → aprovação do cliente → agendamento), cronômetro de horas, link público de aprovação para o cliente.
6. **Calendário** — pautas (conteúdos planejados) com copy, direção de vídeo e peças.
7. **Distribuição** — agendar/publicar nas redes, métricas, BI de eficiência.
8. **Financeiro** — fechamento do mês (faturas dos contratos ativos + excedentes), envio da fatura por e-mail, DRE por cliente, inadimplência (atualizada todo dia às 06:00), relatórios.
9. **Integrações** — e-mail (SMTP/Gmail), fontes de lead (WAHA, Meta Lead Ads), canais de publicação.
10. **Automações** — regras "ao entrar na etapa" e "SLA estourado" nos dois quadros.
11. **Custos** — funções e profissionais com custo/hora (alimenta orçamento, BI e DRE).
12. **Equipe** — contas de login e convites.

Em todas as telas logadas: **Assistente IgIg**, o chat de ajuda que responde dúvidas de uso a partir deste manual (ver §13.2).

Tudo é **multiempresa**: cada agência é uma **organização** e só enxerga os próprios dados.

---

## 2. Acesso, login, SSO, convites, organizações

### 2.1 Página pública inicial (Landing) — `/`
Quem não está logado vê: barra com o logotipo (ícone de paleta) e "IgIg", botão "Entrar" (→ `/login`); título "O ERP da sua agência de comunicação"; botões "Começar agora" (→ `/login`) e "Conhecer NoctusAI" (site da NoctusAI); rodapé "© <ano> NoctusAI. Todos os direitos reservados.". Qualquer outro endereço interno aberto sem login redireciona para `/`, mas **o endereço pedido é lembrado**: depois de entrar na mesma aba (login direto ou retorno do SSO), a pessoa é levada de volta a ele (ex.: um link `/esteira?tarefa=<id>` recebido numa notificação ou compartilhado por um colega). O endereço fica guardado só naquela aba do navegador (`sessionStorage`), só vale para caminhos internos do próprio IgIg e é usado uma única vez; se a pessoa, depois de entrar, já estiver navegando para outra página, ele é descartado. `/landing` também redireciona para `/`.

### 2.2 Duas formas de entrar
**A) SSO pela central NoctusAI (caminho principal).** A pessoa entra no portal NoctusAI e abre o IgIg de lá; o navegador chega em `/sso?token=...` e a tela mostra "Autenticando via NoctusAI..." até abrir o Dashboard. O portal grava no perfil a organização, o papel, a assinatura e a licença. Limite de tentativas: "Aguardando limite de requisicoes" com contagem ("Tentando novamente em:"). Falha: "Erro no login SSO" com "Tentar novamente" e "Voltar ao NoctusAI". Quem entrou por SSO vê "Voltar ao NoctusAI" no rodapé do menu.

**B) Login direto — `/login`.** "Entrar" / "ERP para agências de comunicação"; campos "Email" (exemplo "seu@email.com") e "Senha"; link "Esqueceu a senha?" (→ `/forgot-password`); botão "Entrar" ("Entrando..."). Validações "Email invalido", "Senha deve ter no minimo 6 caracteres". Sucesso "Login realizado com sucesso!"; erro "Erro ao entrar". Rodapé "Acesse pelo NoctusAI". Não existe "criar conta" no IgIg: contas nascem por convite ou pela central.

### 2.3 Esqueci a senha — `/forgot-password`
"Email" → "Enviar link de recuperacao". Sucesso "Email enviado com sucesso!" ("Verifique sua caixa de entrada"); erros "Erro ao enviar email", "Erro inesperado ao enviar email"; validação "Email invalido". A redefinição é do provedor de autenticação (Supabase). O IgIg **não tem tela própria de "nova senha"** (nenhuma rota de redefinição é registrada); para onde o link do e-mail leva e se ele já abre uma sessão dependem da configuração do provedor (não confirmado no código). Logado, a senha também muda pelo menu do usuário ("Nova Senha", "Confirmar Senha", "Atualizar Senha").

### 2.4 Convites — `/accept-invite/<token>`
1. Um Proprietário, Administrador ou Gerente convida em "Equipe" (e-mail + papel — a lista de papéis já vem filtrada pelo que a própria pessoa pode conceder, veja 3.1). O convite vale **7 dias**; não pode haver dois convites pendentes para o mesmo e-mail ("Ja existe um convite pendente para este email"). O convite é sempre criado; se o e-mail não puder ser enviado (ex.: serviço de e-mail não configurado), a tela mostra "Convite criado, mas o e-mail não foi enviado — copie o link" com um botão "Copiar link" que copia o próprio link de aceite (`/accept-invite/<token>`) para compartilhar manualmente.
2. O convidado abre o link: "Aceitar Convite" / "Validando convite..."; se válido, mostra o e-mail (só leitura) e o papel e pede "Nome completo", "Senha", "Confirmar senha" → "Aceitar Convite" ("Criando conta..."). Validações "Nome e obrigatorio", "Senha deve ter no minimo 6 caracteres", "Senhas nao conferem".
3. Sucesso: "Conta criada com sucesso!" / "Voce ja pode fazer login com seu email e senha." + "Ir para o login".
4. Erros: "Token de convite nao encontrado na URL.", "Convite invalido ou expirado.", "Convite nao encontrado", "Convite expirado", "Este convite ja foi utilizado ou cancelado", "Erro ao validar convite. Tente novamente.", "Erro ao aceitar convite.", "Erro de conexao. Tente novamente.", "Erro ao vincular usuario a organizacao"; link "Voltar ao login".
Regras: o e-mail do convite manda (não dá para aceitar com outro); conta já existente com o mesmo e-mail é vinculada sem trocar a senha; quem aceita logado entra com a conta atual (senha digitada ignorada); uma pessoa pertence a **uma** organização — se já estiver em outra: 409 "Voce ja pertence a outra organizacao. Entre em contato com o suporte para transferir sua conta.".

### 2.5 Sair, sessão, avisos
- "Sair": avatar (canto superior direito) → ícone de saída. Quem entrou por SSO volta à central; quem entrou direto volta a `/login`.
- A sessão é renovada automaticamente em uso. Após **28 minutos sem interação** aparece o aviso "Sessao expirando" — "Sua sessao sera encerrada em M:SS por inatividade." — com o botão "Continuar" (renova a sessão). Sem clique, aos **30 minutos** a sessão termina e o navegador volta para a central NoctusAI.
- Avisos da central no topo (últimos 7 dias): "Periodo de teste expira em N dias." / "Periodo de teste expirado." / "Licenca expira em N dias." / "Licenca expirada.".

### 2.6 Organizações (multiempresa)
- Cada agência é uma organização (`org_id`). Toda tabela de negócio tem `org_id`; o banco aplica **RLS**: só volta linha com `org_id` igual ao da função `public.current_org_id()`, que lê a tabela confiável `public.noctus_users` (nunca dados editáveis pelo usuário).
- O servidor também filtra `org_id` em toda operação, inclusive nos caminhos com acesso de serviço (portal de aprovação, webhooks, rotinas, card hub, formulário público).
- Não existe "trocar de organização" no IgIg. O nome da organização aparece sob "IgIg" no topo do menu (sem nome: "NoctusAI").
- **Cliente final da plataforma** (papel de organização `membro`, reservado a clientes que se cadastram sozinhos em produtos NoctusAI voltados ao consumidor) **não enxerga nada do IgIg**: para esse papel `public.current_org_id()` responde vazio e todas as regras RLS negam acesso (migração 031). Esse papel nunca é atribuível pela tela Equipe.

---

## 3. Papéis e permissões

### 3.1 Papéis existentes
Papéis de organização (rótulo na tela Equipe): "Proprietário" (`owner`), "Administrador" (`admin`), "Gerente" (`manager`), "Membro" (`member`), "Visualizador" (`viewer`), "Desenvolvedor" (`dev`), "Teste" (`test`), "Corretor" (`corretor`). Além deles, o **administrador da plataforma** NoctusAI (acesso total).

Grupos que o código usa:
- **Administrador da agência** (`ADMIN_ROLES`) = Proprietário ou Administrador (ou admin da plataforma). No servidor: `exigir_admin_da_org` / `exigir_admin_do_quadro` (`app/pipelines.py`) e a checagem própria do Cofre (`marca_router`); no navegador: `useIsOrgAdmin` (só esconde o que o servidor recusaria).
- **Pode convidar** (`MANAGE_TEAM_ROLES`) = Proprietário, Administrador, Gerente — com teto: só Proprietário convida como "Proprietário"; só Proprietário ou Administrador convidam como "Administrador"; o Gerente convida nos demais papéis. O papel e a organização de quem convida/remove são lidos da tabela confiável `public.noctus_users` (nunca de dados editáveis pelo usuário), e toda leitura, convite e remoção da Equipe fica restrita à organização de quem pede.
- **Vê páginas em desenvolvimento** (`DEV_ROLES`) = Proprietário, Desenvolvedor, Administrador.
- Todos os demais papéis (Membro, Visualizador, Desenvolvedor, Teste, Corretor, Gerente fora do convite) são tratados como **membro comum**. **Visualizador NÃO é somente leitura** no IgIg (não há trava no código).

Recusa de ação só-admin: 403, `code` `admin_obrigatorio`, com "Apenas administradores podem alterar as etapas do quadro." (editores de etapas) ou "Apenas administradores da organização podem realizar esta ação." (demais). Revelar senha do Cofre: 403 "Apenas administradores podem revelar senhas". Equipe (seed): 403 "Sem permissao para convidar" / "Sem permissao para convidar como <papel>" / "Sem permissao"; 400 "Papel invalido: <papel>".

### 3.2 Matriz papel × ação
Legenda: ✅ pode; ❌ o servidor recusa; "UI" = o que a tela faz para quem não pode.

| Ação | Proprietário / Administrador / admin da plataforma | Gerente | Membro, Visualizador, Desenvolvedor, Teste, Corretor | Tela para quem não pode |
|---|---|---|---|---|
| Ver qualquer página do menu em `producao` | ✅ | ✅ | ✅ | — |
| Ver páginas em `desenvolvimento` (selo "DEV") | ✅ | ❌ (só Desenvolvedor, além de Proprietário/Admin) | Desenvolvedor ✅; demais ❌ | Item some do menu |
| Criar lead, mover/fechar/perder/reabrir negócio, editar lead/negócio, card do negócio, Assistente IA | ✅ | ✅ | ✅ | — |
| Lembretes do card (cliente e negócio): criar, editar, concluir/reabrir, excluir | ✅ | ✅ | ✅ | — |
| **Criar/renomear/recolorir/reordenar/excluir etapas do Comercial** | ✅ | ❌ | ❌ | Cabeçalhos sem controles; sem "Configurar etapas" e "+ coluna" |
| **Criar/renomear/recolorir/reordenar/excluir etapas da Esteira** | ✅ | ❌ | ❌ | Idem |
| **Reatribuir papel de etapa da Esteira** ("Papéis das etapas") | ✅ | ❌ | ❌ | Painel não aparece |
| **Reatribuir o papel "Fechado" do Comercial** ("Papéis das etapas") | ✅ | ❌ | ❌ | Painel não aparece |
| Criar/editar/ativar clientes, marcas, acessos do Cofre (sem revelar) | ✅ | ✅ | ✅ | — |
| **Remover cliente** (exclusão em cascata) | ✅ | ❌ | ❌ | Botão aparece; servidor recusa com 403 |
| **Revelar senha do Cofre** | ✅ | ❌ | ❌ | Selo "Protegida" com cadeado |
| Orçamentos (criar, versionar, PDF, enviar, aceitar, recusar, gerar pautas), contratos (gerar, marcar assinado), produtos e serviços | ✅ | ✅ | ✅ | — |
| Custos — ver funções/profissionais | ✅ | ✅ | ✅ | — |
| **Custos — criar/editar/remover/ativar/desativar funções e profissionais, vincular usuário** | ✅ | ❌ | ❌ | Controles escondidos: a pessoa vê as tabelas só para leitura |
| Esteira — tarefas, cronômetro, link de aprovação; Calendário — pautas e peças | ✅ | ✅ | ✅ | — |
| Distribuição — agendar, publicar, cancelar publicação, métricas | ✅ | ✅ | ✅ | — |
| Financeiro — ver, criar fatura manual, adicionar item | ✅ | ✅ | ✅ | — |
| **Financeiro — marcar fatura paga** | ✅ | ❌ | ❌ | Botão escondido (página Financeiro e aba Financeiro do card do cliente) |
| **Financeiro — "Enviar fatura" / "Marcar como enviada"** | ✅ | ❌ | ❌ | Botões escondidos |
| **Financeiro — cancelar fatura** | ✅ | ❌ | ❌ | Botão escondido |
| **Financeiro — "Gerar competência" (fechar o mês)** | ✅ | ❌ | ❌ | "Somente administradores da agência podem fechar o mês." |
| **Automações — criar/editar/pausar/excluir** | ✅ | ❌ | ❌ | "Somente administradores da agência podem criar ou alterar automações." |
| Automações — ver regras e execuções | ✅ | ✅ | ✅ | — |
| **Integrações — fontes de lead (WAHA, Meta): salvar/desconectar** | ✅ | ❌ | ❌ | Formulário desabilitado + "Somente administradores da agência podem alterar esta configuração." |
| **Integrações — canais de publicação: conectar/desconectar** | ✅ | ❌ | ❌ | "Somente administradores da agência podem alterar este canal." |
| **Integrações — SMTP salvar/remover; Gmail conectar/desconectar** | ✅ | ❌ | ❌ | Formulário/botões escondidos, com "Apenas administradores da organização podem configurar o SMTP." / "Apenas administradores da organização podem conectar ou desconectar o Gmail." |
| Integrações — testar SMTP; ver status | ✅ | ✅ | ✅ | — |
| Equipe — ver membros | ✅ | ✅ | ✅ | — |
| **Equipe — convidar** | ✅ (Administrador não convida como Proprietário) | ✅ (não como Administrador/Proprietário) | ❌ | Sem botão "Convidar"; a lista de papéis do formulário já esconde o que a pessoa não pode conceder (nunca mostra "Administrador" para um Gerente) — o 403 "Sem permissao para convidar como <papel>" só apareceria numa chamada direta à API |
| **Equipe — ver/cancelar convites pendentes; remover membro** | ✅ | ❌ | ❌ | Sem "Convites pendentes" e sem coluna "Ações" |
| Portal de aprovação (`/aprovar/<token>`), formulário de pré-qualificação | público (qualquer pessoa com o link) | | | — |

### 3.3 Lista completa das ações só-admin no servidor
`exigir_admin_do_quadro` (mensagem "Apenas administradores podem alterar as etapas do quadro."): POST/PATCH/DELETE e POST `/reordenar` em `/api/comercial/pipeline/stages` e `/api/esteira/stages`; PATCH `/api/comercial/pipeline/stages/{id}/papel` e PATCH `/api/esteira/stages/{id}/papel` (reatribuir papel).
`exigir_admin_da_org` (mensagem "Apenas administradores da organização podem realizar esta ação."): DELETE `/api/clientes/{id}`; POST/PATCH/DELETE `/api/automacoes…`; PUT/DELETE `/api/integracoes/leads/whatsapp` e `/meta`; POST/DELETE `/api/integracoes/{canal}`; PUT/DELETE `/api/integracoes/email/smtp`; GET `/api/integracoes/email/gmail/oauth/start`; DELETE `/api/integracoes/email/gmail`; POST/PATCH/DELETE `/api/custos/funcoes…` e `/api/custos/profissionais…`; POST `/api/financeiro/faturas/{id}/pagar`, `/cancelar`, `/enviar`, `/marcar-enviada` e `/api/financeiro/faturas/gerar-competencia`.
Checagem própria: POST `/api/marcas/acessos/{id}/revelar` ("Apenas administradores podem revelar senhas").
Seed (Equipe): POST `/api/team/invite` (owner/admin/manager, com o teto de papel acima); GET/DELETE `/api/team/invitations…` e DELETE `/api/team/{user_id}` (owner/admin; só remove membros da própria organização — "Membro nao encontrado" (404) para quem não é dela; só o Proprietário remove um Proprietário: 403 "Somente o proprietario pode remover um proprietario"; ninguém remove a si mesmo: 400 "Nao pode remover a si mesmo").

---

## 4. Navegação

### 4.1 Menu lateral (ordem, rótulo, rota)
Um único grupo, "Principal" (aberto por padrão):

| # | Rótulo | Ícone | Rota | Título na tela | Chave `status_pagina` |
|---|---|---|---|---|---|
| 1 | "Dashboard" | painel | `/` | "Dashboard" | `dashboard` |
| 2 | "Comercial" | maleta | `/comercial` | "Comercial" | `comercial` |
| 3 | "Clientes" | prédio | `/clientes` | "Clientes" | `clientes` |
| 4 | "Orçamentos" | documento | `/orcamentos` | "Orçamentos" | `orcamentos` |
| 5 | "Produtos e Serviços" | pacote | `/produtos-servicos` | "Produtos e Serviços" | `produtos_servicos` |
| 6 | "Esteira" | quadro kanban | `/esteira` | "Esteira de Produção" | `esteira` |
| 7 | "Calendário" | calendário | `/calendario` | "Calendário Editorial" | `calendario` |
| 8 | "Distribuição" | gráfico de barras | `/distribuicao` | "Distribuição e Métricas" | `distribuicao` |
| 9 | "Financeiro" | carteira | `/financeiro` | "Financeiro" | `financeiro` |
| 10 | "Integrações" | tomada | `/integracoes` | "Integrações" | `integracoes` |
| 11 | "Automações" | fluxo | `/automacoes` | "Automações" | `automacoes` |
| 12 | "Custos" | caixas | `/custos` | "Custos" | `custos` |
| 13 | "Equipe" | pessoas | `/equipe` | "Equipe" | `equipe` |

Topo do menu: ícone de paleta, "IgIg" e o nome da organização. Rodapé (só SSO): "Voltar ao NoctusAI". Não há item "Marca": a Central da Marca fica em Clientes → card → aba "Marcas"; `/marca` redireciona para `/clientes`.

### 4.2 Celular × computador
- **Celular**: menu escondido; botão de menu (três linhas) no canto superior esquerdo abre o menu deslizando da esquerda sobre o conteúdo com fundo escurecido. Escolher um item **fecha o menu** (corrigido nesta versão); tocar fora também fecha. Não há barra inferior.
- **Computador**: faixa estreita fixa à esquerda só com ícones, que se expande com os nomes ao passar o mouse (ou foco do teclado).
- Listas viram cartões no celular e tabelas em telas maiores; quadros kanban rolam para o lado dentro da própria moldura; arrastar card no celular é "pressionar e segurar". Diálogos grandes abrem em tela cheia no celular (≤640px).

### 4.3 Cabeçalho
Botão de menu (celular); à direita: selos de IA (consentimentos pendentes e gasto de IA da organização), **sino de notificações** e **avatar**. O avatar abre: nome, papel ("Administrador" para Proprietário/Administrador, senão o rótulo do papel), "Sair", tema claro/escuro, edição de perfil ("Nome", "Email", "Telefone", "Salvar"/"Salvando..."; "Apenas administradores podem alterar o email" quando o e-mail não é editável) e troca de senha. Mensagens "Perfil atualizado com sucesso!", "Senha atualizada com sucesso!".

**Sino**: notificações do usuário (mais recentes primeiro), contador de não lidas, marcar uma/todas como lidas. O IgIg gera notificações quando: o cliente aprova ou pede ajuste no portal ("Cliente aprovou: <tarefa>" / "Cliente pediu ajuste: <tarefa>", link `/esteira?tarefa=<id>`, que abre a tarefa direto); o cliente responde por e-mail a um orçamento ("Resposta ao orçamento: <título>", link `/orcamentos?id=<id>`; vai para o responsável do negócio, os Proprietários **e os Administradores** da agência); uma automação "Notificar" roda (tipo `automacao`) ou um SLA estoura (tipo `sla_estourado`), com link `/comercial?negocio=<id>` ou `/esteira?tarefa=<id>` (os dois abrem o card/tarefa certo); um lembrete de card vence ("Lembrete: <título do lembrete>" — "Lembrete agendado para “<título do lembrete>”.", ou o nome do cliente/título do negócio quando o "Título" do lembrete ficou vazio; link `/clientes?id=<id>` ou `/comercial?negocio=<id>`; vai para o "Responsável" escolhido no lembrete (quando tem login vinculado) **e** os membros do card vinculados a um login em Custos, sem repetir ninguém; sem nenhum dos dois, para os administradores). Ver §9 e a aba "Lembretes" do card (Capítulo 1).

### 4.4 Visibilidade de páginas (`status_pagina`)
Cada item do menu tem uma linha em `igig.status_pagina` (`nome_pagina` = chave da rota, `status`):

| Status | Quem vê no menu |
|---|---|
| `producao` | Todos |
| `desenvolvimento` | Só Proprietário, Administrador e Desenvolvedor, com o selo "DEV" |
| `desativado` | Ninguém |

- Registradas (todas `producao`): `dashboard`, `equipe`, `comercial`, `clientes`, `esteira`, `calendario`, `distribuicao`, `financeiro`, `integracoes`, `custos`, `orcamentos`, `produtos_servicos`, `automacoes`. A linha inerte `marca` foi removida (migração 030).
- Página do menu sem linha fica escondida para todos (quando a tabela tem alguma linha).
- Enquanto a lista carrega (ou se falhar), o menu aparece completo, sem filtro.
- RLS: `todos_veem_producao` libera as linhas `producao`; `dev_veem_desenvolvimento` libera `desenvolvimento` só para owner/dev/admin.
- A trava é **só do menu**: quem souber o endereço ainda abre a tela.
- Mudança de status é feita pela equipe da plataforma no banco (não há tela no IgIg); o navegador guarda o status por até 10 minutos.

---

## 5. Tabela completa de rotas do frontend

### 5.1 Públicas (sem login)
| Rota | Tela | Para que serve |
|---|---|---|
| `/` (não logado) | Landing | Apresentação e "Entrar" |
| `/landing` | — | Redireciona para `/` |
| `/login` | Login | E-mail e senha |
| `/sso` | Retorno do SSO | Recebe o login vindo da central |
| `/forgot-password` | Esqueci a senha | Link de recuperação |
| `/accept-invite/<token>` | Aceitar Convite | Cria/vincula a conta do convidado |
| `/aprovar/<token>` | Portal de aprovação (white-label) | O cliente da agência aprova ou pede ajuste de uma peça (Capítulo 3) |
| `/pre-qualificacao/<orgId>` | Formulário de pré-qualificação | O prospect envia seus dados; vira lead + negócio (Capítulo 1) |
| `/consent`, `/consent/privacy-policy`, `/consent/terms-of-use` | Central de consentimento | Páginas legais da plataforma (seed) |

### 5.2 Internas (logado)
| Rota | Tela | Parâmetros de URL |
|---|---|---|
| `/` | Dashboard | — |
| `/comercial` | Comercial | `?negocio=<id>` abre o card do negócio (também perdido; é para onde "Novo negócio" no card do cliente leva) |
| `/clientes` | Clientes | `?id=<id>` abre o card do cliente |
| `/orcamentos` | Orçamentos | `?id=<id>` abre o orçamento |
| `/produtos-servicos` | Produtos e Serviços | — |
| `/esteira` | Esteira de Produção | `?cliente=<id>` filtra; `?tarefa=<id>` abre a tarefa (usado pelas notificações), mesmo fora do filtro de cliente; se ela não existir mais: aviso "Tarefa não encontrada — pode ter sido excluída."; fechar a tarefa limpa o parâmetro |
| `/calendario` | Calendário Editorial | `?cliente=<id>` filtra |
| `/distribuicao` | Distribuição e Métricas | — |
| `/financeiro` | Financeiro | — |
| `/integracoes` | Integrações | `?gmail=ok\|erro` (retorno do Google) |
| `/automacoes` | Automações | — |
| `/custos` | Custos | — |
| `/equipe` | Equipe | — |
| `/marca` | — | Redireciona para `/clientes` |
| `/settings/ai` | Configurações de IA (consentimentos) | Página do seed; não aparece no menu |
| qualquer outra | Página não encontrada | "404", "Pagina nao encontrada", "A pagina que voce esta procurando nao existe ou foi movida.", "Voltar", "Ir ao Inicio" |

---

## 6. Tabela completa de endpoints do backend

Base `/api` (exceto sondas `/_health` e `/_ready`). **Auth** = exige login (`Authorization: Bearer …`; sem token válido → 401) e atua só na organização do usuário. **Admin** = Proprietário/Administrador/admin da plataforma (senão 403). **Público** = sem login. "Limitado" = 60 requisições/minuto por IP (`WEBHOOK_RATE_LIMIT`).

### 6.1 Plataforma (seed)
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/health`, GET `/_health`, GET `/_ready` | Saúde do serviço | Público |
| GET `/api/notificacoes?page=&page_size=` | Notificações do usuário | Auth |
| GET `/api/notificacoes/contagem` | `{nao_lidas}` | Auth |
| PATCH `/api/notificacoes/{id}/ler` | Marca uma como lida | Auth |
| POST `/api/notificacoes/ler-todas` | Marca todas | Auth |
| GET `/api/team` | Membros | Auth |
| POST `/api/team/invite` | Convida (`email`, `role`) e envia e-mail | Auth — owner/admin/manager |
| GET `/api/team/accept/validate?token=` | Valida convite | Público |
| POST `/api/team/accept` | Aceita convite | Público (ou logado) |
| GET `/api/team/invitations` | Convites pendentes | Auth — owner/admin |
| DELETE `/api/team/invitations/{id}` | Cancela convite | Auth — owner/admin |
| DELETE `/api/team/{user_id}` | Remove membro da própria organização (não a si mesmo; Proprietário só por Proprietário) | Auth — owner/admin |
| POST `/api/ajuda/chat` | Assistente IgIg (chat de ajuda, resposta em streaming) — ver §13.2 | Auth, 20/min por pessoa |

Não montados no IgIg: `/api/llm/…`, `/api/ai/…`, `/api/scheduler/…`, `/api/status-paginas`, `/api/example`, `/api/webhooks/example` (removido nesta versão).

### 6.2 Clientes
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/clientes?busca=&status=&limit=&offset=` | Lista (padrão 50, máx. 200) + `total` | Auth |
| POST `/api/clientes` | Cria (sempre `prospect`) | Auth |
| GET `/api/clientes/{id}` | Um cliente | Auth |
| PATCH `/api/clientes/{id}` | Edita (`null` limpa o campo) | Auth |
| POST `/api/clientes/{id}/ativar` | prospect → ativo | Auth |
| DELETE `/api/clientes/{id}` | Exclusão definitiva em cascata | **Admin** |

### 6.3 Card hub (mesmos endpoints com prefixo `/api/clientes` — card do cliente — e `/api/comercial/negocios` — card do negócio)
| Método e caminho (após o prefixo) | Propósito | Acesso |
|---|---|---|
| GET/POST `/tags`, PATCH/DELETE `/tags/{tag_id}` | Catálogo de etiquetas | Auth |
| GET `/documentos/tipos` | Tipos de documento (LGPD) | Auth |
| GET `/{id}/card` | Resumo do card | Auth |
| GET `/{id}/timeline` | Linha do tempo paginada | Auth |
| POST `/{id}/notas`, PATCH/DELETE `/{id}/notas/{nota_id}` | Descrição e comentários | Auth |
| PUT `/{id}/tags` | Etiquetas do card | Auth |
| GET/PUT `/{id}/membros` | Membros (profissionais; `profissional_ids`) | Auth |
| GET/POST `/{id}/lembretes`, PATCH/DELETE `/{id}/lembretes/{lembrete_id}` | Aba "Lembretes": lista (pendentes e concluídos, sem os cancelados, por data), cria `{titulo, dispara_em, responsavel_id?}` (201), edita qualquer subconjunto de `titulo`/`dispara_em`/`responsavel_id`/`concluido` (`responsavel_id: null` remove o responsável), exclui de vez (204) | Auth |
| GET/POST `/{id}/checklists`, PATCH/DELETE `/{id}/checklists/{cid}` | Checklists | Auth |
| POST `/{id}/checklists/{cid}/itens`, PATCH/DELETE `/{id}/checklists/{cid}/itens/{iid}` | Itens | Auth |
| GET/POST `/{id}/checklist-extras`, PATCH/DELETE `/{id}/checklist-extras/{eid}`, POST/DELETE `/{id}/checklist-extras/{eid}/documento` | Linhas livres (sem tela no IgIg) | Auth |
| GET/POST `/{id}/documentos` | Lista/envia documento (até 25 MB) | Auth |
| GET `/{id}/documentos/{doc}/url` | Link temporário (5 min), registra acesso | Auth |
| DELETE `/{id}/documentos/{doc}?motivo=` | Exclusão lógica com motivo | Auth |
| GET `/{id}/documentos/{doc}/acessos` | Quem viu/baixou/excluiu | Auth |

### 6.4 Comercial
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/comercial/pipeline/stages`, GET `…/opcoes` | Etapas; cores e papéis válidos | Auth |
| POST `/api/comercial/pipeline/stages`, PATCH/DELETE `…/{stage_id}` (`?reassign_to=`), POST `…/reordenar` | Editar etapas | **Admin** |
| PATCH `/api/comercial/pipeline/stages/{stage_id}/papel` `{papel}` | Move o papel `fechado` para esta etapa (tirando-o da anterior) ou o limpa | **Admin** |
| GET `/api/comercial/board` | Quadro (negócios aberto + ganho) | Auth |
| GET `/api/comercial/negocios?status=&q=` | Todos os negócios (inclui perdidos) | Auth |
| GET `/api/comercial/negocios/{id}` | Um negócio (qualquer status) | Auth |
| POST `/api/comercial/negocios` | Novo negócio (lead existente ou novo manual; `cliente_id` opcional = negócio para um cliente já existente) | Auth |
| PATCH `/api/comercial/negocios/{id}` | Título, valor, responsável | Auth |
| POST `/api/comercial/negocios/{id}/mover-etapa` | Move; Fechado exige `orcamento_id` | Auth |
| POST `/api/comercial/negocios/{id}/perder` | Marca perdido (motivo) | Auth |
| POST `/api/comercial/negocios/{id}/reabrir` | Reabre perdido | Auth |
| POST `/api/comercial/negocios/{id}/assistente` | Assistente IA | Auth, 20/min por pessoa |
| POST `/api/comercial/leads/publico` | Formulário de pré-qualificação | **Público**, limitado |
| GET `/api/comercial/leads?status_filtro=` | Lista leads | Auth |
| GET/PATCH `/api/comercial/leads/{id}` | Um lead / editar | Auth |
| POST `/api/comercial/assinatura/webhook` | Retorno do provedor de assinatura | **Público**, HMAC obrigatório, limitado |

(`POST /api/comercial/leads/{id}/converter` foi removido nesta versão.)

### 6.5 Orçamentos, produtos, contratos, e-mail do orçamento
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/orcamentos?…` | Lista (abas, busca, `negocio_id`, `cliente_id`) | Auth |
| POST `/api/orcamentos/calcular` | Calcula sem gravar | Auth |
| GET/POST/PATCH `/api/orcamentos[/{id}]` | Ler/criar/editar | Auth |
| POST `/api/orcamentos/{id}/nova-versao` | Nova versão | Auth |
| POST `/api/orcamentos/{id}/aceitar` | Aceita: fecha o negócio, cliente, pautas | Auth |
| POST `/api/orcamentos/{id}/gerar-pautas` | Gera pautas que faltam (idempotente; só Aceito) | Auth |
| POST `/api/orcamentos/{id}/recusar` | Recusa (motivo) | Auth |
| POST/GET `/api/orcamentos/{id}/pdf` | Gera PDF / link do PDF | Auth |
| POST `/api/orcamentos/{id}/contrato` | Gera contrato | Auth |
| POST `/api/orcamentos/{id}/enviar` | Envia por e-mail com PDF | Auth |
| GET `/api/orcamentos/{id}/emails` | Histórico de e-mails | Auth |
| GET/POST `/api/produtos-servicos`, PATCH/DELETE `…/{id}` | Catálogo (excluir usado só desativa) | Auth |
| GET `/api/contratos?cliente_id=` | Contratos | Auth |
| GET `/api/contratos/{id}/pdf` | Links temporários do contrato/assinado | Auth |
| POST `/api/contratos/{id}/marcar-assinado` | Contrato físico assinado (upload opcional, 25 MB) | Auth |

### 6.6 Marca e Cofre
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET/POST `/api/marcas` | Marcas / criar | Auth |
| GET `/api/marcas/repertorio/{cliente_id}?marca_id=` | Repertório da marca | Auth |
| GET/PATCH/DELETE `/api/marcas/{id}` | Ler/editar/excluir | Auth |
| POST `/api/marcas/{id}/logo` | Logo (PNG, JPEG, WebP; até 2 MB) | Auth |
| GET `/api/marcas/acessos/{cliente_id}` | Acessos (sem senhas) | Auth |
| POST `/api/marcas/acessos`, PATCH/DELETE `/api/marcas/acessos/{id}` | Criar/editar/remover acesso | Auth |
| POST `/api/marcas/acessos/{id}/revelar` | Revela senha (registrado em `cofre_revelacoes`) | **Admin** |

### 6.7 Calendário (pautas)
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/pautas/calendario?…` | Pautas num período | Auth |
| GET/POST `/api/pautas` | Todas / criar | Auth |
| GET/PATCH `/api/pautas/{id}` | Ler/editar | Auth |
| DELETE `/api/pautas/{id}?confirmar_perda_horas=` | Excluir (409 se há horas e não confirmou); apaga também os arquivos das peças no armazenamento | Auth |
| GET/POST `/api/pautas/{id}/pecas` | Peças (com link) / enviar (até 50 MB) | Auth |
| DELETE `/api/pautas/{id}/pecas/{peca_id}` | Remover peça | Auth |

### 6.8 Esteira
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/esteira/stages`, GET `…/opcoes` | Etapas | Auth |
| POST, PATCH/DELETE `/{id}`, POST `/reordenar` em `/api/esteira/stages` | Editar etapas | **Admin** |
| PATCH `/api/esteira/stages/{id}/papel` | Reatribuir papel | **Admin** |
| GET `/api/esteira/board?cliente_id=` | Quadro | Auth |
| GET `/api/esteira/tarefas/{id}` | Uma tarefa, no mesmo formato do quadro (pauta, cliente, responsável), **sem** filtro de cliente — usado pelo link `?tarefa=` quando a tarefa não está no quadro carregado; 404 "Tarefa não encontrada" se não existe ou é de outra organização | Auth |
| POST `/api/esteira/tarefas` | Nova tarefa (exige pauta) | Auth |
| PATCH `/api/esteira/tarefas/{id}` | Editar título/responsável/prazo/pauta | Auth |
| DELETE `/api/esteira/tarefas/{id}?confirmar_perda_horas=` | Excluir | Auth |
| POST `/api/esteira/tarefas/{id}/mover-etapa` | Mover | Auth |
| GET `/api/esteira/tarefas/{id}/apontamentos` | Horas | Auth |
| POST `/api/esteira/tarefas/{id}/timer/iniciar` / `…/encerrar` | Cronômetro | Auth |
| POST `/api/esteira/tarefas/{id}/link-aprovacao` | Link do cliente + mover para aprovação | Auth |
| GET/POST `/api/esteira/aprovar/{token}` | Portal do cliente (423 `portal_bloqueado` quando o bloqueio por inadimplência está ligado e se aplica) | **Público**, limitado |

### 6.9 Distribuição
GET/POST `/api/distribuicao/publicacoes`; POST `…/publicacoes/{id}/executar`; POST `…/publicacoes/{id}/cancelar`; GET `/api/distribuicao/fila`; POST/GET `…/publicacoes/{id}/metricas`; GET `/api/distribuicao/bi/eficiencia` — todos Auth.

### 6.10 Financeiro e relatórios
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET/POST `/api/financeiro/faturas` | Lista / nova fatura (contrato opcional) | Auth |
| GET/POST `/api/financeiro/faturas/{id}/itens` | Itens / adicionar | Auth |
| POST `/api/financeiro/faturas/{id}/pagar` | Marcar paga | **Admin** |
| POST `/api/financeiro/faturas/{id}/cancelar` | Cancelar fatura | **Admin** |
| POST `/api/financeiro/faturas/{id}/enviar` | Envia a fatura por e-mail ao cliente com o PDF anexo; marca `enviada` | **Admin** |
| POST `/api/financeiro/faturas/{id}/marcar-enviada` | Marca `enviada` sem mandar e-mail | **Admin** |
| POST `/api/financeiro/faturas/gerar-competencia` | Fechamento do mês | **Admin** |
| GET `/api/financeiro/resumo?competencia=` | A receber, recebido, inadimplente, MRR | Auth |
| GET `/api/financeiro/excedentes/{competencia}` | Entregue × contratado | Auth |
| GET `/api/financeiro/dre?competencia=&custo_por_competencia=` | Receita × custo real por cliente. `competencia` filtra só a receita; com `custo_por_competencia=true` (usado só pelo Dashboard) o custo também fica restrito às horas apontadas naquele mês — exige `competencia` (senão 422 "custo_por_competencia requer uma competência") | Auth |
| GET `/api/financeiro/inadimplentes?hoje=` | Faturas vencidas | Auth |
| GET `/api/relatorios/{comercial\|financeiro}?inicio=&fim=&formato=json\|pdf\|csv` | Relatório do período | Auth |

### 6.11 Custos
GET `/api/custos/funcoes`, GET `/api/custos/profissionais` — Auth. POST/PATCH/DELETE em `/api/custos/funcoes[/{id}]` e `/api/custos/profissionais[/{id}]` — **Admin**.

### 6.12 Integrações
| Método e caminho | Propósito | Acesso |
|---|---|---|
| GET `/api/integracoes` | Status dos canais de publicação | Auth |
| POST/DELETE `/api/integracoes/{canal}` | Conectar/desconectar canal social | **Admin** |
| GET `/api/integracoes/email/smtp` | Status SMTP | Auth |
| PUT/DELETE `/api/integracoes/email/smtp` | Salvar/remover SMTP | **Admin** |
| POST `/api/integracoes/email/smtp/testar` | Testar SMTP | Auth |
| GET `/api/integracoes/email/gmail` | Status Gmail | Auth |
| GET `/api/integracoes/email/gmail/oauth/start` | Iniciar conexão Google | **Admin** |
| GET `/api/integracoes/email/gmail/oauth/callback` | Retorno do Google | Público (estado assinado) |
| DELETE `/api/integracoes/email/gmail` | Desconectar Gmail | **Admin** |
| GET `/api/integracoes/leads/whatsapp`, `/meta` | Status + URL do webhook | Auth |
| PUT/DELETE `/api/integracoes/leads/whatsapp`, `/meta` | Configurar / desconectar fonte de lead | **Admin** |

### 6.13 Automações
GET `/api/automacoes?pipeline=&stage_id=`, GET `/api/automacoes/execucoes?limit=&automacao_id=` — Auth. POST `/api/automacoes`, PATCH/DELETE `/api/automacoes/{id}` — **Admin**.

### 6.14 Webhooks públicos (chamados por fornecedores)
| Método e caminho | Quem chama | Proteção |
|---|---|---|
| POST `/api/webhooks/waha/{token}` | WAHA (novas conversas → leads) | Token da organização na URL + HMAC opcional (`IGIG_WAHA_WEBHOOK_HMAC_SECRET`) |
| GET `/api/webhooks/meta/leadgen` | Meta — verificação | Verify token da organização |
| POST `/api/webhooks/meta/leadgen` | Meta Lead Ads | `X-Hub-Signature-256` (app secret) obrigatório |
| POST `/api/webhooks/gmail/push` | Google Pub/Sub (respostas a orçamentos) | Token OIDC do Google |
| POST `/api/comercial/assinatura/webhook` | Provedor de assinatura | HMAC obrigatório (`IGIG_ASSINATURA_WEBHOOK_SECRET`) |
Todos limitados a 60/min por IP.

---

## 7. Modelo de dados (schema `igig`)

Todas as tabelas têm `id` (UUID) e `org_id`; em geral `created_at`/`updated_at`. RLS restringe cada linha à organização do usuário (tabelas do card hub: o usuário comum só lê; gravações passam pelo servidor).

### 7.1 Plataforma
- **status_pagina** — `nome_pagina` (única), `status` (`producao`/`desenvolvimento`/`desativado`), `descricao`.
- **invitations** — `email`, `role` (padrão `member`), `invited_by`, `token` (único), `status` (`pending`/`accepted`/`expired`/`canceled`), `expires_at` (+7 dias), `accepted_at`, `accepted_by`.
- (A tabela de exemplo `examples` foi removida — migração 030.)

### 7.2 Comercial
- **lead** — `nome`, `email`, `telefone`, `empresa`, `nicho`, `canais_atuais`, `dores`, `orcamento_disponivel`, `instagram`, `especificacoes` (JSON), `observacoes`, `origem` (`formulario`/`manual`/`whatsapp`/`meta_ads`), `como_conheceu` (texto livre), `status` (`novo`/`qualificado`/`descartado`/`convertido`), `cliente_id`, `meta_lead_id`, `waha_chat_id`.
- **negocio** — `lead_id` (obrigatório), `titulo`, `valor_estimado`, `etapa_id`, `kanban_pos`, `responsavel_id` (→ profissional), `status` (`aberto`/`ganho`/`perdido`), `stage_entered_at`, `ganho_em`, `perdido_em`, `motivo_perda`, `perdido_stage_id`, `orcamento_aceito_id`, `cliente_id`, datas do card (`data_inicio`, `data_entrega`, `entrega_concluida`, `lembrete_minutos_antes`, `recorrencia`).
- **pipeline_stages** — `pipeline` (`comercial`/`esteira`), `slug`, `label`, `cor`, `posicao`, `papel` (`fechado`; `aprovacao_cliente`, `agendado`; no máximo uma etapa por papel), `ativo`.
- **pipeline_movimentos** — `pipeline`, `entidade_id`, `cliente_id`, `de_etapa_id` (vazio = entrada no quadro), `para_etapa_id`, `responsavel_id` (quem moveu; vazio quando foi o cliente no portal; na exclusão de etapa com realocação, o administrador que excluiu), `motivo` (na exclusão de etapa: "Etapa "<nome>" excluída — carta movida para "<destino>"."), `created_at`.
- **produto_servico** — `secao` (`criacao_conteudo`/`gestao_conta`), `nome` (único por seção), `descricao`, `preco_base`, `unidade`, `horas_estimadas`, `formato`, `ativo`, `ordem`.
- **orcamento** — `negocio_id`, `lead_id`, `cliente_id`, `titulo`, `versao`, `validade`, `horas_estimadas`, `custo_estimado`, `preco_sugerido`, `preco_final`, `margem_alvo` (legado), `subtotal_criacao`, `subtotal_gestao`, `desconto`, `total_mensal`, `margem_estimada`, `limites_escopo` (JSON), `observacoes`, `pdf_key`, `enviado_em`, `email_message_id`, `email_thread_id` (legado), `respondido_em`, `aceito_em`, `recusado_em`, `motivo_recusa`, `status` (`rascunho`/`enviado`/`aceito`/`recusado`/`expirado`/`substituido`). Só um `aceito` por negócio.
- **orcamento_item** — `orcamento_id`, `produto_servico_id`, `secao`, `descricao`, `preco_unitario`, `recorrente`, `dias_semana` (seg=1 … dom=64, somados), `qtd_por_dia`, `quantidade_mensal`, `subtotal`, `ordem`.
- **orcamento_email** — `direction` (`out`/`in`), `message_id`, `thread_id`, `from_addr`, `subject`, `snippet`, `occurred_at`.
- **gmail_watch** — `email`, `history_id`, `expiration`, `topic`.

### 7.3 Clientes, marca, contratos
- **cliente** — `nome`, `nicho`, `email`, `telefone`, `status` (`prospect`/`ativo`/`inativo`/`inadimplente`), `origem`, `observacoes`, `encerrado_em`, `lead_id` (um cliente por lead), `negocio_id`, datas do card (`recorrencia` diaria/semanal/mensal/anual).
- **marca** — `cliente_id`, `nome`, `logo_url`/`logo_key`, `paleta`, `tom_de_voz`, `termos_proibidos`, `nivel_formalidade`, `linhas_editoriais`, `personas`.
- **acesso** — `cliente_id`, `rotulo`, `plataforma`, `url`, `usuario`, `senha_cifrada`, `observacoes`.
- **cofre_revelacoes** (migração 028) — `acesso_id`, `revelado_por`, `revelado_em`: registro permanente (só inclusão) de cada revelação de senha do Cofre.
- **contrato** — `cliente_id`, `orcamento_id`, `numero`, `valor_mensal`, `posts_por_mes`, `valor_excedente`, `dia_vencimento` (1–31), `data_inicio`, `data_fim`, `status` (`rascunho`/`aguardando_assinatura`/`ativo`/`encerrado`), `assinado_em`, `modalidade_assinatura` (`digital`/`fisica`), `assinado_manual_em`, `documento_key`, `documento_assinado_key`, `provedor_assinatura`, `assinatura_external_id`, `link_assinatura`.

### 7.4 Produção
- **pauta** — `cliente_id`, `marca_id`, `titulo`, `formato`, `funil` (`topo`/`meio`/`fundo`), `linha_editorial`, `copy_texto`, `direcao_video`, `canal`, `data_publicacao`, `publicado_em` (gravado quando uma publicação sai), `orcamento_item_id`, `gerada_automaticamente`.
- **peca** — `pauta_id`, `storage_key`, `nome_arquivo`, `mime_type`, `tamanho_bytes`, `ordem`.
- **tarefa** — `pauta_id`, `cliente_id`, `titulo`, `etapa_id`, `kanban_pos`, `responsavel_id`, `prazo`, `refacoes`, `observacao_cliente`.
- **apontamento** — `tarefa_id`, `usuario_id`, `profissional_id`, `iniciado_em`, `encerrado_em`, `minutos` (arredondado para baixo, legado), `duracao_segundos` (migração 028: duração exata em segundos; o total da Esteira, o BI de eficiência, a DRE e o relatório financeiro somam os segundos e só então convertem para horas/custo; linhas antigas sem segundos usam `minutos × 60`). No máximo um cronômetro aberto por pessoa.
- **aprovacao** — `tarefa_id`, `token`, `expira_em` (+14 dias), `emitido_por`, `decidido_em`, `decisao` (`aprovado`/`ajuste`), `observacao`.
- **pauta_slot_gerado** (migração 033) — `orcamento_item_id`, `slot_date`, `created_at`; único por (organização, item, dia). Registro **só de inclusão** de cada "vaga" (item recorrente × dia) para a qual uma pauta automática já foi gerada. A geração de pautas consulta este registro, e não as pautas existentes: apagar uma pauta automática ou arrastá-la para outra data **não** libera a vaga, então ela nunca é recriada sozinha.

### 7.5 Custos
- **funcao** — `nome` (único), `custo_hora_padrao`.
- **profissional** — `nome`, `usuario_id`, `funcao_id`, `custo_hora_override` (vazio = herda; 0 = custo zero), `ativo`.

### 7.6 Distribuição e integrações
- **publicacao** — `pauta_id`, `canal` (`instagram`/`facebook`/`tiktok`/`linkedin`), `status` (`agendada`/`publicando`/`publicada`/`falhou`/`cancelada`), `agendada_para`, `publicada_em`, `external_id`, `permalink`, `erro` (ex.: "tentativa interrompida" quando a rotina recupera uma publicação presa em `publicando`), `tentativas`.
- **metrica** — `publicacao_id`, `coletada_em`, `curtidas`, `comentarios`, `compartilhamentos`, `alcance`, `cliques_bio`, `visualizacoes`.
- **integracao** — `canal` (`instagram`, `facebook`, `tiktok`, `linkedin`, `smtp`, `gmail`, `whatsapp`, `meta_leads`), `token_cifrado`, `config`, `conta_externa`, `conectado_em`, `ultimo_erro`, `ativo`. Uma por canal.

### 7.7 Financeiro
- **fatura** — `cliente_id`, `contrato_id`, `competencia` (`AAAA-MM`), `valor_total`, `vencimento`, `status` (`aberta`/`enviada`/`paga`/`vencida`/`cancelada`), `pago_em`, `enviada_em` (migração 032: data do último "Enviar fatura"/"Marcar como enviada"; um novo envio atualiza a data), `gateway_id`, `nfse_id` (sem uso: não há gateway de pagamento nem NFS-e). Uma fatura não cancelada por contrato+competência.
- **fatura_item** — `fatura_id`, `descricao`, `tipo` (`mensalidade`/`excedente`/`desconto`/`avulso`; desconto subtrai), `quantidade`, `valor_unit`.

### 7.8 Automações
- **automacao** — `pipeline`, `etapa_id`, `gatilho` (`entrada_etapa`/`sla`), `sla_horas`, `acao` (JSON `{tipo, params}`), `ativo`.
- **automacao_execucao** — `automacao_id`, `entidade_id`, `movimento_id`, `status` (`executando`/`sucesso`/`erro`; `ignorada` existe no banco mas nunca é gravado), `detalhe`, `executado_em`.

### 7.9 Card hub (prefixos `cliente_` e `negocio_`)
`_notas` (descrição/comentários, exclusão lógica), `_tags` e `_tag_links`, `_membros` (profissionais), `_lembretes` (`titulo`, `responsavel_id` → profissional — migração 034 —, `dispara_em` gravado em UTC, `enviado_em` = entregue pela rotina **ou** concluído à mão, `cancelado_em`), `_checklists` e `_checklist_itens`, `_checklist_extras`, `_documento_tipos` (`contrato`, `proposta`, `comprovante_pagamento`, `comprovante_endereco`, `outro`; `rg` e `cpf` inativos), `_documentos` (arquivo, tipo, categoria LGPD, retenção, exclusão com motivo), `_documento_acessos`.

### 7.10 Relações
```
lead ─1:N─ negocio ─1:N─ orcamento ─1:N─ orcamento_item ─(gera)→ pauta
                                              └─1:N─ pauta_slot_gerado (vagas já geradas)
 │            │ (fechar) cria/reusa ↓
 └─ cliente_id ─────────→ cliente ─1:N─ marca ─(opcional)→ pauta
                            ├─1:N─ acesso ─1:N─ cofre_revelacoes
                            ├─1:N─ contrato ─1:N─ fatura ─1:N─ fatura_item
                            └─1:N─ pauta ─1:N─ peca
                                     ├─1:N─ tarefa ─1:N─ apontamento → profissional → funcao
                                     │        └─1:N─ aprovacao
                                     └─1:N─ publicacao ─1:N─ metrica
negocio/tarefa ─ etapa_id → pipeline_stages ; movimentos → pipeline_movimentos
automacao → pipeline_stages ; automacao_execucao → pipeline_movimentos
```
Excluir **cliente** apaga em cascata marcas, acessos, contratos, faturas, pautas (peças, tarefas, apontamentos, aprovações, publicações) e o card. Excluir **pauta** apaga tarefas, apontamentos, peças (inclusive os arquivos no armazenamento) e publicações. Excluir **marca** não apaga pautas. Excluir **etapa** apaga as automações dela.

---

## 8. Ciclo de vida ponta a ponta: do lead à fatura paga

| # | Passo | Quem/onde | O que muda (tabela.campo) |
|---|---|---|---|
| 1 | Lead chega pelo formulário | `/pre-qualificacao/<org>` | `lead` (`origem='formulario'`, `status='novo'`, `como_conheceu`); `negocio` (`status='aberto'`, `etapa_id`=1ª etapa, `stage_entered_at`); `pipeline_movimentos` (entrada); automações da etapa |
| 1b | … pelo WhatsApp / Meta | Webhooks | `lead` (`origem='whatsapp'`/`'meta_ads'`, `waha_chat_id`/`meta_lead_id`), `negocio`, `pipeline_movimentos`, automações |
| 1c | … manual | Comercial → "Novo lead" ("Novo contato") | `lead` (`origem='manual'`), `negocio`, `pipeline_movimentos`, automações |
| 1d | Novo negócio para cliente existente (upsell/renovação) | Comercial → "Novo lead" → "Cliente existente", ou Clientes → card → "Novo negócio" | `lead` novo (`origem='manual'`, com nome/e-mail/telefone do cliente), `negocio` com `cliente_id` do cliente escolhido; ao fechar, o **mesmo** cliente é reaproveitado |
| 2 | Qualificação/negociação | Arrastar no Comercial | `negocio.etapa_id`, `kanban_pos`, `stage_entered_at`; nova linha em `pipeline_movimentos`; `automacao_execucao` (+ `public.notifications`) |
| 3 | Orçamento | Modal do orçamento | `orcamento` (`versao=1`, `status='rascunho'`, totais, `margem_estimada`); `orcamento_item` |
| 4 | PDF e envio | "Gerar PDF", "Enviar" | `orcamento.pdf_key`; `status='enviado'`, `enviado_em`; `orcamento_email` (`out`) |
| 5 | Resposta do lead (Gmail conectado) | Webhook Gmail | `orcamento_email` (`in`); `orcamento.respondido_em`; notificação "Resposta ao orçamento: …" + e-mail ao responsável, aos Proprietários e aos Administradores |
| 6 | Fechamento (ganho) — arrastar para Fechado **ou** "Aceitar orçamento" (mesmo mecanismo) | Comercial / Orçamentos | outros orçamentos abertos → `status='substituido'`; escolhido → `status='aceito'`, `aceito_em`, `cliente_id`; `cliente` criado ou reaproveitado (`status='prospect'`, `lead_id`, `negocio_id`); `lead.status='convertido'`, `lead.cliente_id`; `negocio.status='ganho'`, `ganho_em`, `orcamento_aceito_id`, `cliente_id`; `pauta` dos próximos 30 dias (`gerada_automaticamente=true`, `orcamento_item_id`) + uma linha em `pauta_slot_gerado` por item × dia gerado; automações da etapa Fechado |
| 6b | Perda | "Marcar como perdido" | `negocio.status='perdido'`, `perdido_em`, `motivo_perda`, `perdido_stage_id` (reabrir volta `status='aberto'`, limpa esses campos, reinicia `stage_entered_at` e grava uma linha em `pipeline_movimentos`) |
| 7 | Pautas contínuas | Job diário 06:45 | novas `pauta` para manter 30 dias à frente de todo orçamento aceito (pausa se o orçamento tem contrato não ativo); vagas já registradas em `pauta_slot_gerado` nunca são geradas de novo |
| 8 | Contrato | "Contrato" no orçamento aceito | `contrato` (`status='aguardando_assinatura'`, `valor_mensal`, `posts_por_mes` = itens recorrentes de criação, `valor_excedente`, `dia_vencimento`, `data_inicio`, `documento_key`, `modalidade_assinatura`) |
| 9a | Assinatura física | Clientes → "Marcar como assinado" | `contrato.status='ativo'`, `assinado_em`, `assinado_manual_em`, `documento_assinado_key`; `cliente.status='ativo'` |
| 9b | Assinatura digital (hoje simulação) | Webhook de assinatura | `assinado` → `contrato.status='ativo'`, `cliente.status='ativo'`, leads `convertido`; `recusado`/`expirado` → `contrato.status='rascunho'` |
| 10 | Marca e acessos | Clientes → Marcas | `marca`, `acesso` (`cofre_revelacoes` a cada revelação) |
| 11 | Produção | Calendário / Esteira | `pauta.copy_texto`/`direcao_video`; `peca`; `tarefa` (1ª etapa); `apontamento` (cronômetro) |
| 12 | Aprovação do cliente | "Gerar link de aprovação" → portal | `aprovacao` (token, 14 dias; links anteriores não respondidos invalidados); `tarefa.etapa_id` → aprovação; decisão: `aprovado` avança uma etapa; `ajuste` volta uma, `refacoes += 1`, `observacao_cliente`; notificação |
| 13 | Distribuição | Distribuição | `publicacao` (`agendada` → `publicada` com `external_id`, ou `falhou`/recusa se canal sem token); `pauta.publicado_em`; `metrica`. A rotina da fila (a cada 5 min) hoje só ignora as agendadas — nenhum canal está homologado — e devolve para `agendada` as presas em `publicando` há mais de 15 min |
| 14 | Fechamento do mês | Financeiro → "Gerar competência" (admin) | `fatura` (`status='aberta'`, `vencimento`=dia do contrato) + `fatura_item` "Retainer mensal" e "Excedentes de <mês anterior>" (só peças **avulsas** entregues além da capacidade que o plano deixou livre no pacote; peças do plano nunca são cobradas, mas ocupam o pacote); `valor_total` recalculado |
| 14b | Envio da fatura | Financeiro → "Enviar fatura" (e-mail com PDF) ou "Marcar como enviada" (admin) | `fatura.enviada_em`; `fatura.status='enviada'` se estava `aberta` (uma fatura `vencida` continua `vencida`) |
| 15 | Cobrança | Job diário 06:00 / Financeiro / Dashboard | Faturas `aberta`/`enviada` com vencimento anterior a hoje → `vencida`; cliente com alguma fatura vencida → `inadimplente`; cliente `inadimplente` sem nenhuma → volta a `ativo`. Com `IGIG_PORTAL_BLOQUEIO_DIAS` ligado, o portal de aprovação desse cliente fica bloqueado após N dias de atraso |
| 16 | Pagamento | "Marcar paga" (admin) | `fatura.status='paga'`, `pago_em` (segunda marcação não sobrescreve); cancelamento: `status='cancelada'` |

---

## 9. Jobs agendados

Só rodam no container implantado com `NOCTUS_SCHEDULERS_ENABLED` ligado (ambiente local e testes não rodam rotinas). Horários em horário de Brasília (São Paulo). Uma falha numa rotina fica registrada no log do servidor e não derruba as outras. As varreduras que olham todas as organizações de uma vez (SLA, inadimplência, lembretes e a fila de publicação) leem os dados em páginas, então não há corte silencioso por volume (o banco devolve no máximo 1000 linhas por consulta). São exatamente seis rotinas:

| Rotina | Quando | O que faz | O que o usuário percebe |
|---|---|---|---|
| `igig_financeiro_inadimplencia` | Todo dia 06:00 | Faturas `aberta`/`enviada` com vencimento **anterior a hoje** → `vencida`. Cliente com pelo menos uma fatura `vencida` → status `inadimplente`. Cliente `inadimplente` sem nenhuma fatura vencida (pagou ou a fatura foi cancelada) → volta a `ativo` | Selo "Vencida" nas faturas; cliente "Inadimplente" em Clientes e na nota do Dashboard. Entre 00:00 e 06:00 uma fatura que venceu ontem ainda aparece `aberta`/`enviada` (mas já está na lista "Inadimplência", que é calculada na hora) |
| `igig_gmail_watch_renovar` | Todo dia 06:15 | Renova a escuta das caixas Gmail conectadas (a escuta do Google expira em até 7 dias) | Respostas de leads a orçamentos continuam sendo detectadas |
| `igig_pautas_extensao` | Todo dia 06:45 | Mantém 30 dias de pautas à frente para todo orçamento Aceito (pausa se o orçamento tem contrato não ativo). Idempotente por dia e consulta o registro `pauta_slot_gerado`: uma pauta automática apagada ou movida de data **nunca** é recriada | Novas pautas aparecem no Calendário a cada manhã |
| `igig_automacoes_sla` | A cada 15 minutos | Varre as regras de SLA ativas; executa a ação e envia `sla_estourado` uma vez por entrada na etapa | Notificações de SLA no sino; linhas em Automações → "Execuções recentes" |
| `igig_publicacao_fila` | A cada 5 minutos | (1) Devolve para `agendada`, com o erro "tentativa interrompida", toda publicação presa em `publicando` há mais de 15 minutos (servidor caiu no meio do envio). (2) Processa, organização por organização, as publicações agendadas cujo horário chegou — **mas só em canais homologados, e hoje nenhum canal está homologado**: as publicações agendadas são ignoradas (continuam `agendada`, sem erro) | Hoje: nada é publicado sozinho. O botão "Publicar agora"/"Publicar" em Distribuição tenta publicar na hora, mas também termina em `falhou` ("A integração com {canal} ainda não está disponível (homologação da API pendente).") enquanto os canais não forem homologados (ver Capítulos 4 e 5). Uma publicação presa volta a aparecer como agendada |
| `igig_lembretes_pendentes` | A cada 5 minutos | Entrega como notificação no sino todo lembrete de card (Cliente ou Negócio) cujo horário chegou e que ainda não foi entregue, concluído nem cancelado — uma única vez ("Lembrete: <título do lembrete>", ou o nome do cliente/título do negócio se o "Título" ficou vazio). Destinatários: o "Responsável" escolhido no lembrete (se tiver login vinculado) e os membros do card com login vinculado em Custos, sem repetir ninguém; sem nenhum dos dois, os administradores da organização; sem nenhum dos três, o lembrete fica pendente (registrado no log) e é tentado de novo na próxima rodada | O lembrete criado na aba "Lembretes" do card chega no sino em até ~5 minutos depois do horário marcado e passa para "concluídos" na lista. Um lembrete concluído à mão antes do horário não é mais entregue |

Não há rotina para: fechar o mês ("Gerar competência" é manual), cobrar/enviar faturas automaticamente, expirar orçamentos (acontece na leitura) ou expirar convites.

---

## 10. Configuração e ambiente

### 10.1 Servidor
| Variável | Para que serve | Se faltar |
|---|---|---|
| `IGIG_COFRE_KEY` | Chave Fernet do Cofre, senha SMTP e tokens das integrações | **Obrigatória em produção: o servidor não sobe sem ela** (checagem de inicialização `required_prod_config`). Fora de produção, gravar senha/token é recusado com 409 ("Cofre não configurado: defina IGIG_COFRE_KEY no ambiente. Nenhuma senha é gravada em texto puro." / "Criptografia não configurada: defina IGIG_COFRE_KEY. …"); chave inválida: 409 "IGIG_COFRE_KEY está mal configurada (não é uma chave Fernet válida). Peça ao responsável técnico para gerar uma nova chave." |
| `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` | Banco, autenticação, arquivos | Nada funciona |
| `JWT_SECRET`, `SSO_JWT_SECRET`, `CORE_API_URL` | Sessão e SSO | Login falha |
| `CORS_ORIGINS` | Domínios autorizados (padrão: registro do produto) | Navegador bloqueia chamadas |
| `PRODUCT_URL_IGIG` | URL pública (webhooks WAHA/Meta, OAuth Gmail) | "URL pública do IgIg não configurada (PRODUCT_URL_IGIG)."; Gmail 503 `url_publica_ausente` |
| `IGIG_ASSINATURA_WEBHOOK_SECRET` | HMAC do webhook de assinatura | Webhook recusa tudo (401); contrato digital não ativa sozinho |
| `WEBHOOK_RATE_LIMIT` | Limite das rotas públicas (padrão `60/minute`) | Usa o padrão |
| `ASSISTENTE_RATE_LIMIT` | Limite do Assistente IA por pessoa (padrão `20/minute`) | Usa o padrão |
| `IGIG_STORAGE_KIND` / `_ROOT` / `_BUCKET` | Armazenamento de peças, logos, PDFs (`supabase`, bucket `igig`) | Padrões |
| `IGIG_CARDHUB_BUCKET` | Documentos dos cards (`igig-cardhub`) | Padrão |
| `IGIG_META_TOKEN`, `IGIG_TIKTOK_TOKEN`, `IGIG_LINKEDIN_TOKEN` | Reserva global de tokens de redes (o normal é por organização) | Publicar sem token da agência recusa: "Canal {canal} não está configurado. Conecte um token em Integrações antes de publicar." |
| `SMTP_HOST`, `SMTP_PORT` (465), `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURITY`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | SMTP reserva da plataforma | Sem SMTP da agência e sem reserva: 409 "Nenhum SMTP configurado: cadastre uma conta em Integrações → E-mail." |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | Conexão Gmail | 503 "OAuth do Google não configurado: defina GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET." |
| `GMAIL_PUSH_GCP_PROJECT`, `GMAIL_PUSH_TOPIC`, `GMAIL_PUSH_AUDIENCE`, `GMAIL_PUSH_SERVICE_ACCOUNT` | Aviso de respostas por e-mail | Qualquer um vazio: nenhuma escuta; webhook do Gmail recusa (503); respostas não detectadas |
| `IGIG_WAHA_WEBHOOK_HMAC_SECRET` | Assinatura extra do webhook WAHA | Mensagens aceitas sem verificar assinatura (só o token da URL protege) |
| `IGIG_META_APP_SECRET` | App secret Meta (reserva) | Sem este e sem o da agência: entregas da Meta recusadas (401) |
| `IGIG_PORTAL_BLOQUEIO_DIAS` | Bloqueio do portal de aprovação para cliente com fatura vencida há **mais de** N dias (0 ou ausente = desligado) | Desligado: o portal nunca bloqueia. Ligado: o cliente vê "Portal temporariamente indisponível" / "Contate a agência." (423 `portal_bloqueado`) — ver Capítulo 3 |
| Chave da Anthropic (`ANTHROPIC_API_KEY` dentro do container, resolvida pela cadeia de credenciais da plataforma; na frota de produção ela vem da variável dedicada e com teto de gasto **`IGIG_ANTHROPIC_API_KEY`**) | Assistente do negócio e Assistente IgIg (chat de ajuda) | Assistente do negócio: 503 "A IA não está configurada (chave da Anthropic ausente)."; Assistente IgIg: "O assistente de IA ainda não foi configurado para este produto." e o campo passa a "Assistente indisponível no momento" |
| `NOCTUS_SCHEDULERS_ENABLED` | Liga as rotinas agendadas | Rotinas não rodam |
| `RESEND_API_KEY` | E-mail de convite da Equipe (provedor da plataforma) | O convite é criado, nenhum e-mail sai, e a tela avisa ("Convite criado, mas o e-mail não foi enviado — copie o link") em vez de mostrar sucesso |
| `REDIS_URL` | Contadores de limite de requisições | Contadores em memória |
| `SENTRY_DSN`, `DEBUG`, `MAX_BODY_BYTES` (1 MB), `DATABASE_BACKEND` | Operação | Padrões |

### 10.2 Navegador (gravadas na construção)
`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` (sem elas o app não abre), `VITE_CORE_URL`, `VITE_CORE_API_URL`, `VITE_BACKEND_API_URL` (em produção, o próprio domínio).

---

## 11. Armazenamento de arquivos, limites, prazos de links

- Bucket privado **`igig`** (criado pela migração 028; só o servidor acessa): peças (`<org>/pautas/<pauta>/<arquivo>` — cada envio com nome único; removidas do armazenamento tanto ao excluir a peça quanto ao excluir a pauta inteira), logos, PDFs de orçamento (`<org>/orcamentos/<id>/v<versão>.pdf`), contratos (`<org>/contratos/<id>/contrato.pdf` e o assinado).
- Bucket privado **`igig-cardhub`**: documentos dos cards (cliente e negócio), na pasta da organização.
- Nada é público; ver/baixar é sempre por **link temporário assinado**:

| Arquivo | Limite de tamanho | Formatos | Validade do link |
|---|---|---|---|
| Peça (pauta) | 50 MB ("Peça excede 50 MB") | PNG, JPEG, WebP, GIF, MP4, MOV | 1 hora (Calendário e portal de aprovação; um link novo é gerado a cada abertura) |
| Logo da marca | 2 MB ("Logo excede 2 MB") | PNG, JPEG, WebP ("Formato não suportado: <tipo>. Envie PNG, JPEG ou WebP."); SVG não é aceito nem oferecido no seletor | 1 hora (um link novo é gerado a cada leitura) |
| Documento do card | 25 MB | PDF, JPEG, PNG, WebP | 5 minutos |
| Contrato assinado (digitalização) | 25 MB | PDF, JPG, PNG ("Envie o contrato assinado em PDF, JPG ou PNG."; vazio: "O arquivo enviado está vazio.") | — |
| PDF de orçamento / contrato | — | PDF | 10 minutos (gere de novo) |
| PDF da fatura | — | PDF | Não há link: o PDF é gerado na hora a cada "Enviar fatura" e vai só como anexo do e-mail ("fatura-AAAA-MM.pdf") |

- Corpo de requisição: 1 MB padrão; uploads têm teto próprio um pouco acima do limite de negócio (60 MB peças, 3 MB logo, 30 MB documentos/contrato assinado) para que a mensagem clara do limite apareça.
- Prazos de negócio: convite 7 dias; link de aprovação 14 dias e uso único para decidir (gerar um novo invalida os anteriores não respondidos); pautas 30 dias à frente.
- Limite de requisições: rotas públicas 60/min por IP; Assistente IA 20/min por pessoa; demais rotas internas sem limite por quantidade. Acima do limite: 429 `{"error":{"code":"RATE_LIMITED","message":"Muitas requisições. Tente novamente em breve."}}`.
---

## 12. Formatos de erro e códigos

### 12.1 Formatos
Sucesso: os módulos mais novos (funil, orçamentos, produtos, contratos, e-mail, automações, fontes de lead, assistente, relatórios JSON, quadros e etapas, equipe) respondem `{"data": …}`; os mais antigos (clientes, marcas, pautas, cronômetro, custos, distribuição, faturas, canais sociais) respondem o objeto direto. A tela trata os dois.

Erros — quatro formatos:
1. **Regra de negócio**: `{"detail": "<mensagem em português>", "code": "<código>"}` (409/422/403/502/503…). A tela mostra a mensagem como aviso ou texto vermelho (sem o prefixo "[409]").
2. **Erro genérico**: `{"error": {"code": "NOT_FOUND" | "UNAUTHORIZED" | "FORBIDDEN" | "BAD_REQUEST" | "HTTP_ERROR" | "CONFLICT" | "INTERNAL_ERROR", "message": "…"}}` — ex.: "Cliente não encontrado", "Negócio não encontrado", "Etapa não encontrada", "Registro duplicado — este recurso já existe", "Só um negócio perdido pode ser reaberto.", "Organização não encontrada.".
3. **Validação de campos**: 422 no formato `{"error": {"code": "VALIDATION_ERROR", "message": "<campo>: <mensagem>; <campo>: <mensagem>…", "details": {"errors": [{field, message, type}]}}}`. A tela mostra `message` — em **português**, um trecho por campo inválido (ex.: "email: E-mail inválido", "nome: Deve ter pelo menos 3 caracteres", "idade: Campo obrigatório"). `details.errors[].message` continua em inglês (texto bruto do validador) — é só para quem lê a resposta programaticamente, nunca aparece na tela.
4. **Limite de requisições**: 429 `{"error": {"code": "RATE_LIMITED", "message": "Muitas requisições. Tente novamente em breve."}}`.

**Duplicados (409) — mensagem específica, também em produção.** Onde a tela tem uma mensagem própria para "já existe" — função com o mesmo nome (`funcao_duplicada` 'Já existe uma função chamada "<nome>".' / "Já existe uma função com esse nome."), fatura do mesmo contrato na mesma competência ("Já existe fatura para este contrato em <AAAA-MM>"), publicação ativa da mesma pauta no mesmo canal ("Esta pauta já tem publicação ativa em <canal>") — é essa mensagem que aparece, e não a genérica "Registro duplicado — este recurso já existe". Só uma violação de **unicidade** vira esse 409; uma falha de banco diferente (ex.: referência quebrada) não é mais rotulada como "já existe" e aparece como o erro real que é.

### 12.2 Tabela de códigos
| Código (HTTP) | Mensagem | O que fazer |
|---|---|---|
| `admin_obrigatorio` (403) | "Apenas administradores podem alterar as etapas do quadro." / "Apenas administradores da organização podem realizar esta ação." | Peça a um Proprietário/Administrador |
| — (403) | "Apenas administradores podem revelar senhas" | Idem |
| — (403) | "Sem permissao para convidar" / "Sem permissao para convidar como <papel>" / "Sem permissao" / "Somente o proprietario pode remover um proprietario" | Convidar: Proprietário/Admin/Gerente (Gerente não convida como Administrador/Proprietário; Administrador não convida como Proprietário); convites/remover: Proprietário/Admin |
| `funil_sem_etapas` (409) | "O funil comercial não tem nenhuma etapa ativa. Configure as etapas primeiro." | Admin cria/ativa etapas no Comercial |
| `funil_sem_fechamento` (409) | "O funil comercial não tem etapa de fechamento ativa. Configure as etapas primeiro." | Garantir uma etapa com papel Fechado ativa |
| `orcamento_obrigatorio` (409) | "Para fechar o negócio, informe qual orçamento foi aceito." | Escolha o orçamento no seletor |
| `orcamento_invalido` (409) | "Este orçamento não pertence a este negócio." / "Este orçamento está <status> e não pode ser aceito." | Use um orçamento deste negócio / crie nova versão |
| `orcamento_expirado` (409) | "A validade deste orçamento já passou." | Nova versão com nova validade |
| `orcamento_ja_aceito` (409) | "Outro orçamento deste negócio já foi aceito — feche com ele." | Escolha o já aceito |
| `negocio_ganho` (409) | "Um negócio fechado não sai da etapa de fechamento." / "Este negócio já foi fechado com outro orçamento." | Ganho é definitivo |
| `negocio_perdido` (409) | "Este negócio foi marcado como perdido." | Reabra em "Perdidos" |
| `negocio_encerrado` (409) | "Só um negócio em aberto pode ser marcado como perdido (status: …)." / "Este negócio está <status> — não aceita novos orçamentos." | — |
| `motivo_obrigatorio` (422) | "Informe o motivo da perda." / "Informe o motivo da recusa." / "Informe o motivo para devolver a tarefa a uma etapa anterior." | Preencha o motivo |
| `sem_campos` (422) | "Nenhum campo para atualizar." | Altere algo antes de salvar |
| `orcamento_bloqueado` (409) | "Não é possível <ação>: este orçamento está <status>." / "Orçamento <status> não pode ser enviado." | Crie nova versão |
| `aceite_nao_aplicado` (409) | "O negócio não pôde ser fechado com este orçamento — verifique a etapa do card." | Verifique o card no Comercial |
| `orcamento_nao_aceito` (409) | "Só um orçamento aceito gera contrato. Aceite o orçamento primeiro." / "Só um orçamento aceito pode gerar pautas." | Aceite antes |
| `recorrencia_invalida` (422) | 'O item "<nome>" é recorrente: escolha ao menos um dia da semana e a quantidade por dia.' | Complete o item |
| `desconto_invalido` (422) | "O desconto não pode ser maior que o subtotal do orçamento." | Reduza o desconto |
| `produto_invalido` (422) | "Um dos itens referencia um produto/serviço que não existe neste catálogo." | Recarregue e escolha outro item |
| `produto_duplicado` (409) | 'Já existe "<nome>" nesta seção do catálogo.' | Use outro nome |
| `pdf_nao_gerado` (409) | "Gere o PDF do orçamento antes de enviar." / "O PDF deste orçamento ainda não foi gerado." / "O PDF do orçamento não foi encontrado no armazenamento — gere-o novamente." / "Este contrato não tem documento gerado." | Gere o PDF |
| `email_destinatario_ausente` (422) | "O lead não tem e-mail cadastrado — informe o destinatário." | Informe o e-mail |
| `envio_falhou` (502) | "Falha ao enviar o e-mail: <erro>" | Verifique o SMTP |
| `smtp_nao_configurado` (409/404) | "Nenhum SMTP configurado: cadastre uma conta em Integrações → E-mail." / "SMTP incompleto: <erro>" / "Nenhum SMTP próprio configurado." | Configure em Integrações → E-mail |
| `senha_obrigatoria` (422) | "Informe a senha do SMTP." | — |
| `cofre_nao_configurado` (409) | "Criptografia não configurada: defina IGIG_COFRE_KEY. …" | Responsável técnico configura o servidor |
| `oauth_nao_configurado` (503) | "OAuth do Google não configurado: defina GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET." | Idem |
| `url_publica_ausente` (503) | "URL pública do produto não configurada: defina PRODUCT_URL_IGIG (ou PRODUCT_URL_PATTERN)." | Idem |
| `state_invalido` (400) | "Estado OAuth inválido ou expirado." | Tente conectar o Gmail de novo |
| `gmail_nao_conectado` (404) | "Gmail não conectado." | — |
| `contrato_existente` (409) | "Este orçamento já tem um contrato gerado." | Use o contrato existente |
| `contrato_digital` (409) | "Este contrato é de assinatura digital — ele é ativado pela confirmação da assinatura." | — |
| `contrato_ja_assinado` (409) | "Este contrato já está assinado." | — |
| `contrato_encerrado` (409) | "Este contrato está encerrado e não pode ser reativado." | Gere novo contrato |
| `arquivo_invalido` / `arquivo_vazio` (422) | "Envie o contrato assinado em PDF, JPG ou PNG." / "O arquivo enviado está vazio." | Envie outro arquivo |
| `funcao_duplicada` (409) | 'Já existe uma função chamada "<nome>".' | Use outro nome |
| `esteira_sem_etapas` (409) | "A esteira não tem nenhuma etapa ativa. Configure as etapas primeiro." | Admin cria etapas |
| `etapa_invalida` (409/422) | "A tarefa só pode avançar uma etapa por vez." / "Esta etapa está desativada." / "Esta tarefa já passou da aprovação do cliente." / "Esta etapa não existe neste quadro." | — |
| `etapa_aprovacao_ausente` (409) | "Nenhuma etapa da esteira está marcada como 'Aprovação do cliente'." | Admin atribui o papel |
| `papel_obrigatorio` (409) | "Esta é a única etapa marcada como '<Aprovação do cliente \| Agendado>'. Atribua esse papel a outra etapa antes de trocá-lo ou removê-lo desta." | Esteira: primeiro mova o papel atual da etapa para outra etapa em "Papéis das etapas" |
| `papel_fechado_obrigatorio` (409) | "Esta é a única etapa marcada como 'Fechado'. Atribua o papel a outra etapa antes de tirá-lo desta." | Comercial: escolha outra etapa para "Fechado" em "Papéis das etapas" |
| `fora_de_aprovacao` (409) | "Este conteúdo não está mais aguardando a sua aprovação." | (cliente) contate a agência |
| `horas_serao_perdidas` (409) | "Isto tem <Xh> de horas apontadas em N apontamento(s). Confirme a exclusão para perder esses registros." | Confirme na segunda janela |
| `canal_nao_configurado` (409) | "Canal {canal} não está configurado. Conecte um token em Integrações antes de publicar." | Admin conecta o canal |
| `credencial_ilegivel` (409) | "O token salvo para {canal} não pôde ser lido. Reconecte o canal." | Reconecte |
| `publicacao_cancelada` (409) | "Publicação cancelada não pode ser executada." | Agende de novo |
| `publicacao_em_andamento` (409) | "Esta publicação já está sendo executada." | Aguarde |
| `fatura_paga` / `fatura_cancelada` (409) | "Fatura paga não pode ser cancelada." / "Fatura cancelada não pode ser paga." | — |
| `fatura_fechada` (409) — envio | "Fatura <paga\|cancelada> não pode ser enviada." / "Fatura <paga\|cancelada> não pode ser marcada como enviada." | Fatura paga ou cancelada não é mais enviada |
| `email_destinatario_ausente` (422) — fatura | "O cliente não tem e-mail cadastrado." | Cadastre o e-mail em Clientes → card → Dados |
| `fatura_nao_encontrada` / `cliente_nao_encontrado` (404) | "Fatura não encontrada." / "Cliente não encontrado." | Recarregue a página |
| `portal_bloqueado` (423) | "Portal temporariamente indisponível, contate a agência." (na tela: "Portal temporariamente indisponível" / "Contate a agência.") | (cliente) falar com a agência; (agência) regularizar a fatura vencida |
| `fatura_fechada` (409) | "Fatura <status> não aceita novos itens." | — |
| `total_negativo` (422) | "Este desconto deixaria o total da fatura negativo." | Reduza o desconto |
| `acao_incompativel` (422) | "Checklists automáticos existem só no funil comercial (card do negócio)." | Escolha outra ação |
| `profissional_invalido` (422) | "O profissional informado não existe." | Escolha outro |
| `sla_sem_horas` (422) | "Uma automação de SLA precisa de `sla_horas`." | Informe as horas |
| `verify_token_obrigatorio` / `page_access_token_obrigatorio` (422) | "Informe o verify token (usado uma vez pela Meta para validar a URL)." / "Informe o token de acesso da Página (lê os dados do lead)." | Preencha |
| `pagina_em_uso` (409) | "Esta Página já está conectada a outra organização." | Desconecte na outra organização |
| `whatsapp_nao_configurado` / `meta_leads_nao_configurado` (404) | "WhatsApp (WAHA) não estava configurado." / "Meta Lead Ads não estava configurado." | — |
| `corpo_invalido` (422) | "<campo>: <problema>" (webhook de assinatura) | (provedor) corrigir o envio |
| `ia_nao_configurada` (503) | "A IA não está configurada (chave da Anthropic ausente)." | Responsável técnico |
| `orcamento_ia_excedido` (429) | "O limite de uso de IA da organização foi atingido." | Aguarde o próximo período ou aumente o limite |
| `ia_indisponivel` (502) | "O provedor de IA não respondeu. Tente novamente em instantes." | Tente de novo |
| `ia_resposta_vazia` (502) | "A IA não retornou texto. Tente novamente." | Tente de novo |
| `RATE_LIMITED` (429) | "Muitas requisições. Tente novamente em breve." | Aguarde um minuto |

---

## 13. IA na plataforma

### 13.1 Assistente do negócio (card do negócio → aba "Assistente")
- Ações: "Resumo" (até 6 tópicos), "Próxima ação" (com porquê, prazo e riscos) e "Rascunho de mensagem" (WhatsApp curto, até 3 parágrafos, ou e-mail com linha "Assunto:").
- Modelo: Claude (Anthropic) pela pilha de IA da plataforma, **fixo em `claude-sonnet-4-6`** (Claude Sonnet), temperatura 0.4, até 1200 tokens de resposta. O modelo não muda sozinho quando o catálogo de modelos da plataforma é atualizado; se esse modelo sair do catálogo, o assistente falha de forma visível em vez de trocar de modelo em silêncio.
- Contexto enviado (minimização de dados): lead (nome, empresa, e-mail, telefone, Instagram, origem, como conheceu, especificações, observações, status, nicho, canais atuais, dores, orçamento disponível), negócio (título, valor, status, entrada na etapa, motivo de perda, criação, etapa, responsável), histórico de etapas, orçamentos (versão, título, status, total, validade, envio, resposta, motivo de recusa) e até 30 itens da linha do tempo (nunca o conteúdo dos documentos).
- Instruções: responder sempre em português do Brasil, só com fatos do contexto, sem inventar dados; se faltar informação, dizer o que falta.
- **Nada é gravado nem enviado**; sem cache de respostas (dados pessoais).
- Limites: gasto de IA da organização (selo no cabeçalho) e **20 pedidos por minuto por pessoa**.
- Erros: `ia_nao_configurada` (503), `orcamento_ia_excedido` (429), `RATE_LIMITED` (429), `ia_indisponivel` (502), `ia_resposta_vazia` (502); genérico na tela "O assistente não respondeu.".
- Endpoint: POST `/api/comercial/negocios/{id}/assistente` `{acao, canal?}` → `{data:{texto}}`.
- Observação LGPD: o assistente envia dados pessoais do lead à Anthropic sem um consentimento de IA específico do produto (o catálogo de consentimentos de IA do IgIg não está ativado — `consent_features` comentado no `main.py`). Ativar esse consentimento é uma **decisão pendente do dono do produto** (ver Capítulo 5).

### 13.2 Assistente IgIg (chat de ajuda) — disponível em todas as telas
- **O que é**: um balão de chat flutuante, no canto inferior direito da tela, presente em **todas as páginas logadas** do IgIg. Título do painel: "Assistente IgIg". A pessoa pergunta como usar a plataforma e um especialista de IA responde a partir **deste manual** (`app/knowledge/guia-igig.md`), que é todo o seu conhecimento do IgIg. Construído sobre o organ do seed `noctusai_lib.domain.help_chat` (frontend `HelpChatBubble`, ligado pelo layout do seed com a opção `helpChat` em `App.tsx`; backend `app/routers/ajuda_router.py`).
- **Modelo**: `claude-haiku-4-5` (Anthropic), temperatura 0.4, até 1200 tokens por resposta, **resposta em streaming** (o texto aparece aos poucos).
- **Comportamento** (definido no prompt do organ): entende a dúvida antes de responder e faz perguntas curtas de esclarecimento quando falta contexto; nunca adivinha; guia passo a passo com os nomes EXATOS de menus, botões e campos; explica o porquê das regras; sugere o próximo passo; se este manual não cobre algo, diz isso e sugere contatar o suporte — nunca inventa funcionalidades, números ou prazos; menciona limitações com honestidade; nunca pede, guarda ou revela senhas, tokens ou chaves; usa a página em que a pessoa está como contexto (o endereço atual vai junto com a pergunta); responde em português do Brasil (ou no idioma em que a pessoa escrever); parágrafos curtos e listas (uso em celular).
- **Dados**: **só** este manual + a conversa. O assistente **não acessa** dados da organização (clientes, negócios, faturas, documentos) — ele explica como fazer, não consulta nem altera registros. O servidor não grava a conversa nem registra o texto das mensagens (só tamanhos/tempos). O histórico fica apenas no navegador, naquela aba (`sessionStorage`, limitado), e some ao fechar a aba ou tocar em "Nova conversa".
- **Limites**: até 20 mensagens por pedido, até 4000 caracteres por mensagem, **20 pedidos por minuto por pessoa**; sujeito ao orçamento de IA da organização.
- **Endpoint**: POST `/api/ajuda/chat` (login obrigatório) `{messages:[…], pagina_atual?}` → `text/event-stream` (`data: {"delta": …}` … `data: {"done": true}`; erro no meio: `data: {"error": {"code", "message"}}`).
- **Erros e mensagens na tela**: `ia_nao_configurada` (503) "O assistente de IA ainda não foi configurado para este produto." (e o campo passa a "Assistente indisponível no momento"); `orcamento_ia_excedido` (429) "O limite de uso de IA da organização foi atingido. Tente novamente mais tarde."; `limite_de_mensagens` (429) "Você enviou mensagens rápido demais. Aguarde um instante e tente novamente."; `ia_indisponivel` (502) "O assistente não respondeu. Tente novamente em instantes."; falha de rede "Falha de conexão com o assistente. Verifique sua internet e tente novamente.". Junto de qualquer erro aparece o link "Tentar de novo", que reenvia a última pergunta.
- **Configuração**: precisa da chave da Anthropic no servidor — em produção, `IGIG_ANTHROPIC_API_KEY` (mapeada para `ANTHROPIC_API_KEY` no container). O servidor se recusa a iniciar se este manual estiver ausente ou vazio (de propósito: sem conhecimento, o assistente inventaria respostas).
- **Manutenção**: toda mudança de página, regra ou mensagem do IgIg atualiza este manual no mesmo commit; um manual desatualizado faz o assistente descrever com confiança um comportamento que não existe mais.

### 13.2.1 Como usar o Assistente IgIg
1. Em qualquer tela logada, toque no **balão de chat** no canto inferior direito (rótulo de acessibilidade "Abrir Assistente IgIg"). No celular o painel abre em tela cheia; no computador, como uma janela flutuante.
2. Na primeira vez aparece "Olá! Envie uma pergunta ou escolha um exemplo:" com quatro sugestões prontas — toque numa para enviá-la:
   - "Como cadastro um lead e levo até cliente?"
   - "Como monto e envio um orçamento?"
   - "Como funciona a esteira de produção e a aprovação do cliente?"
   - "Por que minha margem aparece como indisponível?"
3. Ou escreva no campo "Digite sua pergunta..." e toque em "Enviar" (ou tecle Enter; Shift+Enter quebra a linha). A resposta aparece aos poucos; enquanto isso, três pontinhos indicam que o assistente está escrevendo.
4. Seja específico e diga em que tela está ("Em Orçamentos, por que o botão Enviar está desabilitado?"). O assistente já sabe a página aberta, mas detalhes ajudam. Se ele fizer uma pergunta de volta, responda — é para acertar a resposta.
5. "Nova conversa" apaga o histórico e recomeça; "Fechar" (ou tocar de novo no balão) recolhe o painel sem perder a conversa daquela aba.
6. O que ele **não** faz: não executa ações (não cria lead, não envia orçamento, não marca fatura), não vê os seus dados, não sabe valores ou nomes dos seus clientes e não guarda senhas. Para ações, siga o passo a passo que ele indicar na própria tela.
7. Se ele disser que o manual não cobre o assunto, ou se o comportamento na tela divergir do que ele descreveu, fale com o suporte do produto.

### 13.3 Outros usos
Nenhuma outra parte do IgIg usa IA (as automações não têm ação de IA). Resumo: **Assistente do negócio** (card do negócio, `claude-sonnet-4-6`, usa os dados do lead/negócio) e **Assistente IgIg** (balão de ajuda, `claude-haiku-4-5`, usa só este manual).

---

## 14. Glossário

- **Agência / organização** — a empresa que usa o IgIg; dados separados por organização.
- **Administrador da agência** — Proprietário ou Administrador (ou admin da plataforma).
- **Lead** — pessoa/empresa interessada; origem (formulário, manual, WhatsApp, Meta Ads) e status (novo, qualificado, descartado, convertido).
- **Negócio** — oportunidade de venda de um lead; card do funil; aberto, ganho ou perdido.
- **Perdidos** — arquivo de negócios perdidos, com busca e "Reabrir".
- **Funil / quadro Comercial** — kanban de vendas; etapas padrão "Leads", "Qualificação", "Negociação", "Agendar briefing", "Fechado".
- **Etapa** — coluna de um quadro; admins criam/renomeiam/reordenam/recolorem/excluem.
- **Papel da etapa** — marca especial: "fechado" (Comercial: fechar exige orçamento), "aprovação do cliente" e "agendado" (Esteira). Regras seguem o papel, não o nome. Admins reatribuem em "Papéis das etapas" (Comercial e Esteira); um papel nunca fica sem etapa.
- **Etapa de entrada** — a primeira etapa ativa; onde todo lead novo entra.
- **Pré-qualificação** — formulário público preenchido pelo prospect antes da reunião.
- **Orçamento** — proposta mensal de um negócio; status rascunho, enviado, aceito, recusado, expirado, substituído.
- **Versão** — nova edição de um orçamento.
- **Produtos e Serviços / catálogo** — itens vendáveis: Criação de conteúdo e Gestão de conta.
- **Item recorrente** — item que se repete em dias da semana (gera pautas).
- **Margem estimada** — (total − horas × custo/hora) ÷ total.
- **Cliente** — conta da agência; prospect, ativo, inativo, inadimplente.
- **Card (card hub)** — janela de detalhe do cliente/negócio: etiquetas, membros, descrição, anexos (LGPD), checklists, comentários, linha do tempo.
- **Marca / Central da Marca** — identidade de uma marca do cliente (logo, paleta, tom de voz, termos proibidos, formalidade, linhas editoriais, personas); um cliente pode ter várias.
- **Repertório** — resumo da marca ao lado das telas de trabalho.
- **Cofre de Acessos** — logins do cliente com senha criptografada; só admins revelam; cada revelação é registrada.
- **Contrato** — gerado do orçamento aceito: retainer, pacote, excedente, dia de vencimento; assinatura digital (hoje simulação) ou física.
- **Retainer** — valor mensal fixo ("Retainer mensal" na fatura).
- **Pacote (posts por mês)** — peças incluídas no retainer (itens recorrentes de criação).
- **Lembrete** — aviso com data e hora marcadas, criado na aba "Lembretes" do card do cliente ou do negócio; na hora, vira uma notificação no sino (rotina a cada 5 minutos). Pendente, "Atrasado" (horário passou e ainda não foi entregue nem concluído) ou concluído.
- **Excedente** — peça **avulsa** (criada fora do plano, direto no Calendário) entregue além da capacidade do pacote que as peças do plano deixaram livre naquele mês; cobrada na fatura do mês seguinte. Peças do plano recorrente nunca viram excedente, mas ocupam o pacote.
- **Peça do plano × peça avulsa** — do plano: pauta gerada automaticamente a partir de um item recorrente do orçamento aceito; avulsa: qualquer outra pauta.
- **Entregue** (para excedentes) — pauta publicada de verdade (`publicado_em`) ou, na falta disso, aprovada pelo cliente no portal; a data planejada não conta.
- **Pauta** — conteúdo planejado no calendário (título, formato, funil, linha editorial, copy, direção de vídeo, data, marca, canal).
- **Formato** — feed, carrossel, reels, story, artigo, vídeo.
- **Funil (da pauta)** — topo, meio, fundo.
- **Copy** — texto/legenda da peça. **Direção de vídeo** — orientações de gravação/edição.
- **Peça** — arquivo criativo de uma pauta, visto pelo cliente na aprovação.
- **Esteira** — kanban de produção ("Aguardando roteiro", "Roteiro em produção", "Aguardando design", "Design em produção", "Revisão interna", "Aprovação do cliente", "Pronto para agendamento", "Agendado").
- **Tarefa** — card da Esteira ligado a uma pauta.
- **Refação** — cada volta da tarefa a partir da aprovação do cliente.
- **Portal / link de aprovação** — página pública onde o cliente aprova ou pede ajuste; 14 dias, uma decisão.
- **Apontamento** — trecho de horas registrado pelo cronômetro.
- **Profissional** — pessoa com custo/hora (pode ter login vinculado). **Função** — cargo com custo/hora padrão. **Custo/hora efetivo** — do profissional, senão da função.
- **Membro da equipe** — conta de login (tela Equipe); diferente de profissional.
- **Custo real** — horas apontadas × custo/hora de quem trabalhou.
- **BI de eficiência** — taxa de refação e custo real por cliente.
- **Publicação** — agendamento/postagem de uma pauta numa rede. **Métrica** — retrato de desempenho.
- **Competência** — mês de referência AAAA-MM. **Fechamento do mês** — "Gerar competência".
- **Fatura** — cobrança de um contrato numa competência; aberta, enviada (por "Enviar fatura" ou "Marcar como enviada"), paga, vencida (pela rotina diária das 06:00), cancelada.
- **MRR** — soma dos retainers dos contratos ativos.
- **DRE** — receita faturada (da competência) × custo real (histórico completo) por cliente.
- **Inadimplência** — faturas vencidas e não pagas; o cliente com alguma delas fica com status "Inadimplente" (rotina diária).
- **Automação** — regra "ao entrar na etapa" ou "SLA estourado" → checklist, responsável, tarefa, notificação, e-mail, WhatsApp.
- **SLA** — tempo máximo de um card numa etapa.
- **Execução** — registro de uma automação que rodou (sucesso/erro + detalhe).
- **Fontes de lead** — WhatsApp (WAHA) e Meta Lead Ads, que criam leads sozinhos.
- **WAHA** — servidor de WhatsApp usado para receber leads e enviar mensagens.
- **SSO** — login único pela central NoctusAI.
- **RLS** — regra do banco que só deixa cada organização ver os próprios dados.
- **status_pagina / DEV** — controle de visibilidade de páginas no menu.
- **Assistente IA** — IA do card do negócio (resumo, próxima ação, rascunho).
- **Assistente IgIg** — chat de ajuda flutuante, em todas as telas, que responde dúvidas sobre o uso do IgIg a partir deste manual (não acessa dados da agência).

---

---

# Capítulo 1 — Comercial e Clientes

## IgIg — Guia: Dashboard, Comercial, Pré-qualificação, Clientes, Automações, Fontes de lead e Equipe

> Manual de instruções e especificação por página. Público: (1) o assistente de ajuda do IgIg, que responde usuários a partir deste texto; (2) o dono do produto, como especificação durável. Tudo aqui foi conferido no código final do IgIg (frontend React + backend FastAPI + migrations) e, onde o IgIg delega, no código do seed da plataforma. Rótulos, mensagens e avisos aparecem "entre aspas" exatamente como na tela ou no servidor. O que não pôde ser confirmado está marcado "(não confirmado no código)".

## Vocabulário essencial desta parte (leia antes)

- **Lead** (tabela `igig.lead`): a pessoa/empresa interessada — nome, e-mail, telefone, empresa, Instagram, nicho, canais atuais, dores, orçamento disponível, observações. Tem uma **origem** (o canal por onde chegou): "Formulário" (`formulario`), "Manual" (`manual`), "WhatsApp" (`whatsapp`) ou "Meta Ads" (`meta_ads`). O lead não tem tela própria: ele é visto sempre através do seu negócio (aba "Lead" do card).
- **Negócio** (tabela `igig.negocio`): a oportunidade de venda — é o **card** do funil do Comercial. Tem etapa, título, valor estimado (R$/mês), responsável e status: `aberto` (em andamento), `ganho` (fechado) ou `perdido` (arquivado com motivo).
- **Cliente** (tabela `igig.cliente`): a conta da agência. Nasce automaticamente quando um negócio é fechado com orçamento aceito, ou é criado à mão em "Clientes". Status: "Prospect", "Ativo", "Inativo", "Inadimplente".
- **Administrador da agência**: usuário com papel Proprietário (`owner`) ou Administrador (`admin`) na organização, ou administrador da plataforma NoctusAI. O servidor confere isso numa tabela confiável (`public.noctus_users`), nunca em dados que o próprio usuário possa editar. Quando uma ação só-admin chega ao servidor vinda de outra pessoa, a resposta é 403 com o código `admin_obrigatorio` e uma de duas mensagens: "Apenas administradores podem alterar as etapas do quadro." (editores de etapas do Comercial e da Esteira) ou "Apenas administradores da organização podem realizar esta ação." (todas as demais ações só-admin).
- **Membros da Equipe × Profissionais**: "Equipe" lista as **contas de login**. "Custos" lista os **profissionais** (cadastro de trabalho com custo/hora e, opcionalmente, o usuário de login vinculado). O campo "Responsável" do negócio, a lista "Membros" dos cards e os responsáveis das automações vêm dos **profissionais ativos (Custos)**. Para alguém receber notificações como responsável, o profissional precisa estar **vinculado a um usuário de login** em Custos. Já "Notificar também" (automações) lista os **membros da Equipe**.

---

## Página: Dashboard

### 1. Propósito
Tela inicial depois do login: visão geral da agência — carteira de clientes, produção, financeiro do mês e, desde esta versão, o funil Comercial. Subtítulo: "Visão geral da agência — carteira, produção e financeiro."

### 2. Acesso
- Rota: `/`. Menu lateral: "Dashboard" (1º item do grupo "Principal").
- Quem vê: qualquer usuário logado da organização (sem restrição de papel). Visibilidade no menu depende de `status_pagina` (`dashboard`) — ver Capítulo 0.
- Ações: nenhuma ação de escrita; todos os blocos são atalhos (links) para outras páginas.

### 3. Layout
De cima para baixo:
1. Cabeçalho "Dashboard" + subtítulo.
2. **Alerta de custo/hora** (faixa vermelha clicável → `/custos`), só depois que a lista de profissionais terminou de carregar:
   - sem nenhum profissional: "Nenhum profissional com custo/hora cadastrado — a calculadora de escopo, o BI de eficiência e o DRE não conseguem calcular custo real." + "Cadastrar em Custos";
   - com profissionais sem custo/hora: "N profissional(is) sem custo/hora — as horas deles não entram no custo real e a margem fica superestimada." + "Cadastrar em Custos".
3. **Quatro indicadores** (cada um é um link):
   - "Clientes ativos" → `/clientes`: total de clientes com status Ativo, contado **no servidor**; nota "N inadimplente(s)" quando há clientes com status Inadimplente.
   - "Peças em produção" → `/esteira`: tarefas da Esteira em todas as etapas **antes** da etapa de papel "Aprovação do cliente"; nota "N aguardando cliente".
   - "Receita no mês" → `/financeiro`: soma da receita do DRE da **competência atual** (mês corrente no horário de Brasília).
   - "Margem no mês" → `/financeiro`: receita da competência atual − custo das horas apontadas **nesse mesmo mês** (soma por cliente), ou "indisponível" com a nota "sem custo/hora" quando há profissional sem custo/hora ou nenhum profissional. Não é o mesmo número da tela Financeiro → "DRE por conta", que usa o custo do histórico completo (ver regra 6).
4. **Três indicadores do Comercial** (links para `/comercial`): "Negócios abertos" (quantidade de negócios `aberto` no quadro), "Valor em negociação" (soma do valor estimado dos abertos, em R$) e "Ganhos no mês" (negócios `ganho` com data de ganho no mês corrente).
5. Duas seções lado a lado (empilhadas no celular):
   - "Aguardando aprovação do cliente": tarefas na etapa de aprovação do cliente, com selo "N refação(ões)" quando houver refações.
   - "Inadimplência": faturas vencidas e não pagas (competência, valor · dias de atraso "Nd").
- Celular (≤640px): tudo em uma coluna. A partir de 640px os indicadores ficam em 2 colunas (os do Comercial em 3); em telas grandes (≥1024px) os quatro primeiros ficam em 4 colunas e as duas seções lado a lado.

### 4. Campos
— (página só de leitura)

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| Tocar num indicador | — | Abre a página correspondente (`/clientes`, `/esteira`, `/financeiro`, `/comercial`) | — | — |
| Tocar no alerta vermelho | Alerta visível | Abre `/custos` | — | — |

### 6. Estados
- Carregando: cada indicador mostra "—" enquanto o seu próprio dado carrega (clientes, quadro da Esteira, quadro Comercial, DRE). As seções "Aguardando aprovação do cliente" e "Inadimplência" mostram linhas de esqueleto no primeiro carregamento. O alerta de custo/hora **não aparece** enquanto os profissionais carregam (antes aparecia por um instante e dava a impressão falsa de que não havia profissionais).
- Vazio: "Nada parado com o cliente no momento." / "Nenhuma fatura vencida.".
- Erro: a seção "Inadimplência" mostra a mensagem do servidor (ou "Não foi possível carregar a inadimplência.") em vermelho — nunca "Nenhuma fatura vencida." no lugar de um erro. Os indicadores e a seção "Aguardando aprovação do cliente" não têm mensagem de erro própria: se a busca falhar, o indicador continua mostrando "—".
- Atualizando: sem indicador visual.

### 7. Regras de negócio e por quê
1. "Clientes ativos" usa a contagem total do servidor (não a lista paginada de 50) — o número bate com a realidade mesmo com mais de 50 clientes.
2. "Receita no mês" e "Margem no mês" usam a competência do mês corrente no fuso `America/Sao_Paulo`, nunca o relógio do navegador.
3. A margem é mostrada como "indisponível" quando falta custo/hora, porque "0%" e "desconhecido" pareceriam iguais.
4. "Peças em produção" é calculado pela **ordem e papel** das etapas (tudo antes da etapa de papel `aprovacao_cliente`), nunca pelo nome das colunas — a agência pode renomear/reordenar etapas livremente.
5. Sem nenhuma etapa com papel "Aprovação do cliente", todas as tarefas contam como "em produção" e "aguardando cliente" fica 0.
6. **"Margem no mês" compara o mesmo mês dos dois lados**: receita das faturas (não canceladas) da competência atual e custo só das horas apontadas nessa competência. *Por quê:* comparar a receita de um mês com o custo de todas as horas desde o início da conta deixava a margem cada vez mais baixa (e errada) à medida que o histórico crescia. A tela Financeiro → "DRE por conta" continua, de propósito, com custo do histórico completo (e diz isso na própria tela); por isso os dois números podem ser diferentes.

### 8. Fluxo de dados
- `useClientes({status:"ativo"})` e `useClientes({status:"inadimplente"})` → GET `/api/clientes?status=…` (usa o `total`).
- `esteiraPipeline.useBoard()` → GET `/api/esteira/board`.
- `comercialPipeline.useBoard()` → GET `/api/comercial/board` (negócios `aberto` + `ganho`).
- `useProfissionais()` → GET `/api/custos/profissionais` (campo `custo_hora_indefinido`).
- `useDRE(competência, true)` → GET `/api/financeiro/dre?competencia=AAAA-MM&custo_por_competencia=true` → `FinanceiroService.dre` (receita de `igig.fatura` da competência; custo de `BIService.eficiencia_por_cliente` filtrado pela mesma competência).
- `useInadimplentes()` → GET `/api/financeiro/inadimplentes` (esqueleto só no primeiro carregamento; erro exibido).
- Nada é gravado.

### 9. Dependências de configuração
- Profissionais com custo/hora em Custos (senão alerta vermelho e margem "indisponível").
- Etapa da Esteira com papel "Aprovação do cliente" (senão os indicadores de produção perdem o sentido).

### 10. Limitações conhecidas
- Horas apontadas num mês para um cliente que não teve fatura nesse mês entram só como custo (margem negativa naquele mês); a margem mensal depende de a fatura e o trabalho caírem na mesma competência.
- "Ganhos no mês" compara o mês da data de ganho gravada em UTC; um negócio ganho perto da meia-noite do último dia do mês (horário de Brasília) pode cair no mês seguinte.
- A lista de inadimplência não mostra o nome do cliente (só competência, valor e dias).
- A nota "N inadimplente(s)" usa o status do cliente, que a rotina diária das 06:00 atualiza (Capítulo 0, §9); já a seção "Inadimplência" é calculada na hora. Entre a meia-noite e as 06:00 os dois podem divergir por um dia.
- Os indicadores não mostram mensagem de erro própria quando a busca falha (ficam em "—").

### 11. Perguntas frequentes
- **P: Por que a margem aparece "indisponível"?** R: Há profissional sem custo/hora (ou nenhum profissional) em Custos. Cadastre o custo/hora e a margem volta a ser calculada.
- **P: A receita do mês inclui meses anteriores?** R: Não. Soma só as faturas (não canceladas) da competência do mês atual.
- **P: Por que a "Margem no mês" do Dashboard é diferente da margem do DRE no Financeiro?** R: O Dashboard usa o custo só das horas apontadas no mês atual; o "DRE por conta" do Financeiro usa o custo de todo o histórico de horas (a própria tela avisa: "custo real é sempre o histórico completo"). Os dois estão certos, medem coisas diferentes.
- **P: O número de clientes ativos está certo mesmo com mais de 50 clientes?** R: Sim, é a contagem do servidor.
- **P: O que é "Peças em produção"?** R: Tarefas da Esteira nas etapas anteriores à "Aprovação do cliente".
- **P: "Valor em negociação" inclui negócios ganhos?** R: Não, só os abertos.
- **P: Por que um cliente com fatura vencida não aparece como inadimplente?** R: O status muda sozinho todo dia às 06:00 (horário de Brasília). Se a fatura venceu ontem, espere a rotina da manhã; ela já aparece na seção "Inadimplência". Quando não houver mais fatura vencida (paga ou cancelada), o cliente volta a "Ativo" na rotina seguinte.

---

## Página: Comercial

### 1. Propósito
O funil de vendas (kanban) da agência. Contém: o link do formulário de pré-qualificação, os botões "Perdidos" e "Novo lead" e o quadro com as colunas (etapas). Cada card é um **negócio**. Subtítulo: "Cada lead novo entra na primeira etapa do funil."

### 2. Acesso
- Rota: `/comercial`. Menu lateral: "Comercial" (2º item). Deep link: `/comercial?negocio=<id>` abre direto o card daquele negócio (usado pelas notificações de automação e de lembretes).
- Qualquer membro logado: ver o funil, criar lead (novo contato ou cliente existente), mover cards (inclusive fechar), marcar como perdido, ver Perdidos e **reabrir**, editar lead/negócio, usar o card, o Assistente IA e gerar orçamento.
- Só administradores: criar, renomear, recolorir, reordenar e excluir etapas ("Configurar etapas", "+ coluna", menu "⋯" do cabeçalho da coluna) e mover o papel "Fechado" para outra etapa (painel "Papéis das etapas"). Para os demais, os cabeçalhos aparecem sem controles de edição e o painel não aparece.

### 3. Layout
- **Cabeçalho**: título "Comercial", subtítulo, botões "Perdidos" (ícone de arquivo) e "Novo lead" (ícone +).
- **Quadro do link** "Formulário de pré-qualificação": mostra a URL `https://<endereço do IgIg>/pre-qualificacao/<id da organização>` e o botão "Copiar" (vira "Copiado"). Só aparece se o usuário logado tiver organização associada.
- **Barra de ferramentas do quadro** (só administradores): botão "Configurar etapas" (vira "Fechar configuração"), que abre o painel de gerenciamento de etapas acima do quadro.
- **Quadro**: uma coluna por etapa ativa, na ordem configurada. Cabeçalho da coluna: nome da etapa (para admin, editável), contador de cards (se a coluna estiver truncada, "X de Y" com a dica "Mostrando X de Y cartões") e a soma dos valores estimados da coluna em R$. Etapa com papel mostra o selo "Fechado (exige orçamento aceito)". No fim do quadro, para admin, a coluna "+ coluna".
- **Face do card**: título = empresa do lead (ou nome do lead, ou título do negócio); abaixo, o nome da pessoa se for diferente da empresa; selo da origem ("Formulário", "Manual", "WhatsApp", "Meta Ads"); selo "Ganho" (com troféu) se fechado; valor estimado em R$; nome do responsável (ícone de pessoa). Em negócios abertos, ícone "Gerar orçamento" (documento com +), que abre o modal de orçamento sem abrir o card.
- **Painel "Papéis das etapas"** (só administradores, abaixo do quadro, recolhido por padrão — toque no título para abrir): uma linha "Fechado (exige orçamento aceito)" com um seletor das etapas do funil ("Escolha uma etapa…"); a etapa marcada é a que hoje tem o papel.
- **Quais negócios aparecem**: só `aberto` e `ganho`. Perdidos saem do quadro e ficam na área "Perdidos". Ganhos continuam na coluna de papel Fechado.
- **Celular (≤640px)**: cada coluna ocupa ~85% da largura da tela; o quadro rola para os lados **dentro da própria moldura** (a página não rola lateralmente) e cada coluna rola verticalmente. Para arrastar um card: **pressionar e segurar** (~250 ms) e arrastar; um deslize rápido é rolagem. Diálogos (Novo lead, card, Perdidos, seletor de orçamento) abrem em tela cheia. **Computador**: colunas de largura fixa (~320px), arrastar com o mouse.

### 4. Campos
Formulário "Novo lead" (janela "Novo lead" — "Entra na primeira etapa do funil."). No topo, duas opções: **"Novo contato"** (padrão; campos abaixo) e **"Cliente existente"** (negócio para um cliente que a agência já tem — upsell/renovação).

Opção "Novo contato":

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Nome" | texto | Sim | 1–200 caracteres | vazio | Botão "Criar lead" fica desabilitado sem nome |
| "Empresa" | texto | Não | até 200 | vazio | Vira o título do card |
| "E-mail" | e-mail | Não | até 200 | vazio | — |
| "Telefone" | telefone | Não | até 40 | vazio | — |
| "Instagram" | texto | Não | até 120 | vazio | Exemplo "@perfil" |
| "Valor estimado (R$/mês)" | número | Não | ≥ 0 (negativo vira 0) | vazio | — |
| "Observações" | texto longo | Não | até 4000 | vazio | — |

Opção "Cliente existente":

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Buscar cliente por nome…" | busca | Sim (escolher um) | lista até 20 clientes da agência que batem com a busca | vazio | Cada linha mostra nome, nicho · e-mail ou telefone (ou "Sem dados adicionais") e o selo de status. Escolhido, vira um resumo com o botão "Trocar"; o botão principal vira "Criar negócio" e só habilita com um cliente escolhido |
| "Valor estimado (R$/mês)" | número | Não | ≥ 0 | vazio | Aparece depois de escolher o cliente |

Campos do card do negócio (aba "Geral" → resumo):

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Valor estimado (R$/mês)" | número | Não | ≥ 0; vazio = sem valor | valor atual | Salva ao sair do campo; bloqueado se o negócio não está aberto |
| "Responsável" | lista | Não | profissional existente | atual | Opções: "Sem responsável" + profissionais **ativos** (Custos); bloqueado se não aberto |

Aba "Lead" do card:

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Nome" | texto | Sim | 1–200 | dado do lead | — |
| "Empresa" | texto | Não | até 200 | — | Vazio grava "sem valor" |
| "E-mail" | e-mail | Não | até 200; formato validado no servidor | — | E-mail inválido é recusado pelo servidor |
| "Telefone" | telefone | Não | até 40 | — | — |
| "Instagram" | texto | Não | até 200 | — | — |
| "Observações" | texto longo | Não | até 2000 | — | — |
| "Nicho", "Orçamento disponível", "Dores" | só leitura | — | — | — | Aparecem só se o lead tiver esses dados (vindos do formulário público) |

Seletor "Qual orçamento foi aceito?": lista de orçamentos elegíveis (escolha única) — ver Ações.

Perdidos: campo de busca "Buscar por título, empresa ou motivo…".

Marcar como perdido: campo de motivo (exemplo "Ex.: sem orçamento, escolheu outra agência, sem resposta…"), obrigatório, até 2000 caracteres.

Etapas (admin): nome da etapa 1–60 caracteres; cor entre `primary`, `secondary`, `success`, `warning`, `destructive`, `muted`.

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Copiar" (link do formulário) | Usuário com organização | Copia a URL pública do formulário | Botão vira "Copiado" | Se o navegador bloquear a área de transferência, nada é copiado; a URL continua visível para copiar à mão |
| "Novo lead" → "Criar lead" (ou Enter) | Nome preenchido | Cria o lead com origem "Manual" e um negócio na **primeira etapa ativa**, no topo da coluna; grava o histórico de entrada; roda as automações "Ao entrar na etapa" dessa etapa | "Lead criado — o card entrou na primeira etapa." | 409 `funil_sem_etapas` "O funil comercial não tem nenhuma etapa ativa. Configure as etapas primeiro." (peça a um admin para criar/ativar etapas); 404 profissional inexistente; outros: mensagem do servidor ou "Não foi possível criar o lead." |
| "Novo lead" → "Cliente existente" → escolher o cliente → "Criar negócio" | Cliente escolhido | Cria um lead novo (origem "Manual") com nome, e-mail e telefone do cliente e um negócio **ligado a esse cliente** na primeira etapa ativa; roda as automações da etapa. Ao fechar esse negócio, o **mesmo** cliente é reaproveitado (nunca é criado um segundo cadastro) | "Negócio criado para <cliente> — o card entrou na primeira etapa." | 409 `funil_sem_etapas` (como acima); 404 cliente inexistente; outros: mensagem do servidor ou "Não foi possível criar o negócio." |
| "Papéis das etapas" → escolher outra etapa em "Fechado (exige orçamento aceito)" (admin) | Painel aberto | Move o papel `fechado` para a etapa escolhida numa única operação (a etapa anterior perde o papel); a nova etapa passa a exigir orçamento aceito e ganha o selo | — (o seletor e o selo atualizam) | Mensagem do servidor ou "Não foi possível reatribuir o papel."; 409 `papel_fechado_obrigatorio` "Esta é a única etapa marcada como 'Fechado'. Atribua o papel a outra etapa antes de tirá-lo desta." (tentativa de apenas remover o papel); 403 "Apenas administradores podem alterar as etapas do quadro." |
| Arrastar card para outra coluna | Negócio não perdido; se ganho, só pode ser reordenado dentro da coluna Fechado | Card move na hora (otimista); servidor grava etapa, data de entrada na etapa e histórico (`pipeline_movimentos`); roda automações "Ao entrar na etapa" da etapa destino | — (o card fica na nova coluna) | Recusa: o card volta e aparece um aviso com a mensagem do servidor (ou "Não foi possível mover o negócio."): 409 "Este negócio foi marcado como perdido."; 409 "Um negócio fechado não sai da etapa de fechamento."; 404 "Etapa não encontrada" (recarregue a página) |
| Reordenar dentro da coluna | — | Posição salva; não é nova entrada na etapa (não roda automação) | — | Idem acima |
| Arrastar para a etapa de papel Fechado | Negócio aberto | Abre "Qual orçamento foi aceito?" (card fica aguardando a decisão) | — | Ver linha seguinte |
| "Fechar negócio" (no seletor) | Um orçamento elegível escolhido | Em uma requisição: valida o orçamento; encontra ou cria o **Cliente** a partir do lead (status "Prospect"); marca o lead como convertido; os demais orçamentos "Rascunho"/"Enviado" do negócio viram "Substituído"; o escolhido vira "Aceito"; **gera as pautas do calendário** (30 dias à frente, itens recorrentes de Criação de conteúdo); o negócio vira `ganho` na coluna Fechado; roda automações da etapa Fechado; a tela recarrega os dados do IgIg | (sem toast; o card aparece com selo "Ganho") | 409 `orcamento_obrigatorio` "Para fechar o negócio, informe qual orçamento foi aceito."; 409 `orcamento_invalido` "Este orçamento não pertence a este negócio." ou "Este orçamento está <status> e não pode ser aceito."; 409 `orcamento_expirado` "A validade deste orçamento já passou." (crie nova versão com nova validade); 409 `orcamento_ja_aceito` "Outro orçamento deste negócio já foi aceito — feche com ele." Em qualquer recusa o card volta e o aviso mostra a mensagem |
| "Cancelar" (no seletor) | — | O card volta à coluna original; nada é gravado | — | — |
| "Gerar orçamento" (no seletor sem orçamento elegível) | Nenhum orçamento elegível | Cancela o movimento e abre o modal de orçamento para o negócio | — | — |
| Ícone "Gerar orçamento" (card ou cabeçalho do card aberto) | Negócio aberto | Abre o modal de orçamento vinculado ao negócio (guia de Orçamentos) | — | — |
| Clicar/tocar num card | — | Abre o card do negócio | — | "Não foi possível carregar este cartão." |
| "Marcar como perdido" (ícone no cabeçalho do card) → "Marcar como perdido" | Negócio aberto; motivo preenchido | Negócio vira `perdido` com data, motivo e a etapa em que estava (`perdido_stage_id`); sai do quadro; não é apagado | "Negócio marcado como perdido." (o card fecha) | 409 `negocio_encerrado` "Só um negócio em aberto pode ser marcado como perdido (status: ganho)."; 422 `motivo_obrigatorio` "Informe o motivo da perda."; outros: "Não foi possível marcar como perdido." |
| "Perdidos" | — | Abre a área "Perdidos" com todos os negócios perdidos da organização | — | "Não foi possível carregar os perdidos." (ou mensagem do servidor) |
| "Reabrir" (em Perdidos) | Negócio com status `perdido` | Devolve o negócio para a etapa em que foi perdido (se essa etapa foi excluída ou desativada, vai para a primeira etapa ativa), no topo da coluna; limpa data/motivo/etapa de perda; status volta a `aberto`; **reinicia o relógio "tempo nesta etapa"** (`stage_entered_at`), inclusive quando volta para a mesma etapa em que foi perdido; grava histórico com motivo "Reaberto do arquivo de perdidos" (e, na volta para a mesma etapa, uma nova entrada no histórico do card); roda automações "Ao entrar na etapa" da etapa destino; fecha Perdidos e abre o card | "Negócio reaberto." | 409 "Só um negócio perdido pode ser reaberto."; 409 "O funil comercial não tem nenhuma etapa ativa. Configure as etapas primeiro."; outros: "Não foi possível reabrir o negócio." |
| Editar valor / responsável (aba Geral) | Negócio aberto | PATCH do negócio | — (campo atualiza) | "Não foi possível salvar o valor." / "Não foi possível trocar o responsável."; 404 profissional inexistente |
| "Salvar lead" (aba Lead) | Algo alterado e nome preenchido | Atualiza os dados de contato do lead (campo apagado grava vazio de verdade) | "Lead atualizado." | Mensagem inline: mensagem do servidor (ex.: e-mail inválido) ou "Não foi possível salvar o lead."; 422 "Nenhum campo para atualizar."; 404 "Lead não encontrado" |
| Renomear etapa (admin) | — | Duplo clique no nome (dica "Clique duas vezes para renomear") ou menu "⋯" → "Renomear"; Enter salva, Esc cancela | Etapa "X" atualizada | "Erro ao atualizar etapa" + mensagem: "O nome da etapa não pode ficar vazio.", "O nome da etapa deve ter no máximo 60 caracteres.", "Já existe uma etapa com o identificador '<slug>'. Escolha outro nome." |
| Mudar cor (admin) | — | Menu "⋯" → escolher bolinha | Etapa "X" atualizada | "Erro ao atualizar etapa" |
| "+ coluna" → "Adicionar" (admin) | Nome preenchido | Nova etapa no **fim** do funil | 'Etapa "X" criada' | "Erro ao criar etapa" + mensagem do servidor |
| Excluir etapa (admin) | Etapa sem papel | Menu "⋯" → "Excluir etapa". Sem cards: exclui. Com cards: pede "Mover cartas para" uma etapa e "Confirmar exclusão"; os cards são movidos em massa antes e **cada card movido ganha uma linha no histórico de movimentos** (`pipeline_movimentos`), atribuída ao administrador que excluiu, com o motivo "Etapa "<nome>" excluída — carta movida para "<destino>"." | "Etapa excluída" ou "Etapa excluída — N negócio(s) movido(s)" | Etapa com papel: botão desabilitado ("Esta etapa tem um papel do qual outras funcionalidades dependem"); servidor: "A etapa 'X' não pode ser excluída porque tem o papel 'fechado', do qual outras funcionalidades dependem. Atribua o papel a outra etapa antes de excluí-la."; "Um funil precisa de pelo menos uma etapa."; "Não é possível mover as cartas para a própria etapa."; destino com papel: "'Fechado' tem o papel 'fechado' — mover cartas para lá em massa ignoraria as regras desse papel. Escolha uma etapa sem papel especial, ou mova essas cartas manualmente antes de excluir." |
| Reordenar colunas (admin) | — | Arrastar o cabeçalho da coluna (ou setas "Mover X para cima/baixo" em "Configurar etapas") | "Ordem das etapas atualizada" | "Erro ao reordenar etapas" |
| Qualquer escrita de etapa por não-admin | — | Recusada | — | 403 "Apenas administradores podem alterar as etapas do quadro." |

### 6. Estados
- Carregando: três colunas-esqueleto no quadro.
- Vazio: "Cliente existente" sem resultado: "Nenhum cliente encontrado."; coluna sem cards "Nenhum negócio nesta etapa"; nenhuma etapa: "Nenhuma etapa configurada." (para admin acrescenta ' Use "Configurar etapas" para criar a primeira.'); Perdidos vazio: "Nenhum negócio perdido ainda."; busca sem resultado: "Nenhum perdido corresponde à busca."; aba Orçamentos vazia: "Nenhum orçamento ainda."; seletor de Fechado sem elegíveis: "Este negócio ainda não tem orçamento em aberto.".
- Erro: "Cliente existente": "Não foi possível carregar os clientes."; card "Não foi possível carregar este cartão."; seletor "Não foi possível carregar os orçamentos."; Perdidos "Não foi possível carregar os perdidos."; aba Lead "Não foi possível carregar o lead.".
- Atualizando: movimentos são otimistas (o card já aparece na nova coluna); o quadro recarrega em segundo plano.

### 7. Regras de negócio e por quê
1. **Primeira etapa = etapa de entrada.** Todo lead novo (manual, formulário, WhatsApp, Meta Ads) entra na primeira etapa ativa por posição, no topo. Mover outra etapa para a primeira posição muda a etapa de entrada.
2. **As regras seguem o papel, não o nome.** A coluna de papel `fechado` pode ser renomeada ou movida; a exigência de orçamento continua valendo para ela.
3. **Fechar exige orçamento.** Não existe fechamento sem orçamento aceito, porque o orçamento vira o contrato e a base do cliente.
4. **Os dois caminhos de fechamento são o mesmo.** Arrastar para Fechado e "Aceitar orçamento" no modal passam pelo mesmo mecanismo: ambos criam/reaproveitam o cliente e **geram as pautas**. (Antes, arrastar não gerava pautas.)
5. **Só um orçamento aceito por negócio**; ao fechar, os outros "Rascunho"/"Enviado" viram "Substituído".
6. **O cliente nunca é duplicado**: é localizado pelo cliente já ligado ao negócio, depois pelo lead (índice único cliente×lead).
7. **Negócio ganho não sai de Fechado** (pode ser reordenado dentro dela). Não há "desfechar".
8. **Perder não apaga**: guarda motivo, etapa e tempo parado, que alimentam as estatísticas de perda.
9. **Reabrir é uma nova entrada**: volta à etapa onde foi perdido, as automações daquela etapa rodam de novo e o tempo na etapa recomeça do zero — o período arquivado como perdido não conta como tempo parado na etapa (nem para o SLA).
10. **Uma automação roda uma vez por entrada**: reordenar na coluna, repetir a requisição ou o SLA correndo junto nunca executam a mesma regra duas vezes.
11. **Falha de automação não desfaz o movimento**; fica registrada em Automações → "Execuções recentes".
12. **Excluir etapa com cards** exige um destino; destino com papel especial é recusado (movê-los em massa pularia as regras do papel, ex.: criar cliente). Cada card movido fica registrado no histórico de movimentos, em nome do administrador que excluiu a etapa. *Por quê:* a movimentação em massa precisa ser tão auditável quanto um arrasto manual (vale para os dois quadros, Comercial e Esteira).
13. **Etapa com papel não pode ser excluída nem desativada**.
14. Isolamento: todas as tabelas do funil são filtradas pela organização (RLS).
15. **Negócio para cliente existente reaproveita o cliente.** Todo negócio precisa de um lead, então é criado um lead novo com os dados do cliente, mas o negócio já nasce ligado ao cliente escolhido; o fechamento usa esse cliente primeiro. *Por quê:* evita cadastros duplicados da mesma conta em upsell/renovação.
16. **O papel "Fechado" nunca fica sem etapa.** Mover o papel é uma operação só (tira de uma, põe na outra); apenas remover é recusado. *Por quê:* sem etapa de fechamento nenhum negócio poderia ser fechado.

### 8. Fluxo de dados
- Quadro: `PipelineBoard` (seed) + `comercialPipeline` → GET `/api/comercial/board` → `comercial_funil.quadro` → `negocio` (status aberto/ganho) + `lead` + `profissional`, agrupado por `pipeline_stages` (`pipeline='comercial'`). As etapas padrão ("Leads", "Qualificação", "Negociação", "Agendar briefing", "Fechado" com papel `fechado`) são criadas na primeira leitura de uma organização que nunca configurou o funil.
- Mover: POST `/api/comercial/negocios/{id}/mover-etapa` `{para_etapa_id, novo_indice, orcamento_id?}` → `comercial_funil.mover_negocio` → `_fechar` quando o destino tem papel `fechado` (tabelas `orcamento`, `cliente`, `lead`, `pauta`) → seed `move_card` (grava `negocio.etapa_id`, `kanban_pos`, `stage_entered_at` e `pipeline_movimentos`) → `automacoes.ao_entrar_etapa` (automações, notificações `automacao`).
- Novo lead: `NovoLeadDialog` → `useCriarNegocio` → POST `/api/comercial/negocios` `{lead:{…}, valor_estimado, cliente_id?}` → insert `lead` (origem `manual`) → `comercial_funil.abrir_negocio` (grava `negocio.cliente_id` quando veio `cliente_id`; confere que o cliente existe na organização) → `pipeline_movimentos` (entrada) → automações. Cliente existente: `useClientes({busca, limit:20})` → GET `/api/clientes?busca=…`.
- Papéis das etapas: `StageRolePanel` → `useAtribuirPapelEtapaComercial` → PATCH `/api/comercial/pipeline/stages/{id}/papel` `{papel:"fechado"}` → `comercial_funil.reatribuir_papel` (limpa a etapa anterior e grava a nova em `pipeline_stages.papel`).
- Editar negócio: PATCH `/api/comercial/negocios/{id}` (`titulo`, `valor_estimado`, `responsavel_id`).
- Perder: POST `/api/comercial/negocios/{id}/perder` `{motivo}` → `negocio.status='perdido'`, `perdido_em`, `motivo_perda`, `perdido_stage_id`.
- Perdidos: `usePerdidos` → GET `/api/comercial/negocios?status=perdido` (traz etapa de perda e `dwell_dias`); filtro por texto feito no navegador.
- Reabrir: `useReabrirNegocio` → POST `/api/comercial/negocios/{id}/reabrir` → seed `move_card` com `status='aberto'`, campos de perda limpos e `stage_entered_at` = agora → (mesma etapa) nova linha em `pipeline_movimentos` → automações.
- Deep link: `?negocio=<id>` → procura o card no quadro; se não estiver (ex.: perdido), busca GET `/api/comercial/negocios/{id}`. Fechar o card remove o parâmetro da URL.
- Etapas (admin): GET/POST `/api/comercial/pipeline/stages`, GET `/api/comercial/pipeline/stages/opcoes`, PATCH/DELETE `/api/comercial/pipeline/stages/{stage_id}` (`?reassign_to=`), POST `/api/comercial/pipeline/stages/reordenar`. Escrita protegida por `exigir_admin_do_quadro`.
- Lead: GET `/api/comercial/leads/{id}` (um lead só) e PATCH `/api/comercial/leads/{id}`.

### 9. Dependências de configuração
- Profissionais **ativos** em Custos para aparecerem em "Responsável" e "Membros"; vinculados a um usuário de login para receberem notificações.
- Bucket privado `igig-cardhub` (`IGIG_CARDHUB_BUCKET`) para anexos do card.
- Automações que enviam e-mail/WhatsApp dependem de Integrações (ver Página Automações).
- Assistente IA: chave da Anthropic no servidor (senão "A IA não está configurada (chave da Anthropic ausente).").

### 10. Limitações conhecidas
- Não há "desfechar" um negócio ganho; ganhos acumulam na coluna Fechado.
- Não há busca/filtro no quadro; a busca existe só em Perdidos.
- Não há tela para ver/filtrar leads diretamente nem para mudar o status do lead (novo/qualificado/descartado).
- Na exclusão de etapa com realocação, o histórico de cada card movido é gravado (em nome do administrador), mas **não há tela para consultá-lo**; além disso, a data de entrada na etapa não é reiniciada (o SLA desses cards continua contando da entrada anterior) e as automações "Ao entrar na etapa" do destino não rodam para eles.
- Um negócio para cliente existente ainda cria uma linha de lead nova (o funil exige um lead por negócio).
- Anexo removido no card é removido na hora, sem confirmação (motivo registrado automaticamente como "Removido pelo usuário"; exclusão lógica).
- O quadro de Perdidos não tem paginação (lista todos os perdidos da organização).

### 11. Perguntas frequentes
- **P: Por que não consigo arrastar para Fechado?** R: Fechar exige escolher o orçamento aceito. Se não houver orçamento elegível (rascunho, enviado ou aceito e dentro da validade), toque em "Gerar orçamento".
- **P: Fechei arrastando; o calendário ganhou pautas?** R: Sim. Arrastar para Fechado e aceitar pelo orçamento geram as pautas do mesmo jeito. Para negócios fechados antes dessa correção, use "Gerar pautas" no orçamento aceito.
- **P: Onde estão os negócios perdidos?** R: Botão "Perdidos" no topo do Comercial. Lá é possível buscar e "Reabrir".
- **P: Para onde vai um negócio reaberto?** R: Para a etapa em que foi perdido; se ela não existe mais, para a primeira etapa do funil.
- **P: Não consigo editar as colunas.** R: Só Proprietário/Administrador da agência editam etapas.
- **P: Não consigo excluir a etapa Fechado.** R: Ela tem o papel de fechamento, do qual o fechamento de negócios depende.
- **P: A pessoa não aparece como responsável.** R: Cadastre-a como profissional ativo em Custos.
- **P: O responsável não recebe notificações.** R: Vincule o profissional ao usuário de login em Custos.
- **P: A notificação de automação abre o card?** R: Sim, o link `/comercial?negocio=<id>` abre o card do negócio.
- **P: Como vendo mais para um cliente que já existe?** R: Em Comercial, "Novo lead" → "Cliente existente", busque o cliente e toque em "Criar negócio". Ou, em Clientes, abra o card do cliente e toque em "Novo negócio". Ao fechar, o mesmo cliente é reaproveitado.
- **P: Quero que outra coluna seja a de fechamento.** R: Um administrador abre "Papéis das etapas" (abaixo do quadro) e escolhe a nova etapa em "Fechado (exige orçamento aceito)". O papel sai da etapa antiga automaticamente.

---

## Funcionalidade: Card do negócio (todas as subpáginas) e Assistente IA

### 1. Propósito
Janela de detalhe de um negócio (mesmo "card" usado no cliente): dados do negócio, lead, orçamentos, colaboração (etiquetas, membros, descrição, anexos, checklists, comentários), lembretes e o Assistente IA.

### 2. Acesso
- Abre ao tocar num card do Comercial, por "Reabrir" em Perdidos, ou por `/comercial?negocio=<id>`.
- Qualquer membro logado pode usar todas as abas. Ícones "Gerar orçamento" e "Marcar como perdido" só aparecem em negócios **abertos**.

### 3. Layout
- Computador: janela grande (90% da tela) em três colunas: barra de abas com ícones à esquerda, conteúdo da aba no centro e, à direita, a coluna **"Comentários e atividade"** (~360px).
- Celular (≤640px): tela cheia, conteúdo e atividade empilhados.
- Título: empresa ou nome do lead (ou título do negócio). Cabeçalho: ícones "Gerar orçamento" e "Marcar como perdido" (só se aberto).
- Abas (só a aba ativa carrega dados):
  - **"Geral"** (padrão): barra "Etiquetas", "Membros", "Checklist"; resumo do negócio ("Valor estimado (R$/mês)", "Responsável" e, se ganho, "Ganho em <data> — o cliente já foi criado."); "Descrição"; "Anexos"; checklists.
  - **"Lead"**: selo da origem, "Como conheceu: …", "Desde <data>", campos do lead e, se houver, "Nicho", "Orçamento disponível", "Dores" (só leitura).
  - **"Orçamentos"**: contador ("1 orçamento" / "N orçamentos"), botão "Gerar orçamento" (se aberto) e a lista "<título> · v<versão>", "R$ X/mês · <data>", selo de status.
  - **"Lembretes"** (ícone de sino): botão "Novo lembrete" (ícone +; no celular ocupa a largura toda); formulário embutido ("Título", "Data e hora (América/São Paulo)", "Responsável" e os botões "Adicionar"/"Salvar" e "Cancelar"); lista de **pendentes** (mais antigos primeiro; os que já passaram do horário ficam com borda vermelha e a etiqueta "Atrasado") seguida da lista de **concluídos** (esmaecidos e riscados). Cada linha: caixa de marcação (concluir/reabrir), título, data e hora "dd/mm/aaaa hh:mm" no horário de Brasília, "· <responsável>" se houver, e os ícones de lápis ("Editar lembrete <título>") e lixeira ("Excluir lembrete <título>"). É a mesma aba do card do cliente (ver "Página: Clientes").
  - **"Assistente"**: botões "Resumo", "Próxima ação", "Rascunho de mensagem" e o seletor "Canal do rascunho" ("WhatsApp"/"E-mail").
- Coluna "Comentários e atividade": campo "Escrever um comentário…" + "Comentar"; linha do tempo (comentários, checklists, documentos, movimentos de etapa) com "Carregar mais".

### 4. Campos
| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Buscar etiquetas…" / "Nome da etiqueta" + cor | texto + cor | Nome sim | cor `#RRGGBB` | — | Catálogo de etiquetas da organização compartilhado entre cards de negócio |
| "Pesquisar membros" | lista de seleção | Não | profissionais ativos | — | Membros do card são profissionais |
| Título do checklist | texto | Sim | — | — | Botão "Adicionar" |
| "Adicionar um item" | texto | Sim | — | — | Item de checklist |
| Descrição | texto longo | Não | — | "Sem descrição ainda." | Botões "Editar descrição"/"Salvar descrição" |
| "Tipo do documento" + arquivo | lista + arquivo | Sim | PDF, JPEG, PNG, WebP; até **25 MB** | — | Tipos habilitados: contrato, proposta, comprovante de pagamento, comprovante de endereço, outro (RG e CPF inativos) |
| "Escrever um comentário…" | texto | Sim | — | — | "Comentar" |
| "Canal do rascunho" | lista | — | "WhatsApp"/"E-mail" | "WhatsApp" | Só para "Rascunho de mensagem" |
| "Título" (Lembretes) | texto | Sim | ao menos 1 caractere (espaços nas pontas são removidos) | vazio | Placeholder "Ex.: Ligar para confirmar a arte". Sem ele o botão "Adicionar"/"Salvar" fica desabilitado |
| "Data e hora (América/São Paulo)" (Lembretes) | data e hora (seletor nativo) | Sim | — (aceita horário no passado: o lembrete já nasce "Atrasado" e é entregue na próxima rodada da rotina) | vazio | Sempre interpretada no horário de Brasília, qualquer que seja o fuso do aparelho; gravada em UTC |
| "Responsável" (Lembretes) | lista | Não | profissional ativo da organização | "Nenhum" | Só aparece se a organização tem pelo menos um profissional ativo em Custos; lista **qualquer** profissional ativo, não só os membros do card. Também recebe a notificação, se tiver login vinculado (ver regra 7) |

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| Marcar/desmarcar etiqueta | — | Define as etiquetas do card | — | "Não foi possível atualizar as etiquetas." |
| Criar etiqueta | Nome | Adiciona ao catálogo | — | "Não foi possível criar a etiqueta." |
| Editar etiqueta (lápis) | — | Abre o prompt "Renomear etiqueta" | — | "Não foi possível renomear a etiqueta." |
| Interruptor "Habilitar o modo compatível para usuários com daltonismo" | — | Mostra padrões nas cores (só nesta sessão) | — | — |
| Marcar/desmarcar membro | — | Define os membros (profissionais) do card | — | "Não foi possível atualizar os membros." |
| Criar checklist / adicionar, marcar, remover item / remover checklist | — | Grava no card | — | "Não foi possível criar o checklist." / "…adicionar o item." / "…atualizar o item." / "…remover o item." / "…remover o checklist." |
| Salvar descrição | — | Cria ou atualiza a descrição | — | "Não foi possível salvar a descrição." / "Não foi possível criar a descrição." |
| "Enviar anexo" | Tipo escolhido (senão o botão diz "Escolha o tipo do documento antes de enviar") | Envia o arquivo ao bucket `igig-cardhub` | — | "Não foi possível enviar o anexo." (arquivo acima de 25 MB ou formato não aceito é recusado pelo servidor) |
| Abrir anexo | — | Gera link temporário (**5 minutos**) e abre em nova aba; o acesso é registrado | — | "Não foi possível abrir o anexo." |
| Remover anexo (lixeira) | — | Remove **sem confirmação**; exclusão lógica com motivo "Removido pelo usuário"; registrado | — | "Não foi possível remover o anexo." |
| "Comentar" | Texto | Adiciona comentário à linha do tempo | — | "Não foi possível enviar o comentário." |
| "Carregar mais" | Há mais itens | Carrega itens antigos da linha do tempo | — | "Não foi possível carregar a atividade." |
| "Resumo" / "Próxima ação" / "Rascunho de mensagem" | — | Envia ao servidor, que monta o contexto e chama a IA; o texto aparece num quadro. Nada é salvo nem enviado | Botão "Copiar" → "Copiado." | 503 `ia_nao_configurada` "A IA não está configurada (chave da Anthropic ausente)."; 429 `orcamento_ia_excedido` "O limite de uso de IA da organização foi atingido."; 429 "Muitas requisições. Tente novamente em breve." (mais de 20 pedidos por minuto da mesma pessoa); 502 `ia_indisponivel` "O provedor de IA não respondeu. Tente novamente em instantes."; 502 `ia_resposta_vazia` "A IA não retornou texto. Tente novamente."; genérico "O assistente não respondeu."; copiar: "Não foi possível copiar." |
| Tocar num orçamento (aba Orçamentos) | — | Abre o modal do orçamento | — | "Não foi possível carregar os orçamentos." |
| "Novo lembrete" → "Adicionar" (Lembretes) | "Título" e "Data e hora" preenchidos | Cria um lembrete pendente no card; a lista recarrega. Quando o horário chegar, a rotina de 5 em 5 minutos entrega a notificação no sino (Capítulo 0, §9) e o lembrete passa para "concluídos" | — (o lembrete aparece na lista) | Aviso "Não foi possível criar o lembrete." ou a mensagem do servidor: 404 "profissional não encontrado" (responsável removido nesse meio-tempo — escolha outro); 404 do card ("negocio não encontrado"/"cliente não encontrado") se o card foi excluído; 422 de validação |
| Lápis → editar → "Salvar" (Lembretes) | — | Reabre o mesmo formulário preenchido; grava título, data/hora e responsável ("Nenhum" remove o responsável). Mudar o horário de um lembrete **pendente** muda quando ele será entregue | — | "Não foi possível atualizar o lembrete." ou mensagem do servidor (404 "profissional não encontrado"; 404 "Lembrete não encontrado" se foi excluído em outra aba) |
| Caixa de marcação — "Marcar lembrete como concluído" / "Reabrir lembrete" (Lembretes) | — | Concluir: marca como feito agora; **a rotina não entrega mais** esse lembrete. Reabrir: volta a pendente; se o horário já passou, ele é entregue na próxima rodada da rotina (até ~5 min) | — | "Não foi possível atualizar o lembrete." |
| Lixeira → "Confirmar exclusão?" (Lembretes) | — | O primeiro toque troca os ícones pelo botão vermelho "Confirmar exclusão?" e um "X" ("Cancelar"); só o segundo toque exclui — **de vez**, sem lixeira nem histórico. Não há janela de confirmação separada | — (a linha some) | "Não foi possível excluir o lembrete." |

### 6. Estados
- Carregando: esqueleto no card inteiro; na aba Assistente, três linhas-esqueleto ("Gerando").
- Vazio: "Sem descrição ainda."; "Nenhum orçamento ainda."; Lembretes: "Nenhum lembrete neste cartão ainda.".
- Erro: "Não foi possível carregar este cartão."; "Não foi possível carregar a atividade."; Lembretes: mensagem do servidor ou "Não foi possível carregar os lembretes." (em vermelho, acima da lista).
- Atualizando: lista de anexos em segundo plano sem esconder o conteúdo; Lembretes: esqueleto só no primeiro carregamento e "Atualizando…" embaixo da lista ao recarregar.

### 7. Regras de negócio e por quê
1. **Assistente — minimização de dados (LGPD)**: a IA recebe só: do lead (nome, empresa, e-mail, telefone, Instagram, origem, como conheceu, especificações, observações, status e — desde esta versão — **nicho, canais atuais, dores e orçamento disponível**); do negócio (título, valor, status, entrada na etapa, motivo de perda, criação, etapa atual, responsável); histórico de etapas; orçamentos (versão, título, status, total mensal, validade, envio, resposta, motivo de recusa); até 30 itens da linha do tempo (sem conteúdo de documentos).
2. A IA responde em português do Brasil, só com fatos do contexto; resumo em até 6 tópicos; próxima ação com porquê e prazo; rascunho de WhatsApp curto (até 3 parágrafos) ou e-mail com linha "Assunto:".
3. **Nada é gravado nem enviado** pelo Assistente; gerar de novo substitui o texto.
4. Limite por pessoa: 20 pedidos por minuto (configurável), além do limite de gasto de IA da organização.
5. Anexos são privados; ver/baixar só por link temporário de 5 minutos, com registro de acesso.
6. **Lembretes — horário sempre de Brasília.** A data/hora digitada é lida como horário de São Paulo (UTC−3, sem horário de verão) e gravada em UTC; a lista mostra de volta no horário de Brasília. *Por quê:* quem cria e quem recebe o lembrete podem estar em aparelhos com fusos diferentes; o horário combinado é o da agência.
7. **Lembretes — entrega só no sino.** Único canal: notificação no app (não há e-mail nem WhatsApp, por isso o formulário não tem "canal"). A notificação diz "Lembrete: <título do lembrete>" / "Lembrete agendado para “<título do lembrete>”." (ou o título do negócio, se o "Título" do lembrete ficou vazio) e abre `/comercial?negocio=<id>`. Vai para o "Responsável" escolhido (se tiver login vinculado) **e** os membros do card com login vinculado em Custos, sem repetir ninguém; sem nenhum dos dois, para os administradores.
8. **Lembretes — concluído = não entregar mais.** Entregue pela rotina ou marcado à mão, o lembrete vai para "concluídos" e nunca é reenviado; só volta a valer se for reaberto. *Por quê:* a mesma marca (`enviado_em`) serve para "já avisou" e "já resolvido".
9. **Lembretes — duas confirmações para excluir**, em vez de uma janela: a aba roda dentro da área de rolagem do card, e uma terceira janela por cima no celular atrapalharia mais do que ajudaria. A exclusão é definitiva.

### 8. Fluxo de dados
- Card hub (seed) sob o prefixo `/api/comercial/negocios`: GET `/{id}/card`, GET `/{id}/timeline`, POST/PATCH/DELETE `/{id}/notas…`, GET/POST/PATCH/DELETE `/tags…`, PUT `/{id}/tags`, GET/PUT `/{id}/membros` (`profissional_ids`), `/{id}/checklists…`, GET/POST `/{id}/documentos`, GET `/{id}/documentos/{doc}/url`, DELETE `/{id}/documentos/{doc}?motivo=` → tabelas `negocio_notas`, `negocio_tags`, `negocio_tag_links`, `negocio_membros`, `negocio_checklists`, `negocio_checklist_itens`, `negocio_documentos`, `negocio_documento_acessos` (gravação pelo cliente service-role filtrando `org_id`).
- Lembretes: `useLembretesSubpage` (IgIg) → `LembretesSubpage` (seed) → `useLembretes`/`useLembreteMutations` → GET/POST `/api/comercial/negocios/{id}/lembretes`, PATCH/DELETE `/api/comercial/negocios/{id}/lembretes/{lembrete_id}` → seed `card_hub.services` (`list_/create_/update_/delete_lembrete`) → tabela `igig.negocio_lembretes` (`titulo`, `dispara_em` em UTC, `responsavel_id` → `igig.profissional`, `enviado_em` = concluído, `cancelado_em`). "Responsável" lista `useProfissionais()` (ativos). Entrega: rotina `igig_lembretes_pendentes` → `notificacoes.processar_lembretes_pendentes` → `public.notifications` (tipo `lembrete_negocio`) e grava `enviado_em`. A lista esconde lembretes com `cancelado_em` (gravado só pelo mecanismo "lembrete X minutos antes da entrega" do seed, que o IgIg não usa: não há seção de datas no card do IgIg).
- Assistente: `AssistenteSubpage` → `useAssistenteNegocio` → POST `/api/comercial/negocios/{id}/assistente` `{acao, canal?}` → `assistente.montar_contexto` → provedor `anthropic`, modelo fixo `claude-sonnet-4-6` (conferido contra o catálogo de modelos do seed; se sair do catálogo, o assistente falha em vez de trocar de modelo), temperatura 0.4, até 1200 tokens → `{data:{texto}}`.

### 9. Dependências de configuração
- `IGIG_CARDHUB_BUCKET` (padrão `igig-cardhub`) para anexos.
- Chave Anthropic (resolvida pela plataforma) e orçamento de IA da organização para o Assistente.
- `assistente_rate_limit` (padrão "20/minute").

### 10. Limitações conhecidas
- Não há histórico das respostas do Assistente.
- Remover anexo não pede confirmação.
- Linhas livres de checklist (texto/arquivo) existem no servidor, mas não têm tela no IgIg.
- Lembretes: usa o "Título" digitado (ou o título do negócio, se ficou vazio) e avisa o "Responsável" escolhido (quando tem login vinculado), além dos membros do card ou, sem nenhum dos dois, dos administradores. Não há e-mail/WhatsApp nem repetição (recorrência) de lembrete, e a entrega pode atrasar até ~5 minutos. Lembretes não aparecem em "Comentários e atividade".
- Lembretes só funcionam no ambiente implantado (a rotina de entrega não roda localmente).
- O Assistente envia dados pessoais do lead à Anthropic sem um consentimento de IA específico do produto (decisão pendente do dono do produto — Capítulo 5).
- Este Assistente (do negócio) é diferente do **Assistente IgIg** (balão de ajuda em todas as telas), que só explica o uso da plataforma e não vê os dados do negócio.

### 11. Perguntas frequentes
- **P: O Assistente envia a mensagem ao cliente?** R: Não. Ele só sugere; copie, revise e envie você.
- **P: O Assistente lê os dados do formulário de pré-qualificação?** R: Sim: nicho, canais atuais, dores e orçamento disponível.
- **P: O Assistente lê meus anexos?** R: Não, só os metadados (nome/tipo) que aparecem na linha do tempo.
- **P: Por que aparece "Muitas requisições. Tente novamente em breve."?** R: Você fez mais de 20 pedidos em um minuto. Aguarde um pouco.
- **P: Quanto tempo vale o link de um anexo?** R: 5 minutos; abra de novo para gerar outro.
- **P: As etiquetas de um negócio aparecem nos clientes?** R: Não; o catálogo de etiquetas de clientes é separado.
- **P: Qual IA o Assistente usa?** R: Claude Sonnet (`claude-sonnet-4-6`), da Anthropic, sempre o mesmo modelo.
- **P: Como crio um lembrete para um negócio?** R: Abra o card, aba "Lembretes" (sino) → "Novo lembrete", preencha "Título" e "Data e hora" (horário de Brasília), opcionalmente o "Responsável", e toque em "Adicionar".
- **P: Quem recebe o aviso do lembrete?** R: O "Responsável" escolhido (se tiver login vinculado) e os membros do card que têm login vinculado em Custos; sem nenhum dos dois, os administradores. O aviso chega no sino em até ~5 minutos depois do horário, com o texto "Lembrete: <título do lembrete>".
- **P: Marquei o lembrete como concluído antes da hora. Vou ser avisado mesmo assim?** R: Não. Concluído não é mais entregue; reabra-o se ainda quiser o aviso.

---

## Página: Formulário de Pré-qualificação (público)

### 1. Propósito
Página pública (sem login) onde o prospect preenche seus dados antes da primeira reunião. Feita para ser enviada por link ou incorporada no site da agência. Cada envio vira **um lead (origem "Formulário") + um negócio na primeira etapa do Comercial**.

### 2. Acesso
- Rota pública: `/pre-qualificacao/<id da organização>`. Não aparece no menu.
- A agência encontra o link pronto no topo da página Comercial (quadro "Formulário de pré-qualificação", botão "Copiar").
- Qualquer pessoa com o link pode enviar. O link não é segredo, mas precisa apontar para uma organização real.

### 3. Layout
- Tela "white-label": sem menu e sem marca da agência; um cartão centralizado.
- Título "Vamos conhecer o seu projeto" e o texto "Preencha antes da nossa reunião — assim chegamos com uma proposta que já faz sentido para o seu momento."
- Celular (≤640px): campos em uma coluna. Telas maiores: os seis primeiros campos em duas colunas; "Canais que já usa", "Como você conheceu a gente?" e "O que mais te incomoda hoje?" ocupam a largura toda.

### 4. Campos
| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Seu nome *" | texto | Sim | 1–200 | vazio | Exemplo "Ana Souza"; botão "Enviar" desabilitado sem nome |
| "Empresa" | texto | Não | até 200 | vazio | Exemplo "Padaria Sol"; vira o título do card |
| "E-mail" | e-mail | Não | até 200 | vazio | Exemplo "ana@padariasol.com" |
| "Telefone / WhatsApp" | texto | Não | até 40 | vazio | Exemplo "(11) 99999-9999" |
| "Nicho" | texto | Não | até 120 | vazio | Exemplo "Alimentação" |
| "Orçamento disponível (R$/mês)" | número | Não | ≥ 0 | vazio | Exemplo "5000" |
| "Canais que já usa" | texto | Não | até 500 | vazio | Exemplo "Instagram, TikTok, LinkedIn…" |
| "Como você conheceu a gente?" | texto | Não | até 120 (no servidor) | vazio | Exemplo "Indicação, Instagram, Google…"; gravado como "Como conheceu" do lead |
| "O que mais te incomoda hoje?" | texto longo | Não | até 2000 | vazio | Exemplo "Pouco alcance, sem constância, não sei o que postar…" |

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Enviar" (vira "Enviando…") | Nome preenchido; link com id de organização existente | Grava o lead (origem `formulario`, "Como conheceu" = resposta do campo, ou vazio); cria o negócio na primeira etapa ativa, no topo; grava o histórico de entrada; **roda as automações "Ao entrar na etapa"** da etapa de entrada | Tela "Recebemos seus dados" — "Obrigado! Entraremos em contato em breve para agendar a conversa." | Qualquer falha mostra "Não foi possível enviar. Verifique sua conexão e tente novamente." e o formulário continua preenchido. Causas: 404 "Organização não encontrada." (link com id errado ou de organização inexistente — peça o link correto à agência); 422 (campo acima do limite, ex.: "Como você conheceu a gente?" com mais de 120 caracteres); 429 (mais de 60 envios por minuto do mesmo endereço) |

### 6. Estados
- Link sem id: "Link inválido" — "Este formulário precisa ser aberto pelo link enviado pela agência."
- Enviando: botão "Enviando…" desabilitado.
- Sucesso: tela fixa de agradecimento, sem repetir nenhum dado enviado.
- Erro: mensagem acima do botão (texto na linha de Ações).

### 7. Regras de negócio e por quê
1. **Somente escrita**: a resposta nunca devolve o registro nem um id — um endpoint anônimo que ecoasse dados seria fonte de raspagem.
2. **Organização precisa existir**: um id desconhecido é recusado com 404 (antes criava leads e um funil inteiro para uma "organização fantasma").
3. **"Como conheceu" é resposta real**: vem do campo "Como você conheceu a gente?"; vazio fica vazio (antes era gravado um texto fixo "formulario-publico").
4. **Automações rodam** como em qualquer outra origem de lead.
5. Se a agência estiver sem nenhuma etapa ativa, o lead **é salvo mesmo assim**, mas fica sem card (o erro vai só para o log do servidor) — o prospect não é penalizado pela configuração da agência.
6. Não há verificação de duplicidade: enviar duas vezes cria dois leads e dois cards.
7. Se a organização nunca abriu o funil, as etapas padrão são criadas neste momento.

### 8. Fluxo de dados
`PreQualificacao.tsx` → `fetch` sem token → POST `/api/comercial/leads/publico` `{org_id, nome, email, telefone, empresa, nicho, canais_atuais, dores, orcamento_disponivel, origem: <"Como você conheceu a gente?">}` → `comercial_router.capturar_lead` (cliente service-role; verifica a organização em `public.organizations`) → insert `igig.lead` (`origem='formulario'`, `como_conheceu`) → `comercial_funil.abrir_negocio` → `igig.negocio` + `igig.pipeline_movimentos` → `automacoes.ao_entrar_etapa`. Resposta: `{"ok": true, "mensagem": "Recebemos seus dados. Entraremos em contato em breve."}`.

### 9. Dependências de configuração
- `WEBHOOK_RATE_LIMIT` (padrão 60 por minuto por IP).
- O link exibido no Comercial usa o endereço atual do navegador + o id da organização do usuário logado.
- A página chama o backend em `VITE_BACKEND_API_URL` (em produção, o próprio domínio).

### 10. Limitações conhecidas
- Sem captcha e sem deduplicação; a proteção é o limite de 60 envios/minuto.
- A mensagem de erro é sempre a mesma (não diferencia link errado, campo longo ou excesso de envios).
- O campo "Como você conheceu a gente?" não limita o tamanho na tela; acima de 120 caracteres o envio falha com a mensagem genérica.
- "Canais que já usa" é gravado e enviado ao Assistente IA, mas não aparece na aba "Lead" do card (só "Nicho", "Orçamento disponível" e "Dores" aparecem).

### 11. Perguntas frequentes
- **P: Onde pego o link do formulário?** R: No topo da página Comercial, quadro "Formulário de pré-qualificação" → "Copiar".
- **P: O que acontece quando alguém preenche?** R: Nasce um card na primeira etapa do funil, com origem "Formulário", e as automações daquela etapa rodam.
- **P: O prospect viu "Não foi possível enviar".** R: Confira se o link é o da sua agência, se nenhum campo está exageradamente longo e peça para tentar de novo em um minuto.
- **P: Posso colocar o formulário no meu site?** R: Sim, o link é público; basta divulgá-lo ou incorporá-lo.
- **P: Onde vejo as respostas (nicho, dores, orçamento)?** R: No card do negócio, aba "Lead".
- **P: O formulário mostra a marca da agência?** R: Não, é neutro (white-label).

---

## Página: Clientes

### 1. Propósito
A carteira de clientes da agência. A lista abre o **card do cliente**, que reúne tudo sobre ele: dados, marcas (Central da Marca) e Cofre de Acessos, orçamentos e contratos, calendário, lembretes, esteira e financeiro — além da colaboração do card (etiquetas, membros, descrição, anexos, checklists, comentários e linha do tempo).

### 2. Acesso
- Rota: `/clientes`. Menu lateral: "Clientes" (3º item). Deep link: `/clientes?id=<id do cliente>` abre o card (fechar remove o `?id=`). O endereço antigo `/marca` redireciona para `/clientes`.
- Qualquer membro logado: ver, criar, editar, ativar clientes; abrir um **"Novo negócio"** para o cliente; usar todas as abas; criar/editar marcas e acessos do Cofre.
- Só administradores: **"Remover cliente"** (o botão aparece para todos, mas o servidor recusa não-admins com 403 "Apenas administradores da organização podem realizar esta ação."); **"Revelar"** senha do Cofre (para não-admin aparece o selo "Protegida" com cadeado); **"Paga"** na aba Financeiro (o botão só aparece para administradores).

### 3. Layout
- Cabeçalho: "Clientes" e o total ("N cliente"/"N clientes"; "Carregando…" na primeira carga; " · atualizando…" durante recarga). Botão "Novo cliente".
- Filtros: busca "Buscar por nome…" (espera 300 ms; busca parte do nome) e "Filtrar por status" ("Todos os status", "Prospect", "Ativo", "Inativo", "Inadimplente").
- Lista: **celular (<768px)**: um cartão por cliente com nome, "nicho · e-mail ou telefone" (ou "Sem nicho definido"), selo de status e seta. **Computador**: tabela com colunas "Cliente", "Nicho", "Contato", "Status", "Desde".
- Paginação: 50 clientes por página; com mais de uma página aparecem no rodapé "Anterior", "Página X de Y" e "Próxima". Trocar busca/status volta para a página 1.
- Cores do status: Prospect (cinza), Ativo (principal), Inativo (contorno), Inadimplente (vermelho).
- **Card do cliente**: mesma janela do card do negócio (computador: abas à esquerda, conteúdo ao centro, "Comentários e atividade" à direita; celular: tela cheia). Cabeçalho com o selo de status e o botão **"Novo negócio"** (ícone +). Abas:
  - **"Geral"**: "Etiquetas", "Membros", "Checklist"; resumo do cliente ("Nicho", "E-mail", "Telefone", "Origem", "Cliente desde" — só os preenchidos); descrição; anexos; checklists. O catálogo de etiquetas dos clientes é separado do dos negócios.
  - **"Dados"**: todos os campos editáveis do cliente, "Salvar", "Ativar" (só para Prospect) e "Remover cliente".
  - **"Marcas"**: chips das marcas do cliente, "Nova marca", o painel da marca selecionada e, abaixo, o **"Cofre de Acessos"** (um por cliente). Detalhes completos no Capítulo 3 (Funcionalidade: Central da Marca + Cofre de Acessos).
  - **"Orçamentos & Contratos"**: seção "Orçamentos" (orçamentos ligados ao cliente) e seção "Contratos". Detalhes de contrato no Capítulo 2.
  - **"Calendário"**: o calendário editorial filtrado para este cliente (Capítulo 3).
  - **"Lembretes"** (ícone de sino): lembretes com hora marcada deste cliente — "Novo lembrete", formulário ("Título", "Data e hora (América/São Paulo)", "Responsável"), lista de pendentes (com "Atrasado" em vermelho quando o horário já passou) e de concluídos. Campos, ações, mensagens e regras são os mesmos do card do negócio (ver "Funcionalidade: Card do negócio"); aqui a notificação diz "Lembrete: <título do lembrete>" (ou o nome do cliente, se ficou vazio) e abre `/clientes?id=<id>`.
  - **"Esteira"**: o quadro de produção filtrado para este cliente (Capítulo 3).
  - **"Financeiro"**: totais "Em aberto" e "Recebido" e a lista de faturas do cliente (competência; "vence dd/mm/aaaa"; " · paga em dd/mm/aaaa"; numa fatura **vencida** que já foi enviada, " · enviada em dd/mm/aaaa"; valor; selo de status); para administradores, botão "Paga" nas faturas não pagas nem canceladas.
  - Não existe aba de "Notas" separada: comentários e descrição ficam em "Geral" e na coluna "Comentários e atividade".

### 4. Campos
"Novo cliente":

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Nome" | texto | Sim | 1–200 | vazio | Exemplo "Padaria Sol" |
| "Nicho" | texto | Não | até 120 | vazio | Exemplo "Alimentação" |
| "E-mail" | e-mail | Não | até 200 | vazio | — |
| "Telefone" | telefone | Não | até 40 | vazio | — |

Aba "Dados":

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Nome" | texto | Sim | 1–200 | atual | — |
| "Nicho" | texto | Não | até 120 | atual | Apagar e salvar grava vazio de verdade |
| "E-mail" | e-mail | Não | até 200 | atual | Idem |
| "Telefone" | telefone | Não | até 40 | atual | Idem |
| "Origem" | texto | Não | até 120 | atual | Para clientes vindos do funil, a origem do lead (ex.: `whatsapp`) |
| "Status" | lista | Sim | Prospect / Ativo / Inativo / Inadimplente | atual | — |
| "Observações" | texto longo | Não | — | atual | Idem |

Janela "Novo negócio" (botão do cabeçalho do card):

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Título (opcional)" | texto | Não | — | vazio (sugestão: nome do cliente) | Vazio: o título vira o nome do cliente |
| "Valor estimado (R$/mês)" | número | Não | ≥ 0 | vazio | — |

Modal "Marcar como assinado" (contrato físico): arquivo opcional "Escolher arquivo" — PDF, JPG ou PNG, até 25 MB.

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Novo cliente" → "Adicionar" | Nome | Cria o cliente sempre como **Prospect** e abre o card dele | "Cliente criado." | Mensagem do servidor ou "Não foi possível criar o cliente." |
| Tocar num cliente | — | Abre o card (`?id=`) | — | "Não foi possível carregar este cartão." / "Cartão não encontrado." (id inexistente) |
| "Anterior" / "Próxima" | Mais de 50 resultados | Troca de página mantendo busca e filtro | — | — |
| "Salvar" (Dados) | Algo alterado; nome preenchido | Atualiza o cliente; campos apagados viram vazio | "Cliente atualizado." | "Não foi possível salvar as alterações." (ou mensagem do servidor); 400 "Nenhum campo para atualizar"; 404 "Cliente não encontrado" |
| "Ativar" (Dados) | Cliente Prospect | Status → Ativo | "Cliente ativado." | "Não foi possível ativar." |
| "Remover cliente" → "Remover" | **Administrador** | Exclusão **definitiva em cascata**: marcas, acessos do Cofre, contratos, faturas, pautas (e peças, tarefas, apontamentos, aprovações, publicações) e o conteúdo do card | "Cliente removido." (o card fecha) | 403 "Apenas administradores da organização podem realizar esta ação." (peça a um administrador); 404 "Cliente não encontrado"; "Não foi possível remover o cliente." |
| Abas Geral (etiquetas, membros, checklist, descrição, anexos, comentários) | — | Igual ao card do negócio (ver Funcionalidade: Card do negócio) | idem | idem |
| Aba "Lembretes": "Novo lembrete" → "Adicionar"; lápis → "Salvar"; caixa de marcação (concluir/reabrir); lixeira → "Confirmar exclusão?" | "Título" e "Data e hora" para criar | Igual ao card do negócio: o lembrete pendente é entregue no sino pela rotina de 5 em 5 minutos ao chegar o horário; concluído não é mais entregue; exclusão definitiva | — | "Não foi possível criar o lembrete." / "Não foi possível atualizar o lembrete." / "Não foi possível excluir o lembrete." ou a mensagem do servidor (ex.: 404 "profissional não encontrado", "Lembrete não encontrado") |
| Marcas / Cofre | — | Ver Capítulo 3 | "Marca criada." / "Marca removida." etc. | ver Capítulo 3 |
| Tocar num orçamento (Orçamentos & Contratos) | — | Abre o modal do orçamento por cima do card | — | "Não foi possível carregar os orçamentos." |
| "PDF" / "Via assinada" (contrato) | Documento existe | Abre link temporário do PDF em nova aba | — | "Documento indisponível."; "Não foi possível abrir o contrato." |
| "Marcar como assinado" → "Confirmar assinatura" | Contrato **físico** ainda não Ativo nem Encerrado | Ativa o contrato e o cliente a partir de hoje; guarda a digitalização se enviada | "Contrato assinado e ativo." | "Não foi possível marcar como assinado." / mensagens do servidor (ex.: "Envie o contrato assinado em PDF, JPG ou PNG.", "O arquivo enviado está vazio.", "Este contrato está encerrado e não pode ser reativado.") |
| "Reenviar / gerar novamente" | Contrato em Rascunho com orçamento | Abre o orçamento para gerar novo contrato | — | — |
| "Paga" (Financeiro) → "Marcar paga" | Fatura não paga nem cancelada; **administrador** (o botão só aparece para eles) | Abre a confirmação "Marcar fatura como paga" — "Marcar esta fatura como paga? Registra a data de agora; não há como desfazer pela tela." ("Cancelar" / "Marcar paga", que vira "Marcando…"); confirmada, marca a fatura como paga | "Fatura marcada como paga." | 403 "Apenas administradores da organização podem realizar esta ação."; 409 "Fatura cancelada não pode ser paga."; "Não foi possível marcar como paga." |
| "Novo negócio" (cabeçalho do card) → "Criar negócio" | — | Cria um negócio **ligado a este cliente** na primeira etapa do Comercial (com um lead novo, origem "Manual", com nome/e-mail/telefone do cliente); roda as automações da etapa; fecha a janela e leva ao card do novo negócio em `/comercial?negocio=<id>`. Ao fechar esse negócio, o mesmo cliente é reaproveitado | "Negócio criado para <cliente> — o card entrou na primeira etapa." | 409 "O funil comercial não tem nenhuma etapa ativa. Configure as etapas primeiro."; outros: mensagem do servidor ou "Não foi possível criar o negócio." (mostrado na janela) |

### 6. Estados
- Carregando: esqueleto de tabela na lista; "Carregando…" no cabeçalho; esqueletos nas abas.
- Vazio: sem filtro — "Nenhum cliente ainda. Clientes nascem quando um negócio é fechado no Comercial — ou adicione um agora." + "Novo cliente"; com filtro — "Nenhum cliente corresponde aos filtros."; Orçamentos — "Nenhum orçamento ligado a este cliente. Orçamentos nascem de um negócio no Comercial."; Contratos — "Nenhum contrato. Gere um a partir de um orçamento aceito."; Financeiro — 'Nenhuma fatura para este cliente. Faturas saem de "Gerar competência" no Financeiro.'; Marcas — "Nenhuma marca cadastrada para este cliente." + "Criar marca".
- Erro: "Não foi possível carregar os clientes."; "Não foi possível carregar o cliente."; "Não foi possível carregar os contratos."; "Não foi possível carregar as faturas."; "Não foi possível carregar as marcas.".
- Atualizando: " · atualizando…" no cabeçalho; a lista anterior continua visível enquanto a nova busca carrega.
- Avisos em contratos: digital aguardando assinatura mostra "Link de assinatura (simulação — assinatura digital ainda não integrada): …"; digital que voltou para rascunho mostra "Assinatura recusada ou expirada — o contrato voltou para rascunho.".

### 7. Regras de negócio e por quê
1. Todo cliente novo nasce **Prospect**; vira **Ativo** automaticamente quando um contrato físico é marcado como assinado ou um contrato digital é confirmado pelo provedor, ou manualmente ("Ativar" ou campo "Status").
2. Clientes nascem sozinhos ao fechar um negócio no Comercial (nome = empresa ou nome do lead, com e-mail, telefone, origem e o vínculo ao lead e ao negócio).
3. **Remover cliente é só para administrador** e é definitivo em cascata — por isso a confirmação cita marcas, contratos, pautas, tarefas e apontamentos.
4. Limpar um campo em "Dados" grava vazio de verdade (não texto vazio).
5. Orçamentos só nascem de um negócio. Para orçar para um cliente já existente (inclusive um criado à mão), use "Novo negócio" no card do cliente: o negócio já nasce ligado a ele e, ao fechar, o mesmo cliente é reaproveitado.
6. O Cofre é um por **cliente** (não por marca); senhas nunca aparecem na listagem e só administradores revelam, com cada revelação gravada (quem e quando).
7. A lista usa paginação real no servidor (50 por página, máx. 200 por chamada) e o total vem com os mesmos filtros.
8. "Paga" é uma movimentação financeira: só administradores veem o botão, e ele sempre pede confirmação — a mesma regra da página Financeiro.

### 8. Fluxo de dados
- Lista: `useClientes({busca, status, limit:50, offset})` → GET `/api/clientes?busca=&status=&limit=&offset=` → `igig.cliente` + contagem.
- Detalhe: `useCliente(id)` → GET `/api/clientes/{id}`.
- Criar: POST `/api/clientes`. Editar: PATCH `/api/clientes/{id}` (só os campos enviados; `null` limpa). Ativar: POST `/api/clientes/{id}/ativar`. Remover: DELETE `/api/clientes/{id}` (admin, `exigir_admin_da_org`).
- Card hub sob `/api/clientes` (mesmos endpoints do card do negócio) → tabelas `cliente_notas`, `cliente_tags`, `cliente_tag_links`, `cliente_membros`, `cliente_checklists`, `cliente_checklist_itens`, `cliente_documentos`, `cliente_documento_acessos`.
- Lembretes: `useLembretesSubpage` → GET/POST `/api/clientes/{id}/lembretes`, PATCH/DELETE `/api/clientes/{id}/lembretes/{lembrete_id}` → `igig.cliente_lembretes` → entrega pela rotina `igig_lembretes_pendentes` (notificação tipo `lembrete_cliente`, link `/clientes?id=<id>`).
- Marcas/Cofre: `/api/marcas…` e `/api/marcas/acessos…` (Capítulo 3).
- Orçamentos: GET `/api/orcamentos?cliente_id=`. Contratos: GET `/api/contratos?cliente_id=`, GET `/api/contratos/{id}/pdf`, POST `/api/contratos/{id}/marcar-assinado`.
- Financeiro: GET `/api/financeiro/faturas?cliente_id=`; POST `/api/financeiro/faturas/{id}/pagar` (admin).
- Novo negócio: `NovoNegocioClienteDialog` → `useCriarNegocio` → POST `/api/comercial/negocios` `{lead:{nome,email,telefone}, cliente_id, titulo?, valor_estimado?}` → navegação para `/comercial?negocio=<id>`.
- Calendário/Esteira: os mesmos componentes das páginas Calendário e Esteira, filtrados por `cliente_id`.

### 9. Dependências de configuração
- `IGIG_COFRE_KEY` para guardar senhas no Cofre (sem ela aparece "Cofre não configurado neste ambiente (IGIG_COFRE_KEY). …" e senhas são recusadas).
- `IGIG_ASSINATURA_WEBHOOK_SECRET` para contratos digitais ativarem sozinhos (sem ele o webhook recusa tudo).
- `IGIG_CARDHUB_BUCKET` para anexos.

### 10. Limitações conhecidas
- Remover cliente é definitivo (sem lixeira). O botão "Remover cliente" aparece para quem não é administrador, que recebe o erro 403 ao confirmar.
- O status "Inadimplente" é aplicado (e retirado) pela rotina diária das 06:00; entre a meia-noite e as 06:00 pode estar um dia atrasado em relação às faturas.
- O e-mail/WhatsApp de boas-vindas e o formulário de onboarding após a assinatura não estão implementados (`NOC-REMEDIATE[igig-onboarding]`).
- Assinatura digital ainda é simulação (link de teste).
- Lembretes: a notificação usa o "Título" digitado (ou o nome do cliente, se ficou vazio) e avisa o "Responsável" escolhido (quando tem login vinculado), além dos membros do card com login, ou, sem nenhum dos dois, dos administradores; só no sino, sem e-mail/WhatsApp; pode chegar até ~5 minutos depois do horário.
- Na aba Financeiro o status da fatura aparece com o código técnico (ex.: "aberta", "paga").

### 11. Perguntas frequentes
- **P: Como um cliente vira Ativo?** R: Ao marcar o contrato físico como assinado, quando o provedor confirma o contrato digital, pelo botão "Ativar" (Prospect) ou pelo campo "Status" em Dados.
- **P: Onde fica a Central da Marca?** R: Clientes → abrir o cliente → aba "Marcas".
- **P: Não consigo remover um cliente.** R: Só Proprietário/Administrador podem; é uma exclusão definitiva de tudo do cliente.
- **P: Só aparecem 50 clientes.** R: Use "Próxima" no rodapé ou a busca.
- **P: Criei um cliente à mão; como faço o orçamento?** R: Abra o card do cliente e toque em "Novo negócio". Você será levado ao card do negócio no Comercial, onde gera o orçamento.
- **P: Não vejo o botão "Paga" na aba Financeiro.** R: Só administradores da agência marcam fatura como paga.
- **P: Quem pode ver as senhas do Cofre?** R: Só administradores, pelo botão "Revelar"; cada revelação fica registrada.
- **P: Como abro um cliente direto por link?** R: `/clientes?id=<id>`.
- **P: Apaguei o telefone e salvei; ficou vazio?** R: Sim, o campo é gravado vazio.
- **P: Como agendo um lembrete sobre um cliente (ex.: ligar na sexta às 10h)?** R: Abra o card do cliente → aba "Lembretes" → "Novo lembrete"; preencha "Título" e "Data e hora" (horário de Brasília) e toque em "Adicionar". Na hora marcada chega um aviso no sino.
- **P: Por que o lembrete aparece como "Atrasado"?** R: O horário já passou e ele ainda não foi concluído nem entregue. A entrega pela rotina acontece em até ~5 minutos; depois disso ele vai para os concluídos.

---

## Página: Automações

### 1. Propósito
Regras que rodam sozinhas quando um card **entra numa etapa** ou **fica parado** numa etapa além de um prazo (SLA), nos dois quadros: "Comercial (funil)" e "Esteira de produção". Subtítulo: "Regras que rodam quando um card entra numa etapa ou fica parado além do SLA."

### 2. Acesso
- Rota: `/automacoes`. Menu lateral: "Automações" (11º item).
- Todos os membros: ver regras e "Execuções recentes".
- Só administradores: "Nova automação", "Editar", "Excluir", interruptor pausar/ativar. Não-admin vê o aviso "Somente administradores da agência podem criar ou alterar automações.".

### 3. Layout
- Cabeçalho + botão "Nova automação" (admin).
- Seção "Regras": filtro "Filtrar por quadro" ("Todos os quadros", "Comercial (funil)", "Esteira de produção"); lista de cartões. Cada regra: selo "Comercial"/"Esteira", nome da etapa (ou "etapa removida"), selo "pausada" se inativa, linha "<gatilho> → <tipo de ação>" (ex.: "SLA estourado · 24h → Notificar") e resumo da ação (ex.: 'Checklist "Onboarding"', "Responsável: Ana", 'Tarefa "Ligar" · prazo 2d', "Notificar o responsável", 'E-mail "Assunto" ao contato do card', "WhatsApp ao contato do card"). Admin: interruptor, "Editar", "Excluir".
- Seção "Execuções recentes" com botão "Atualizar": últimas 50 execuções; cada linha com selo de status ("Executando", "Sucesso", "Erro"), "<tipo de ação> · <etapa>" (ou "Automação excluída"), data/hora e o detalhe (vermelho se erro).
- Editor ("Nova automação"/"Editar automação"): janela; tela cheia no celular (≤640px).

### 4. Campos
| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Quadro" | lista | Sim | "Comercial (funil)" / "Esteira de produção" | Comercial | Não pode mudar depois de criada |
| "Etapa" | lista | Sim | etapas **ativas** do quadro | — | "Carregando etapas…" / "Escolha a etapa" |
| "Quando" | escolha | Sim | "Ao entrar na etapa" / "SLA estourado" | Ao entrar na etapa | — |
| "Horas parado na etapa até disparar" | número | Sim se SLA | inteiro 1–8760 | 24 | — |
| "Ação" | lista | Sim | "Criar checklist" (só Comercial), "Definir responsável", "Criar tarefa", "Notificar", "Enviar e-mail", "Enviar WhatsApp" | "Notificar" | — |
| "Título do checklist" | texto | Sim (checklist) | até 200 | — | — |
| "Itens (um por linha)" | texto longo | Não | até 50 itens | — | — |
| "Responsável" (definir) | lista | Sim | profissional ativo | — | — |
| "Título da tarefa" | texto | Sim (tarefa) | até 200 | — | — |
| "Prazo (dias)" | número | Não | inteiro 0–365 | vazio | — |
| "Responsável" (tarefa) | lista | Não | "O do card" ou profissional ativo | "O do card" | — |
| "Título" (notificar) | texto | Não | até 200 | — | Exemplo "{titulo} entrou em {etapa}" |
| "Mensagem" (notificar) | texto longo | Não | até 2000 | — | — |
| "Notificar também (o responsável do card sempre recebe)" | caixas | Não | até 50 membros da Equipe | — | "Carregando equipe…" / "Nenhum membro na equipe." |
| "Assunto" (e-mail) | texto | Sim | até 300 | — | — |
| "Mensagem" (e-mail) | texto longo | Sim | até 20000 | — | — |
| "Para (vazio = e-mail do contato do card)" | e-mail | Não | formato de e-mail; até 320 | — | — |
| "Mensagem" (WhatsApp) | texto longo | Sim | até 4000 | — | — |
| "Para (vazio = WhatsApp do contato do card)" | telefone | Não | até 40 | — | — |
| "Ativa" | interruptor | — | — | ligado | — |

Variáveis nos textos: "Textos aceitam {nome}, {empresa}, {titulo}, {etapa} e {cliente}." ({nome} = nome do lead ou do cliente; {empresa} = empresa do lead ou nome do cliente; {titulo} = título do card; {etapa} = nome da etapa; {cliente} = nome do cliente).

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Nova automação" / "Editar" → "Salvar" | Admin; formulário válido (senão o motivo aparece embaixo: "Escolha a etapa.", "SLA em horas: um número entre 1 e 8760.", "Informe o título do checklist.", "Escolha o responsável.", "Informe o título da tarefa.", "Prazo em dias deve ser um número inteiro.", "Prazo máximo: 365 dias.", "Informe o assunto.", "Escreva a mensagem.", "E-mail do destinatário inválido.") | Grava a regra | "Automação criada." / "Automação atualizada." | 422: "Esta etapa não existe neste quadro.", "Esta etapa está desativada.", "Checklists automáticos existem só no funil comercial (card do negócio).", "O profissional informado não existe.", "Uma automação de SLA precisa de `sla_horas`."; "Nenhum campo para atualizar."; 403 "Apenas administradores da organização podem realizar esta ação."; genérico "Não foi possível salvar a automação." |
| Interruptor pausar/ativar | Admin | Liga/desliga a regra (mantém histórico) | "Automação ativada." / "Automação pausada." | "Não foi possível alterar a automação." |
| "Excluir" → "Excluir" | Admin | Confirmação "Excluir esta automação e todo o histórico de execuções dela? Para só parar de rodar mantendo o histórico, pause em vez de excluir." Exclui a regra e suas execuções | "Automação excluída." | "Não foi possível excluir a automação." |
| "Atualizar" (Execuções) | — | Recarrega o registro | — | "Não foi possível carregar as execuções." |

Execução das ações (motor):
| Tipo | Efeito | Detalhe gravado (sucesso) | Erros comuns (detalhe da execução) → o que fazer |
|---|---|---|---|
| Criar checklist | Cria o checklist (com itens) no card do negócio | "Checklist “X” criado com N item(ns)" | "Checklists automáticos existem só no funil comercial (card do negócio)." |
| Definir responsável | Troca o responsável do card | "Responsável definido: Ana" | "O profissional configurado nesta automação não existe mais." → edite a regra |
| Criar tarefa | Comercial: item no checklist "Tarefas" do card (com "(até dd/mm/aaaa)" se houver prazo). Esteira: nova tarefa na mesma pauta | "Tarefa “X” adicionada ao checklist Tarefas" / "Tarefa “X” criada na esteira (…)" | "A tarefa de origem não tem pauta — não há onde criar a nova tarefa." |
| Notificar | Notificação no sino | "Notificação enviada a N usuário(s)" | "Nenhum destinatário para a notificação (sem responsável nem usuários)." → defina responsável com usuário vinculado ou marque usuários |
| Enviar e-mail | E-mail pelo SMTP da agência (ou da plataforma) | "E-mail enviado para x@y.com — <id>" (com " (SMTP da plataforma)" quando usa o reserva) | "Sem destinatário: o contato não tem e-mail e a automação não define `para`."; "Nenhum SMTP configurado: cadastre uma conta em Integrações → E-mail." |
| Enviar WhatsApp | Mensagem pelo WAHA da agência | "WhatsApp enviado para 5511…@c.us" | "Sem destinatário: o contato não tem telefone válido e a automação não define `para`."; "WhatsApp (WAHA) não configurado — Integrações › WhatsApp." (configure o cartão em Integrações → Fontes de lead); "WhatsApp: existe um segredo gravado, mas IGIG_COFRE_KEY não está definida." (problema do servidor) |

### 6. Estados
- Carregando: esqueletos nas duas seções; "Carregando etapas…" no editor.
- Vazio: "Nenhuma automação ainda." ou "Nenhuma automação neste quadro." (+ "Criar a primeira" para admin); "Nenhuma execução ainda.".
- Erro: "Não foi possível carregar as automações."; "Não foi possível carregar as execuções."; "Não foi possível carregar as etapas.".
- Atualizando: lista fica levemente transparente; botão "Atualizando…".

### 7. Regras de negócio e por quê
1. **"Ao entrar na etapa"** roda logo depois de: mover um card (Comercial ou Esteira), criar negócio por "Novo lead", lead chegando pelo formulário público, WhatsApp ou Meta, "Aceitar orçamento" (entrada em Fechado), reabrir um perdido e, na Esteira, criar tarefa, gerar link de aprovação e decisão do cliente no portal.
2. **Uma execução por entrada**: cada execução é amarrada ao registro de entrada do card na etapa. Reordenar na coluna, repetir a requisição ou o SLA correndo junto nunca executam duas vezes; sair e voltar é nova entrada.
3. **SLA**: a cada 15 minutos o servidor verifica as regras de SLA ativas; para cada card na etapa há mais tempo que o limite (desde a entrada), executa a ação da regra **e** envia "SLA estourado: <card>" — "“<card>” está em <etapa> há mais de Nh." (se a ação da regra já é "Notificar", o título/mensagem dela substituem esses textos). Uma vez por entrada. No Comercial só conta negócios abertos.
4. **Destinatários**: "Notificar também" + o usuário vinculado ao profissional responsável do card; se ninguém, quem fez o movimento; no SLA sem ninguém, os administradores da organização.
5. **Falha nunca desfaz o movimento** — fica como "Erro" nas execuções, com o motivo.
6. A ação da regra roda antes do alerta de SLA (um "Definir responsável" por SLA já define quem recebe o alerta).
7. Escrita só-admin porque uma regra age em todos os cards do quadro, para toda a agência.
8. "Quadro" não muda depois de criada (a etapa pertence a um quadro).

### 8. Fluxo de dados
`Automacoes.tsx` / `AutomacaoForm.tsx` → `useAutomacoes`/`useExecucoes`/`useAutomacaoMutations` → GET `/api/automacoes?pipeline=`, POST `/api/automacoes` (admin), PATCH/DELETE `/api/automacoes/{id}` (admin), GET `/api/automacoes/execucoes?limit=50` → tabelas `igig.automacao` (`pipeline`, `etapa_id`, `gatilho`, `sla_horas`, `acao` JSON, `ativo`) e `igig.automacao_execucao` (`status`, `detalhe`, `movimento_id`). Motor `services/automacoes.py` (`ao_entrar_etapa`, `varrer_sla`); agendador `igig_automacoes_sla` (15 min). Notificações em `public.notifications` (tipos `automacao` e `sla_estourado`) com link `/comercial?negocio=<id>` ou `/esteira?tarefa=<id>`.

### 9. Dependências de configuração
- "Enviar WhatsApp": WhatsApp (WAHA) configurado em Integrações → Fontes de lead.
- "Enviar e-mail": SMTP em Integrações → E-mail (ou SMTP da plataforma).
- Notificar responsáveis: profissional com usuário vinculado (Custos).
- SLA só roda no servidor implantado (`NOCTUS_SCHEDULERS_ENABLED`).

### 10. Limitações conhecidas
- Excluir uma etapa apaga as automações dela (cascata no banco).
- Não há ação de IA nas automações.
- "Ignorada" foi removido da tela porque o motor nunca grava esse status.

### 11. Perguntas frequentes
- **P: Não consigo criar automação.** R: Só Proprietário/Administrador.
- **P: A regra rodou duas vezes?** R: Não roda: uma execução por entrada na etapa. Se o card saiu e voltou, é nova entrada.
- **P: O SLA não disparou.** R: A verificação é a cada 15 minutos e só no servidor de produção; a contagem começa na entrada do card na etapa.
- **P: Tocar na notificação abre o card?** R: Sim. Notificações de automação e de SLA levam a `/comercial?negocio=<id>` (card do negócio) ou `/esteira?tarefa=<id>` (detalhes da tarefa). A tarefa abre mesmo que seja de um cliente fora do filtro "Cliente" da Esteira; só se ela tiver sido excluída aparece "Tarefa não encontrada — pode ter sido excluída.".
- **P: A notificação não chegou.** R: Veja o detalhe em "Execuções recentes". Normalmente falta responsável com usuário vinculado em Custos.
- **P: O e-mail da automação falhou.** R: Configure o SMTP em Integrações → E-mail, ou preencha "Para"/o e-mail do contato.
- **P: Pausar ou excluir?** R: Pausar mantém o histórico; excluir apaga a regra e suas execuções.
- **P: Leads do formulário disparam automações?** R: Sim, como qualquer outra origem.

---

## Funcionalidade: Fontes de lead (WhatsApp/WAHA e Meta Lead Ads)

### 1. Propósito
Receber leads automaticamente: a primeira mensagem de um contato novo no WhatsApp e cada formulário de anúncio Meta preenchido viram **lead + negócio na primeira etapa do Comercial**, com as automações da etapa de entrada.

### 2. Acesso
- Menu "Integrações" (`/integracoes`) → grupo "Fontes de lead": cartões "WhatsApp (WAHA) — leads" e "Meta Lead Ads — leads".
- Todos os membros: ver status, erro recente e URLs.
- Só administradores: salvar e **"Desconectar"**. Para os demais o formulário fica desabilitado e aparece "Somente administradores da agência podem alterar esta configuração.".

### 3. Layout
Cada cartão: ícone, título, descrição, selo ("configurado", "não configurado" ou "com erro"), avisos de configuração do servidor (vermelhos), o último erro (se houver), o formulário, os botões ("Desconectar" à esquerda, só admin e só se configurado; "Salvar WhatsApp"/"Salvar Meta" à direita) e a URL para copiar. Celular: campos em uma coluna.
- WhatsApp: "A primeira mensagem de um contato novo vira lead + negócio na primeira etapa do Comercial."
- Meta: "Cada formulário de anúncio preenchido na Página vira lead + negócio na primeira etapa do Comercial."

### 4. Campos
| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "URL do WAHA" | URL | Sim | começa com http:// ou https://; até 500 | — | Exemplo "https://waha.suaagencia.com" |
| "Sessão" | texto | Sim | 1–100 | "default" | — |
| "API key" | senha | Não | até 500 | vazio | Placeholder "X-Api-Key do WAHA" ou "manter chave atual…" (vazio mantém a atual) |
| "ID da Página" | texto | Sim | só dígitos; até 64 | — | Exemplo "1234567890" |
| "Verify token" | senha | Sim na 1ª vez | mínimo 8, até 200 | — | Placeholder "mín. 8 caracteres" ou "manter atual…" |
| "Token de acesso da Página" | senha | Sim na 1ª vez | até 2000 | — | Placeholder "page access token" ou "manter atual…" |
| "App secret (opcional · <origem>)" | senha | Não | até 200 | — | Origem: "app secret próprio", "app secret da plataforma" ou "sem app secret"; placeholder "usa o da plataforma" ou "manter atual…" |

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Salvar WhatsApp" | Admin; URL válida, sessão, alguma alteração | Grava a configuração (API key cifrada); gera o token secreto da URL do webhook **uma vez** e o mantém nas edições seguintes | "WhatsApp salvo." + aparece "URL do webhook (cole no WAHA)" com botão de copiar ("Copiado.") | 409 `cofre_nao_configurado` (sem `IGIG_COFRE_KEY`); 403 admin; "Não foi possível salvar o WhatsApp." |
| "Salvar Meta" | Admin; ID numérico; verify token (≥8) e token da Página na 1ª vez | Grava (segredos cifrados); mostra "URL de callback (cole no app da Meta)" | "Meta Lead Ads salvo." | 422 "Informe o verify token (usado uma vez pela Meta para validar a URL)."; 422 "Informe o token de acesso da Página (lê os dados do lead)."; 409 "Esta Página já está conectada a outra organização."; 409 "Criptografia não configurada: defina IGIG_COFRE_KEY. …"; "Não foi possível salvar o Meta Lead Ads." |
| "Desconectar" (WhatsApp) → "Desconectar" | Admin; configurado | Confirmação "Desconectar o WhatsApp (WAHA)? A URL do webhook atual para de funcionar; mensagens novas deixam de virar leads até reconectar." Apaga a configuração inteira; reconectar gera **URL nova** | "WhatsApp desconectado." | 404 "WhatsApp (WAHA) não estava configurado."; "Não foi possível desconectar o WhatsApp." |
| "Desconectar" (Meta) → "Desconectar" | Admin; configurado | Confirmação "Desconectar o Meta Lead Ads? A Página fica livre para ser conectada a outra organização; leads novos de anúncios deixam de chegar até reconectar." Apaga a configuração | "Meta Lead Ads desconectado." | 404 "Meta Lead Ads não estava configurado."; "Não foi possível desconectar o Meta Lead Ads." |
| Mensagem chega no WAHA | Integração ativa | Token da URL conferido; assinatura HMAC conferida só se `IGIG_WAHA_WEBHOOK_HMAC_SECRET` existir; ignora mensagens da própria agência, eventos que não são mensagem recebida e **grupos**; se o chat já tem lead, nada é criado; senão cria lead (nome do contato, ou telefone, ou "Contato do WhatsApp"; origem "WhatsApp"; observações "Primeira mensagem: <texto>") + negócio + automações | — | Token/integração inválidos → 404 ao WAHA; falha → registrada no cartão "Falha ao criar lead do WhatsApp: …" (o WAHA recebe 200) |
| Verificação da Meta (handshake) | Verify token configurado | Responde o desafio só se o token bater com o de alguma organização | — | 403 "forbidden" |
| Lead chega da Meta | Página conectada | Assinatura `X-Hub-Signature-256` conferida com o app secret da agência (ou da plataforma); lead já importado é ignorado; busca os dados na Meta; cria lead (nome, e-mail, telefone, empresa; demais respostas em "Observações" e nas especificações; origem "Meta Ads") + negócio + automações | — | Sem app secret: 401 (recusado); falha: "Lead <id> não importado: …" no cartão (a Meta recebe 200) |

### 6. Estados
- Carregando: esqueleto no cartão.
- Não configurado: selo "não configurado"; WhatsApp mostra "Salve a configuração para gerar a URL do webhook.".
- Erro de leitura: "Não foi possível carregar o WhatsApp." / "Não foi possível carregar o Meta Lead Ads.".
- Com erro recente: selo "com erro" e o texto do erro em vermelho.
- Avisos do servidor: "Criptografia não configurada neste ambiente (IGIG_COFRE_KEY): a API key não pode ser salva." / "…: os tokens não podem ser salvos."; "Assinatura do webhook não configurada na plataforma (IGIG_WAHA_WEBHOOK_HMAC_SECRET): as mensagens recebidas serão aceitas sem verificar a assinatura (apenas o token da URL protege)."; "Sem app secret (nem da agência nem da plataforma, IGIG_META_APP_SECRET): as entregas da Meta não podem ter a assinatura verificada e serão recusadas."; "URL pública do IgIg não configurada (PRODUCT_URL_IGIG).".

### 7. Regras de negócio e por quê
1. Nenhuma resposta do servidor devolve segredos — só "configurado: sim/não".
2. Segredos são cifrados com `IGIG_COFRE_KEY`; sem a chave o servidor recusa em vez de gravar texto puro.
3. O token da URL do WAHA é mantido entre edições (mudar quebraria o que já foi colado no WAHA); desconectar apaga tudo e reconectar gera URL nova (sem "meio-desligado").
4. Só a **primeira** mensagem de um contato vira lead; grupos não são pessoas.
5. Uma Página Meta pertence a uma só organização (o webhook roteia pela Página).
6. Webhooks sempre respondem 200 aos fornecedores em caso de falha interna, para evitar reenvio em loop; o erro fica visível no cartão.
7. Todos os webhooks públicos: 60 requisições por minuto por IP.

### 8. Fluxo de dados
- Tela: `LeadSourceCards.tsx` → `useLeadSources` → GET/PUT/DELETE `/api/integracoes/leads/whatsapp` e `/api/integracoes/leads/meta` → tabela `igig.integracao` (canais `whatsapp` e `meta_leads`: `config`, `token_cifrado`, `ultimo_erro`, `ativo`).
- Entrada: POST `/api/webhooks/waha/{token}`; GET/POST `/api/webhooks/meta/leadgen` → `services/fontes_lead.py` → `igig.lead` (`waha_chat_id`/`meta_lead_id` evitam duplicar) + `comercial_funil.abrir_negocio` + `automacoes.ao_entrar_etapa`.

### 9. Dependências de configuração
| Variável | Efeito se faltar |
|---|---|
| `IGIG_COFRE_KEY` | Não salva API key/tokens (409) |
| `IGIG_WAHA_WEBHOOK_HMAC_SECRET` | Mensagens do WAHA aceitas sem verificar assinatura (só o token da URL protege) |
| `IGIG_META_APP_SECRET` (ou app secret da agência) | Entregas da Meta recusadas (401) |
| `PRODUCT_URL_IGIG` | A URL do webhook não pode ser montada |

### 10. Limitações conhecidas
- Só a primeira mensagem de um contato aparece (não há caixa de conversa).
- Não há "testar conexão".
- Integração Meta depende do app Meta configurado fora do IgIg (produto Webhooks → objeto Page → campo `leadgen`).

### 11. Perguntas frequentes
- **P: O WhatsApp não gera leads.** R: Veja se o cartão está "configurado", se a URL do webhook foi colada no WAHA e o erro mostrado. Só a primeira mensagem de um número novo (não de grupo) vira lead.
- **P: Leads do Meta não chegam.** R: É preciso app secret (da agência ou da plataforma), token da Página válido, URL de callback e verify token configurados no app da Meta, e a Página não pode estar ligada a outra organização.
- **P: Como desligo o WhatsApp?** R: "Desconectar" (admin). A URL antiga para de funcionar; ao reconectar, cole a URL nova no WAHA.
- **P: Mudei a API key; preciso trocar a URL no WAHA?** R: Não, a URL se mantém entre edições.
- **P: Por que o formulário está cinza?** R: Só administradores alteram.

---

## Página: Equipe

### 1. Propósito
Lista as **contas de login** da agência (membros da organização) e os convites pendentes; permite convidar e remover membros. Não confundir com Profissionais (Custos).

### 2. Acesso
- Rota: `/equipe`. Menu lateral: "Equipe" (13º, último item).
- Todos: ver a lista de membros.
- **"Convidar"**: Proprietário, Administrador **e Gerente** (e administrador da plataforma). Teto de papel: só o Proprietário convida como Proprietário; só Proprietário/Administrador convidam como "Administrador"; o Gerente convida como "Gerente", "Membro", "Visualizador", "Desenvolvedor", "Teste" ou "Corretor" — a lista "Papel" do formulário já mostra só o que a pessoa pode conceder (ver Campos).
- **"Ações"** (remover membro) e **"Convites pendentes"** (ver/cancelar): só Proprietário e Administrador.

### 3. Layout
- Cabeçalho "Equipe" — "N membro(s) na organização" ("Carregando…" / " · atualizando…"); botão "Convidar" (quem pode).
- Tabela: "Nome" (selo "Você" na sua linha; no celular o e-mail aparece embaixo do nome), "E-mail" (oculto no celular), "Papel", "Entrou em" (oculto em telas pequenas), "Ações" (só admin; botão "Remover", que não aparece para você mesmo nem para o Proprietário).
- Seção "Convites pendentes" (só admin) com contador: "E-mail", "Papel", "Expira em" (oculto no celular), "Ações" → "Cancelar".
- Janela "Convidar membro" (tela cheia no celular).
- Rótulos de papel: "Proprietário", "Administrador", "Gerente", "Membro", "Visualizador", "Desenvolvedor", "Teste", "Corretor".

### 4. Campos
| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "E-mail" | e-mail | Sim | — | vazio | Exemplo "colaborador@empresa.com" |
| "Papel" | lista | Sim | Administrador, Gerente, Membro, Visualizador, Desenvolvedor, Teste, Corretor | "Membro" | "Proprietário" não é oferecido. A lista muda conforme quem convida: um Gerente vê "Gerente, Membro, Visualizador, Desenvolvedor, Teste, Corretor" (sem "Administrador"); Proprietário/Administrador/admin da plataforma veem todas as sete — a mesma regra do servidor (403 "Sem permissao para convidar como <papel>"), só que aplicada também na tela |

### 5. Ações
| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Convidar" → "Enviar convite" ("Enviando…") | Proprietário/Admin/Gerente; e-mail | Cria convite (válido por **7 dias**, na organização de quem convida) e tenta enviar e-mail "Aceitar Convite" com o link `/accept-invite/<token>`, pelo provedor de e-mail da plataforma (Resend) | E-mail enviado: "Convite enviado com sucesso". E-mail NÃO enviado (ex.: provedor não configurado): "Convite criado, mas o e-mail não foi enviado — copie o link", com botão "Copiar link" (copia `/accept-invite/<token>` para a área de transferência) | "Erro ao enviar convite" + descrição: 403 "Sem permissao para convidar"; 403 "Sem permissao para convidar como <papel>" (papel acima do permitido para você); 400 "Papel invalido: <papel>"; 400 "Email e obrigatorio"; 409 "Ja existe um convite pendente para este email" |
| "Cancelar" (convite) | Proprietário/Admin | Cancela o convite | "Convite cancelado" | "Erro ao cancelar convite"; 403 "Sem permissao" |
| "Remover" → "Confirmar remoção" ("Removendo…") | Proprietário/Admin; não é você nem o Proprietário | Confirmação "Tem certeza que deseja remover <nome> da organização? Esta ação não pode ser desfeita." Remove o membro (só se ele for da sua organização) | "Membro removido" | "Erro ao remover membro" + descrição: 400 "Nao pode remover a si mesmo"; 403 "Sem permissao"; 403 "Somente o proprietario pode remover um proprietario"; 404 "Membro nao encontrado" |

### 6. Estados
- Carregando: esqueleto de tabela; "Carregando…".
- Vazio: "Nenhum membro encontrado"; "Nenhum convite pendente".
- Erro: "Não foi possível carregar a equipe."; "Não foi possível carregar os convites pendentes." (antes o erro era escondido).
- Atualizando: " · atualizando…".
- Aviso (convite criado, e-mail não enviado): "Convite criado, mas o e-mail não foi enviado — copie o link", com o motivo (ex.: "Servico de e-mail nao configurado") e um botão "Copiar link".

### 7. Regras de negócio e por quê
1. Três níveis: ver (todos), convidar (Proprietário/Administrador/Gerente, com teto de papel), gerenciar (Proprietário/Administrador).
2. O convite vale 7 dias e só pode ser aceito com o e-mail convidado.
3. Uma pessoa pertence a uma organização; se já está em outra, o aceite é recusado ("Voce ja pertence a outra organizacao. Entre em contato com o suporte para transferir sua conta.").
4. Ser membro não cria custo/hora: para aparecer como responsável/membro dos cards e ter custo nas horas, cadastre a pessoa como profissional em Custos e vincule o usuário.
5. **Ninguém convida acima de si.** O Gerente não cria Administradores e o Administrador não cria Proprietários. *Por quê:* sem o teto, qualquer Gerente poderia se promover indiretamente a administrador por meio de uma conta convidada.
6. **Papel e organização vêm da tabela confiável** (`public.noctus_users`), nunca do perfil editável do usuário; todo convite, listagem e remoção é filtrado pela organização de quem pede. *Por quê:* as rotas de equipe usam acesso de serviço, então esse filtro é a fronteira entre agências.

### 8. Fluxo de dados
`Equipe.tsx` → `useEquipe` (TanStack Query) → GET `/api/team`, GET `/api/team/invitations` (só se admin), POST `/api/team/invite` `{email, role}`, DELETE `/api/team/invitations/{id}`, DELETE `/api/team/{user_id}` → roteador de equipe do seed → `public.noctus_users` e `igig.invitations`. Aceite: página `/accept-invite/<token>` (ver Capítulo 0).

### 9. Dependências de configuração
- E-mail do convite: provedor **Resend** da plataforma, variável `RESEND_API_KEY`, remetente "NoctusAI <noreply@noctusai.com>"; o link usa o primeiro domínio de `CORS_ORIGINS`. **Sem `RESEND_API_KEY` (ou se o envio falhar), o convite é criado mas nenhum e-mail sai** — a tela avisa ("Convite criado, mas o e-mail não foi enviado — copie o link") em vez de dizer que o e-mail foi enviado, e oferece o botão "Copiar link" para compartilhar o link de aceite por outro meio.

### 10. Limitações conhecidas
- Não é possível mudar o papel de um membro existente nesta tela.
- As mensagens de erro vindas do servidor da plataforma estão sem acento ("Sem permissao", "Nao pode remover a si mesmo") — a mensagem de "e-mail não enviado" e a de validação de campos (ver Capítulo 0 § 12) já vêm com acento, em português.
- Depois de convidar, é preciso cadastrar a pessoa em Custos para ela aparecer como responsável.

### 11. Perguntas frequentes
- **P: Sou Gerente; posso convidar?** R: Sim, como Gerente, Membro, Visualizador, Desenvolvedor, Teste ou Corretor (não como Administrador). Ver e cancelar convites pendentes e remover membros é só para Proprietário/Administrador.
- **P: A pessoa diz que não recebeu o convite.** R: Confira o spam. Se o convite foi criado com o aviso "e-mail não foi enviado", use o botão "Copiar link" e mande o link de aceite por outro meio (WhatsApp, etc.) — não precisa cancelar e convidar de novo. Se o aviso não apareceu e mesmo assim não chegou, peça ao responsável técnico para verificar o provedor de e-mail da plataforma.
- **P: Quanto tempo vale o convite?** R: 7 dias.
- **P: A pessoa entrou mas não aparece como responsável dos cards.** R: Cadastre-a como profissional em Custos e vincule o usuário.
- **P: Posso mudar o papel de alguém?** R: Não por esta tela.
- **P: Por que não consigo remover o Proprietário?** R: O botão não é oferecido para o Proprietário nem para você mesmo.
- **P: Convidei e deu "Ja existe um convite pendente para este email".** R: Já há convite aberto; cancele-o em "Convites pendentes" ou peça para a pessoa usar o link já enviado.

---

---

# Capítulo 2 — Orçamentos, Produtos e Serviços, Custos, Contrato, E-mail

## IgIg — Guia: Orçamentos, Produtos e Serviços, Custos, PDF, E-mail, Contrato e Integrações → E-mail

> Manual de instruções e especificação por página. Público: (1) o assistente de ajuda do IgIg, que responde usuários a partir deste texto; (2) o dono do produto, como especificação durável. Tudo aqui foi conferido no código final (backend FastAPI + frontend React do IgIg). Rótulos, mensagens e avisos aparecem "entre aspas" exatamente como na tela ou no servidor. O que não pôde ser confirmado está marcado "(não confirmado no código)".

## Como as peças se encaixam (visão geral)

1. **Custos** guarda quanto custa uma hora de cada profissional (pela função ou por um valor próprio).
2. **Produtos e Serviços** é o catálogo: cada item tem preço base, **horas estimadas** por unidade e, opcionalmente, um **formato** de pauta.
3. **Orçamento** monta a proposta mensal de um **negócio** do Comercial com itens do catálogo. O servidor calcula os totais e a **margem estimada** = (total − horas × custo/hora médio da equipe) ÷ total.
4. O orçamento vira **PDF**, que é **enviado por e-mail** pelo SMTP (Integrações → E-mail). Com o **Gmail** conectado, a resposta do lead é detectada e gera notificação.
5. **Aceitar** fecha o negócio (etapa Fechado), cria ou reaproveita o **Cliente** e gera as **pautas** do calendário dos próximos 30 dias; um job diário mantém sempre 30 dias à frente.
6. Do orçamento aceito gera-se o **Contrato** (Digital ou Física). Contrato **Ativo** ⇒ cliente ativo ⇒ o fechamento mensal do Financeiro gera a fatura ("Retainer mensal" + excedentes).

Todas as telas exigem login e são isoladas por agência (organização): toda consulta filtra pela organização do usuário.

---

## Página: Orçamentos

### 1. Propósito
Criar, versionar, enviar e decidir (aceitar/recusar) as **propostas comerciais mensais** feitas a um lead. Um orçamento pertence sempre a exatamente **um negócio** do funil Comercial (e ao lead desse negócio). Um negócio pode ter várias **versões** (v1, v2, v3…), mas **só uma pode ser aceita**. A página reúne: a lista de orçamentos, o modal do orçamento (OrcamentoModal) com a calculadora ao vivo (painel "Totais"), versões, aceite/recusa e o botão "Gerar pautas".

Status possíveis:

| Status (rótulo) | Significado | Editável? |
|---|---|---|
| "Rascunho" | Criado, ainda não enviado. | Sim |
| "Enviado" | Enviado por e-mail pelo IgIg. | Sim |
| "Aceito" | O lead aceitou; o negócio foi fechado (ganho). | Não |
| "Recusado" | O lead recusou (motivo registrado). | Não |
| "Expirado" | A validade passou antes de uma decisão. | Não |
| "Substituído" | Uma versão mais nova (ou outra versão aceita) tomou o lugar dele. | Não |

### 2. Acesso
- **Rota**: `/orcamentos`. Link direto para abrir um orçamento no modal: `/orcamentos?id=<id do orçamento>` (é o link usado pela notificação de resposta por e-mail).
- **Menu lateral**: grupo "Principal", item **"Orçamentos"** — 4ª posição (Dashboard, Comercial, Clientes, **Orçamentos**, Produtos e Serviços, Esteira, Calendário, Distribuição, Financeiro, Integrações, Automações, Custos, Equipe). A visibilidade do item segue a configuração de páginas da plataforma (status da página "orcamentos": produção = todos; desenvolvimento = só dev/dono; desativado = ninguém).
- **Outras portas para o mesmo modal**: no Comercial (`/comercial`), o ícone "Gerar orçamento" no card do negócio; a aba "Orçamentos" do card do negócio (com "Gerar orçamento"); o seletor "Qual orçamento foi aceito?" ao arrastar um card para Fechado. Em Clientes (`/clientes`), aba "Orçamentos & Contratos" do card do cliente.
- **Quem vê / quem executa**: qualquer usuário autenticado da agência pode listar, criar, editar, criar versão, gerar PDF, enviar, aceitar, recusar, gerar pautas e gerar contrato. **Não há ação só-admin nesta página** (o código não checa papel nessas rotas).

### 3. Layout
**Lista (página)**
- Cabeçalho: título "Orçamentos", subtítulo "Propostas por lead — crie, envie e acompanhe o aceite." e botão **"Novo orçamento"**.
- Abas: **"Ativos"** (Rascunho + Enviado) · **"Aceitos"** (Aceito) · **"Recusados"** (Recusado + Expirado + Substituído — a aba "Recusados" também mostra expirados e substituídos).
- Filtros: busca "Buscar por título, lead ou empresa…" (procura no título, nome, empresa e e-mail do lead); seletor de status ("Todos os status" + os status da aba atual); seletor de lead ("Todos os leads" + empresa ou nome de cada lead); datas **"De"** e **"Até"** (pela **data de criação**, inclusive nas pontas); botão **"Limpar filtros"** (só aparece com filtro ativo).
- Aba, filtros e orçamento aberto ficam na URL: copiar o endereço reproduz a mesma visão para um colega.
- Cada card mostra: empresa ou nome do lead (ou o título); "{título} · v{versão}"; selo de status; **total/mês**; selo de margem (só se o total for maior que zero); linha "Criado em {data}" + " · válido até {data}" (se houver validade) + " · respondeu por e-mail" (se houve resposta detectada) ou " · enviado em {data}".
- Ordem: mais novos primeiro.
- **Celular (≤640px)**: cards em 1 coluna; filtros empilhados; "De"/"Até" lado a lado. **Computador**: cards em 2 colunas; busca, status e lead na mesma linha.

**Janela "Novo orçamento" (escolher negócio)**
- Título "Novo orçamento", descrição "Para qual negócio?", busca "Buscar lead ou empresa…".
- Lista só negócios **em aberto** (nem ganhos, nem perdidos): empresa/nome, etapa do funil e valor estimado.

**Modal do orçamento (OrcamentoModal)**
- Título: "Novo orçamento" (novo) ou "{título} · v{versão}". Descrição: "{empresa ou nome do lead} · {e-mail}" (ou, no novo, "Monte o escopo mensal — os totais são calculados ao vivo."). Selo de status ao lado do título.
- Corpo, de cima para baixo: caixas de confirmação (aceite / nova versão) quando abertas; mensagem de erro; "Motivo da recusa: …" (se recusado); link do PDF ("Visualizar PDF" ou "Abrir PDF", + " · enviado em {data}"); **"Título"** e **"Validade"**; seção **"Criação de conteúdo"** e seção **"Gestão de conta"** (cada uma com seus itens, subtotal "R$ X/mês" e o seletor "+ Adicionar item…"); seção de condições (**"Desconto (R$)"**, **"Revisões incluídas"**, **"Valor por excedente (R$)"**, **"Observações do escopo"**, **"Observações"**); painel **"Totais"**; painel **"Enviar por e-mail"** (quando aberto); painel **"Contrato"** (só em orçamento Aceito); seção **"E-mails"** (histórico).
- Cada linha de item: "Descrição do item", lixeira "Remover {nome}", "Preço unitário", chave "Recorrente"; se recorrente, os 7 botões de dia **S T Q Q S S D** (segunda a domingo) e o contador "/dia"; se não, o contador "/mês"; rodapé "{quantidade}/mês · R$ {subtotal}" — com "≈ " na frente enquanto o servidor não respondeu (estimativa local).
- Painel **"Totais"**: "Criação de conteúdo", "Gestão de conta", "Desconto" (se > 0, mostrado como "− R$ X"), **"Total mensal"**, selo de margem, linha "Custo estimado R$ X · Y h/mês" e, abaixo, os **alertas âmbar** do servidor (só durante a edição). Ícone girando = "Recalculando".
- Rodapé (botões): "Criar orçamento"/"Salvar", "Nova versão", "Gerar PDF", "Gerar pautas", "E-mail", e à direita os ícones X "Recusar orçamento" e ✓ "Aceitar orçamento". Linha de aviso "Salve as alterações para gerar PDF, enviar ou aceitar." quando há alterações não salvas.
- **Celular (<640px)**: o modal abre em **tela cheia**, cabeçalho e rodapé fixos, conteúdo rola; botões de dia e contadores com 40px (toque com o polegar). **Computador**: painel centralizado; botões de dia/contadores com 32px.

### 4. Campos

| Campo (rótulo exato) | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Título" | texto | Não | até 200 caracteres | "Proposta mensal" (novo) | Se ficar vazio na criação, o servidor usa "Proposta — {título do negócio}". |
| "Validade" | data | Não | — | hoje + 15 dias (fuso de São Paulo) | Vazio = nunca expira ("Sem validade — o orçamento não expira."). Vale até o fim do dia da validade. |
| "Descrição do item" | texto | Sim | 1 a 300 caracteres | nome do produto (catálogo) ou vazio (avulso) | Item avulso nasce vazio: até preencher, o painel Totais mostra erro de validação. |
| "Preço unitário" | número (R$) | Sim | ≥ 0 | preço base do produto; 0 no avulso | Copiado do catálogo no momento em que o item é adicionado. |
| "Recorrente" | chave | — | — | Ligada em Criação de conteúdo; desligada em Gestão de conta | Recorrente ⇒ dias da semana + quantidade por dia. |
| Dias da semana (S T Q Q S S D) | 7 botões | Sim, se recorrente | ao menos 1 dia | segunda a sexta (Criação); nenhum (Gestão) | Máscara: Seg=1, Ter=2, Qua=4, Qui=8, Sex=16, Sáb=32, Dom=64. |
| Quantidade "/dia" | contador | Sim, se recorrente | mínimo 1 (tela); máximo 50 (servidor) | 1 | — |
| Quantidade "/mês" | contador | Sim, se não recorrente | mínimo 1 (tela); até 10.000 (servidor) | 1 | — |
| "Desconto (R$)" | número | Não | ≥ 0 e ≤ subtotal bruto | 0 | Acima do subtotal: erro `desconto_invalido`. |
| "Revisões incluídas" | número inteiro | Não | 0 a 100 | 2 | Vai para o PDF e o contrato. |
| "Valor por excedente (R$)" | número | Não | ≥ 0 | 0 | Vira o `valor_excedente` do contrato (cobrança de peças além do pacote). |
| "Observações do escopo" | texto longo | Não | até 2.000 | vazio | Aparece no bloco "Escopo" do PDF. |
| "Observações" | texto longo | Não | até 4.000 | vazio | Aparece em "Observações" no PDF. |
| Itens por orçamento | — | — | até 200 | 0 | Qualquer campo desconhecido enviado ao servidor é rejeitado (422). |
| "Validade da nova versão" (caixa de Nova versão) | data | Não | — | mesma quantidade de dias de validade que o original tinha (da criação à validade), contada a partir de hoje; vazio se o original não tinha validade | Vazio = "Sem validade — a nova versão não expira." |
| Motivo (janela "Recusar orçamento") | texto | Sim | até 2.000 | vazio | Placeholder "Ex.: achou caro, fechou com outra agência…". |

### 5. Ações

| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Novo orçamento" → escolher negócio | Existir negócio em aberto | Abre o modal novo com os valores padrão (título "Proposta mensal", validade hoje+15, 2 revisões, excedente R$ 0, desconto R$ 0, sem itens). | — | Sem negócios: "Nenhum negócio em aberto. Crie um lead no Comercial primeiro." Falha: "Não foi possível carregar o funil." |
| "+ Adicionar item…" | Orçamento editável | Opções: produtos **ativos** da seção, "{nome} — R$ {preço}", ou "Item avulso (fora do catálogo)". Adiciona a linha. | — | "Carregando catálogo…" enquanto carrega. |
| Editar qualquer campo/item | Editável | Recalcula os totais no servidor ~0,4 s depois (nada é gravado). | — | 422 `recorrencia_invalida` "O item "{descrição}" é recorrente: escolha ao menos um dia da semana e a quantidade por dia." → marque ao menos um dia. 422 `desconto_invalido` "O desconto não pode ser maior que o subtotal do orçamento." → reduza. 422 `produto_invalido` "Um dos itens referencia um produto/serviço que não existe neste catálogo." → remova e readicione. Genérico: "Não foi possível calcular." |
| "Criar orçamento" | Negócio escolhido e em aberto | Grava como Rascunho; versão = maior versão do negócio + 1; lead e cliente copiados do negócio; totais recalculados e gravados. | "Orçamento v{N} criado." | Sem negócio: "Escolha o negócio deste orçamento." 409 `negocio_encerrado` "Este negócio está {ganho/perdido} — não aceita novos orçamentos." → abra um novo negócio no Comercial. Os 422 acima. Genérico: "Não foi possível salvar o orçamento." |
| "Salvar" | Rascunho/Enviado, com alteração | Substitui todos os itens, recalcula e grava os totais e **apaga a referência ao PDF** (o PDF anterior deixa de valer; o link some da tela). | "Orçamento salvo." | 409 `orcamento_bloqueado` "Não é possível editar: este orçamento está {status}." → use "Nova versão". 422 `sem_campos` "Nenhum campo para atualizar." Os 422 de cálculo. |
| "Nova versão" → caixa → "Confirmar nova versão" | Status Rascunho, Enviado, Recusado ou Expirado; sem alterações não salvas (o botão não aparece para Aceito nem Substituído) | Cria cópia (título, itens, desconto, limites, observações) em Rascunho com a validade escolhida; **recalcula totais e margem com o custo/hora ATUAL**. O original: se Rascunho/Enviado → "Substituído"; se Recusado/Expirado → **mantém** o status. O modal passa para a nova versão. | Original Rascunho/Enviado: caixa "Cria uma cópia como nova versão em Rascunho; a atual vira Substituído." e aviso "Versão {N} criada — a anterior foi substituída.". Original Recusado/Expirado: caixa "Cria uma cópia como nova versão em Rascunho; esta continua recusado." (ou "… continua expirado.") e aviso "Versão {N} criada — a anterior continua recusado." (ou "… continua expirado.") | 409 `orcamento_bloqueado` "Não é possível criar nova versão: este orçamento está {aceito/substituido}." Genérico: "Não foi possível criar a nova versão." |
| "Gerar PDF" | Orçamento salvo (qualquer status) | Ver "Funcionalidade: PDF do orçamento". | "PDF gerado." | "Não foi possível gerar o PDF." |
| "E-mail" | Rascunho/Enviado, salvo | Abre/fecha o painel "Enviar por e-mail". | — | Ver "Funcionalidade: Envio do orçamento por e-mail". |
| ✓ "Aceitar orçamento" → "Confirmar aceite" | Rascunho/Enviado, salvo. Caixa: "Aceitar move o negócio para **Fechado**, cria o cliente e gera as pautas do calendário. Confirmar?" | Fecha o negócio (etapa com papel Fechado), cria/reaproveita o Cliente, marca este Aceito e as outras versões abertas como Substituído, gera as pautas dos próximos 30 dias, dispara as automações de entrada em Fechado. O modal passa a mostrar o painel "Contrato". | "Orçamento aceito — cliente {nome} criado, {N} pautas no calendário." — "já existia" no lugar de "criado" quando o cliente foi reaproveitado; termina em "criado." / "já existia." quando este aceite não criou nenhuma pauta. {N} = pautas **criadas por este aceite** (não o total histórico do negócio). | 409 `negocio_ganho` "Este negócio já foi fechado com outro orçamento." 409 `orcamento_expirado` "A validade deste orçamento já passou." → Nova versão com nova validade. 409 `orcamento_ja_aceito` "Outro orçamento deste negócio já foi aceito — feche com ele." 409 `orcamento_invalido` "Este orçamento está {status} e não pode ser aceito." / "Este orçamento não pertence a este negócio." 409 `negocio_perdido` "Este negócio foi marcado como perdido." 409 `funil_sem_fechamento` "O funil comercial não tem etapa de fechamento ativa. Configure as etapas primeiro." → no Comercial, garanta uma etapa com papel Fechado. 409 `aceite_nao_aplicado` "O negócio não pôde ser fechado com este orçamento — verifique a etapa do card." → mova o card para outra etapa e aceite de novo. Genérico: "Não foi possível aceitar o orçamento." |
| X "Recusar orçamento" → "Recusar" | Rascunho/Enviado; motivo preenchido. Janela "Recusar orçamento" — "O motivo fica registrado para as estatísticas de perda." | Grava Recusado, data e motivo. **Não** marca o negócio como perdido. | "Orçamento recusado." | 422 `motivo_obrigatorio` "Informe o motivo da recusa." 409 `orcamento_bloqueado` "Não é possível recusar: este orçamento está {status}." Genérico: "Não foi possível recusar o orçamento." |
| "Gerar pautas" | Status Aceito | Completa as pautas dos próximos 30 dias a partir de hoje, sem duplicar nenhuma (idempotente) e sem recriar pautas automáticas que foram apagadas ou movidas de data. | "Calendário em dia — {N} pautas geradas ao todo." ou "Nenhuma pauta para gerar (nenhum item recorrente de Criação de conteúdo)." | 409 `orcamento_nao_aceito` "Só um orçamento aceito pode gerar pautas." Genérico: "Não foi possível gerar as pautas." |
| Tocar num card da lista | — | Abre o modal (põe `?id=` na URL). | — | "Não foi possível carregar o orçamento." |
| "Limpar filtros" | Algum filtro ativo | Limpa busca, status, lead e datas, mantendo a aba. | — | — |

### 6. Estados
- **Carregando**: lista com 4 blocos cinza (esqueleto); modal com 3 blocos cinza; painel Totais "Calculando…" antes da primeira resposta.
- **Vazio**: com filtros "Nenhum orçamento com esses filtros."; aba Ativos "Nenhum orçamento em aberto. Crie um pelo botão acima ou pelo card do lead no Comercial."; aba Aceitos "Nenhum orçamento aceito ainda."; aba Recusados "Nenhum orçamento recusado."; seção sem itens "Nenhum item nesta seção."; Totais sem itens "Adicione itens para calcular o orçamento."
- **Erro**: lista "Não foi possível carregar os orçamentos." (ou a mensagem do servidor); modal "Não foi possível carregar o orçamento."; histórico "Histórico de e-mails indisponível no momento."; ações: aviso vermelho no topo do modal com o texto do servidor.
- **Atualizando**: a lista fica levemente esmaecida sem sumir; no Totais o ícone girando ("Recalculando"); os números anteriores permanecem na tela até a nova resposta.

### 7. Regras de negócio e por quê
1. **Os totais são do servidor.** O navegador só envia itens (descrição, preço, recorrência, quantidade) e desconto; o servidor calcula quantidade mensal, subtotais, total, horas, custo e margem. Por quê: um cliente nunca pode dizer ao servidor quanto custa uma proposta.
2. **Mês = 4 semanas.** Item recorrente: quantidade mensal = (nº de dias marcados) × (quantidade por dia) × 4. Não recorrente: a quantidade informada. Subtotal = preço × quantidade mensal (arredondado em centavos).
3. **Fórmula completa:**
   ```
   subtotal_criacao = Σ subtotais da seção "Criação de conteúdo"
   subtotal_gestao  = Σ subtotais da seção "Gestão de conta"
   bruto            = subtotal_criacao + subtotal_gestao
   total_mensal     = bruto − desconto          (desconto > bruto ⇒ erro 422)
   horas_estimadas  = Σ (horas_estimadas do produto no catálogo × quantidade mensal)
   custo_estimado   = horas_estimadas × custo/hora médio da equipe
   margem_estimada  = (total_mensal − custo_estimado) ÷ total_mensal × 100   (%)
   ```
4. **Custo/hora médio da equipe** = média simples do custo/hora efetivo dos profissionais **ativos** em Custos. Quem não tem custo definido (sem função e sem valor próprio) é **excluído** da média (não entra como zero) e gera o alerta "{N} profissional(is) sem custo/hora definido — excluídos da média." A média não é ponderada por quem vai trabalhar no job.
5. **Margem pode ser negativa** (preço abaixo do custo) — nunca é travada em zero, para o dono ver o problema. Com total zero, a margem é indefinida e o selo mostra **"Margem indisponível"** (cinza, sem número).
6. **Selo de margem**: menor que 20% → "Margem baixa" (vermelho); de 20% a menos de 40% → "Margem média" (âmbar); 40% ou mais → "Margem saudável" (verde). Mostra o número com até 1 casa decimal (ex.: "Margem média · 32,5%").
7. **Margem sem base**: se **nenhum** profissional ativo tem custo/hora (nem próprio, nem herdado da função), o servidor **não calcula margem**: custo estimado R$ 0 e o selo mostra **"Margem indisponível"** (cinza, sem número) — nunca mais "Margem saudável · 100%". *Por quê:* 100% seria um número confiante sobre um cálculo sem base nenhuma. Durante a edição o painel Totais mostra o alerta âmbar "Nenhum profissional com custo/hora definido: custo e margem estimados ficam sem base e NÃO devem ser usados. Cadastre funções e custos antes de orçar." Em orçamento já salvo e não editável, o alerta **não** aparece (mostra os totais gravados).
8. **Itens avulsos e produtos com 0 horas** não somam horas → não somam custo → deixam a margem maior do que a real.
9. **As horas vêm do catálogo no momento do cálculo**; o preço é copiado no momento em que o item é adicionado. A margem é **gravada** ao criar/salvar/criar versão: mudar Custos ou horas depois não altera orçamentos salvos até serem salvos de novo (ou até uma nova versão, que recalcula).
10. **Validade**: vazia = nunca expira. Vencido = validade **anterior a hoje** no fuso America/São_Paulo. A expiração é gravada **na leitura** (ao listar, abrir, salvar, enviar, criar versão, recusar ou aceitar); não há rotina agendada para isso. Expirado não pode ser editado, enviado nem aceito; use "Nova versão".
11. **Só um aceito por negócio** (índice único no banco). Ao aceitar, as outras versões em Rascunho/Enviado do mesmo negócio viram "Substituído".
12. **Edição só em Rascunho/Enviado.** Enviar não trava a edição, mas salvar depois de enviar **anula o PDF** (o lead continua com o PDF antigo no e-mail).
13. **Nova versão** nunca apaga a estatística de perda: Recusado/Expirado mantêm o status no original; só um original em aberto vira Substituído. Aceito não gera versão (é o acordo fechado); Substituído também não (abra a versão mais nova).
14. **Recusar não perde o negócio**: para perder, use "Marcar como perdido" no card do negócio no Comercial. O servidor também aceita recusar um Expirado, mas a tela só oferece o X em Rascunho/Enviado.
15. **O aceite usa a mesma transição do funil** (mover o negócio para a etapa com papel "fechado", qualquer que seja o nome dela). Arrastar o card para Fechado no Comercial e o ✓ do modal fazem exatamente o mesmo, **inclusive gerar as pautas**. Re-aceitar um orçamento já aceito é inofensivo.
16. **Cliente no aceite**: procura o cliente ligado ao negócio, depois ao lead, depois um cliente com o mesmo lead; senão cria um novo com nome = empresa do lead (ou nome), e-mail, telefone, origem e status **"prospect"**. O lead passa a **"convertido"**. O cliente só fica "ativo" quando o contrato é ativado.
17. **Pautas geradas**: só itens de **Criação de conteúdo recorrentes**; uma pauta por dia marcado × quantidade por dia, nos 30 dias a partir do dia do aceite (inclusive); horário provisório **10:00** (Brasília); título = descrição do item, com "(1/2)", "(2/2)"… se a quantidade por dia for maior que 1; formato = o "Formato" do produto no catálogo (avulso ou produto sem formato ⇒ sem formato); marcadas como geradas automaticamente. Não cria tarefas na Esteira.
18. **Idempotência por dia**: para cada item, um dia que já tem pauta ligada ao item não recebe outra. Aceitar de novo ou clicar "Gerar pautas" várias vezes nunca duplica.
19. **Renovação automática**: um job diário às **06:45 (Brasília)** estende o calendário de todo orçamento Aceito para manter sempre 30 dias à frente, atravessando meses. Pausa quando o orçamento tem contrato(s) e nenhum está Ativo (ex.: só "Aguardando assinatura", "Rascunho" ou "Encerrado"); um aceito **sem contrato** continua sendo preenchido. O job só roda no ambiente implantado.
20. **Automações** configuradas para a entrada na etapa Fechado disparam no aceite pelo modal; cada entrada na etapa dispara uma única vez.

**Exemplo trabalhado — totais e margem (números conferidos pela fórmula do servidor)**

Equipe em Custos (todos ativos): Ana (função "Designer", R$ 40/h), Bruno (sem função, custo/hora próprio R$ 60/h), Carla (sem função e sem valor próprio).
- Custo/hora médio = (40 + 60) ÷ 2 = **R$ 50/h**. Carla é excluída e gera o alerta "1 profissional(is) sem custo/hora definido — excluídos da média."

| Item | Seção | Preço | Frequência | Qtd/mês | Subtotal | Horas no catálogo | Horas/mês |
|---|---|---|---|---|---|---|---|
| Post feed | Criação | R$ 80 | Seg, Qua, Sex × 1 | 3 × 1 × 4 = 12 | R$ 960,00 | 2,0 | 24 |
| Reels | Criação | R$ 250 | Ter, Qui × 1 | 2 × 1 × 4 = 8 | R$ 2.000,00 | 4,0 | 32 |
| Gestão de conteúdo | Gestão | R$ 500 | Mensal (não recorrente, 1/mês) | 1 | R$ 500,00 | 8,0 | 8 |

- Criação de conteúdo = 960 + 2.000 = **R$ 2.960,00**; Gestão de conta = **R$ 500,00**; bruto = R$ 3.460,00.
- Desconto R$ 160,00 → **Total mensal = R$ 3.300,00**.
- Horas = 24 + 32 + 8 = **64 h/mês**; custo = 64 × 50 = **R$ 3.200,00** → linha "Custo estimado R$ 3.200,00 · 64 h/mês".
- Margem = (3.300 − 3.200) ÷ 3.300 × 100 = 3,03% → selo **"Margem baixa · 3%"**.
- Para 40% de margem com esse custo: total ≥ 3.200 ÷ 0,6 ≈ **R$ 5.333,34**. Ex.: tirando o desconto e subindo o Reels para R$ 400: criação = 960 + 3.200 = 4.160; total = 4.660; margem = (4.660 − 3.200) ÷ 4.660 = 31,3% → "Margem média · 31,3%".
- Variações: (a) se Ana e Bruno fossem desativados, não há custo/hora → custo R$ 0 → "Margem indisponível" + alerta "Nenhum profissional com custo/hora definido…"; (b) trocando o Post feed por um item avulso de mesmo preço, as 24 h somem do custo (40 h × R$ 50 = R$ 2.000) e a margem sobe artificialmente de 3% para 39,4% ("Margem média · 39,4%").
- No **aceite** em segunda-feira 28/09/2026, a janela vai de 28/09 a 27/10 (30 dias): Post feed gera 13 pautas (12 Seg/Qua/Sex em 4 semanas + seg. 26/10) e Reels 9 (8 + ter. 27/10) → toast "…, 22 pautas no calendário." (30 dias ≠ as 4 semanas do preço). Essas 22 são peças **do plano**: nunca viram excedente no Financeiro, mesmo num mês "de 5 semanas".
- No **contrato** gerado desse orçamento: valor mensal R$ 3.300,00; posts/mês = 12 + 8 = **20** (só Criação recorrente; Gestão não conta); valor do excedente = o "Valor por excedente (R$)".

### 8. Fluxo de dados
| Ação | Hook | Endpoint | Serviço → tabelas / efeitos |
|---|---|---|---|
| Listar | `useOrcamentos` | `GET /api/orcamentos?aba=&status=&negocio_id=&lead_id=&cliente_id=&q=` | `orcamentos.listar` → `igig.orcamento` (+ `orcamento_item`, `lead`, `negocio`); grava `status='expirado'` nos vencidos. Filtro "De/Até" aplicado no navegador sobre `created_at`. |
| Abrir | `useOrcamento` | `GET /api/orcamentos/{id}` | `orcamentos.obter` (expira se vencido). |
| Cálculo ao vivo | `useCalculoOrcamento` (espera 400 ms) | `POST /api/orcamentos/calcular` | `normalizar_itens` + `calcular_totais`; lê `produto_servico.horas_estimadas` e o custo/hora médio (`funcao`, `profissional`); devolve `alertas`; **não grava**. |
| Criar | `useOrcamentoMutations().criar` | `POST /api/orcamentos` (201) | insere `orcamento` (rascunho, versão = máx+1) + `orcamento_item`. |
| Salvar | `.atualizar` | `PATCH /api/orcamentos/{id}` | apaga e reinsere itens, recalcula, zera `pdf_key`. |
| Nova versão | `.novaVersao` | `POST /api/orcamentos/{id}/nova-versao` `{validade}` (201) | origem aberta → `substituido`; insere cópia + itens com totais recalculados. `validade` omitida ⇒ servidor calcula os mesmos dias do original; `null` ⇒ sem validade. |
| Aceitar | `.aceitar` | `POST /api/orcamentos/{id}/aceitar` | `orcamentos.aceitar` → `comercial_funil.mover_negocio` → `_fechar` (orcamento, negocio, cliente, lead) → `pautas.gerar` (tabela `pauta`) → automações de entrada em Fechado. Resposta: orçamento, negócio, cliente, `cliente_criado`, `pautas_criadas` (total do negócio) e `pautas_novas` (criadas por esta chamada — é o número do aviso). Cada pauta gerada registra sua vaga em `pauta_slot_gerado`. |
| Recusar | `.recusar` | `POST /api/orcamentos/{id}/recusar` `{motivo}` | `status='recusado'`, `recusado_em`, `motivo_recusa`. |
| Gerar pautas | `.gerarPautas` | `POST /api/orcamentos/{id}/gerar-pautas` | `pautas.gerar` (consulta `pauta_slot_gerado` para saber quais item × dia já foram gerados) → `{pautas_criadas}` (total no calendário). |
| Job diário | — | agendador `igig_pautas_extensao` (06:45) | `pautas.estender_pendentes` → `pauta`. |
| PDF / E-mail / Contrato | ver as Funcionalidades | — | — |

Toda gravação atualiza a lista de orçamentos e o quadro do Comercial; o aceite atualiza também a lista de clientes.

### 9. Dependências de configuração
- **Custos** com funções/profissionais (senão margem sem base; alerta no Totais).
- **Horas estimadas** e **Formato** nos produtos do catálogo.
- **Etapa com papel Fechado** no funil comercial (senão `funil_sem_fechamento`).
- **Armazenamento privado** do IgIg (bucket `igig`) para PDFs.
- **SMTP** para enviar por e-mail; **Gmail + Pub/Sub** para detectar respostas.
- Agendador ligado no ambiente implantado para a renovação diária das pautas.

### 10. Limitações conhecidas
- O alerta de custo/hora incompleto só aparece durante a edição; orçamentos salvos exibem a margem gravada sem alerta — uma margem "100%" gravada **antes desta versão** pode ter sido calculada sem custos (salve de novo ou crie nova versão para recalcular).
- "já existia" × "criado" considera o cliente ligado ao negócio ou ao lead; um cliente reaproveitado apenas pela busca "mesmo lead" pode aparecer como "criado".
- Uma pauta automática apagada (ou movida de data) **não volta**: o registro `pauta_slot_gerado` guarda que aquela vaga já foi gerada. Se foi engano, crie a pauta à mão no Calendário — mas ela conta como peça avulsa para excedentes.
- Preço em 4 semanas × calendário real: meses com mais ocorrências dos dias marcados geram mais pautas que o pacote do contrato; essas peças do plano **não** geram excedente (ver Página Financeiro).
- A tela não oferece recusar um orçamento Expirado (o servidor permite).
- O filtro "De/Até" é aplicado no navegador, sobre a data de criação.

### 11. Perguntas frequentes
- **P: Por que a margem aparece "Margem indisponível"?** R: Nenhum profissional ativo tem custo/hora em Custos (ou o total é zero). Cadastre funções e profissionais com custo/hora em Custos e salve o orçamento de novo (ou crie nova versão, que recalcula).
- **P: Por que a margem está 100% (ou alta demais)?** R: Produtos com 0 horas ou itens avulsos não somam custo. Informe as horas no catálogo. Um orçamento salvo antes desta versão pode ter 100% gravado sem custo nenhum: salve de novo.
- **P: Apaguei uma pauta gerada pelo orçamento; ela volta?** R: Não. Pautas automáticas apagadas ou movidas de data nunca são recriadas pelo job diário nem por "Gerar pautas".
- **P: Por que não consigo editar?** R: Só Rascunho e Enviado são editáveis. Use "Nova versão" (não disponível para Aceito).
- **P: Meu orçamento virou "Expirado". E agora?** R: A validade passou. Toque "Nova versão", defina a nova validade e confirme.
- **P: Por que as outras versões viraram "Substituído"?** R: Só uma proposta vale por negócio: ao aceitar ou criar nova versão de uma aberta, as demais em aberto são substituídas.
- **P: Aceitei e não apareceram pautas.** R: Só itens de Criação de conteúdo **recorrentes** geram pautas. Se houver algum e mesmo assim faltar, abra o orçamento aceito e toque "Gerar pautas" — não duplica nada.
- **P: As pautas acabam depois de 30 dias?** R: Não: todo dia às 06:45 o IgIg estende para manter 30 dias à frente, enquanto não houver contrato parado (sem nenhum Ativo).
- **P: O painel Totais mostra erro ao adicionar item avulso.** R: A descrição é obrigatória; digite a descrição do item.
- **P: Liguei "Recorrente" num item de Gestão e deu erro.** R: Itens de Gestão não vêm com dias marcados; escolha ao menos um dia ou desligue "Recorrente".
- **P: Recusar o orçamento perde o negócio?** R: Não. Para perder o negócio use "Marcar como perdido" no card do negócio no Comercial.
- **P: O botão ✓ / E-mail / Gerar PDF está cinza.** R: Há alterações não salvas. Toque "Salvar" primeiro.

---

## Página: Produtos e Serviços

### 1. Propósito
O **catálogo** de onde saem os itens dos orçamentos. Cada item tem seção, nome, descrição, preço base, unidade, **horas estimadas** (alimentam custo e margem do orçamento) e **formato** (alimenta o formato das pautas geradas no aceite).

### 2. Acesso
- **Rota**: `/produtos-servicos`. **Menu lateral**: grupo "Principal", item **"Produtos e Serviços"** — 5ª posição. Visibilidade conforme o status da página "produtos_servicos".
- **Quem vê / executa**: qualquer usuário autenticado da agência lista, cria, edita, reativa e exclui. Nenhuma ação é só-admin (sem checagem de papel no código).

### 3. Layout
- Cabeçalho "Produtos e Serviços" — "O catálogo de onde saem os itens dos orçamentos." — e a chave **"Mostrar inativos"** (desligada = só ativos).
- Duas seções: "Criação de conteúdo" e "Gestão de conta", cada uma com botão **"Adicionar"**, ordenadas por ordem e nome.
- Cada item: nome (riscado se inativo); descrição (até 2 linhas); "R$ {preço} / {unidade}" + " · {horas} h" (se houver horas); selo **"Ativo"** (só no computador) ou botão **"Reativar"** (inativos); lápis "Editar {nome}"; lixeira "Excluir {nome}".
- Janela **"Novo item"** / **"Editar item"** com o formulário (tela cheia no celular <640px; painel estreito no computador).
- **Celular**: lista em cartões de largura total; o selo "Ativo" fica oculto; botões de 40px.

### 4. Campos

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Seção" | lista | Sim | Criação de conteúdo / Gestão de conta | a seção onde tocou "Adicionar" | Nome único por seção. |
| "Nome" | texto | Sim | 1 a 200; único na seção | vazio (ex.: "Ex.: Reels") | "Salvar" fica desabilitado sem nome. |
| "Descrição" | texto longo | Não | até 2.000 | vazio | — |
| "Preço base (R$)" | número | Sim | ≥ 0 | 0 | Copiado para o item no momento em que é adicionado ao orçamento. |
| "Unidade" | lista | — | unidade, mês, hora, post, vídeo (até 40 caracteres) | "mês" em Gestão; "unidade" em Criação | Só texto de exibição. |
| "Horas estimadas" | número | Não | ≥ 0, passo 0,25 | 0 | Horas por unidade; alimentam custo e margem. |
| "Ativo" | chave | — | — | ligado | Inativo não aparece no "+ Adicionar item…". |
| "Formato (opcional)" | lista | Não | "Sem formato", Feed, Carrossel, Reels, Stories, Artigo, Vídeo | "Sem formato" | Vira o formato das pautas geradas no aceite. |

Nota exibida no formulário: "As horas alimentam o custo estimado e a margem do orçamento (custo/hora médio da equipe). O formato alimenta as pautas geradas quando o orçamento é aceito."

### 5. Ações

| Ação | Pré-condições | O que acontece | Sucesso | Erros |
|---|---|---|---|---|
| "Adicionar" → "Salvar" | Nome preenchido | Cria o item. | "Item criado." | 409 `produto_duplicado` "Já existe "{nome}" nesta seção do catálogo." → use outro nome (o mesmo nome pode existir na outra seção). Genérico: "Não foi possível salvar." |
| Lápis "Editar {nome}" → "Salvar" | — | Atualiza o item. Não altera orçamentos existentes, exceto que as **horas** passam a valer no próximo recálculo/salvamento de qualquer orçamento que use o produto. | "Item atualizado." | 409 `produto_duplicado`; 422 `sem_campos` "Nenhum campo para atualizar."; 404 produto não encontrado. |
| "Reativar" | Item inativo (visível com "Mostrar inativos") | Liga "Ativo". | (sem aviso) | "Não foi possível reativar." |
| Lixeira "Excluir {nome}" | Confirmação do navegador "Excluir "{nome}"?" | Se o produto já foi usado em algum item de orçamento: **desativa** em vez de apagar. Senão, apaga de vez. | ""{nome}" está em orçamentos — foi desativado em vez de excluído." ou ""{nome}" excluído." | "Não foi possível excluir." |
| "Cancelar" | — | Fecha sem salvar. | — | — |

### 6. Estados
- **Carregando**: 3 blocos cinza.
- **Vazio**: por seção, "Nenhum item nesta seção."
- **Erro**: "Não foi possível carregar o catálogo." (ou a mensagem do servidor).
- **Atualizando**: seções levemente esmaecidas; conteúdo permanece.

### 7. Regras de negócio e por quê
1. **Catálogo inicial automático**: na primeira leitura do catálogo (esta página ou o modal de orçamento), se a agência não tem **nenhum** item (nem inativo), o sistema cria 6 exemplos: Gestão de conta — "Gestão de conteúdo" (R$ 500/mês, 8 h) e "Gestão de DMs" (R$ 500/mês, 10 h); Criação de conteúdo — "Post feed" (R$ 80/post, 2 h, Feed), "Carrossel" (R$ 150/post, 3,5 h, Carrossel), "Reels" (R$ 250/vídeo, 4 h, Reels), "Stories" (R$ 40/story, 0,5 h, Stories). Se a agência apagar/desativar os exemplos, eles **não voltam** (foi uma escolha dela).
2. **Nome único por seção** (índice organização + seção + nome).
3. **Exclusão protege o histórico**: produto usado em orçamento é só desativado, para não perder a origem das horas nas propostas já enviadas.
4. **Inativos** somem do seletor do orçamento, mas continuam nos orçamentos já feitos e suas horas continuam contando no recálculo desses orçamentos.
5. **Preço copiado, horas lidas ao vivo**: mudar o preço no catálogo não muda itens já adicionados; mudar as horas afeta o próximo cálculo/salvamento.
6. **Formato**: só faz sentido para Criação de conteúdo recorrente (só esses geram pautas).

### 8. Fluxo de dados
`useProdutosServicos` → `GET /api/produtos-servicos?secao=&ativo=` (semeia se vazio) · `useProdutoServicoMutations` → `POST /api/produtos-servicos` (201) · `PATCH /api/produtos-servicos/{id}` · `DELETE /api/produtos-servicos/{id}` → `{id, removido, desativado}` → `produtos.*` → tabela `igig.produto_servico` (`secao, nome, descricao, preco_base, unidade, horas_estimadas, formato, ativo, ordem`). O modal de orçamento lê o mesmo cache: uma edição aqui aparece lá sem recarregar.

### 9. Dependências de configuração
— (nenhuma variável de ambiente; depende só do banco).

### 10. Limitações conhecidas
- Não há reordenação pela tela (a ordem é a de criação).
- "Reativar" não mostra aviso de sucesso.
- Itens criados antes do campo "Formato" existir ficam "Sem formato" até alguém editá-los.

### 11. Perguntas frequentes
- **P: Excluí um produto e ele continua lá.** R: Ele estava em orçamentos e foi desativado. Ligue "Mostrar inativos" para vê-lo.
- **P: Mudei o preço e o orçamento não mudou.** R: O preço é copiado ao adicionar o item. Edite o "Preço unitário" no orçamento ou remova e adicione o item de novo.
- **P: Para que servem as horas?** R: Horas × quantidade × custo/hora médio = custo estimado, que define a margem.
- **P: Por que as pautas do Reels vieram sem formato?** R: O produto está "Sem formato". Edite o item e escolha o "Formato (opcional)"; vale para as próximas pautas geradas.
- **P: Posso ter "Reels" nas duas seções?** R: Sim; o nome é único só dentro da seção.
- **P: Apaguei os exemplos iniciais; eles voltam?** R: Não.

---

## Página: Custos

### 1. Propósito
A **tabela de custo/hora** da agência: funções (com custo/hora padrão) e profissionais. Alimenta a **margem estimada dos orçamentos**, o **BI de eficiência** (custo real dos jobs) e o **DRE** do Financeiro. Sem ela, esses números saem zerados ou sem base.

### 2. Acesso
- **Rota**: `/custos`. **Menu lateral**: grupo "Principal", item **"Custos"** — 12ª posição (penúltimo, antes de "Equipe"). Visibilidade conforme o status da página "custos".
- **Ver**: qualquer usuário autenticado da agência.
- **Só-admin (dono ou admin da agência, ou admin da plataforma)**: criar, editar e remover função; criar, editar (nome, função, custo próprio, vínculo de usuário, ativar/desativar) e remover profissional. Membros comuns (inclui "manager") só leem: para eles a tela **esconde** os formulários "Adicionar função"/"Adicionar profissional", os lápis, as lixeiras, "Desativar"/"Ativar" e o seletor de usuário (que vira só o nome do usuário vinculado, ou "Sem vínculo"). Se uma escrita chegar ao servidor vinda de não-admin, a resposta é 403 "Apenas administradores da organização podem realizar esta ação.".

### 3. Layout
- Cabeçalho "Custos" — "Funções e profissionais. Esta é a tabela de custo/hora que alimenta a calculadora de escopo, o BI de eficiência e o DRE."
- Avisos vermelhos no topo (quando se aplicam):
  - "1 profissional está sem custo/hora definido: as horas dele não entram no custo real e a margem fica superestimada." (ou "N profissionais estão sem custo/hora definido: as horas deles…");
  - "1 profissional não está vinculado a um usuário: as horas que ele apontar na esteira não viram custo, mesmo com custo/hora definido." (ou "N profissionais não estão vinculados…").
- Seção **"Funções"**: formulário (só admin: "Nome da função", "Custo/hora (R$)", botão "Adicionar função") e lista (nome, "R$ X/h", lápis "Editar {nome}", lixeira "Remover {nome}"). Edição em linha: "Nome", "R$/hora", "Salvar", X "Cancelar edição".
- Seção **"Profissionais"**: formulário (só admin: "Nome", "Função", "Usuário", "Custo/hora próprio", botão "Adicionar profissional") e lista: nome; linha "{função ou "Sem função"}" + " · custo próprio" (se tem valor próprio) + " · horas não contabilizadas" (se sem usuário); custo efetivo "R$ X/h" ou selo **"Sem custo/hora"**; seletor "Usuário de {nome}" (muda na hora; para não-admin, só o nome do usuário ou "Sem vínculo"); e, só para admin, lápis "Editar {nome}", botão "Desativar"/"Ativar" e lixeira "Remover {nome}". Edição em linha: "Nome", "Função", "Custo/hora próprio", "Salvar", X "Cancelar edição". A lista mostra ativos e inativos.
- **Celular**: formulários quebram em várias linhas; campos de edição em linha com 44px de altura. **Computador**: formulários numa linha.

### 4. Campos

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Nome da função" | texto | Sim | 1 a 120; único por agência | vazio ("Designer sênior") | — |
| "Custo/hora (R$)" (função) | número | Não | ≥ 0 | vazio = 0 | Placeholder "85,00". |
| "R$/hora" (edição da função) | texto decimal | Sim | ≥ 0; aceita vírgula | valor atual | Valor inválido: o formulário não envia. |
| "Nome" (profissional) | texto | Sim | 1 a 200 | vazio ("Ana Souza") | — |
| "Função" | lista | Não | "Sem função" ou uma função | "Sem função" | — |
| "Usuário" | lista | Não | "Sem vínculo" ou membro da equipe | "Sem vínculo" | Necessário para as horas da Esteira virarem custo no BI/DRE e para notificar o responsável do negócio. |
| "Custo/hora próprio" | número | Não | ≥ 0 | vazio = herda da função | Vazio ≠ 0: vazio herda; 0 é custo real. |

### 5. Ações

| Ação | Pré-condições | O que acontece | Sucesso | Erros |
|---|---|---|---|---|
| "Adicionar função" | Admin; nome preenchido | Cria a função. | (sem aviso; limpa o formulário) | Mensagem real do servidor abaixo do formulário, ex.: 409 `funcao_duplicada` 'Já existe uma função chamada "{nome}".'; sem texto do servidor: "Não foi possível criar a função." |
| Lápis → "Salvar" (função) | Admin | Atualiza nome/custo; todos os profissionais que herdam passam a usar o novo valor. | "Função atualizada — custos e DRE passam a usar o novo valor" | Aviso com a mensagem do servidor (sem o prefixo "[código]"), ex.: 409 `funcao_duplicada`; 404 "Função não encontrada"; sem texto do servidor: "Não foi possível salvar a função." |
| Lixeira "Remover {nome}" (função) | Admin; confirma "Remover a função "{nome}"? Os profissionais vinculados ficam sem função." | Apaga a função; profissionais ficam sem função (quem não tinha custo próprio vira "Sem custo/hora"). | (lista atualiza) | Aviso com a mensagem do servidor ou "Não foi possível remover a função." |
| "Adicionar profissional" | Admin; nome preenchido | Cria o profissional (ativo). | (limpa o formulário) | Mensagem real do servidor abaixo do formulário, ou "Não foi possível criar o profissional." |
| Lápis → "Salvar" (profissional) | Admin | Atualiza nome, função e custo próprio. | (lista atualiza) | Aviso com a mensagem do servidor ou "Não foi possível salvar o profissional." |
| Seletor "Usuário de {nome}" | Admin | Troca o vínculo na hora. | — | Aviso com a mensagem do servidor ou "Não foi possível salvar o profissional." |
| "Desativar" / "Ativar" | Admin | Tira/põe o profissional na média de custo/hora dos orçamentos. | — | Aviso com a mensagem do servidor ou "Não foi possível salvar o profissional." |
| Lixeira "Remover {nome}" (profissional) | Admin; confirma "Remover o profissional "{nome}"?" | Apaga o profissional. | — | Aviso com a mensagem do servidor ou "Não foi possível remover o profissional." |

### 6. Estados
- **Carregando**: tabela-esqueleto de 3 linhas em cada seção.
- **Vazio**: funções "Nenhuma função cadastrada. Sem ela, o orçamento não consegue estimar custo nem margem."; profissionais "Nenhum profissional cadastrado. As horas apontadas na esteira só viram custo real depois disso."
- **Erro**: "Não foi possível carregar as funções." / "Não foi possível carregar os profissionais."
- **Atualizando**: as listas permanecem na tela enquanto recarregam; qualquer gravação recarrega as duas listas juntas.

### 7. Regras de negócio e por quê
1. **Custo/hora efetivo**: tem "Custo/hora próprio" preenchido (inclusive 0) → usa ele; senão, tem função → custo da função; senão → **indefinido** ("Sem custo/hora").
2. **Vazio ≠ 0**: vazio = herdar; 0 = custo real (ex.: estagiário não remunerado).
3. **Indefinido nunca vira zero**: nos orçamentos a pessoa sai da média (com alerta) — e, se **ninguém** tem custo/hora, a margem do orçamento fica "Margem indisponível"; no BI/DRE as horas dela aparecem sem custo e a margem é sinalizada como superestimada.
4. **Remover função não apaga profissionais**: eles ficam sem função.
5. **Desativar** tira o profissional da média de custo/hora dos orçamentos.
6. **Vínculo com usuário**: o BI e o DRE convertem horas apontadas na Esteira em custo pelo usuário que apontou; sem vínculo, as horas não viram custo. Também define quem é notificado quando o lead responde (responsável do negócio). Na margem do orçamento o vínculo **não** importa.
7. **Mudanças valem para os próximos cálculos**: orçamentos já salvos mantêm a margem gravada até serem salvos de novo ou ganharem nova versão.
8. **Escrita só para admin** (dono/admin): a tabela de custos define a margem de toda a agência. A tela só mostra os controles a quem o servidor permitiria.
9. **Custo real em segundos**: o BI, a DRE e o relatório financeiro somam o tempo apontado **em segundos** antes de converter em horas × custo/hora — três sessões de 40 segundos custam o equivalente a 2 minutos, não R$ 0,00.

### 8. Fluxo de dados
`useFuncoes` / `useProfissionais` / `useMembrosEquipe` → `GET /api/custos/funcoes` · `POST /api/custos/funcoes` · `PATCH /api/custos/funcoes/{id}` · `DELETE /api/custos/funcoes/{id}` · `GET /api/custos/profissionais?apenas_ativos=` · `POST /api/custos/profissionais` · `PATCH /api/custos/profissionais/{id}` · `DELETE /api/custos/profissionais/{id}` · `GET /api/team` (membros para o vínculo). Tabelas `igig.funcao` (nome único por agência, `custo_hora_padrao`) e `igig.profissional` (`funcao_id` com "ON DELETE SET NULL", `custo_hora_override`, `usuario_id`, `ativo`). O custo efetivo é calculado na leitura (não é gravado). Efeitos: margem dos orçamentos (`OrcamentoService.custo_hora_medio`), BI e DRE.

### 9. Dependências de configuração
— (nenhuma variável de ambiente). Depende de membros cadastrados em Equipe para o vínculo "Usuário".

### 10. Limitações conhecidas
- Não-admin vê a tabela sem controles, mas nenhum aviso explicando por quê (ao contrário de Integrações → E-mail).
- O cabeçalho ainda fala em "calculadora de escopo"; hoje o orçamento não sugere preço, mostra custo e margem.

### 11. Perguntas frequentes
- **P: Por que aparece "Sem custo/hora"?** R: O profissional não tem função nem custo próprio. Edite e escolha uma função ou informe o custo próprio.
- **P: Deixo o custo próprio em 0 ou vazio?** R: Vazio para herdar da função; 0 só se a hora dele realmente não custa nada.
- **P: Mudei o custo e o orçamento não mudou.** R: Orçamentos salvos guardam a margem. Abra, altere algo e salve, ou crie "Nova versão".
- **P: Não vejo os botões de adicionar/editar.** R: Só Proprietário ou Administrador da agência altera Custos; para os demais a tabela é só leitura. Peça a um administrador.
- **P: Para que vincular o usuário?** R: Para as horas apontadas na Esteira virarem custo no BI/DRE e para esse profissional ser avisado quando o lead responder a um orçamento do negócio dele.
- **P: Desativar e remover dão no mesmo?** R: Não. Desativar mantém o cadastro e só tira da média; remover apaga.

---

## Funcionalidade: PDF do orçamento

### 1. Propósito
Gerar o documento **"Proposta comercial"** que vai para o lead, a partir do orçamento **salvo**.

### 2. Acesso
Modal do orçamento → botão **"Gerar PDF"**. Depois aparece o link **"Visualizar PDF"** (link recém-gerado) ou **"Abrir PDF"** (quando o orçamento já tinha PDF salvo), com " · enviado em {data}" se já foi enviado. Qualquer usuário autenticado da agência.

### 3. Layout (conteúdo do PDF)
- Cabeçalho com o **nome da agência** (nome da organização; sem nome cadastrado, "IgIg") e "Proposta comercial"; à direita "Proposta **v{N}**", "Emitida em {data}", "Válida até {data}" ou "Sem prazo de validade".
- Título do orçamento e cartão **"Para"** com nome, empresa e e-mail do lead.
- Uma tabela por seção com itens ("Criação de conteúdo", "Gestão de conta"): colunas **Item, Frequência, Qtd/mês, Unitário, Subtotal** e linha "Subtotal — {seção}". Frequência: "Seg, Qua, Sex × 1" (recorrente) ou "Mensal". Sem itens: "Nenhum item neste orçamento."
- Bloco **"Escopo"**: "{N} rodada(s) de revisão incluída(s) por peça." e "Peças ou revisões além do escopo: R$ X por unidade." + observações do escopo.
- Bloco **"Investimento mensal"**: subtotais, "Desconto" (se houver) e **"Total mensal"**.
- **"Observações"** (se houver). Rodapé "{agência} · Proposta comercial · página X de Y".
- **Não mostra custo, horas nem margem** (são internos). Layout de celular × computador: — (é um PDF).

### 4. Campos
— (não há campos; o conteúdo vem do orçamento salvo).

### 5. Ações

| Ação | Pré-condições | O que acontece | Sucesso | Erros |
|---|---|---|---|---|
| "Gerar PDF" | Orçamento salvo (sem alterações pendentes), qualquer status | Renderiza, grava no armazenamento privado e mostra "Visualizar PDF". Gerar de novo a mesma versão sobrescreve o arquivo. | "PDF gerado." | "Não foi possível gerar o PDF." (ou o texto do servidor). |
| "Visualizar PDF" | PDF recém-gerado | Abre em nova aba. O link vale **10 minutos**. | — | Link expirado: reabra o modal e use "Abrir PDF". |
| "Abrir PDF" | Orçamento com PDF salvo | Pede um link novo (10 min) e abre em nova aba. | — | 409 `pdf_nao_gerado` "O PDF deste orçamento ainda não foi gerado." → "Gerar PDF". Genérico: "Não foi possível abrir o PDF." |

### 6. Estados
- **Carregando**: botão "Gerando…".
- **Vazio**: sem PDF, nenhum link aparece.
- **Erro**: aviso vermelho no topo do modal.
- **Atualizando**: —.

### 7. Regras de negócio e por quê
1. Só gera com o formulário salvo — um PDF nunca pode mostrar algo diferente do que está gravado.
2. **Salvar qualquer alteração anula o PDF** (o link some); gere de novo antes de enviar.
3. Um arquivo por versão: `v{N}.pdf`; regerar a mesma versão sobrescreve.
4. Links curtos (10 min) porque o armazenamento é privado.

### 8. Fluxo de dados
`useOrcamentoMutations().gerarPdf` → `POST /api/orcamentos/{id}/pdf` → `documentos_pdf.renderizar_orcamento_pdf` (HTML → PDF, xhtml2pdf) → armazenamento `{org_id}/orcamentos/{id}/v{versao}.pdf` no bucket do IgIg → `orcamento.pdf_key` → URL assinada de 600 s. `urlPdf` → `GET /api/orcamentos/{id}/pdf` → nova URL assinada.

### 9. Dependências de configuração
Armazenamento privado configurado (`IGIG_STORAGE_BUCKET`, padrão "igig"). Nome da organização cadastrado (senão o PDF sai com "IgIg").

### 10. Limitações conhecidas
- O arquivo antigo não é apagado quando um salvamento anula o PDF (só a referência some).
- O link "Visualizar PDF" expira em 10 minutos.

### 11. Perguntas frequentes
- **P: O PDF mostra a margem?** R: Não; custo, horas e margem são internos.
- **P: Editei o orçamento e o link do PDF sumiu.** R: Salvar anula o PDF. Toque "Gerar PDF" de novo.
- **P: O link do PDF não abre mais.** R: Expirou (10 min). Reabra o orçamento e toque "Abrir PDF".
- **P: Por que o PDF sai com "IgIg" no topo?** R: A organização não tem nome cadastrado.
- **P: Posso gerar PDF de um orçamento aceito?** R: Sim, em qualquer status.

---

## Funcionalidade: Envio do orçamento por e-mail + observação de respostas (Gmail)

### 1. Propósito
Enviar o PDF do orçamento **anexado** ao lead pelo SMTP da agência (ou, na falta, pelo SMTP da plataforma), registrar o envio no histórico, marcar o orçamento como "Enviado" e — com o Gmail conectado — **detectar a resposta do lead** e avisar a equipe.

### 2. Acesso
Modal do orçamento → botão **"E-mail"** → painel **"Enviar por e-mail"** (só em Rascunho/Enviado e com o formulário salvo). Histórico: seção **"E-mails"** no fim do modal. Qualquer usuário autenticado da agência envia. As notificações de resposta chegam pelo sino do app e por e-mail.

### 3. Layout
- Painel "Enviar por e-mail": aviso "Gere o PDF antes de enviar — ele vai anexado." (sem PDF); campos "Para", "CC (opcional)", "Assunto", "Mensagem (opcional)"; botão **"Enviar"**.
- Seção "E-mails": cada linha com selo "Enviado" ou "Resposta", data, assunto e trecho. Sem nenhum e-mail, a seção não aparece.
- Celular: painel em largura total dentro do modal em tela cheia.

### 4. Campos

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Para" | texto | Não | e-mails válidos; vários separados por vírgula ou ponto e vírgula | e-mail do lead | Vazio = e-mail do lead. Placeholder "email@cliente.com". |
| "CC (opcional)" | texto | Não | e-mails válidos, separados por vírgula/ponto e vírgula | vazio | Placeholder "copia1@agencia.com, copia2@agencia.com". |
| "Assunto" | texto | Não | até 300 | "Proposta: {título} (v{N})" | Vazio: o servidor usa o mesmo padrão. |
| "Mensagem (opcional)" | texto longo | Não | até 10.000 | vazio | Vazia: "Segue em anexo a nossa proposta. Qualquer dúvida, é só responder a este e-mail." |

### 5. Ações

| Ação | Pré-condições | O que acontece | Sucesso | Erros |
|---|---|---|---|---|
| "Enviar" | Rascunho/Enviado, salvo, com PDF gerado, SMTP disponível | Envia com o PDF anexado (`orcamento-{título em minúsculas com hífens, até 40 caracteres}-v{N}.pdf`); grava linha "Enviado" no histórico; orçamento → "Enviado" com data e Message-ID. Pode enviar várias vezes (uma linha por envio). | "Orçamento enviado por e-mail." (o painel fecha) | 409 `orcamento_bloqueado` "Orçamento {status} não pode ser enviado." (inclui vencido: é marcado Expirado antes) → Nova versão. 409 `pdf_nao_gerado` "Gere o PDF do orçamento antes de enviar." / "O PDF do orçamento não foi encontrado no armazenamento — gere-o novamente." 422 `email_destinatario_ausente` "O lead não tem e-mail cadastrado — informe o destinatário." 422 endereço inválido (validação "e-mail inválido: …"). 409 `smtp_nao_configurado` "Nenhum SMTP configurado: cadastre uma conta em Integrações → E-mail." / "SMTP incompleto: {detalhe}". 409 `cofre_nao_configurado` "Criptografia não configurada: defina IGIG_COFRE_KEY. Nenhuma credencial é gravada em texto puro." 502 `envio_falhou` "Falha ao enviar o e-mail: {erro}" → confira o SMTP em Integrações (use "Testar envio"). 404 `orcamento_nao_encontrado` "Orçamento não encontrado." Genérico: "Não foi possível enviar." |

**O que o lead recebe**: corpo "Olá, {nome do lead}!" (ou "Olá!"), a mensagem, um quadro com o título, "Investimento mensal: R$ X", "Válida até {data}" (se houver) e "Proposta completa no PDF em anexo.", e "Atenciosamente, {nome do remetente ou e-mail}" (versão em texto puro equivalente). Remetente = "Remetente (e-mail)/(nome)" do SMTP. **Responder para (Reply-To)**: se a agência conectou um Gmail diferente do e-mail remetente, aponta para esse Gmail — a caixa monitorada.

### 6. Estados
- **Carregando**: botão "Enviando…".
- **Vazio**: sem PDF, aviso "Gere o PDF antes de enviar — ele vai anexado." e "Enviar" desabilitado; histórico vazio = seção oculta.
- **Erro**: texto do servidor em vermelho no painel; histórico "Histórico de e-mails indisponível no momento."
- **Atualizando**: —.

### 7. Regras de negócio e por quê
1. **Nunca há envio "de mentira"**: sem SMTP real o envio é recusado; o orçamento nunca vira "Enviado" sem ter saído.
2. **Prioridade de SMTP**: da agência (ativo) → da plataforma (registrado em log) → recusa 409.
3. **Vencido não sai**: validade passada ⇒ marcado Expirado antes da checagem ⇒ recusado.
4. **Detecção de resposta**: cada envio grava o Message-ID; o Gmail avisa o Pub/Sub do Google a cada mudança na caixa; o IgIg lê o histórico da INBOX e compara `In-Reply-To`/`References` (e a conversa) com os e-mails enviados. A resposta precisa estar na mesma conversa do e-mail enviado pelo IgIg.
5. **Quando é resposta**: grava linha "Resposta" no histórico; preenche "respondido" na primeira vez (o card da lista passa a mostrar "respondeu por e-mail"); **não muda o status** (continua Enviado); uma mesma resposta nunca é registrada duas vezes.
6. **Quem é avisado** (sino **e** e-mail, sem duplicar): todos os **Proprietários e Administradores** da agência **e** o usuário vinculado ao **responsável do negócio** (profissional em Custos com "Usuário"). Sino: título "Resposta ao orçamento: {título}", mensagem "{remetente}: {trecho}", link `/orcamentos?id=…`. E-mail (pelo SMTP): "{remetente} respondeu ao orçamento "{título}": … Abra no IgIg: /orcamentos?id=…". Sem SMTP, só o e-mail não sai (fica em log).
7. **Monitoramento expira** em até 7 dias; um job diário às **06:15 (Brasília)** renova todos (só no ambiente implantado).

### 8. Fluxo de dados
`EnviarEmailPanel` → `useOrcamentoMutations().enviar` → `POST /api/orcamentos/{id}/enviar {para?, cc?, assunto?, mensagem?}` → `orcamento_email.enviar_orcamento` → `email_config.resolver_smtp` → lê o PDF do armazenamento → envia → insere `igig.orcamento_email` (direction `out`) → atualiza `orcamento` (`status`, `enviado_em`, `email_message_id`) → responde o orçamento completo. Histórico: `useOrcamentoEmails` → `GET /api/orcamentos/{id}/emails`. Respostas: Pub/Sub → `POST /api/webhooks/gmail/push` (token OIDC do Google; 503 sem configuração, 401 token inválido, 400 envelope inválido) → `orcamento_email.processar_notificacao` → `orcamento_email` (direction `in`), `orcamento.respondido_em`, `public.notifications` (tipo `orcamento_respondido`) + e-mail. Renovação: agendador `igig_gmail_watch_renovar` (06:15). Cursor em `igig.gmail_watch`.

### 9. Dependências de configuração
SMTP (Integrações → E-mail ou SMTP da plataforma); `IGIG_COFRE_KEY` (para ler a senha do SMTP da agência); armazenamento do PDF. Para respostas: Gmail conectado + `GOOGLE_OAUTH_CLIENT_ID/SECRET` + `GMAIL_PUSH_GCP_PROJECT`, `GMAIL_PUSH_TOPIC`, `GMAIL_PUSH_AUDIENCE`, `GMAIL_PUSH_SERVICE_ACCOUNT`. Detalhes em "Funcionalidade: Integrações → E-mail".

### 10. Limitações conhecidas
- O e-mail aos Proprietários/Administradores/responsável sobre a resposta não sai se não houver SMTP (só log); o aviso no sino sai mesmo assim.
- Gerentes e membros só são avisados se forem o responsável do negócio.
- Respostas fora da conversa original (e-mail novo) não são reconhecidas.
- Editar e salvar depois de enviar deixa o lead com o PDF antigo.

### 11. Perguntas frequentes
- **P: O botão "Enviar" está cinza.** R: Gere o PDF antes (e salve o orçamento).
- **P: Erro "Nenhum SMTP configurado".** R: Integrações → E-mail → cartão "E-mail (SMTP)": preencha, "Salvar SMTP" e teste com "Testar envio".
- **P: Posso mandar para mais de uma pessoa?** R: Sim, separe os e-mails por vírgula em "Para" ou "CC (opcional)".
- **P: O lead respondeu e nada aconteceu.** R: Confira o cartão Gmail: "conectado", "Monitoramento: ativo" e sem o aviso "Configuração GCP pendente…". A resposta precisa ser na mesma conversa do e-mail enviado pelo IgIg.
- **P: A resposta muda o status do orçamento?** R: Não; ele continua "Enviado" e o card mostra "respondeu por e-mail".
- **P: Quem é avisado da resposta?** R: Os Proprietários e Administradores da agência e o responsável do negócio (se o profissional responsável estiver vinculado a um usuário), pelo sino e por e-mail — cada pessoa uma vez só.
- **P: Enviar de novo cria outro registro?** R: Sim, cada envio vira uma linha "Enviado" no histórico.

---

## Funcionalidade: Contrato (Digital/Física, assinatura, marcar assinado)

### 1. Propósito
Gerar o **contrato de prestação de serviços** a partir de um **orçamento aceito**, com valor mensal, posts por mês e valor do excedente, que alimentam o Financeiro. Duas modalidades: **"Digital"** — "Assinatura eletrônica por e-mail." (hoje uma **simulação**) — e **"Física"** — "Impressa e assinada à mão; marque como assinado depois."

### 2. Acesso
- **Gerar**: modal do orçamento (status Aceito) → painel **"Contrato"**.
- **Consultar, abrir PDF, marcar como assinado, reenviar**: menu "Clientes" (`/clientes`) → card do cliente → aba **"Orçamentos & Contratos"** → seção "Contratos".
- **Webhook de assinatura** (sistemas externos): `POST /api/comercial/assinatura/webhook`, público mas exige assinatura HMAC.
- Qualquer usuário autenticado da agência gera e marca como assinado; nenhuma ação é só-admin.

### 3. Layout
**Painel "Contrato" (no orçamento aceito)**
- Se já existe contrato **vivo** (Aguardando assinatura ou Ativo): mostra só "Contrato {físico/digital} gerado · {status}." e "Consulte, baixe o PDF e marque como assinado em Clientes → Orçamentos & Contratos."
- Senão: aviso âmbar (se um contrato digital anterior voltou para rascunho) "O contrato digital anterior voltou para rascunho (assinatura recusada ou expirada) — gere um novo."; escolha **"Digital"** / **"Física"**; "Dia de vencimento (opcional)"; "Número de vias" (Física) ou "E-mail do signatário" (Digital); botão **"Gerar contrato"** (ou **"Gerar novo contrato"**).
- Após gerar: quadro "Contrato {físico/digital} gerado · {status}.", link **"Abrir PDF do contrato"** e, na Digital, em vermelho "Simulação (assinatura digital ainda não integrada) — este link não ativa o contrato de verdade." + "Link (simulação): {link}". Depois que a lista de contratos recarrega, o painel passa à visão do "contrato vivo" (aguardando assinatura ou ativo), que **continua** mostrando o link "Abrir PDF do contrato" (sempre que o contrato tem documento) e, para contrato Digital com link, o aviso em vermelho "Simulação (assinatura digital ainda não integrada) — este link não ativa o contrato de verdade.".

**Aba "Orçamentos & Contratos" do cliente**
- Seção "Orçamentos": orçamentos ligados ao cliente ("{título} · v{versão}", "R$ X/mês · {data}", selo de status); toque abre o modal.
- Seção "Contratos": cada contrato com "Contrato {número}" ou "Contrato de {data}", selo "Física"/"Digital", selo de status ("Rascunho", "Aguardando assinatura", "Ativo", "Encerrado"), linha "R$ X/mês · N posts/mês · vence dia D · assinado em {data}".
  - Digital aguardando: "Link de assinatura (simulação — assinatura digital ainda não integrada): {link}".
  - Digital em rascunho: aviso "Assinatura recusada ou expirada — o contrato voltou para rascunho." + botão **"Reenviar / gerar novamente"** (abre o orçamento).
  - Botões: **"PDF"**, **"Via assinada"** (se houver scan), **"Marcar como assinado"** (só Física, não Ativo e não Encerrado).
- Janela **"Marcar como assinado"** — "Contrato físico: ativa o contrato (e o cliente) a partir de hoje." — "Anexe a via assinada digitalizada (PDF, JPG ou PNG · até 25 MB)." + "Escolher arquivo"; botões "Cancelar" e "Confirmar assinatura".
- Celular: janelas em tela cheia; botões com 40px e lado a lado ocupando a largura.

### 4. Campos

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| Modalidade ("Digital"/"Física") | escolha | Sim | — | Digital | A modalidade define como o contrato é ativado. |
| "Dia de vencimento (opcional)" | número | Não | 1 a 31 | 10 | Vazio: cláusula "em data acordada entre as partes"; fatura sem vencimento. |
| "Número de vias" | número | Não (só Física) | 1 a 10 | 2 | Vai para o fecho do PDF ("em 2 (duas) vias…"). |
| "E-mail do signatário" | e-mail | Não (só Digital) | até 200 | e-mail do lead | Vazio: e-mail do lead, depois do cliente. |
| Via assinada (arquivo) | arquivo | Não (recomendado) | PDF, JPG ou PNG; até 25 MB; não vazio | — | Único registro da assinatura física. |

### 5. Ações

| Ação | Pré-condições | O que acontece | Sucesso | Erros |
|---|---|---|---|---|
| "Gerar contrato" / "Gerar novo contrato" | Orçamento Aceito, sem contrato vivo | Cria o contrato ("Aguardando assinatura") com valor mensal = total mensal; posts/mês = soma das quantidades mensais dos itens de **Criação de conteúdo recorrentes**; valor do excedente = "Valor por excedente (R$)"; início = data da geração. Gera o PDF. Digital: registra a solicitação de assinatura (simulação, provedor "interno", link inválido). | "Contrato gerado." | 409 `orcamento_nao_aceito` "Só um orçamento aceito gera contrato. Aceite o orçamento primeiro." 409 `contrato_existente` "Este orçamento já tem um contrato gerado." Genérico: "Não foi possível gerar o contrato." |
| "Abrir PDF do contrato" / "PDF" | Contrato com documento | Abre o PDF (link de 10 min). | — | 409 `pdf_nao_gerado` "Este contrato não tem documento gerado." "Não foi possível abrir o contrato." / "Documento indisponível." |
| "Via assinada" | Scan anexado | Abre o scan (10 min). | — | "Documento indisponível." |
| "Marcar como assinado" → "Confirmar assinatura" | Contrato **Física**, não Ativo, não Encerrado | Grava o scan (se houver), contrato → **Ativo** com data de assinatura; **cliente → "ativo"**. | "Contrato assinado e ativo." | 409 `contrato_digital` "Este contrato é de assinatura digital — ele é ativado pela confirmação da assinatura." 409 `contrato_ja_assinado` "Este contrato já está assinado." 409 `contrato_encerrado` "Este contrato está encerrado e não pode ser reativado." 422 `arquivo_invalido` "Envie o contrato assinado em PDF, JPG ou PNG." 422 `arquivo_vazio` "O arquivo enviado está vazio." 413 "Arquivo excede 25 MB". Genérico: "Não foi possível marcar como assinado." |
| "Reenviar / gerar novamente" | Contrato em Rascunho | Abre o orçamento; o painel "Contrato" volta a permitir gerar um novo. | — | — |

### 6. Estados
- **Carregando**: bloco cinza no painel "Contrato"; bloco cinza nas seções da aba do cliente; botões "Gerando…" / "Salvando…".
- **Vazio**: "Nenhum orçamento ligado a este cliente. Orçamentos nascem de um negócio no Comercial." / "Nenhum contrato. Gere um a partir de um orçamento aceito."
- **Erro**: "Não foi possível carregar os orçamentos." / "Não foi possível carregar os contratos."; erros de ação como acima.
- **Atualizando**: listas permanecem enquanto recarregam.

### 7. Regras de negócio e por quê
1. **Só orçamento aceito** gera contrato.
2. **Um contrato vivo por orçamento**: Aguardando assinatura ou Ativo bloqueia outro; Rascunho ou Encerrado liberam gerar de novo.
3. **A modalidade é o portão**: Digital **não** pode ser marcado como assinado à mão (seria uma segunda forma de ativar sem assinatura real); só o webhook ativa.
4. **Encerrado não reativa** por "Marcar como assinado".
5. **Posts/mês só conta Criação recorrente** (os únicos que geram pauta) — no exemplo da página Orçamentos, 12 + 8 = 20.
6. **Ativo ⇒ cliente ativo** (Física por "Marcar como assinado"; Digital pelo webhook, que também marca os leads do cliente como convertidos).
7. **Webhook**: HMAC-SHA256 do corpo com `IGIG_ASSINATURA_WEBHOOK_SECRET` no cabeçalho `X-Webhook-Hmac-SHA256`; sem segredo configurado **toda chamada é recusada (401)**. Corpo `{"external_id", "evento": "assinado"|"recusado"|"expirado"}`. `assinado` → ativo (reenvio responde "ja_processado"); `recusado`/`expirado` → contrato volta para **Rascunho**; não encontrado → 404 "Contrato não encontrado".
8. **Conteúdo do PDF**: "Contrato de prestação de serviços de marketing digital"; partes (CONTRATADA = agência; CONTRATANTE = cliente, com e-mail/telefone); "Referente à proposta v{N}", "Emitido em {data}", "Assinatura física/digital"; Cláusula 1ª Do objeto (+ tabela dos itens e "Valor mensal"); 2ª Do valor e do pagamento ("com vencimento todo dia D de cada mês" ou "em data acordada entre as partes"); 3ª Do escopo e das revisões; 4ª Da vigência (**12 meses** a partir do início, renovação automática); 5ª Da rescisão (**aviso prévio de 30 dias**); 6ª Da confidencialidade e dos dados pessoais (LGPD). Física: fecho "…em {N} ({extenso}) vias de igual teor e forma…", linha de local/data, assinaturas CONTRATANTE/CONTRATADA e Testemunha 1/2 (Nome/CPF) mantidas juntas. Digital: reconhecimento da assinatura eletrônica (MP 2.200-2/2001 e Lei 14.063/2020).
9. **Contrato → fatura**: no Financeiro, "Gerar competência" cria uma fatura por contrato **Ativo** com "Retainer mensal" = valor mensal e, quando no mês anterior as peças **avulsas** entregues (fora do plano recorrente) passaram do que as peças do plano deixaram livre em posts/mês, "Excedentes de {AAAA-MM}" = (avulsas entregues − capacidade restante do pacote depois das peças do plano) × valor do excedente. Peças do plano nunca são cobradas como excedente (mas ocupam o pacote), e "entregue" = publicada de verdade ou aprovada pelo cliente no portal. Aguardando assinatura não fatura. (Detalhes no guia do Financeiro.)

### 8. Fluxo de dados
- Gerar: `ContratoPanel` → `useOrcamentoMutations().gerarContrato` → `POST /api/orcamentos/{id}/contrato {modalidade_assinatura, dia_vencimento?, vias?, signatario_email?}` (201) → `contratos.gerar` → insere `igig.contrato` → PDF `{org}/contratos/{id}/contrato.pdf` → `documento_key`; Digital: `contrato_documento.enviar_para_assinatura` (simulação) → `provedor_assinatura='interno'`, `assinatura_external_id` (`<org>.dry-interno-…`), `link_assinatura`.
- Listar: `useContratos` → `GET /api/contratos?cliente_id=`.
- PDF: `useContratoMutations().urlPdf` → `GET /api/contratos/{id}/pdf` → `{url, url_assinado}` (10 min).
- Marcar assinado: `.marcarAssinado` → `POST /api/contratos/{id}/marcar-assinado` (multipart, `arquivo` opcional) → scan `{org}/contratos/{id}/assinado-{arquivo}` → `documento_assinado_key`, `assinado_em`, `assinado_manual_em`, status "ativo" → `cliente.status='ativo'`.
- Webhook: `POST /api/comercial/assinatura/webhook` → `contrato`, `cliente`, `lead`.
- Efeitos: job diário de pautas pausa se o orçamento tem contrato e nenhum Ativo; faturamento mensal só para Ativos.

### 9. Dependências de configuração
- `IGIG_ASSINATURA_WEBHOOK_SECRET` (sem ele, o webhook responde 401 sempre).
- Armazenamento privado para PDFs e scans.
- Nome da organização (aparece como CONTRATADA).

### 10. Limitações conhecidas
- **Assinatura digital é simulação** (`NOC-REMEDIATE[igig-assinatura]`): nenhum provedor (Clicksign, DocuSign, Autentique) está integrado; o link (`https://exemplo.invalido/assinar/...`) **não funciona**. Um contrato Digital só fica Ativo se um sistema externo chamar o webhook com o segredo. **Para ativar contratos hoje, use "Física" + "Marcar como assinado".**
- Enquanto o contrato Digital não ativa, ele não gera fatura e o job de pautas fica pausado para esse orçamento.
- Boas-vindas/onboarding automáticos após a assinatura não existem (`NOC-REMEDIATE[igig-onboarding]`).
- No quadro pós-geração o status aparece com o código interno (ex.: "aguardando_assinatura").
- Cliente com mais de um contrato Ativo com pacote: as peças do plano são atribuídas ao contrato certo (pelo orçamento de origem), mas as peças **avulsas** desse cliente não entram em nenhum contrato (não há como saber a qual pertencem) — então não geram excedente.

### 11. Perguntas frequentes
- **P: Como ativo o contrato?** R: Física: Clientes → card → "Orçamentos & Contratos" → "Marcar como assinado". Digital hoje é simulação e não ativa sozinho.
- **P: O link de assinatura digital não abre.** R: É um link de simulação; a assinatura digital ainda não está integrada. Gere o contrato como "Física".
- **P: Por que o cliente continua "prospect"?** R: O cliente só fica "ativo" quando o contrato é ativado.
- **P: O contrato não gerou fatura.** R: Faturas saem em Financeiro → "Gerar competência", só para contratos **Ativos**.
- **P: Apareceu "Este orçamento já tem um contrato gerado."** R: Já existe contrato aguardando assinatura ou ativo. Consulte em Clientes → "Orçamentos & Contratos".
- **P: A assinatura digital foi recusada. E agora?** R: O contrato volta para "Rascunho"; toque "Reenviar / gerar novamente" e gere um novo.
- **P: Preciso anexar a via assinada?** R: Não é obrigatório, mas é recomendado: é o único registro da assinatura.
- **P: Como é contado "posts/mês"?** R: Soma da quantidade mensal dos itens de Criação de conteúdo recorrentes do orçamento.

---

## Funcionalidade: Integrações → E-mail (SMTP/Gmail)

### 1. Propósito
Configurar a **conta SMTP** que envia orçamentos, faturas e e-mails das automações, e conectar o **Gmail** que **observa** as respostas aos orçamentos (o Gmail não envia; o envio continua pelo SMTP).

### 2. Acesso
- **Rota**: `/integracoes`; **menu lateral**: grupo "Principal", item **"Integrações"** — 10ª posição. Página com os grupos **"E-mail"**, **"Fontes de lead"** e **"Canais de publicação"**; o grupo "E-mail" tem os cartões **"E-mail (SMTP)"** e **"Gmail (respostas de orçamentos)"**.
- **Ver** status: qualquer usuário autenticado. **Testar envio**: qualquer usuário autenticado.
- **Só-admin (dono/admin da agência ou admin da plataforma)**: o formulário do SMTP ("Salvar SMTP", "Remover") e "Conectar Gmail"/"Reconectar"/"Desconectar". Para os demais a tela **esconde** esses controles e mostra "Apenas administradores da organização podem configurar o SMTP." / "Apenas administradores da organização podem conectar ou desconectar o Gmail."; se a escrita chegar ao servidor, 403 "Apenas administradores da organização podem realizar esta ação.".
- **"Testar envio" continua aberto a qualquer membro** (decisão do dono do produto): usar uma configuração já salva para mandar um e-mail de teste não muda a configuração.

### 3. Layout
- Cabeçalho "Integrações" — "E-mail, fontes de lead e canais de publicação. Senhas e tokens são gravados criptografados e nunca são exibidos de volta."
- **Cartão "E-mail (SMTP)"**: selo "configurado" (SMTP próprio) / "usando SMTP da plataforma" / "não configurado"; descrição "Conta usada para enviar orçamentos e e-mails das automações." ou, com SMTP da plataforma, "Sem SMTP próprio, os e-mails saem pela conta da plataforma ({e-mail}). Configure a conta da agência para enviar com o seu endereço."; formulário; "Remover" (só com SMTP próprio) e "Salvar SMTP"; bloco "Testar envio para" + "Testar envio" (quando há algum SMTP utilizável).
- **Cartão "Gmail (respostas de orçamentos)"**: descrição "Conecte a caixa que envia os orçamentos: quando o cliente responde, o orçamento é marcado e o responsável é notificado."; selo "não conectado" / "conectado · sem monitoramento" / "conectado" / "reconectar" (houve erro); aviso vermelho (se a plataforma não tem Pub/Sub) "Configuração GCP pendente na plataforma (Pub/Sub do Gmail, variáveis GMAIL_PUSH_*). A caixa pode ser conectada, mas as respostas ainda não serão detectadas."; quando conectado: "Caixa", "Monitoramento" ("ativo"/"inativo"), "Expira em"; último erro; botões "Conectar Gmail"/"Reconectar" e "Desconectar".
- **Computador (≥1024px)**: os dois cartões lado a lado. **Celular**: empilhados, campos com 40px.

### 4. Campos

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Servidor (host)" | texto | Sim | até 255 | vazio ("smtp.gmail.com") | — |
| "Porta" | número | Sim | 1 a 65535 | 587 | — |
| "Usuário" | texto | Sim | até 320 | vazio | — |
| "Senha" | senha | Sim na 1ª vez | até 1.000 | vazio | Placeholder "senha ou senha de app"; com SMTP próprio, "manter senha atual…" (vazio mantém a gravada). Nunca é mostrada de volta. |
| "Segurança" | lista | Sim | "STARTTLS (587)" ou "SSL/TLS (465)" | STARTTLS | — |
| "Remetente (e-mail)" | e-mail | Sim | e-mail válido; até 320 | vazio | — |
| "Remetente (nome)" | texto | Não | até 200 | vazio ("Agência Exemplo") | — |
| "Testar envio para" | e-mail | Sim para testar | e-mail válido | vazio ("voce@agencia.com") | — |

O formulário só é preenchido com o SMTP **próprio** da agência; os dados da plataforma não aparecem para edição.

### 5. Ações

| Ação | Pré-condições | O que acontece | Sucesso | Erros |
|---|---|---|---|---|
| "Salvar SMTP" | Admin; campos obrigatórios; houve alteração | Grava a conta (senha criptografada). | "SMTP salvo." | 422 `senha_obrigatoria` "Informe a senha do SMTP." 409 `cofre_nao_configurado` "Criptografia não configurada: defina IGIG_COFRE_KEY. Nenhuma credencial é gravada em texto puro." 403 não-admin. Genérico: "Não foi possível salvar o SMTP." |
| "Remover" → confirmação "Remover SMTP" | Admin; SMTP próprio. Texto: "Remover a conta SMTP da agência? Sem ela, os e-mails passam a sair pelo SMTP da plataforma (se houver) ou deixam de ser enviados." | Apaga a conta da agência. | "SMTP removido." | 404 "Nenhum SMTP próprio configurado." Genérico: "Não foi possível remover o SMTP." |
| "Testar envio" | Algum SMTP utilizável; e-mail preenchido | Envia "Teste de envio — IgIg" ("Este é um e-mail de teste enviado pela tela de Integrações do IgIg."). | "E-mail de teste enviado para {e-mail}." | "Falha ao enviar o e-mail: {erro}" (502) ou "O envio de teste falhou."; `smtp_nao_configurado`. |
| "Conectar Gmail" / "Reconectar" | Admin | Vai para a tela de consentimento do Google (permissões de enviar e ler e-mails); há **10 minutos** para concluir; o Google volta para `/integracoes`; o IgIg grava a caixa e inicia o monitoramento (se a plataforma tiver Pub/Sub). | "Gmail conectado." | "Não foi possível conectar o Gmail: {motivo}." com motivo: "o acesso não foi autorizado na tela do Google"; "o Google não devolveu o código de autorização"; "a autorização expirou (mais de 10 minutos) — tente de novo"; "o OAuth do Google não está configurado no servidor"; "não foi possível trocar o código de autorização"; "o Google não devolveu um token permanente — remova o acesso do app na conta Google e conecte de novo"; "a permissão de leitura dos e-mails não foi concedida"; "não foi possível ler o endereço da caixa"; "a criptografia não está configurada no servidor (defina IGIG_COFRE_KEY)". Antes de ir ao Google: 503 "OAuth do Google não configurado: defina GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET." ou 503 "URL pública do produto não configurada: defina PRODUCT_URL_IGIG (ou PRODUCT_URL_PATTERN)." Genérico: "Não foi possível iniciar a conexão com o Google." |
| "Desconectar" → confirmação "Desconectar Gmail" | Admin; conectado. Texto: "Desconectar {e-mail}? As respostas aos orçamentos deixam de ser detectadas." | Para o monitoramento no Google (se falhar, expira sozinho em até 7 dias), apaga o monitoramento e a credencial. | "Gmail desconectado." | 404 "Gmail não conectado." Genérico: "Não foi possível desconectar." |

### 6. Estados
- **Carregando**: esqueleto em cada cartão; botões "Salvando…", "Removendo…", "Enviando…", "Abrindo o Google…", "Desconectando…".
- **Vazio**: SMTP "não configurado"; Gmail "não conectado".
- **Erro**: "Não foi possível carregar o SMTP." / "Não foi possível carregar o Gmail."; último erro do Gmail em vermelho.
- **Atualizando**: após voltar do Google, o status do Gmail é recarregado e os parâmetros `gmail`/`motivo` somem da URL (um recarregamento não repete o aviso).

### 7. Regras de negócio e por quê
1. **Prioridade no envio**: SMTP da agência (ativo) → SMTP da plataforma (`SMTP_HOST/PORT/USER/PASSWORD…`, uso registrado em log) → recusa 409. O selo mostra exatamente a origem que o envio usaria.
2. **Credenciais sempre criptografadas** com `IGIG_COFRE_KEY`; sem a chave, nada é gravado (nunca texto puro).
3. **Gmail só observa**: não envia; o envio é sempre SMTP. Se o Gmail conectado for diferente do remetente SMTP, vira o "Responder para" dos orçamentos.
4. **Monitoramento** (Gmail `users.watch`) expira em até 7 dias e para em silêncio; renovado todo dia às 06:15 (Brasília) no ambiente implantado.
5. **Escrita só para admin**: a conta de e-mail fala em nome de toda a agência. Testar o envio com a conta já salva é livre.
6. O retorno do Google é público, mas a organização vem de um "state" assinado com validade de 10 minutos.
7. Para Gmail/Google Workspace como SMTP normalmente é preciso uma "senha de app" (orientação geral; o IgIg não valida).
8. **A mesma conta SMTP envia as faturas** ("Enviar fatura" no Financeiro), com a mesma prioridade: agência → plataforma → recusa 409.

### 8. Fluxo de dados
| Ação | Hook | Endpoint |
|---|---|---|
| Status SMTP | `useSmtp` | `GET /api/integracoes/email/smtp` (nunca retorna a senha) |
| Salvar SMTP | `useSmtpMutations().salvar` | `PUT /api/integracoes/email/smtp` (admin) |
| Remover SMTP | `.remover` | `DELETE /api/integracoes/email/smtp` (admin) |
| Testar | `.testar` | `POST /api/integracoes/email/smtp/testar {para}` |
| Status Gmail | `useGmail` | `GET /api/integracoes/email/gmail` |
| Iniciar OAuth | `useGmailMutations().iniciarOAuth` | `GET /api/integracoes/email/gmail/oauth/start` → `{url}` (admin) |
| Retorno do Google | — | `GET /api/integracoes/email/gmail/oauth/callback` (público) → `/integracoes?gmail=ok` ou `?gmail=erro&motivo=…` |
| Desconectar | `.desconectar` | `DELETE /api/integracoes/email/gmail` (admin) |
| Push Pub/Sub | — | `POST /api/webhooks/gmail/push` (público, token OIDC) |

Tabelas: `igig.integracao` (canais `smtp` e `gmail`; segredo em `token_cifrado`, dados públicos em `config`), `igig.gmail_watch` (cursor e expiração), `igig.orcamento_email` (histórico). Notificações: `public.notifications`.

### 9. Dependências de configuração
| Variável (servidor) | Para quê | Se faltar, o usuário vê |
|---|---|---|
| `IGIG_COFRE_KEY` | Criptografar senha SMTP e tokens Gmail | 409 "Criptografia não configurada: defina IGIG_COFRE_KEY…" ao salvar SMTP; "a criptografia não está configurada no servidor (defina IGIG_COFRE_KEY)" ao conectar Gmail |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURITY`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME` | SMTP de reserva da plataforma | Agência sem SMTP próprio: selo "não configurado" e envios recusados (409 `smtp_nao_configurado`) |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | App OAuth do Google | 503 "OAuth do Google não configurado…"; caixas já conectadas ficam inutilizáveis |
| `PRODUCT_URL_IGIG` (ou `PRODUCT_URL_PATTERN`) | Endereço público do retorno do Google | 503 "URL pública do produto não configurada…" |
| `GMAIL_PUSH_GCP_PROJECT`, `GMAIL_PUSH_TOPIC`, `GMAIL_PUSH_AUDIENCE`, `GMAIL_PUSH_SERVICE_ACCOUNT` | Pub/Sub das respostas | Aviso "Configuração GCP pendente na plataforma…"; nenhum monitoramento; webhook responde 503 |

Essas variáveis são da plataforma: a agência não as configura pela tela — deve acionar o suporte/administrador da plataforma.

### 10. Limitações conhecidas
- "Testar envio" não exige admin (decisão registrada do dono do produto — não é falha).
- Se o Gmail foi conectado depois do envio, respostas a e-mails antigos só são reconhecidas a partir do início do monitoramento (e desde que na mesma conversa).
- Motivos de falha no retorno do Google fora da lista acima aparecem com o código cru.

### 11. Perguntas frequentes
- **P: Preciso configurar SMTP?** R: Se a plataforma tiver SMTP de reserva, os e-mails saem por ela ("usando SMTP da plataforma"). Para enviar com o endereço da agência, configure o seu.
- **P: Usei minha senha do Gmail e deu erro.** R: Contas Google normalmente exigem uma "senha de app" para SMTP.
- **P: Não vejo o formulário do SMTP / o botão "Conectar Gmail".** R: Só Proprietário ou Administrador da agência configura e-mail (aparece "Apenas administradores da organização podem…"). Você ainda pode usar "Testar envio".
- **P: O Gmail envia os orçamentos?** R: Não; ele só observa as respostas. O envio é pelo SMTP.
- **P: Aparece "conectado · sem monitoramento".** R: A plataforma não tem o Pub/Sub configurado ou o monitoramento expirou. Toque "Reconectar"; se persistir com o aviso "Configuração GCP pendente…", acione o suporte.
- **P: A senha some depois de salvar.** R: É proposital: senhas nunca são exibidas; deixe o campo vazio para manter a atual.
- **P: "a autorização expirou (mais de 10 minutos)".** R: Refaça "Conectar Gmail" e conclua no Google em até 10 minutos.

---

---

# Capítulo 3 — Esteira, Calendário, Central da Marca e Cofre, Portal de Aprovação

## IgIg — Guia: Esteira, Calendário, Central da Marca + Cofre, Portal de Aprovação

> Fonte: código final em `products/igig`, conferido arquivo a arquivo. Rótulos, mensagens e toasts aparecem entre "aspas" exatamente como estão no código. Onde algo não pôde ser confirmado, está escrito "(não confirmado no código)". Onde uma conclusão vem da leitura do código, e não de um texto explícito, está marcada como "(dedução do código)".
>
> **Como as quatro partes se ligam:** Cliente → N **marcas** (identidade) + 1 **Cofre de Acessos** por cliente. Cliente → **pautas** (Calendário). Pauta → **tarefas** (Esteira); a tarefa sempre herda o cliente da pauta. Tarefa → **link de aprovação** → **portal público** `/aprovar/<token>`, onde o cliente final aprova ou pede ajuste, e o cartão anda sozinho na esteira.

---

## Página: Esteira

### 1. Propósito
Quadro kanban da produção. Cada cartão é uma **tarefa** ligada a uma pauta, e anda pelas etapas do roteiro até o agendamento. Na mesma tela ficam o cronômetro (timesheet) por pessoa, os apontamentos de horas, o contador de refações, o link de aprovação do cliente e o painel "Repertório da marca".

Etapas padrão (criadas automaticamente na primeira leitura do quadro pela organização), nesta ordem: "Aguardando roteiro", "Roteiro em produção", "Aguardando design", "Design em produção", "Revisão interna", "Aprovação do cliente" (papel `aprovacao_cliente`), "Pronto para agendamento", "Agendado" (papel `agendado`).

### 2. Acesso
- **Rota:** `/esteira` (filtro opcional `?cliente=<id>`). Deep link `/esteira?tarefa=<id>` (usado pelas notificações de automação, de SLA e da decisão do cliente no portal) abre direto os detalhes daquela tarefa assim que o quadro carrega — mesmo que ela seja de um cliente fora do filtro "Cliente" ativo; fechar a tarefa tira o `?tarefa=` do endereço.
- **Menu lateral:** grupo "Principal", item **"Esteira"**, 6º item (depois de "Dashboard", "Comercial", "Clientes", "Orçamentos", "Produtos e Serviços"; antes de "Calendário"). A visibilidade do item segue o cadastro de páginas do produto (`status_pagina`, rota `esteira` em produção).
- **Também em:** "Clientes" → abrir o cliente → aba **"Esteira"** (mesmo quadro, já filtrado por esse cliente, sem o seletor "Cliente").
- **Quem pode ver/executar:**
  - Qualquer membro logado da agência: ver o quadro, criar, editar, mover e excluir tarefas, usar o próprio cronômetro, ver apontamentos, gerar link de aprovação.
  - **Só administradores** (dono/admin da organização ou admin da plataforma/produto): "Configurar etapas", renomear/recolorir/excluir/criar/reordenar etapas e o painel "Papéis das etapas". Para os demais, esses controles não aparecem, e o servidor recusa com 403.

### 3. Layout
- **Cabeçalho:** título "Esteira de Produção", subtítulo "Arraste o cartão uma etapa por vez. Para voltar, informe o motivo." e o seletor **"Cliente"** ("Todos os clientes" + lista de clientes).
- **Barra do quadro:** botão **"Nova tarefa"**; para admins, botão **"Configurar etapas"** / **"Fechar configuração"**.
- **Colunas:** uma por etapa ativa. Cabeçalho com o nome da etapa, o total de cartões e, para admins, o menu de opções ("Opções da etapa <nome>"). Na etapa com papel aparece a etiqueta "Aprovação do cliente" ou "Agendado". Coluna vazia: "Nenhuma tarefa". Para admins, no fim do quadro há o espaço **"+ coluna"**.
- **Cartão:** nome do cliente (em maiúsculas), título da tarefa, título da pauta com etiqueta do formato, responsável (ou "Sem responsável"), prazo `dd/mm/aa` (em vermelho se vencido) e etiqueta vermelha "N refação"/"N refações". O cartão não tem botões: tocar abre os detalhes.
- **Painel "Papéis das etapas"** (só admins, abaixo do quadro, recolhível): dois seletores, "Aprovação do cliente" e "Agendado", mostrando qual etapa tem cada papel; só etapas **ativas** aparecem como opção. Uma etapa tem no máximo um papel, e nenhum papel pode ficar sem etapa. É o mesmo painel do Comercial (lá com um seletor só, "Fechado (exige orçamento aceito)").
- **Detalhes da tarefa** (janela; tela cheia no celular): título da tarefa, cliente como subtítulo, etiquetas da etapa atual e das refações, nota "Cliente pediu: “…”" quando houver. Campos: "Cliente", "Pauta", "Formato", "Responsável", "Prazo" (com " · vencido"), "Publicação". Seções **"Tempo"**, **"Apontamentos"** e **"Aprovação do cliente"**. Rodapé: **"Editar"**, **"Excluir tarefa"**, **"Fechar"**.
  - **Desktop (≥640px):** "Repertório da marca" aparece como painel lateral fixo à direita.
  - **Celular (<640px):** "Repertório da marca" vira um botão recolhível (com seta) no topo dos detalhes.
- **Celular:** cada coluna ocupa cerca de 82% da largura; o quadro rola para o lado dentro do próprio espaço (a página não rola na horizontal); cada coluna rola na vertical de forma independente.

### 4. Campos

**Nova tarefa** (janela "Nova tarefa")

| Campo (rótulo exato) | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Título" | texto (placeholder "Carrossel — lançamento de outubro") | Sim | 1–200 caracteres | vazio | Botão "Criar tarefa" só ativa com título e pauta. |
| "Pauta" | lista ("Selecione…"; "Carregando…" durante a carga) | Sim | precisa existir na organização | — | Opções no formato "título — data — cliente" (ex.: "Post feed (1/2) — 05/10/2026 — Padaria Sol"); sem data aparece "sem data". Na aba do cliente, só as pautas dele e sem o nome do cliente. Inclui pautas passadas e sem data. |
| "Responsável" | lista | Não | profissional precisa existir | "Sem responsável" | Só profissionais **ativos** em Custos. |
| "Prazo" | data | Não | — | vazio | — |

**Editar tarefa** (botão "Editar" nos detalhes): "Título" (1–200), "Pauta" (todas as pautas da agência, com cliente no rótulo), "Responsável" (só ativos + "Sem responsável"), "Prazo" (data). A etapa **não** é editável aqui.

**Motivo ao voltar** (janela de motivo): campo de texto obrigatório, até 2000 caracteres; placeholder "Por que voltar?" ou, saindo da aprovação, "O que precisa ser refeito?".

**Configurar etapas (admin):** nome da etapa (renomear no cabeçalho ou "Nome da nova etapa" em "+ coluna"), cor ("Cor da etapa"), destino dos cartões ao excluir ("Mover cartas para").

**Papéis das etapas (admin):** seletores "Aprovação do cliente" e "Agendado", com "Escolha uma etapa…" (desabilitada) + as etapas.

### 5. Ações

| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| Filtrar por "Cliente" | — | Mostra só as tarefas do cliente; o filtro fica no endereço (`?cliente=<id>`), dá para salvar/compartilhar o link. | — | — |
| Tocar no cartão | — | Abre os detalhes da tarefa. | — | — |
| Arrastar cartão **uma etapa para frente** | Desktop: clicar e arrastar (começa após ~8px). Celular: tocar e segurar ~0,25 s e arrastar. | Move a tarefa, grava o histórico de movimentos, dispara as automações de entrada da etapa (tela "Automações"). | — | 409 `etapa_invalida` "Esta etapa está desativada." · 404 "Tarefa não encontrada" (recarregue). Em erro o cartão volta ao lugar. |
| Arrastar **pulando etapas para frente** | — | Cancelado antes de enviar; o cartão volta. | — | Toast "Avance uma etapa por vez". (Servidor, se chamado direto: 409 `etapa_invalida` "A tarefa só pode avançar uma etapa por vez.") |
| Arrastar **para trás** (qualquer distância) | Informar motivo | Abre a janela "Devolver para <etapa>?" — "Voltar uma tarefa exige um motivo — ele fica no histórico." — botões "Devolver"/"Cancelar". O cartão fica esmaecido enquanto a janela está aberta. | — | 422 `motivo_obrigatorio` "Informe o motivo para devolver a tarefa a uma etapa anterior." |
| Arrastar **para trás saindo de "Aprovação do cliente"** | Informar o que refazer | Janela "Refação — devolver para <etapa>?" — "Sair da aprovação do cliente conta uma refação para esta tarefa." — botões "Registrar refação"/"Cancelar". O contador de refações sobe 1 (atômico no banco). | — | Iguais ao item acima. |
| Reordenar dentro da coluna | — | Livre; a posição é gravada. | — | Toast com a mensagem do servidor, ou "Não foi possível mover a tarefa." |
| "Nova tarefa" → "Criar tarefa" | Título + pauta; esteira com ao menos uma etapa ativa | Cria a tarefa na **primeira etapa ativa**, no topo da coluna; o cliente vem da pauta; grava o movimento de entrada e **dispara as automações da primeira etapa**. Botão mostra "Criando…". | "Tarefa criada na primeira etapa" | 404 "Pauta não encontrada" · 404 "Profissional não encontrado" · 409 `esteira_sem_etapas` "A esteira não tem nenhuma etapa ativa. Configure as etapas primeiro." (admin cria/reativa etapas) · 422 (título fora de 1–200) · fallback "Não foi possível criar a tarefa." |
| "Editar" → "Salvar" | Título não vazio | Grava título, pauta, responsável, prazo. Trocar a pauta troca o cliente da tarefa. Não muda etapa. Botão mostra "Salvando…". | "Tarefa atualizada." | 400 "Nenhum campo para atualizar" · 404 "Profissional não encontrado" / "Pauta não encontrada" / "Tarefa não encontrada" · 422 (título) · fallback "Não foi possível salvar a tarefa." |
| "Iniciar" (Tempo) | — | Inicia o cronômetro **do usuário logado**. Se ele tinha outro cronômetro rodando em qualquer tarefa, esse é encerrado. O apontamento guarda o profissional vinculado ao usuário (ou fica sem). | Se outro foi encerrado: "O cronômetro de outra tarefa foi encerrado automaticamente." | 404 "Tarefa não encontrada" · fallback "Não foi possível atualizar o cronômetro." |
| "Pausar" (Tempo) | Cronômetro do usuário rodando nesta tarefa | Grava fim, segundos exatos e minutos (arredondados para baixo). | — | 404 "Nenhum apontamento aberto nesta tarefa" (foi encerrado em outro lugar; recarregue) |
| "Gerar e copiar link de aprovação" | Tarefa não pode estar **depois** da etapa de aprovação; precisa existir etapa com papel "Aprovação do cliente" | (1) Move a tarefa direto para a etapa "Aprovação do cliente" (pula as intermediárias; motivo gravado "Link de aprovação enviado ao cliente"); (2) dispara as automações da etapa de aprovação; (3) cria um link novo válido por **14 dias**; (4) **invalida todos os links anteriores ainda não respondidos** dessa tarefa; (5) copia o link e o mostra por extenso. Botão mostra "Gerando…". | "Link copiado — a tarefa foi para aprovação do cliente." ou, se a cópia for bloqueada, "Copie o link abaixo e envie ao cliente." | 409 `etapa_invalida` "Esta tarefa já passou da aprovação do cliente." (devolva a tarefa com motivo e gere de novo) · 409 `etapa_aprovacao_ausente` "Nenhuma etapa da esteira está marcada como 'Aprovação do cliente'." (admin atribui o papel em "Papéis das etapas") · 404 "Tarefa não encontrada" · fallback "Não foi possível gerar o link." |
| "Excluir tarefa" → "Confirmar exclusão" (e, se houver horas, "Excluir mesmo assim") | — | (1) Se **o seu** cronômetro está rodando nesta tarefa, ele é encerrado primeiro (para o aviso mostrar o tempo real, não zero). (2) A primeira confirmação pede a exclusão **sem** forçar. (3) Se a tarefa tem **qualquer** apontamento (mesmo de segundos), o servidor recusa e a janela mostra, em vermelho, a mensagem real do servidor — "Isto tem <h> de horas apontadas em N apontamento(s). Confirme a exclusão para perder esses registros." — e o botão vira **"Excluir mesmo assim"**. (4) Tocando nele, a tarefa é apagada com os apontamentos e os links de aprovação; o histórico de movimentos é mantido. "Cancelar" volta aos detalhes e limpa o aviso. Botão mostra "Excluindo…". | "Tarefa excluída" | Não foi possível encerrar o cronômetro: "Não foi possível encerrar o cronômetro em andamento." (nada é excluído) · 404 "Tarefa não encontrada" · fallback "Não foi possível excluir a tarefa." |
| "Configurar etapas" (admin) | Admin | Abre o gerenciador de etapas. Renomear: clique duplo no nome ou menu → "Renomear" (Enter salva, Esc cancela, sair do campo salva). Menu: "Renomear", "Cor da etapa", "Excluir etapa". "+ coluna" cria etapa ("Nome da nova etapa", "Adicionar"/"Cancelar"). Colunas podem ser arrastadas para reordenar. | — | 403 `admin_obrigatorio` "Apenas administradores podem alterar as etapas do quadro." · Etapa com papel: "Excluir etapa" bloqueado, dica "Esta etapa tem um papel do qual outras funcionalidades dependem"; a janela diz "<etapa> não pode ser excluída: ela tem o papel <papel>, do qual outras funcionalidades dependem. Atribua o papel a outra etapa primeiro." · Etapa com cartões: "Excluir <etapa>? Esta etapa tem N carta(s). Escolha para onde movê-las:" + "Mover cartas para" (cada tarefa movida ganha uma linha no histórico de movimentos, em nome do administrador que excluiu, com o motivo "Etapa "<nome>" excluída — carta movida para "<destino>"."). |
| Trocar etapa em "Papéis das etapas" (admin) | Admin | Atribui o papel à etapa escolhida e tira da etapa que o tinha, numa ação só. | — | 409 `papel_obrigatorio` "Esta é a única etapa marcada como '<Aprovação do cliente \| Agendado>'. Atribua esse papel a outra etapa antes de trocá-lo ou removê-lo desta." — acontece ao dar um papel a uma etapa que já tem **o outro** papel (ex.: pôr "Aprovação do cliente" na etapa "Agendado"); primeiro mova o papel atual dela para outra etapa · 403 `admin_obrigatorio` "Apenas administradores podem alterar as etapas do quadro." · fallback "Não foi possível reatribuir o papel." |
| Abrir `/esteira?tarefa=<id>` (link de notificação) | Logado (se não estiver, entra e volta ao link) | Quando o quadro termina de carregar, abre os detalhes da tarefa. Se ela não está no quadro carregado (ex.: é de outro cliente e o filtro "Cliente" está ativo), a tela busca a tarefa direto no servidor e abre os detalhes do mesmo jeito (etapa, pauta, cliente, responsável). Só avisa quando a tarefa realmente não existe | — | Toast "Tarefa não encontrada — pode ter sido excluída." e o parâmetro é limpo (a tarefa foi excluída ou não é desta organização; nada a fazer) |
| "Repertório da marca" (celular: tocar para abrir) | Tarefa com cliente | Mostra logo, "Paleta" (tocar numa cor copia o HEX), "Tom de voz" + formalidade, "Termos proibidos" (em vermelho), "Linhas editoriais". Se o cliente tem várias marcas, aparece um seletor; a marca da pauta vem pré-selecionada. | Ícone de "copiado" ao lado do HEX. | Nunca mostra erro: "Repertório indisponível." |

### 6. Estados
- **Carregando:** esqueleto do quadro (seed). Apontamentos: barra cinza. Repertório: "Carregando repertório…". Pautas no "Nova tarefa": opção "Carregando…".
- **Vazio:** coluna sem cartões: "Nenhuma tarefa". Esteira sem etapas: "Nenhuma etapa configurada." (+ para admin: " Use "Configurar etapas" para criar a primeira."). Apontamentos: "Nenhum tempo registrado ainda.". Sem pauta no "Nova tarefa": "Nenhuma pauta cadastrada (para este cliente). Crie uma pauta no Calendário Editorial para abrir tarefas na esteira." (o link leva ao Calendário sem recarregar a página). Repertório com várias marcas e nenhuma escolhida: "Este cliente tem mais de uma marca — escolha qual repertório ver acima."; cliente sem marca: "Este cliente ainda não tem marca cadastrada.".
- **Erro:** quadro: "Não foi possível carregar o quadro." ou a mensagem do erro (seed). Link `?tarefa=` de tarefa que não existe (excluída ou de outra organização): toast "Tarefa não encontrada — pode ter sido excluída.". Apontamentos: "Não foi possível carregar os apontamentos.". Movimentos recusados: toast com a mensagem do servidor, sem o prefixo "[código]".
- **Atualizando:** o quadro não volta ao esqueleto durante recargas; movimento de cartão é otimista e volta em caso de erro. Cronômetro rodando: "Rodando desde HH:MM · <tempo>" atualiza a cada 30 s. Parado: "Total: 1h05" / "Total: 40 min".

### 7. Regras de negócio e por quê
1. **Para frente, só uma etapa por vez** — impede pular controles de qualidade como "Revisão interna".
2. **Para trás, qualquer distância, com motivo obrigatório** — o motivo fica no histórico (`pipeline_movimentos`) e torna o retrocesso auditável.
3. **Refação conta só quando o cartão sai da etapa de aprovação para trás** (arrastando com motivo ou pelo "Solicitar ajuste" do portal). Voltar de uma etapa posterior passando por cima da aprovação não conta. A contagem é atômica no banco.
4. **As regras usam papel e ordem das etapas, nunca o nome** — renomear etapas não quebra nada.
5. **Etapas com papel não podem ser excluídas nem desativadas**; o papel pode ser movido para outra etapa em "Papéis das etapas". **Nenhum papel some em silêncio**: não é possível deixar a esteira sem etapa "Aprovação do cliente" nem sem etapa "Agendado" — dar um papel a uma etapa que já carrega o outro é recusado.
6. **A tarefa nasce na primeira etapa ativa e herda o cliente da pauta** — uma única fonte para o cliente evita divergência.
7. **Editar não muda a etapa** — mudança de etapa só pelo arrastar, para que as regras 1–3 e as automações sempre valham.
8. **Cronômetro sempre do usuário logado; um por pessoa** — antes era possível lançar horas em nome de colegas. Um índice único no banco impede dois cronômetros abertos por usuário.
9. **Horas em segundos exatos**: o total soma os segundos antes de converter para minutos, então sessões curtas contam (três sessões de 40 s = 2 min).
10. **Gerar o link = "está com o cliente"**: a tarefa vai para aprovação na mesma hora. Um link novo invalida os anteriores não respondidos, para que um link antigo não decida uma rodada que o cliente não viu.
11. **Excluir tarefa com horas pede confirmação** — as horas alimentam o custo real do job e o DRE. Vale para **qualquer** apontamento, mesmo de poucos segundos ou com cronômetro rodando; a tela mostra o texto que o próprio servidor calculou.
12. **Automações de entrada de etapa** disparam ao arrastar, ao criar a tarefa (primeira etapa), ao gerar o link (etapa de aprovação) e na decisão do cliente no portal. Falhas de automação não desfazem o movimento.
13. **"Sem profissional vinculado"** nos apontamentos = o usuário não está ligado a um profissional em Custos; as horas ficam gravadas, mas sem custo/hora. Vincular em Custos vale para os próximos apontamentos.

### 8. Fluxo de dados
- Quadro: `EsteiraBoard` → seed `esteiraPipeline.useBoard` (chave `igig-esteira-board`) → `GET /api/esteira/board[?cliente_id=]` → `esteira_quadro.quadro` → `igig.pipeline_stages` (cria as padrão na primeira leitura) + `igig.tarefa`, com pauta (título, formato, data, marca), cliente (nome) e responsável (nome) anexados.
- Etapas: seed → `GET/POST/PATCH/DELETE /api/esteira/stages…` (escrita exige admin, `exigir_admin_do_quadro`) → `igig.pipeline_stages`. Excluir com `?reassign_to=` move as tarefas e grava uma linha por tarefa em `igig.pipeline_movimentos` (`responsavel_id` = admin que excluiu).
- Painel de papéis: `StageRolePanel` (componente compartilhado com o Comercial) lê as etapas de `esteiraPipeline.useStages` → `GET /api/esteira/stages` (a mesma consulta do "Configurar etapas"; filtra as inativas).
- Papel: `useAtribuirPapelEtapa` → `PATCH /api/esteira/stages/{id}/papel` `{papel}` (admin, `exigir_admin_do_quadro`) → `esteira_quadro.reatribuir_papel` (recusa com `papel_obrigatorio` se a etapa perderia outro papel).
- Deep link: `Esteira.tsx` lê `?tarefa=` → `EsteiraBoard` (`deepLinkTarefaId`) procura a tarefa nas colunas já carregadas → se não achar, `useTarefaPorId` → `GET /api/esteira/tarefas/{id}` (sem filtro de cliente) → `esteira_quadro.buscar_tarefa` (`igig.tarefa` + pauta, cliente e responsável) → abre os detalhes; 404 → toast e limpa o parâmetro.
- Mover: seed `useMoveCard` (otimista) → `POST /api/esteira/tarefas/{id}/mover-etapa` `{para_etapa_id, novo_indice?, motivo?}` → `esteira_quadro.mover_tarefa` → seed `move_card` (`tarefa.etapa_id`, `kanban_pos`, linha em `igig.pipeline_movimentos`) → RPC `igig.incrementar_refacoes` se saiu da aprovação para trás → `automacoes.ao_entrar_etapa`.
- Criar: `useCriarTarefa` → `POST /api/esteira/tarefas` `{pauta_id, titulo, responsavel_id?, prazo?}` → `esteira_quadro.criar_tarefa` → `igig.tarefa` + movimento de entrada → automações.
- Editar: `useAtualizarTarefa` → `PATCH /api/esteira/tarefas/{id}` → `igig.tarefa` (`titulo`, `responsavel_id`, `prazo`, `pauta_id`, `cliente_id`).
- Excluir: (se o seu cronômetro roda nesta tarefa) `useEncerrarTimer` → `POST …/timer/encerrar`; depois `useExcluirTarefa` → `DELETE /api/esteira/tarefas/{id}` (1ª tentativa) → 409 `horas_serao_perdidas` se houver apontamentos → `DELETE …?confirmar_perda_horas=true` ao tocar "Excluir mesmo assim" → 204; cascata em `igig.apontamento` e `igig.aprovacao`.
- Apontamentos: `useApontamentos` → `GET /api/esteira/tarefas/{id}/apontamentos` → `igig.apontamento` (mais recentes primeiro; `minutos`, `duracao_segundos`).
- Timer: `useIniciarTimer` → `POST …/timer/iniciar` (sem corpo; resposta com `timer_anterior_encerrado`); `useEncerrarTimer` → `POST …/timer/encerrar`.
- Link: `useEmitirLinkAprovacao` → `POST /api/esteira/tarefas/{id}/link-aprovacao` → `levar_para_aprovacao` → automações → `igig.aprovacao` (`token = <org_id>.<segredo 256 bits>`, `expira_em = agora + 14 dias`, `emitido_por`) → `revogar_pendentes` (põe `expira_em = agora` nos links anteriores não decididos). URL = `<origem do app>/aprovar/<token>`.
- Repertório: `RepertorioSidebar` → `useMarcas(clienteId)` + `useRepertorio` → `GET /api/marcas/repertorio/{cliente_id}[?marca_id=]`.
- Uso das horas: os segundos/minutos dos apontamentos alimentam o custo real do job e relatórios; o custo/hora vem do profissional.

### 9. Dependências de configuração
- **Profissionais em Custos** vinculados aos usuários: sem isso, horas "Sem profissional vinculado" (sem custo) e o responsável não recebe notificação do portal.
- **Etapa com papel "Aprovação do cliente"**: sem ela, gerar link dá 409 `etapa_aprovacao_ausente`.
- **Automações** configuradas na tela "Automações" (opcional).
- **Storage** configurado para as peças aparecerem no portal (ver Calendário).

### 10. Limitações conhecidas
- Na lista de apontamentos, cada linha mostra os minutos da sessão arredondados para baixo (uma sessão de 40 s aparece "0 min"), embora o "Total" some os segundos exatos.
- O "Total" do cronômetro é a soma de **todas as pessoas** na tarefa, não só do usuário.
- Não há lançamento manual, edição ou exclusão de apontamentos pela tela.
- Gerar o link **pula as etapas intermediárias** até a aprovação (não passa por "Revisão interna").
- Gerar de novo o link com a tarefa já na aprovação dispara de novo as automações da etapa de aprovação (dedução do código).
- O IgIg **não envia** o link ao cliente; é preciso copiar e mandar (WhatsApp, e-mail…). Não há botão para revogar um link sem gerar outro.
- A etapa com papel `agendado` não tem comportamento automático ligado a ela no código.
- Não existe tela de histórico de movimentos (os dados existem em `pipeline_movimentos`, inclusive os das tarefas movidas na exclusão de uma etapa).
- Na exclusão de etapa com realocação, as tarefas movidas não disparam as automações "Ao entrar na etapa" do destino.
- Excluir a tarefa encerra só o **seu** cronômetro; se um colega estiver com o cronômetro rodando nela, o tempo dele que ainda não foi encerrado não entra no aviso de horas.
- `SHEET_MOBILE` (janelas em tela cheia no celular) é um ajuste local marcado `NOC-REMEDIATE[seed-dialog-mobile-sheet]`.

### 11. Perguntas frequentes
- **P: Não consigo pular etapa.** R: Regra da esteira: avance uma etapa por vez. Voltar pode, com motivo.
- **P: Como transformo uma pauta em tarefa?** R: "Esteira" → "Nova tarefa" → escolha a pauta (a lista mostra título, data e cliente).
- **P: Criei a tarefa com o responsável errado. Preciso excluir?** R: Não. Abra a tarefa → "Editar" → ajuste → "Salvar".
- **P: Por que a refação subiu?** R: O cartão saiu da etapa "Aprovação do cliente" para trás (ajuste pedido pelo cliente no portal ou devolução manual com motivo).
- **P: Meu cronômetro parou sozinho.** R: Você iniciou o cronômetro em outra tarefa; só um roda por pessoa, e a tela avisa "O cronômetro de outra tarefa foi encerrado automaticamente.".
- **P: Aparece "Sem profissional vinculado" nas horas.** R: Em "Custos", vincule seu usuário ao seu cadastro de profissional. Vale para os próximos apontamentos.
- **P: Como mando para o cliente aprovar?** R: Abra a tarefa → "Gerar e copiar link de aprovação" → envie o link. Vale 14 dias e aceita uma resposta. Gerar outro link invalida o anterior não respondido.
- **P: Aparece "Esta tarefa já passou da aprovação do cliente."** R: Arraste a tarefa de volta (com motivo) para antes da aprovação e gere o link de novo.
- **P: Tentei excluir e apareceu "Isto tem … de horas apontadas…".** R: A tarefa tem horas registradas (mesmo que poucos segundos). Se quiser mesmo perder esses registros, toque "Excluir mesmo assim".
- **P: Cliquei na notificação e apareceu "Tarefa não encontrada — pode ter sido excluída.".** R: A tarefa foi excluída (o filtro "Cliente" não interfere: a tarefa abre mesmo sendo de outro cliente).
- **P: Excluí uma etapa e movi as tarefas para outra. Fica registrado?** R: Sim. Cada tarefa movida ganha uma linha no histórico de movimentos, em seu nome, com o motivo "Etapa "<nome>" excluída — carta movida para "<destino>".". Ainda não há tela para consultar esse histórico.
- **P: Não consigo pôr "Aprovação do cliente" na etapa "Agendado".** R: Cada etapa tem um papel só e nenhum papel pode ficar sem etapa. Primeiro mova "Agendado" para outra etapa, depois atribua "Aprovação do cliente".
- **P: Não vejo "Configurar etapas".** R: Só administradores da agência veem e alteram as etapas.
- **P: Não consigo excluir a etapa "Aprovação do cliente".** R: Ela tem um papel do sistema. Em "Papéis das etapas", passe o papel para outra etapa; depois ela pode ser excluída.

---

## Página: Calendário

### 1. Propósito
Planejar **o que será publicado e quando**. Cada item é uma **pauta** (título, cliente, marca, linha editorial, canal, funil, formato, data de publicação, legenda, direção de vídeo e peças). A legenda e as peças são o que o cliente vê no portal de aprovação.

### 2. Acesso
- **Rota:** `/calendario` (filtro opcional `?cliente=<id>`).
- **Menu lateral:** grupo "Principal", item **"Calendário"**, 7º item (logo depois de "Esteira"). Visibilidade segue `status_pagina` (rota `calendario` em produção).
- **Também em:** "Clientes" → cliente → aba **"Calendário"** (só as pautas daquele cliente; novas pautas já nascem nele).
- **Quem pode:** qualquer membro logado da agência vê, cria, edita, reagenda, remove pautas e envia/remove peças. Não há ação só-admin nesta página.

### 3. Layout
- **Cabeçalho:** título "Calendário Editorial"; subtítulo no desktop "Arraste uma pauta para outro dia para reagendar. Toque numa pauta para editar a legenda, as peças e a data."; no celular só "Toque numa pauta para editar a legenda, as peças e a data.". Seletor **"Cliente"** ("Todos os clientes" + clientes).
- **Navegação de mês:** "‹" ("Mês anterior"), nome do mês e ano (ex.: "setembro de 2026"), "›" ("Próximo mês"). Abre no mês atual; não há botão "hoje".
- **Formulário de nova pauta:** "Cliente…" (só quando não há cliente fixo/filtrado), título, data, botão "Adicionar".
- **Desktop (≥640px):** grade do mês com cabeçalhos "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom" (semana começa na segunda); dia 1 na coluna certa; hoje com borda destacada; cada pauta é um chip com título (e ícone de brilho se automática).
- **Celular (<640px):** **agenda** — só os dias com pauta, em ordem (ex.: "segunda-feira, 05/10", com " · hoje"); cada pauta é um botão grande com título, etiqueta do formato e selo "auto".
- **Seção "Sem data (N)":** abaixo do calendário, aparece sempre que existir pauta sem data de publicação (no escopo do filtro). Na página geral, mostra também o nome do cliente.
- **Editor da pauta** (janela; tela cheia no celular): título da pauta, selo "auto", botão "×" ("Fechar editor").

### 4. Campos

**Nova pauta**

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Cliente…" | lista | Sim (na página geral) | cliente precisa existir | vazio | Oculto na aba do cliente e quando o filtro "Cliente" está aplicado (usa o cliente do filtro). |
| Título ("Título da pauta", placeholder "Post institucional") | texto | Sim | 1–200 | vazio | — |
| "Data de publicação" | data | Não | — | vazio | Sem data, a pauta vai para o **dia 1 do mês exibido**. Hora sempre **09:00 (local)**. |

**Editor da pauta**

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Título" | texto | Sim | 1–200 | título atual | Salva ao sair do campo; vazio não é salvo. |
| "Marca" | lista ("Sem marca" + marcas do cliente) | Não | — | "Sem marca" | Salva na hora; trocar a marca **limpa a linha editorial**. |
| "Linha editorial" | lista ("—" + linhas da marca) se a marca tem linhas; senão texto livre | Não | até 80 | — | Placeholder do texto: "Esta marca não tem linhas editoriais cadastradas" ou "Escolha uma marca para listar as linhas". Lista salva na hora; texto salva ao sair do campo. |
| "Canal" | texto (placeholder "instagram, tiktok…") | Não | até 60 | — | Salva ao sair do campo. |
| Funil | 3 botões: "Topo de funil", "Meio de funil", "Fundo de funil" | Não | topo/meio/fundo | nenhum | Salva na hora; não dá para voltar a "sem funil". |
| "Formato" | lista: "—", feed, carrossel, reels, story, artigo, video | Não | valores da lista | "—" | Salva na hora; "—" limpa. |
| "Data de publicação" | data | Não | — | data atual | Salva na hora, sempre às 09:00 local. Apagar a data move a pauta para "Sem data". |
| "Legenda" | texto longo (placeholder "Escreva a legenda…") | Não | contador "N / 2200"; acima disso só aviso | — | Só salva com "Salvar textos". |
| "Anotações de direção de vídeo" | texto (placeholder "Cortes, trilha, enquadramento…") | Não | — | — | Só salva com "Salvar textos". |
| "Peças" → "Enviar peça" | arquivo | Não | PNG, JPEG, WebP, GIF, MP4, MOV; até 50 MB | — | O seletor só oferece esses formatos. Várias peças, uma de cada vez. |

### 5. Ações

| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Adicionar" | Título + cliente | Cria a pauta (09:00 local no dia escolhido ou no dia 1 do mês exibido); limpa título e data. | Nenhuma (a pauta aparece) | 404 "Cliente não encontrado" · 422 (título) · fallback "Não foi possível criar a pauta." |
| Arrastar chip para outro dia (só desktop) | Mesmo mês | Muda a data para aquele dia às 09:00 local (o horário anterior é substituído). | — | 404 "Pauta não encontrada" · fallback "Não foi possível reagendar." |
| Tocar numa pauta (grade, agenda ou "Sem data") | — | Abre o editor. | — | — |
| Mudar funil/formato/marca/linha (lista)/data | — | Salva na hora. Mudar a data para outro mês fecha o editor (a pauta sai da tela atual). | — | 404 "Pauta não encontrada" · 422 (valor inválido) · fallback "Não foi possível salvar." |
| Editar "Título"/"Canal"/linha (texto) e sair do campo | Valor mudou | Salva. | — | Iguais ao item acima. |
| "Salvar textos" | — | Salva Legenda + Direção de vídeo juntas. Botão mostra "Salvando…". | — | fallback "Não foi possível salvar." |
| Fechar o editor ("×", clicar fora ou Esc) com legenda/direção não salvas | Texto alterado | Pergunta do navegador: "Você tem alterações não salvas na legenda ou na direção de vídeo. Fechar sem salvar?" — cancelar mantém o editor aberto. | — | — |
| Lixeira ("Remover pauta") → "Confirmar remoção" | — | Sem horas nas tarefas: remove na hora. Com horas: abre "Excluir pauta com horas apontadas" com a mensagem "Isto tem <h> de horas apontadas em N apontamento(s). Confirme a exclusão para perder esses registros." e o botão "Excluir mesmo assim" (durante: "Excluindo…") ou "Cancelar". Remover apaga em cascata as tarefas da pauta, seus apontamentos, links de aprovação e as peças — **inclusive os arquivos das peças no armazenamento**. Se a pauta foi gerada automaticamente, ela **não** será recriada pela rotina diária nem por "Gerar pautas". | Nenhuma (editor fecha) | 404 "Pauta não encontrada" · fallback "Não foi possível remover." |
| "Enviar peça" | Arquivo aceito | Envia ao armazenamento (cada envio tem arquivo próprio, mesmo com nome repetido) e adiciona à lista. Botão mostra "Enviando…". | — | 422 "Formato não suportado: <tipo>. Envie PNG, JPEG, WebP, GIF, MP4 ou MOV." · 413 "Peça excede 50 MB" · 404 "Pauta não encontrada" · fallback "Não foi possível enviar a peça." |
| Olho ("Ver <arquivo>") | Link assinado disponível | Abre a peça em nova aba. | — | Sem link assinado o ícone não aparece. |
| Lixeira da peça ("Remover <arquivo>") | — | Janela "Remover peça" — "Remover esta peça? O cliente deixa de vê-la no portal de aprovação." — "Remover" (durante: "Removendo…") / "Cancelar". Apaga o registro e o arquivo do armazenamento. | — | 404 "Peça não encontrada" · fallback "Não foi possível remover a peça." |

### 6. Estados
- **Carregando:** esqueleto grande no lugar do calendário; peças: barra cinza.
- **Vazio:** agenda (celular): "Nenhuma pauta agendada em <mês de ano>."; grade (desktop): "Nenhuma pauta agendada neste mês."; peças: "Nenhuma peça enviada. O cliente aprova a arte junto com a legenda."
- **Erro:** "Não foi possível carregar o calendário."
- **Atualizando:** ao trocar de mês, as pautas do mês anterior continuam na tela até as novas chegarem. Pautas automáticas: selo "auto" e, no editor, "Gerada automaticamente a partir de um orçamento aceito.". Legenda acima de 2200: contador vermelho + "Acima do limite de 2200 caracteres do Instagram.".

### 7. Regras de negócio e por quê
1. **Hora padrão 09:00 local** ao escolher/arrastar uma data — horário padrão da agência. Pautas automáticas usam **10:00 (horário de Brasília)** para não "cair" no dia anterior por fuso.
2. **2200 caracteres é só aviso** — é o limite do Instagram, mas a pauta pode ser de outro canal.
3. **Legenda e direção só salvam com "Salvar textos"**; os demais campos salvam sozinhos. Fechar com texto não salvo pede confirmação.
4. **Pautas sem data** ficam fora da grade (a grade é por data), mas aparecem em "Sem data (N)" para receberem uma data.
5. **Remover pauta com horas apontadas pede segunda confirmação** mostrando quanto será perdido — as horas alimentam custo real e DRE.
6. **Pautas automáticas:** ao aceitar um orçamento (no modal ou arrastando o negócio para "Fechado" no Comercial), o sistema cria pautas dos itens **recorrentes** da seção **criação de conteúdo** para os próximos 30 dias: uma por dia da semana marcado, repetida pela quantidade por dia (títulos "Descrição (1/2)", "(2/2)"), formato = formato do produto/serviço. Uma rotina diária (06:45, horário de São Paulo) **mantém o calendário 30 dias à frente** para orçamentos aceitos cujo contrato está ativo ou ainda não existe. É idempotente por dia: nunca duplica. **Cada vaga (item recorrente × dia) é gerada uma única vez na vida**: fica registrada em `pauta_slot_gerado`, então uma pauta automática que você **apagou** ou **arrastou para outra data** nunca volta sozinha. Há também o botão "Gerar pautas" no orçamento aceito (recuperação, mesma regra). Funil, linha editorial, legenda e marca não são preenchidos. **Tarefas não são criadas automaticamente.**
7. **Peças: só imagem e vídeo, até 50 MB** — lista de formatos permitidos, não de proibidos.
8. **O link de cada peça é temporário** (1 hora, gerado a cada carregamento); o armazenamento é privado.
9. **Peça do plano × peça avulsa (Financeiro):** pautas geradas automaticamente pelo plano nunca viram excedente, mas ocupam o pacote do contrato; pautas criadas à mão aqui são **avulsas** e, se entregues (publicadas ou aprovadas pelo cliente no portal) além do que o plano deixou livre no pacote naquele mês, geram excedente na fatura do mês seguinte.

### 8. Fluxo de dados
- Mês: `CalendarioMes` → `useCalendario(inicio, fim, clienteId?)` → `GET /api/pautas/calendario?inicio=&fim=[&cliente_id=]` (início/fim enviados como instantes UTC de 00:00 local do dia 1 e 23:59:59 local do último dia) → `igig.pauta` com `data_publicacao` na janela (pautas sem data excluídas); cada item com `caracteres_copy` calculado no servidor.
- "Sem data" e seletor de pautas: `usePautas(clienteId?)` → `GET /api/pautas[?cliente_id=]`.
- Criar: `useCriarPauta` → `POST /api/pautas` `{cliente_id, titulo, data_publicacao}`.
- Editar/reagendar/tirar data: `useAtualizarPauta` → `PATCH /api/pautas/{id}` (só os campos enviados; `null` limpa).
- Remover: `useRemoverPauta` → `DELETE /api/pautas/{id}[?confirmar_perda_horas=true]` → lê as peças → cascata em `igig.tarefa` → `apontamento`, `aprovacao`; e `igig.peca` → apaga cada arquivo de peça do bucket `igig` (falha ao apagar um arquivo fica no log; a pauta já foi removida). O registro `pauta_slot_gerado` **não** é tocado.
- Peças: `usePecas` → `GET /api/pautas/{id}/pecas` (com `url` assinada); `useEnviarPeca` → `POST /api/pautas/{id}/pecas` (multipart, campo `arquivo`) → bucket `igig`, chave `<org_id>/pautas/<pauta_id>/<uuid>-<arquivo>` + `igig.peca`; `useRemoverPeca` → `DELETE /api/pautas/{id}/pecas/{peca_id}` → apaga linha e arquivo.
- Automáticas: `orcamentos.aceitar` / `comercial_funil._fechar` → `pautas.gerar`; job `igig_pautas_extensao` → `pautas.estender_pendentes`; botão "Gerar pautas" → `POST /api/orcamentos/{id}/gerar-pautas`. Gravam `gerada_automaticamente=true` e `orcamento_item_id`, e registram cada item × dia em `igig.pauta_slot_gerado` (consultado antes de gerar).

### 9. Dependências de configuração
- **Armazenamento:** `IGIG_STORAGE_KIND` (padrão "supabase"), `IGIG_STORAGE_BUCKET` (padrão "igig", privado; criado pela migration 028). Sem ele, o envio de peças falha ("Não foi possível enviar a peça." ou a mensagem do servidor) e o olho de ver peça não aparece.
- **Pautas automáticas:** produtos/serviços com formato; itens de orçamento recorrentes na seção criação de conteúdo com dias da semana marcados. A extensão diária depende do agendador estar ligado no ambiente (`NOCTUS_SCHEDULERS_ENABLED`, ligado só no container implantado; o valor em produção é configuração da frota, não do código).

### 10. Limitações conhecidas
- Não há visão semanal nem diária, só o mês (grade/agenda).
- Arrastar só no desktop e dentro do mesmo mês; no celular use a "Data de publicação" do editor.
- O horário não é editável: mudar a data sempre põe 09:00.
- Mudar a data para outro mês fecha o editor na hora; texto de legenda/direção não salvo nesse momento é perdido **sem** a pergunta de confirmação (dedução do código).
- A pergunta de "alterações não salvas" é a caixa nativa do navegador.
- Personas, termos proibidos e tom de voz da marca não são verificados contra a legenda.
- Remover pauta sem horas apontadas remove as tarefas dela sem aviso específico sobre tarefas.
- Peças não podem ser reordenadas nem substituídas (só remover e enviar de novo).
- Não existe publicação nas redes a partir desta tela: agendar e publicar ficam em Distribuição, e hoje nenhum canal está homologado (nada é publicado de verdade — ver Capítulos 4 e 5).
- Uma pauta automática apagada por engano não volta sozinha; recrie à mão (ela passa a contar como avulsa para excedentes).

### 11. Perguntas frequentes
- **P: Como reagendo pelo celular?** R: Toque na pauta → "Data de publicação".
- **P: Tirei a data de uma pauta e ela sumiu.** R: Ela está na seção "Sem data (N)", abaixo do calendário. Toque nela e escolha uma data.
- **P: Como vejo só um cliente?** R: Use o seletor "Cliente" no topo; o filtro fica no endereço e pode ser compartilhado.
- **P: A legenda passou de 2200, e agora?** R: É só um aviso do limite do Instagram; dá para salvar.
- **P: Escrevi a legenda e sumiu.** R: É preciso tocar em "Salvar textos". Ao fechar com texto não salvo, a tela pergunta antes.
- **P: Apareceram pautas com ícone de brilho/"auto".** R: São pautas automáticas dos itens recorrentes de um orçamento aceito; o sistema mantém 30 dias à frente.
- **P: Como ligo a pauta a uma marca?** R: No editor, campo "Marca". Depois, "Linha editorial" lista as linhas dessa marca.
- **P: Não consigo remover a pauta, abriu outra janela.** R: As tarefas dela têm horas apontadas; a janela mostra quanto será perdido. "Excluir mesmo assim" confirma.
- **P: Como vejo ou apago uma peça?** R: No editor, em "Peças": ícone de olho para ver, lixeira para remover.
- **P: Apaguei (ou mudei a data de) uma pauta automática. Ela vai voltar amanhã?** R: Não. Cada vaga do plano é gerada uma única vez; apagar ou mover é definitivo.
- **P: Apagar a pauta apaga os arquivos das peças?** R: Sim, os arquivos saem do armazenamento junto com a pauta.

---

## Funcionalidade: Central da Marca (card do cliente) + Cofre de Acessos

### 1. Propósito
O "manual da marca" de cada cliente: identidade visual (logo), paleta HEX, tom de voz e formalidade, termos proibidos, linhas editoriais e personas — o que designers e redatores consultam para produzir no padrão. Um cliente pode ter **várias marcas**. O **Cofre de Acessos** guarda com criptografia as credenciais das contas do cliente (Meta Business, TikTok, Drive…); é **um cofre por cliente**, compartilhado por todas as marcas.

### 2. Acesso
- **Caminho:** menu **"Clientes"** (3º item de "Principal") → tocar no cliente → aba **"Marcas"**. Abas do cartão: "Geral", "Dados", "Marcas", "Orçamentos & Contratos", "Calendário", "Esteira", "Financeiro".
- **Não existe item de menu "Marca".** A rota antiga `/marca` só redireciona para `/clientes`.
- **Também:** o painel "Repertório da marca" aparece nos detalhes de cada tarefa da Esteira (somente leitura).
- **Quem pode:** qualquer membro logado vê, cria, edita e remove marcas; cria, edita e remove acessos do cofre. **Revelar senha: só administradores** (dono/admin da organização ou admin da plataforma). Para não-admin, no lugar de "Revelar" aparece a etiqueta "Protegida" com cadeado.

### 3. Layout
Na aba "Marcas", de cima para baixo:
1. **Chips das marcas** (botões arredondados; o selecionado destacado; quebram linha no celular, sem rolagem lateral) + botão **"Nova marca"**. Por padrão a primeira marca da lista (ordem alfabética) vem selecionada.
2. **Editor da marca selecionada:** "Nome da marca" + lixeira; seções "Identidade visual", "Paleta", "Tom de voz" (com "Formalidade:"), "Termos proibidos", "Linhas editoriais", "Personas".
3. **Bloco "Cofre de Acessos":** aviso de cofre não configurado (se for o caso), formulário de novo acesso, lista de acessos.

No celular os botões ficam maiores (altura 40px) e os formulários do cofre empilham os campos.

### 4. Campos

**Marca**

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| Nome da nova marca (placeholder = nome do cliente ou "Nome da marca") | texto | Não | 1–200 | nome do cliente, ou "Nova marca" | Vazio → usa o padrão. |
| "Nome da marca" | texto | Sim | 1–200 | nome atual | Salva ao sair do campo. Vazio ou igual: nada é salvo e o nome antigo volta a aparecer. |
| Logo ("Enviar logo"/"Trocar logo") | arquivo | Não | PNG, JPEG, WebP; até 2 MB | — | Dica na tela: "PNG, JPEG ou WebP · até 2 MB."; o seletor de arquivo só oferece esses formatos (SVG não é oferecido nem aceito). |
| Paleta: "Nome da cor" (placeholder "primária") + "Cor" (seletor) | texto + cor | Nome sim | nome 1–60; HEX `#RGB` ou `#RRGGBB` | cor `#f97316` | "+" ("Adicionar cor") só ativo com nome. |
| "Tom de voz" (placeholder "Como a marca fala com o público…") | texto longo | Não | — | — | Salva ao sair, se mudou. |
| "Formalidade:" | 3 botões: "informal", "neutro", "formal" | Não | só esses | nenhum | Salva ao tocar; não volta a "nenhuma". |
| "Termos proibidos" (placeholder "Palavras e expressões que a marca não usa…") | texto longo livre | Não | — | — | Salva ao sair, se mudou. |
| "Linhas editoriais" (placeholder "Institucional, Educacional, Comercial…") | lista de nomes | Não | nome 1–80 | — | "+" ("Adicionar") ou Enter. Descrição não editável na tela. |
| "Personas" (placeholder "Nome da persona…") | lista de nomes | Não | nome 1–80 | — | Só o nome é editável; dores, desejos, faixa etária, ocupação e avatar existentes são preservados. |

**Cofre de Acessos**

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Rótulo" (placeholder "Meta Business") | texto | Sim | 1–120 | — | "Guardar" só ativo com rótulo. |
| "Usuário" (placeholder "usuário") | texto | Não | até 200 | — | — |
| "URL" (placeholder "https://…") | URL | Não | — | — | Presente na criação e na edição. |
| "Senha" (placeholder "senha") | senha (oculta) | Não | até 500 | — | Criptografada; nunca volta em listagens. |
| Edição: rótulo, usuário, URL, nova senha (placeholder "manter senha atual…") | — | Rótulo sim | iguais | valores atuais; senha vazia | Usuário/URL em branco **apagam** o valor. Senha em branco **mantém** a atual. |

### 5. Ações

| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Nova marca"/"Criar marca" → "Criar" (ou Enter) | — | Cria a marca e a seleciona. Botão mostra "Criando…". "Cancelar" fecha o formulário. | "Marca criada." | 404 "Cliente não encontrado" · 422 (nome) · fallback "Não foi possível criar a marca." |
| Tocar num chip | — | Seleciona a marca. | — | — |
| Sair de "Nome da marca" | Nome mudou e não vazio | Salva. | — | 404 "Marca não encontrada" · 422 · fallback "Não foi possível salvar a marca." |
| Lixeira ("Remover marca <nome>") → "Remover" | — | Janela "Remover marca": "Remover a marca <nome>? Paleta, tom de voz, linhas editoriais e personas dela são apagados. As pautas continuam, sem marca; o cofre do cliente não é afetado." Apaga a marca e o arquivo de logo dela; pautas ficam com marca vazia. Seleção passa para a primeira marca restante. Botão "Removendo…". | "Marca removida." | 404 "Marca não encontrada" · fallback "Não foi possível remover a marca." |
| "Enviar logo"/"Trocar logo" | Escolher arquivo | Envia na hora ("Enviando…"); troca apaga o arquivo antigo do armazenamento. O campo é limpo (dá para escolher o mesmo arquivo de novo). | Nenhuma (o logo aparece) | 422 "Formato não suportado: <tipo>. Envie PNG, JPEG ou WebP." · 413 "Logo excede 2 MB" · 404 "Marca não encontrada" · fallback "Não foi possível enviar o logo. Verifique o formato e o tamanho." (em vermelho abaixo do botão) |
| "+" ("Adicionar cor") | Nome preenchido | Adiciona a cor ao fim e salva. | — | 422 (nome/HEX) · fallback "Não foi possível salvar a marca." |
| Lixeira da cor ("Remover <nome>") | — | Remove e salva. | — | Idem. |
| Botão de formalidade | — | Salva na hora. | — | Idem. |
| Adicionar linha/persona ("+" ou Enter) | Nome preenchido | Adiciona e salva. | — | 422 (nome > 80) · fallback idem. |
| Tocar na etiqueta "<nome> ×" | — | Remove na hora, sem confirmação, e salva. | — | Idem. |
| "Guardar" (cofre) | Rótulo | Guarda o acesso; com senha, criptografa. Limpa o formulário. | Nenhuma | 409 "Cofre não configurado: defina IGIG_COFRE_KEY no ambiente. Nenhuma senha é gravada em texto puro." (guarde sem senha e peça ao responsável técnico) · 409 "IGIG_COFRE_KEY está mal configurada (não é uma chave Fernet válida). Peça ao responsável técnico para gerar uma nova chave." · 404 "Cliente não encontrado" · 422 (tamanhos) · fallback "Não foi possível guardar." |
| "Revelar" (só admin) | Acesso com senha | Mostra a senha em texto no lugar do botão; grava permanentemente quem revelou e quando. | — | 403 "Apenas administradores podem revelar senhas" · 404 "Acesso não encontrado" · 404 "Este acesso não possui senha armazenada" · 409 (chave ausente/mal configurada, mensagens acima) · fallback "Não foi possível revelar." |
| Olho riscado ("Ocultar senha de <rótulo>") | Senha revelada | Esconde a senha de novo. | — | — |
| Lápis ("Editar <rótulo>") → "Salvar" | Rótulo não vazio | Grava rótulo, usuário, URL; nova senha só se preenchida. "X" cancela. | — (sai do modo edição) | 409 (chave, ao trocar senha) · 404 "Acesso não encontrado" · 400 "Nenhum campo para atualizar" · 422 · fallback "Não foi possível salvar." |
| Lixeira ("Remover <rótulo>") → "Remover" | — | Janela "Remover acesso": "Remover o acesso <rótulo>? Isto não pode ser desfeito." Apaga o acesso. | — | 404 "Acesso não encontrado" · fallback "Não foi possível remover." |
| Tocar numa cor no "Repertório da marca" (Esteira) | — | Copia o HEX. | Ícone de confirmação por ~1 s | Cópia bloqueada: nada acontece, o HEX segue visível. |

### 6. Estados
- **Carregando:** esqueleto no lugar das marcas; esqueleto na lista do cofre.
- **Vazio:** "Nenhuma marca cadastrada para este cliente." + "Criar marca"; "Nenhum logo enviado."; "Nenhum acesso guardado."; acesso sem senha: etiqueta "sem senha"; sem usuário: "sem usuário".
- **Erro:** "Não foi possível carregar as marcas." (ou mensagem do servidor); "Não foi possível carregar o cofre." (ou mensagem do servidor). Cofre sem chave: "Cofre não configurado neste ambiente (IGIG_COFRE_KEY). Acessos sem senha ainda podem ser guardados; senhas serão recusadas até que o servidor seja configurado."
- **Atualizando:** botões mostram "Criando…", "Removendo…", "Enviando…"; após salvar, a lista de marcas e o repertório recarregam. Mensagens de erro nunca trazem o prefixo "[código]".

### 7. Regras de negócio e por quê
1. **N marcas por cliente; cofre por cliente** — o cofre guarda contas do cliente, não de uma marca.
2. **O logo guarda a chave do arquivo, e o link é gerado a cada leitura** (validade de 1 hora) — antes o link salvo expirava e o logo "sumia". Se o logo não aparecer, recarregue.
3. **SVG recusado no servidor** — SVG pode conter script executável quando aberto direto.
4. **Trocar o logo ou remover a marca apaga o arquivo antigo** do armazenamento.
5. **Senha nunca aparece em listagens** (nem criptografada); só um booleano "tem senha".
6. **Sem chave, o cofre recusa senha em vez de gravar em texto puro.** Nunca cole a senha em outro campo.
7. **Só admin revela**, e o papel é lido de fonte confiável no servidor (não de dados que o usuário pode alterar). Cada revelação fica registrada em tabela própria.
8. **Senha em branco na edição sempre mantém a atual** — não há como apagar uma senha pela tela.
9. **Remover marca não apaga pautas** (ficam sem marca) nem o cofre.
10. **Repertório na tarefa:** mostra a marca da pauta; se a pauta não tem marca e o cliente tem várias, pede para escolher (sem escolha arbitrária); com uma só marca, mostra direto.

### 8. Fluxo de dados
- Listar: `useMarcas(clienteId)` → `GET /api/marcas?cliente_id=` → `igig.marca` (ordem alfabética), `logo_url` assinada a partir de `logo_key`.
- Criar: `useCriarMarca` → `POST /api/marcas` `{cliente_id, nome}`.
- Editar: `useAtualizarMarca` → `PATCH /api/marcas/{id}` → colunas `nome`, `paleta`, `tom_de_voz`, `termos_proibidos`, `nivel_formalidade`, `linhas_editoriais`, `personas` (campos nulos ignorados).
- Remover: `useRemoverMarca` → `DELETE /api/marcas/{id}` → linha apagada; `pauta.marca_id` vira NULL; arquivo de logo apagado.
- Logo: `useEnviarLogo` (`api.upload`, campo `arquivo`) → `POST /api/marcas/{id}/logo` → bucket `igig`, chave `<org_id>/marcas/<marca_id>/logo-<uuid>.<ext>` → `marca.logo_key` → resposta `{storage_key, url}`.
- Repertório: `useRepertorio` → `GET /api/marcas/repertorio/{cliente_id}[?marca_id=]` → marca pedida (se for do cliente) ou a primeira em ordem alfabética; sem marca, 200 só com o nome do cliente.
- Cofre: `useAcessos` → `GET /api/marcas/acessos/{cliente_id}` → `{cofre_configurado, itens[]}`; `useCriarAcesso` → `POST /api/marcas/acessos`; `useAtualizarAcesso` → `PATCH /api/marcas/acessos/{id}`; `useRevelarSenha` → `POST /api/marcas/acessos/{id}/revelar` → `igig.cofre_revelacoes` + log `cofre: senha revelada…`; `useRemoverAcesso` → `DELETE /api/marcas/acessos/{id}`. Criptografia Fernet em `igig.acesso.senha_cifrada`.
- Tabelas: `igig.marca` (006 + `logo_key` 015), `igig.acesso` (008), `igig.cofre_revelacoes` (028). Isolamento por organização. Remover um cliente apaga em cascata marcas, acessos e pautas.

### 9. Dependências de configuração
- **`IGIG_COFRE_KEY`** (chave Fernet, fora do banco). Ausente: aviso vermelho e senhas recusadas (409). Mal formada: o aviso **não** aparece (a tela considera configurado), mas guardar/revelar senha dá 409 "IGIG_COFRE_KEY está mal configurada…". Trocar a chave impede revelar as senhas antigas (dedução do código; não há rotina de migração de chave).
- **Armazenamento** (`IGIG_STORAGE_KIND`, `IGIG_STORAGE_BUCKET`="igig") para o logo.

### 10. Limitações conhecidas
- Não há remoção de logo (só troca).
- Cores da paleta não são editáveis nem reordenáveis (remova e adicione de novo).
- Formalidade não volta a "nenhuma" (decisão mantida).
- Personas: só o nome; linhas editoriais: descrição não editável.
- Termos proibidos são texto livre e não são verificados nas legendas.
- Não há tela para consultar o histórico de revelações (os dados existem).
- Não é possível apagar uma senha guardada; os campos "plataforma" e "observações" do acesso não aparecem na tela.
- Remover linha editorial/persona não pede confirmação.

### 11. Perguntas frequentes
- **P: Cadê a Central da Marca?** R: "Clientes" → abra o cliente → aba "Marcas".
- **P: Posso ter mais de uma marca por cliente?** R: Sim, use "Nova marca".
- **P: Meu logo não aparece.** R: Recarregue a tela; o link da imagem é temporário. Formatos: PNG, JPEG ou WebP, até 2 MB (SVG não é aceito).
- **P: Não vejo o botão "Revelar".** R: Só administradores revelam senhas; para os demais aparece "Protegida".
- **P: Apareceu "Cofre não configurado".** R: O servidor está sem a chave `IGIG_COFRE_KEY`. Guarde o acesso sem senha e peça ao responsável técnico.
- **P: Como escondo uma senha revelada?** R: Toque no ícone de olho riscado ao lado dela.
- **P: Como apago o usuário de um acesso?** R: Lápis → apague o campo → "Salvar". (A senha em branco mantém a atual.)
- **P: Onde vejo a paleta enquanto trabalho numa tarefa?** R: Nos detalhes da tarefa, painel "Repertório da marca" (no celular, toque para abrir). Tocar numa cor copia o HEX.
- **P: Removi a marca; perdi as pautas?** R: Não. As pautas continuam, sem marca.

---

## Funcionalidade: Portal de Aprovação público (/aprovar/:token)

### 1. Propósito
Página pública e sem marca do IgIg onde o **cliente final** da agência vê a peça e a legenda de uma tarefa e responde **"Aprovar conteúdo"** ou **"Solicitar ajuste"**. A resposta move o cartão na esteira e avisa a agência.

### 2. Acesso
- **Rota:** `/aprovar/<token>` (rota pública; sem login e sem menu lateral).
- **Quem pode:** qualquer pessoa com o link — o token é a credencial. Trate o link como uma senha.
- **Quem gera:** qualquer membro da agência, nos detalhes da tarefa → "Gerar e copiar link de aprovação" (ver Página: Esteira).

### 3. Layout
Um cartão centralizado (largura máxima média), igual no celular e no desktop:
- nome do cliente (pequeno, em maiúsculas, no topo), título da **tarefa**, formato (ex.: "carrossel");
- **peças**: imagens (texto alternativo "Peça N — <título>") e vídeos com player; se uma peça não carregar: "A peça não pôde ser carregada. Revise pela legenda ou peça um novo link.";
- "Legenda" e "Direção de vídeo" (quando existem);
- campo de observações e os botões "Aprovar conteúdo" / "Solicitar ajuste".

O cliente **não** vê: nomes da equipe, responsável, refações, IDs internos, data de publicação, logo da marca, nem a marca do IgIg/da agência.

### 4. Campos

| Campo | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Observações (opcional para aprovar, recomendado ao pedir ajuste)" (placeholder "O que você gostaria de ajustar?") | texto longo | Não | até 2000 caracteres | vazio | Ao pedir ajuste, vira a nota "Cliente pediu: “…”" na tarefa. |

### 5. Ações

| Ação | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| Abrir o link | Link existe, não expirou (14 dias) e não foi invalidado | Mostra o conteúdo **atual** da pauta (se a agência mudou a legenda ou as peças depois, o cliente vê a versão nova). | — | 404 → "Link inválido ou expirado" · 423 `portal_bloqueado` → "Portal temporariamente indisponível" + "Contate a agência." (bloqueio por inadimplência ligado) · 429 → "Muitas tentativas" · falha de conexão/5xx → "Não foi possível carregar" |
| "Aprovar conteúdo" | Tarefa na etapa "Aprovação do cliente"; link não respondido | A tarefa avança **uma etapa** (padrão: "Pronto para agendamento"; histórico "Aprovado pelo cliente"); limpa a nota antiga "Cliente pediu…"; dispara automações da etapa de destino; grava decisão; notifica a agência. Se a aprovação for a última etapa, o cartão não se move. | "Resposta registrada" + "Obrigado! Sua agência já foi notificada." (ou "Obrigado pela resposta." se ninguém foi notificado) | Qualquer erro: "Não foi possível registrar sua resposta. Tente novamente." (inclui 404 link usado/expirado, 409 `fora_de_aprovacao`, 423 `portal_bloqueado`, 429) |
| "Solicitar ajuste" | Idem | A tarefa **volta uma etapa** (padrão: "Revisão interna"); **refação +1**; grava a observação como "Cliente pediu"; histórico = observação ou "Ajuste solicitado pelo cliente"; automações; notificação. | Idem | Idem |

**Notificação no sininho do IgIg** (tipo `igig_aprovacao_cliente`) para quem gerou o link e para o usuário ligado ao profissional responsável: título "Cliente aprovou: <tarefa>" ou "Cliente pediu ajuste: <tarefa>"; mensagem = observação, ou "Conteúdo aprovado." / "Ajuste solicitado."; link `/esteira?tarefa=<id>`, que abre direto os detalhes da tarefa (mesmo fora do filtro de cliente). Se a notificação falhar, a decisão vale mesmo assim.

### 6. Estados
- **Carregando:** esqueleto cinza.
- **Link inválido** (desconhecido, malformado, expirado, invalidado por um link mais novo, ou já respondido na hora de decidir): "Link inválido ou expirado" + "Peça um novo link de aprovação à sua agência."
- **Portal bloqueado (423, cliente com fatura vencida além do limite configurado):** ícone de cadeado + "Portal temporariamente indisponível" + "Contate a agência." — nenhum conteúdo é mostrado, e nunca uma tela em branco ou erro genérico.
- **Muitas tentativas (429):** "Muitas tentativas" + "Aguarde um minuto e tente novamente."
- **Sem conexão / erro do servidor:** "Não foi possível carregar" + "Verifique sua conexão e tente novamente."
- **Já respondido** (reabrir um link respondido antes de expirar, ou logo após responder): "Resposta registrada" + "Obrigado! Sua agência já foi notificada." (só quando a resposta desta visita notificou alguém) ou "Obrigado pela resposta.". O conteúdo **não** é mostrado de novo.
- **Retirado da aprovação pela agência:** conteúdo só para leitura + "Este conteúdo não está mais aguardando a sua aprovação. Se precisar, fale com a sua agência." (sem botões).
- **Erro ao responder:** "Não foi possível registrar sua resposta. Tente novamente."
- **Enviando:** botões desabilitados.

### 7. Regras de negócio e por quê
1. **Link vale 14 dias e aceita uma decisão** — um link sem validade seria uma porta aberta permanente para o conteúdo do cliente.
2. **Uma mensagem só para link desconhecido/expirado/usado** — impede "testar" quais links existem.
3. **Gerar um link novo invalida os anteriores não respondidos** — um link antigo não decide uma rodada que o cliente não viu. Links já respondidos ficam como registro.
4. **Só decide com a tarefa na etapa de aprovação** — se a agência puxou o conteúdo de volta, o link antigo não aprova algo que mudou.
5. **Token = `<org_id>.<segredo aleatório de 256 bits>`** — o portal descobre a organização pelo token e faz leituras restritas a ela.
6. **Limite de 60 acessos por minuto por IP** (GET e POST).
7. **Projeção estreita:** o portal nunca devolve dados internos da agência.
8. **"Sua agência já foi notificada" só aparece quando a notificação de fato foi gravada** para ao menos um destinatário.
9. **Bloqueio por inadimplência (opcional, desligado por padrão):** com `IGIG_PORTAL_BLOQUEIO_DIAS` = N > 0, se o cliente dono da tarefa tem alguma fatura vencida há **mais de** N dias, abrir o link e responder são recusados com 423 `portal_bloqueado`. A checagem é feita na hora (mesma consulta da faixa de faturas em atraso do Financeiro), sem esperar a rotina diária, e vem **antes** de qualquer outra validação da decisão — uma resposta nesse estado nunca é aplicada. *Por quê:* bloquear o cliente é uma política que a agência escolhe ligar, nunca um efeito colateral. O link continua válido: regularizada a fatura (paga ou cancelada), o mesmo link volta a funcionar.
10. **Aprovação conta como entrega:** enquanto nenhum canal publica de verdade, a aprovação do cliente aqui é o que marca a peça como "entregue" para o cálculo de excedentes do Financeiro (a data da primeira aprovação).

### 8. Fluxo de dados
- Ver: `AprovacaoPublica` → `useAprovacaoPublica(token)` (sem novas tentativas) → `GET /api/esteira/aprovar/{token}` (público, limite `WEBHOOK_RATE_LIMIT`) → `_resolver_link` (`igig.aprovacao` pelo token; 404 se não existe/expirou) → `igig.tarefa` → `igig.pauta` → nome em `igig.cliente` → `igig.peca` com URLs assinadas → `{titulo, copy_texto, direcao_video, formato, cliente_nome, pecas[], ja_decidida, aguardando_aprovacao}`.
- Bloqueio (GET e POST): `_recusar_se_bloqueado` → `financeiro_service.cliente_bloqueado_no_portal(dias_bloqueio=IGIG_PORTAL_BLOQUEIO_DIAS)` → `FinanceiroService.inadimplentes` (faturas `igig.fatura` não pagas/canceladas com vencimento passado) → 423 `{detail, code:"portal_bloqueado"}`.
- Decidir: `useDecidirAprovacao(token)` → `POST /api/esteira/aprovar/{token}` `{decisao: "aprovado"|"ajuste", observacao}` → 404 se já decidido → 423 se bloqueado → `esteira_quadro.decidir_aprovacao` (409 `fora_de_aprovacao`; move ±1 etapa; ajuste: `incrementar_refacoes` + `observacao_cliente`; aprovado: limpa `observacao_cliente`) → `automacoes.ao_entrar_etapa` → `registrar_decisao` (`decisao`, `observacao`, `decidido_em`) → `notificar` em `public.notifications` → resposta `{ok, decisao, notificado}`.
- Usa clientes de serviço (sem usuário logado); todas as leituras filtram pelo `org_id` do token.

### 9. Dependências de configuração
- **Etapa com papel "Aprovação do cliente"** na esteira.
- **Armazenamento** configurado para as peças (URLs temporárias). Sem URL, aparece o aviso de peça não carregada.
- **`WEBHOOK_RATE_LIMIT`** (padrão "60/minute").
- **Profissionais vinculados a usuários** (Custos) para o responsável ser notificado.
- **`IGIG_PORTAL_BLOQUEIO_DIAS`** (padrão 0 = desligado): N > 0 bloqueia o portal para clientes com fatura vencida há mais de N dias (regra 9). É configuração do servidor — a agência não liga pela tela; peça ao responsável técnico.

### 10. Limitações conhecidas
- O bloqueio por inadimplência vale para a organização inteira (um único N no servidor); não há exceção por cliente nem liga/desliga pela tela.
- Qualquer erro ao responder mostra a mesma mensagem genérica, inclusive quando a agência já retirou o conteúdo da aprovação, o link foi invalidado ou o portal ficou bloqueado entre abrir e responder.
- Reabrir um link já respondido mostra só "Resposta registrada", sem o conteúdo e sem dizer qual foi a decisão.
- O portal não mostra o logo da marca nem a data de publicação.
- O IgIg não envia o link por e-mail ou WhatsApp.
- O link expira em 14 dias fixos (não configurável).

### 11. Perguntas frequentes
- **P: O cliente diz que o link está inválido.** R: Pode ter expirado (14 dias), já ter sido respondido ou ter sido substituído por um link mais novo. Gere um novo link na tarefa.
- **P: O cliente vê "Muitas tentativas".** R: Mais de 60 acessos por minuto do mesmo IP; peça para aguardar um minuto.
- **P: O cliente vê "Não foi possível carregar".** R: Falha de conexão ou instabilidade; tentar de novo depois. O link continua válido.
- **P: O cliente precisa de login?** R: Não. O link é a credencial; não o publique em lugares abertos.
- **P: Mudei a legenda depois de enviar o link. O cliente vê a nova?** R: Sim, o portal sempre mostra o conteúdo atual da pauta.
- **P: O que acontece quando o cliente aprova?** R: O cartão avança uma etapa (padrão: "Pronto para agendamento") e quem gerou o link e o responsável recebem notificação.
- **P: E quando pede ajuste?** R: O cartão volta uma etapa (padrão: "Revisão interna"), conta uma refação e a observação aparece na tarefa como "Cliente pediu: …".
- **P: O cliente vê quem da equipe fez a peça?** R: Não. O portal não mostra equipe, responsável, refações nem dados internos.
- **P: O cliente aparece como "Este conteúdo não está mais aguardando a sua aprovação".** R: A tarefa foi tirada da etapa de aprovação pela agência. Quando voltar, gere um novo link.
- **P: O cliente vê "Portal temporariamente indisponível".** R: O bloqueio por inadimplência está ligado no servidor e esse cliente tem fatura vencida há mais dias que o limite. Regularize a fatura (Financeiro → "Marcar paga") e o mesmo link volta a funcionar.

---

---

# Capítulo 4 — Distribuição, Financeiro, Integrações, Relatórios

## IgIg — Guia: Distribuição, Financeiro, Integrações e Relatórios

> Fonte: código final do IgIg (backend FastAPI + frontend React). Rótulos, mensagens e avisos entre "aspas" são copiados do código. Quando algo não pôde ser confirmado no código, está marcado "(não confirmado no código)".
>
> Convenções usadas em todo este arquivo:
> - **Competência** = o mês a que uma cobrança se refere, no formato `AAAA-MM` (ex.: `2026-09`). NÃO é a data de vencimento.
> - **Agência (org)** = a organização do usuário logado. Todo dado é isolado por agência (cada linha tem `org_id`; o banco aplica RLS).
> - **Administrador da agência** = usuário com papel de proprietário/administrador da agência (`ADMIN_ROLES`) ou administrador da plataforma/produto. É a mesma regra no servidor (`exigir_admin_da_org`) e na tela (`useIsOrgAdmin`). **Membro** = qualquer outro usuário autenticado da agência.
> - Mensagens de erro do servidor aparecem nas notificações (toast) sem o prefixo de status HTTP (a tela usa `describeError`, que remove o "[409] ").
> - Botões com confirmação usam uma janela padrão com o botão "Cancelar" (fecha sem fazer nada) e o botão de confirmação citado em cada ação.

---

## Página: Distribuição

### 1. Propósito
Colocar pautas do Calendário Editorial na fila de publicação de cada rede social (Instagram, Facebook, TikTok, LinkedIn), disparar a publicação, cancelar agendamentos, registrar manualmente métricas de engajamento de posts publicados e ver o **BI de Eficiência** (taxa de refação, horas e custo real por cliente). Título na tela: "Distribuição e Métricas"; subtítulo: "Fila de publicação e eficiência por cliente."

Importante para quem responde usuários: **hoje nenhuma rede social publica de verdade.** Sem token o sistema recusa; com token, a tentativa falha com "A integração com {canal} ainda não está disponível (homologação da API pendente)." Nada é marcado como `publicada` sem confirmação real da plataforma.

### 2. Acesso
- **Rota:** `/distribuicao`.
- **Menu lateral:** grupo "Principal", item "Distribuição" — 8º item (Dashboard, Comercial, Clientes, Orçamentos, Produtos e Serviços, Esteira, Calendário, **Distribuição**, Financeiro, Integrações, Automações, Custos, Equipe). No celular, abra o menu (ícone de menu) e toque em "Distribuição". A visibilidade do item no menu também depende da configuração de status de página da plataforma (`status_pagina`, rota `distribuicao`).
- **Quem vê:** qualquer usuário autenticado da agência.
- **Quem executa:** todas as ações desta página (agendar, publicar, cancelar, registrar métricas, ver BI) estão liberadas para **qualquer membro** — o servidor não exige administrador em nenhum endpoint de `/api/distribuicao`. Não há ações só-admin nesta página.

### 3. Layout
De cima para baixo:
1. **"BI de Eficiência"** — tabela com colunas "Cliente", "Tarefas", "Refações", "Taxa", "Horas", "Custo real". Logo abaixo de um cliente com horas sem custo aparece uma linha vermelha com ícone de alerta e o texto do alerta. No celular a tabela rola para o lado.
2. **"Agendar publicação"** (ícone de calendário) — formulário "Pauta", "Canal", "Quando" e botão "Agendar". Celular (≤640px): campos um embaixo do outro; desktop: tudo numa linha (Pauta mais larga).
3. **"Fila — prontas para publicar"** (ícone de relógio) — publicações `agendada` cujo horário já passou. Cada linha: etiqueta do canal, título da pauta, "agendada para {data e hora}" e botão "Publicar agora".
4. **"Todas as publicações"** — histórico completo, ordenado pela data agendada (mais antiga primeiro). Cada linha: etiqueta de status (`agendada`, `publicando`, `publicada`, `falhou`, `cancelada`), canal, título da pauta, "publicada em {data}" ou "agendada para {data}" (ou "sem data"), e, se houve erro, o texto do erro em vermelho seguido de "(tentativas: N)". Botões conforme o status: "Publicar" + ícone de proibido ("Cancelar publicação") para itens que não estão `publicada` nem `cancelada`; link "ver post" se houver permalink; botão "Métricas" só para `publicada`, que abre/fecha o painel de métricas logo abaixo da linha.
- Painel de métricas: histórico de coletas (mais recente primeiro) com data/hora, "♥" curtidas, "💬" comentários, "↗" compartilhamentos, "alcance", "bio", "views"; formulário com seis campos numéricos e botão "Registrar coleta"; aviso fixo "Entrada manual — a coleta automática via Meta/TikTok/LinkedIn depende dos tokens de canal ainda não configurados em Integrações."
- Datas e horas aparecem no formato do navegador em pt-BR (ex.: "28/09/2026, 14:00:00").

### 4. Campos
| Campo (rótulo exato) | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Pauta" | lista (títulos das pautas) | Sim | pauta precisa existir na agência (404 se não) | "Selecione…" ("Carregando…" enquanto carrega) | Sem pautas, o bloco mostra "Nenhuma pauta cadastrada. Crie uma no Calendário Editorial." com link para `/calendario` |
| "Canal" | lista | Sim | `instagram`, `facebook`, `tiktok`, `linkedin` (em minúsculas) | `instagram` | Outro valor → 422 (não acontece pela tela) |
| "Quando" | data e hora local | Sim | precisa ser data/hora válida (422 senão); **não precisa ser no futuro** | vazio | O horário do aparelho é convertido para UTC antes do envio |
| "Curtidas", "Comentários", "Compart.", "Alcance", "Cliques bio", "Visualizações" (painel Métricas) | número inteiro | Não | ≥ 0 (negativo → 422) | vazio = 0 | Campo vazio conta como 0 observado, não "desconhecido" |

### 5. Ações
| Ação (botão/gesto exato) | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Agendar" (texto "Agendando…" durante envio) | Pauta e Quando preenchidos (botão desabilitado senão) | Cria em `igig.publicacao` uma linha `agendada` com `agendada_para`, `tentativas=0`. Limpa Pauta e Quando. Recarrega todas as listas da página. | "Publicação agendada" | 404 "Pauta não encontrada" (pauta apagada com a tela aberta — recarregue). 409 "Esta pauta já tem publicação ativa em {canal}" (já existe publicação não cancelada da mesma pauta no mesmo canal — cancele a existente para reagendar, ou use "Publicar" nela). 422 validação de data/canal. Genérico: "Não foi possível agendar." |
| "Publicar agora" (Fila) / "Publicar" (Todas as publicações) | Item não `publicada` nem `cancelada`; botão desabilitado enquanto outra publicação está sendo enviada | 1) Recusa se já publicada/cancelada/em andamento. 2) Resolve o token do canal (da agência, depois do servidor). Sem token ou token ilegível → **recusa (409) sem tocar no status** (continua `agendada`/`falhou`, não conta tentativa). 3) Com token: marca `publicando`, chama o publicador real. Hoje ele sempre falha → linha vira `falhou`, grava o motivo em `erro` (até 2000 caracteres), `tentativas + 1`, resposta HTTP 200 (sem toast; o erro aparece na linha). 4) Sucesso (futuro, quando homologado): `publicada`, `external_id`, `permalink`, `publicada_em`, e grava `pauta.publicado_em`. | Nenhum toast; a linha atualiza | 409 "Publicação já enviada". 409 "Publicação cancelada não pode ser executada." 409 "Esta publicação já está sendo executada." (duplo toque ou execução simultânea). 409 "Canal {canal} não está configurado. Conecte um token em Integrações antes de publicar." (peça a um administrador para conectar o canal em Integrações). 409 "O token salvo para {canal} não pôde ser lido. Reconecte o canal." (o canal também passa a mostrar "reconectar" em Integrações; um administrador deve colar o token de novo). 404 "Publicação não encontrada". Falha registrada na linha (não é toast): "A integração com {canal} ainda não está disponível (homologação da API pendente)." — nada a fazer pelo usuário. Genérico: "Não foi possível publicar." |
| Ícone de proibido ("Cancelar publicação") → confirmação | Item não `publicada` nem `cancelada` | Abre janela "Cancelar publicação": "Cancelar esta publicação? Ela sai da fila e da lista de pendentes; para publicar de novo será preciso agendar outra vez." Botão "Cancelar publicação" ("Cancelando…"). Confirmado: status `cancelada`, histórico mantido, libera a combinação pauta+canal para novo agendamento. Cancelar algo já cancelado não dá erro (idempotente). | Nenhum toast; os botões da linha somem | 409 "Publicação já enviada não pode ser cancelada". 404 "Publicação não encontrada". Genérico: "Não foi possível cancelar a publicação." |
| "Métricas" | Item `publicada` | Abre/fecha o painel de métricas da publicação | — | — |
| "Registrar coleta" ("Salvando…") | Painel aberto | Insere uma coleta em `igig.metrica` com `coletada_em = agora` e os seis contadores; limpa os campos. Coletas só se somam — nunca substituem. | Campos limpam (sem toast) | Texto no painel: "Não foi possível registrar a coleta." (ex.: número negativo → 422; publicação inexistente → 404 "Publicação não encontrada") |
| Link "ver post" | Existe `permalink` | Abre o post na rede em nova aba | — | — |

### 6. Estados
- **Carregando:** blocos cinza (skeleton) no BI, na Fila, em "Todas as publicações" e no painel de métricas; lista de pautas mostra "Carregando…".
- **Vazio:** BI: "Nenhum cliente ainda." · Fila: "Nada na fila agora." · Todas as publicações: "Nenhuma publicação ainda. Use "Agendar publicação" acima." · Agendar sem pautas: "Nenhuma pauta cadastrada. Crie uma no Calendário Editorial." · Métricas: "Nenhuma coleta registrada ainda."
- **Erro:** BI: "Não foi possível carregar o BI de eficiência." · Fila: "Não foi possível carregar a fila." · Todas as publicações: "Não foi possível carregar as publicações." · Métricas: a mensagem do servidor ou "Não foi possível carregar as coletas de métricas." (nunca "Nenhuma coleta registrada ainda." no lugar de um erro).
- **Atualizando:** após cada ação, a página recarrega todas as consultas de distribuição; não há indicador visual específico de "atualizando".

### 7. Regras de negócio e por quê
1. **Uma publicação ativa por pauta + canal** (índice único parcial `idx_igig_publicacao_unica`, ignora canceladas). *Por quê:* uma duplicata postaria duas vezes na conta real do cliente. Uma publicação `publicada` ou `falhou` continua ocupando a vaga; para uma que falhou, use "Publicar" de novo.
2. **Cada canal é uma publicação separada.** A mesma pauta no Instagram e no TikTok vira duas publicações, cada uma com status, erro e tentativas próprios.
3. **Nada é marcado `publicada` sem um identificador confirmado pela plataforma (`external_id`).** *Por quê:* um post que o cliente nunca viu aparecendo como publicado destrói a confiança no módulo, e sem o id não há como buscar métricas.
4. **Canal sem credencial RECUSA, não simula.** Sem token (nem da agência, nem do servidor) a publicação é recusada com 409 e continua como estava. *Por quê:* antes o sistema "fingia" sucesso com um link falso; agora não existe caminho em produção que publique em simulação.
5. **Recusa por credencial não é tentativa.** Falta de token ou token ilegível não muda o status nem soma em "tentativas" — depois de conectar o canal, basta tocar "Publicar" de novo.
6. **Integração pendente de homologação é falha registrada, não problema de credencial.** Ela vira `falhou` com o motivo, mas **não** marca o canal como "reconectar" em Integrações. *Por quê:* reconectar não resolveria; o aviso levaria o operador a fazer algo inútil.
7. **Token ilegível marca "reconectar".** Se a chave do cofre do servidor mudou e o token gravado não pode ser decifrado, o erro é gravado na integração (`ultimo_erro`) — aqui reconectar resolve.
8. **Trava contra execução dupla:** o status `publicando` é gravado imediatamente antes da tentativa; uma segunda execução recebe "Esta publicação já está sendo executada.".
9. **Falhas não voltam para a Fila.** A Fila só mostra `agendada` com horário ≤ agora. Itens `falhou` ficam em "Todas as publicações", com o erro e o botão "Publicar".
10. **Agendar no passado é permitido** — o item aparece imediatamente na Fila.
11. **Métricas são somente-adição.** *Por quê:* as métricas mudam ao longo da primeira semana do post; substituí-las destruiria o histórico.
12. **BI — Tarefas por cliente:** cada tarefa da Esteira pertence a uma pauta, e a pauta a um cliente. Tarefas cuja pauta não tem cliente conhecido são ignoradas.
13. **BI — Refações:** soma do contador `refacoes` das tarefas do cliente (o contador é incrementado pela Esteira/portal de aprovação — ver guia da Esteira).
14. **BI — Taxa** = refações ÷ tarefas, arredondada em 3 casas, exibida com 2 casas e vírgula (ex.: "0,40"). **Não é porcentagem:** 0,40 = 0,4 refação por tarefa. Sem tarefas, "0,00".
15. **BI — Horas** = soma da duração **exata em segundos** dos apontamentos (cronômetro da Esteira) das tarefas do cliente, convertida em minutos inteiros e depois em horas (2 casas), exibida como "1,5 h" / "39 h". Apontamentos antigos sem a duração em segundos usam os minutos gravados. Inclui TODAS as horas, mesmo as que não puderam ser custeadas.
16. **BI — Custo real** = Σ (segundos ÷ 3600 × custo/hora efetivo de quem apontou), arredondado em centavos, sobre **todo o histórico** (sem filtro de período). *Por quê (segundos):* somar minutos já arredondados por sessão fazia três sessões de 40 s custarem R$ 0,00; agora custam o equivalente a 2 minutos.
17. **Qual custo/hora vale:** (a) apontamento com `profissional_id` usa o custo desse profissional; (b) apontamentos antigos usam o `usuario_id` e procuram o profissional vinculado a esse usuário. Custo/hora efetivo: o "custo/hora próprio" do profissional se preenchido — **inclusive 0**, que é valor real (ex.: estagiário não remunerado); senão o custo/hora padrão da função; sem ambos (ou função sem valor) → **indefinido**.
18. **Horas sem custo nunca são tratadas como grátis.** Apontamentos com custo indefinido são contados à parte e geram o alerta "{N} apontamento(s) sem custo/hora definido — o custo real está SUBESTIMADO." N conta **apontamentos** (segmentos de cronômetro), não horas. *Por quê:* um custo que parece preciso mas está baixo leva a conclusões erradas sobre margem. *O que fazer:* na página "Custos", dar função ou custo/hora próprio a cada profissional e vincular cada profissional ao seu usuário.
19. **BI e DRE usam a mesma conta de custo** (`BIService`) — as duas telas nunca discordam sobre o custo de um cliente.

**Exemplo trabalhado — BI custo real.** Cliente "Padaria Sol": 10 tarefas, refações somadas = 4 → Taxa = 4 ÷ 10 = "0,40".

| Quem apontou | Configuração em Custos | Horas | Custo |
|---|---|---|---|
| Ana | função Designer (padrão R$ 60,00/h), sem custo próprio | 20h | 20 × 60 = R$ 1.200,00 |
| Bruno | função Redator (R$ 50,00/h), mas custo próprio R$ 90,00/h | 10h | 10 × 90 = R$ 900,00 (o próprio vence a função) |
| Duda | custo próprio R$ 0,00 (estagiária) | 4h | 4 × 0 = R$ 0,00 (zero é real, sem alerta) |
| Carla | sem função e sem custo próprio; 3 segmentos de cronômetro | 5h | não somado → alerta |

Na tabela: Tarefas 10 · Refações 4 · Taxa 0,40 · Horas 39 h · Custo real R$ 2.100,00, e abaixo: "3 apontamento(s) sem custo/hora definido — o custo real está SUBESTIMADO." As 5h da Carla entram em "Horas", mas não em "Custo real". Se a Carla recebesse a função Designer (R$ 60/h), o custo subiria 5 × 60 = R$ 300,00 → R$ 2.400,00 e o alerta sumiria.

### 8. Fluxo de dados
- **Listas:** `usePublicacoes` → **GET `/api/distribuicao/publicacoes`** (opcional `pauta_id`) → `igig.publicacao` ordenada por `agendada_para`. Títulos das pautas vêm de `usePautas` (Calendário). `useFila` → **GET `/api/distribuicao/fila`** (opcional `ate`, ISO-8601; padrão agora) → `PublicacaoRepository.pendentes` (`status='agendada'` e `agendada_para <= ate`).
- **Agendar:** `useAgendarPublicacao` → **POST `/api/distribuicao/publicacoes`** `{pauta_id, canal, agendada_para}` → checa `igig.pauta` → `PublicacaoRepository.agendar` insere em `igig.publicacao`.
- **Publicar:** `useExecutarPublicacao` → **POST `/api/distribuicao/publicacoes/{id}/executar`** → checa status → `resolver_token` (1º `igig.integracao.token_cifrado` decifrado com `IGIG_COFRE_KEY`; 2º variável `IGIG_META_TOKEN` para instagram/facebook, `IGIG_TIKTOK_TOKEN`, `IGIG_LINKEDIN_TOKEN`) → lê `igig.pauta.copy_texto` e `igig.peca.storage_key` → `status='publicando'` → `get_publisher(canal, token)` (`MetaPublisher`/`TikTokPublisher`/`LinkedInPublisher`, que hoje lançam `CanalNaoHomologado`) → `marcar_falha` (`status='falhou'`, `erro`, `tentativas+1`) ou `marcar_publicada` + `pauta.publicado_em`. Token ilegível → `igig.integracao.ultimo_erro`.
- **Cancelar:** `useCancelarPublicacao` → **POST `/api/distribuicao/publicacoes/{id}/cancelar`** → `status='cancelada'`.
- **Métricas:** `useMetricas` → **GET `/api/distribuicao/publicacoes/{id}/metricas`** (mais nova primeiro); `useRegistrarMetrica` → **POST `/api/distribuicao/publicacoes/{id}/metricas`** → `igig.metrica`.
- **BI:** `useEficiencia` → **GET `/api/distribuicao/bi/eficiencia`** → `BIService.eficiencia_por_cliente`: `igig.cliente`, `igig.pauta`, `igig.tarefa` (`pauta_id`, `refacoes`), `igig.profissional` (`custo_hora_override`, `funcao_id`, `usuario_id`), `igig.funcao.custo_hora_padrao`, `igig.apontamento` (`tarefa_id`, `minutos`, `profissional_id`, `usuario_id`). Somente leitura.
- **Efeitos automáticos:** a rotina `igig_publicacao_fila` roda a cada 5 minutos: (1) devolve para `agendada`, com erro "tentativa interrompida", publicações presas em `publicando` há mais de 15 minutos; (2) processa as agendadas vencidas, organização por organização — mas só tenta canais homologados (hoje nenhum), então elas continuam `agendada` sem erro. Toda mutação invalida as consultas de distribuição. Quando "Publicar" falha com `credencial_ilegivel`, a tela também recarrega o status de Integrações (o canal passa a mostrar "reconectar" sem precisar recarregar a página).

### 9. Dependências de configuração
- Pelo menos uma pauta no Calendário Editorial (senão o bloco de agendar mostra o aviso com link).
- Para publicar: token do canal em Integrações → "Canais de publicação" (conectado por administrador) **ou** variável de servidor (`IGIG_META_TOKEN`, `IGIG_TIKTOK_TOKEN`, `IGIG_LINKEDIN_TOKEN`). Sem isso o usuário vê "Canal {canal} não está configurado. Conecte um token em Integrações antes de publicar.".
- `IGIG_COFRE_KEY` no servidor para decifrar tokens gravados. Se a chave mudar, o usuário vê "O token salvo para {canal} não pôde ser lido. Reconecte o canal.".
- Homologação dos apps nas plataformas (Meta/TikTok/LinkedIn) — pendente; enquanto isso toda tentativa com token falha com "A integração com {canal} ainda não está disponível (homologação da API pendente).".
- BI: tabela de custo/hora na página "Custos" (funções, profissionais, vínculo profissional↔usuário) e uso do cronômetro na Esteira.
- Agendar não exige canal conectado; a checagem só ocorre ao publicar.

### 10. Limitações conhecidas
- **Publicação real não implementada** em nenhum canal (`NOC-REMEDIATE[igig-publishing]`). O conjunto de canais homologados está vazio.
- **Agendar não publica sozinho — ainda.** A rotina da fila já roda a cada 5 minutos, mas só tenta canais homologados, e hoje nenhum está: as publicações agendadas ficam `agendada` (sem erro) na "Fila". Tocar "Publicar"/"Publicar agora" tenta na hora, mas também termina em `falhou` com "A integração com {canal} ainda não está disponível (homologação da API pendente).". Quando um canal for homologado, a rotina passa a publicá-lo sozinha, sem mudança na tela.
- Não há como editar o horário de uma publicação; cancele e agende outra. Não há "descancelar".
- Sem política automática de novas tentativas: cada tentativa é manual; o sistema só conta.
- Se o servidor cair no meio de uma tentativa, a linha fica em `publicando` por até ~15–20 minutos (tocar "Publicar" nela devolve "Esta publicação já está sendo executada."); depois a rotina da fila a devolve para `agendada` com o erro "tentativa interrompida", e ela pode ser publicada de novo.
- As mídias enviadas ao publicador são chaves de armazenamento, não URLs públicas — precisará ser ajustado quando a integração real existir.
- Métricas: coleta automática pelas APIs não existe; não há painel agregado por cliente; as métricas não entram no BI.
- BI: sem filtro de período (sempre todo o histórico); não mostra custo por tarefa.

### 11. Perguntas frequentes
- **P: Agendei o post e ele não saiu no horário.** R: Nenhuma rede está homologada ainda, então o IgIg não publica de verdade — nem sozinho, nem pelo botão "Publicar agora". Publique pela própria rede social; o agendamento fica registrado aqui. Quando a integração for liberada, a fila passa a publicar sozinha.
- **P: Toquei em "Publicar" e apareceu "Canal instagram não está configurado. Conecte um token em Integrações antes de publicar."** R: O canal não tem token. Um administrador da agência precisa conectar o canal em Integrações → "Canais de publicação". A publicação continua agendada; nada foi perdido.
- **P: Apareceu "A integração com instagram ainda não está disponível (homologação da API pendente)."** R: O token está salvo, mas a conexão real com a rede ainda não foi liberada pela plataforma. Reconectar não resolve; é pendência de desenvolvimento/homologação.
- **P: Apareceu "O token salvo para facebook não pôde ser lido. Reconecte o canal."** R: A chave de criptografia do servidor mudou. Um administrador deve colar o token de novo em Integrações ("Substituir").
- **P: "Esta pauta já tem publicação ativa em tiktok".** R: Já existe uma publicação dessa pauta nesse canal (agendada, falhou ou publicada). Cancele-a para reagendar, ou use "Publicar" nela.
- **P: Por que a publicação que falhou não está na Fila?** R: A Fila mostra só itens agendados cujo horário chegou. Falhas ficam em "Todas as publicações", com o erro e o botão "Publicar" para tentar de novo.
- **P: A taxa 0,40 é 40%?** R: Não. É 0,4 refação por tarefa (refações ÷ tarefas).
- **P: Uma publicação ficou em "publicando" e não sai disso.** R: O servidor caiu durante a tentativa. Em até uns 20 minutos ela volta sozinha para "agendada" (com o erro "tentativa interrompida"); aí é possível tentar de novo.
- **P: Por que aparece "o custo real está SUBESTIMADO"?** R: Há horas apontadas por alguém sem custo/hora (sem função e sem custo próprio) ou sem profissional vinculado ao usuário. Corrija na página "Custos".
- **P: Posso apagar ou corrigir uma coleta de métricas?** R: Não. As coletas só se acumulam; registre uma nova com os números corretos.
- **P: Quem pode publicar ou cancelar?** R: Qualquer membro da agência. Só conectar/desconectar canais (em Integrações) exige administrador.

---

## Página: Financeiro

### 1. Propósito
Controlar a receita recorrente da agência: resumo do mês (MRR, a receber, recebido, inadimplente), fechamento mensal ("Gerar competência") que abre as faturas dos contratos ativos com mensalidade e excedentes, faturas manuais e seus itens (inclusive desconto), envio da fatura por e-mail ("Enviar fatura") ou registro de envio por fora ("Marcar como enviada"), baixa manual ("Marcar paga"), cancelamento de faturas, cálculo de itens excedentes, aviso de inadimplência, DRE por conta (margem por cliente) e acesso ao Relatório (ver "Funcionalidade: Relatórios"). Título: "Financeiro"; subtítulo: "Margem por conta, excedentes e cobrança."

### 2. Acesso
- **Rota:** `/financeiro`.
- **Menu lateral:** grupo "Principal", item "Financeiro" — 9º item (logo após "Distribuição"). Visibilidade também sujeita ao status de página da plataforma (rota `financeiro`).
- **Também:** Clientes → cartão do cliente → aba "Financeiro" mostra as faturas só daquele cliente (ver seção 3).
- **Quem vê:** qualquer usuário autenticado da agência vê tudo (resumo, DRE, excedentes, faturas, atraso, relatório).
- **Quem executa:**
  - Qualquer membro: trocar competência, "Nova fatura", "Adicionar item" (inclusive desconto), abrir "Itens", "Relatório".
  - **Só administradores da agência:** "Gerar competência", "Enviar fatura", "Marcar como enviada", "Marcar paga", "Cancelar fatura" (e "Paga" na aba Financeiro do card do cliente). Para membros a tela esconde esses botões e, na faixa de fechamento, mostra "Somente administradores da agência podem fechar o mês.". O servidor também recusa (403 "Apenas administradores da organização podem realizar esta ação.").

### 3. Layout
- **Cabeçalho:** título e subtítulo à esquerda; à direita o seletor "Competência" (mês/ano; começa no mês atual) e o botão "Relatório".
- **Blocos, de cima para baixo:**
  1. **Resumo** — quatro cartões: "MRR" (detalhe "contratos ativos hoje"), "A receber" (detalhe = competência), "Recebido" (detalhe = competência), "Inadimplente" (detalhe "{N} fatura(s)", valor em vermelho se N > 0). Celular: 2 colunas; telas grandes: 4 colunas.
  2. **Faixa de fechamento** (borda tracejada): "Fechar {competência}: uma fatura por contrato ativo (mensalidade + excedentes do mês)." + botão "Gerar competência" (só administrador; no celular ocupa a largura toda).
  3. **Aviso de atraso** (só aparece se houver): título vermelho "{N} fatura(s) em atraso" e as 5 mais atrasadas: "{Cliente} · {competência} · {valor} · {N} dias". Se a consulta falhar, aparece em vermelho a mensagem do servidor ou "Não foi possível carregar as faturas em atraso." (nunca some em silêncio).
  4. **"DRE por conta — {competência}"** com a nota "Receita da competência selecionada; custo real é sempre o histórico completo." Colunas "Cliente", "Receita", "Custo real", "Margem", "%". Margem negativa em vermelho. Linha de alerta vermelha abaixo do cliente quando há horas sem custo. Rola para o lado no celular.
  5. **"Itens excedentes — {competência}"** com a nota "Cobrados na fatura do mês seguinte. As peças do plano recorrente nunca contam como excedente, mesmo em meses com mais publicações previstas no calendário — mas elas ocupam a capacidade do pacote. Peças avulsas (fora do plano) só geram cobrança extra pela parte do pacote que o plano ainda não usou nesta competência." Cada linha: cliente, "{entregues} / {contratados} entregues", e então etiqueta vermelha "+{N}", valor e "→ {competência de cobrança}", ou etiqueta "dentro do pacote".
  6. **"Faturas"** — botão "Nova fatura" (abre formulário no lugar), lista de todas as faturas de todas as competências (da mais recente para a mais antiga). Cada linha: etiqueta de status (`aberta`, `enviada`, `paga`, `vencida`, `cancelada`) — numa fatura `vencida` que já foi enviada, logo depois da etiqueta aparece "· enviada em dd/mm/aaaa" —, nome do cliente, competência, valor total, "vence {dd/mm/aaaa}" (se houver), botão "Itens" (abre/fecha), e para administradores em faturas não pagas/não canceladas: "Enviar fatura" (ícone de envelope), ícone de envelope com visto ("Marcar fatura {competência} como enviada"), "Marcar paga" e ícone vermelho de cancelar. Rodapé: "Baixa manual: o webhook do gateway (Asaas/Iugu) e a emissão de NFS-e dependem de credenciais e homologação ainda não configuradas."
  - Painel "Itens": tabela "Descrição", "Tipo", "Qtd", "Valor un.", "Total" (desconto aparece com "− " e em vermelho); abaixo, formulário de adicionar item (só em faturas `aberta`, `enviada` ou `vencida`). Se os itens não carregarem: mensagem do servidor ou "Não foi possível carregar os itens desta fatura.".
- **O seletor "Competência" afeta:** cartões do resumo (exceto MRR), "Gerar competência", DRE (só a receita), excedentes e a competência pré-preenchida em "Nova fatura" (cada vez que o formulário é aberto). **Não afeta:** a lista de faturas e o aviso de atraso (mostram tudo).
- **Formulários no celular (≤640px):** "Nova fatura" com campos empilhados; "Adicionar item" em 2 colunas (Descrição e Tipo ocupando a linha inteira). No desktop, cada formulário numa linha.
- **Aba Financeiro do cartão do cliente:** cartões "Em aberto" e "Recebido"; lista das faturas do cliente (competência, "vence {dd/mm/aaaa}" ou "sem vencimento", "· paga em {dd/mm/aaaa}", valor, status) e, **só para administradores**, botão "Paga" em faturas não pagas/não canceladas (com confirmação). Vazio: "Nenhuma fatura para este cliente. Faturas saem de "Gerar competência" no Financeiro."

### 4. Campos
| Campo (rótulo exato) | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Competência" (cabeçalho) | mês/ano | Sim | `AAAA-MM` válido (senão 422 "competência inválida: ...") | mês atual | Controla resumo, fechamento, DRE (receita), excedentes |
| "Cliente" (Nova fatura) | lista | Sim | cliente precisa existir (404) | "Selecione…" | Trocar o cliente limpa o contrato escolhido |
| "Contrato (opcional)" | lista | Não | contrato precisa existir (404 "Contrato não encontrado") | "Avulsa — sem contrato" | Lista só contratos **ativos** do cliente, como "{número} — R$ X/mês". Desabilitado sem cliente ou sem contrato ativo |
| "Competência" (Nova fatura) | mês/ano | Sim | `AAAA-MM`, mês 01–12 | competência do cabeçalho | |
| "Vencimento" (Nova fatura) | data | Não | data válida (422 senão) | vazio | Sem vencimento a fatura nunca entra em atraso |
| "Descrição" (item) | texto | Sim | 1–200 caracteres | vazio | Exemplo no campo: "Post extra — outubro" |
| "Tipo" (item) | lista | Sim | "Mensalidade", "Excedente", "Avulso", "Desconto" | "Avulso" | "Desconto" SUBTRAI; a tela avisa "Este valor será SUBTRAÍDO do total da fatura." |
| "Qtd" (item) | número | Sim | inteiro ≥ 1 (vazio ou inválido vira 1) | 1 | |
| "Valor un. (R$)" (item) | texto decimal | Sim | aceita `1500,00`, `1.500,00`, `1.500` (ponto seguido de grupos de 3 dígitos = milhar) ou `1500.00`/`1500.5` (ponto seguido de 1–2 dígitos = decimal); ≥ 0; vazio ou ilegível → "Valor inválido. Use, por exemplo, 1500,00 ou 1.500,00." e nada é enviado | vazio (exemplo "0,00") | `1.500` = mil e quinhentos (padrão brasileiro) |

### 5. Ações
| Ação (botão/gesto exato) | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| Trocar "Competência" | — | Recarrega resumo, DRE e excedentes da competência (valores anteriores ficam esmaecidos no resumo enquanto carrega) | — | Erro no resumo: texto do servidor ou "Não foi possível carregar o resumo." |
| "Gerar competência" ("Gerando…") | **Administrador**; competência válida. **Sem confirmação.** | Para cada contrato `ativo`: se já tem fatura não cancelada vinculada ao contrato nessa competência → conta como "já existia" e, se faltar, acrescenta a linha de excedentes; senão cria fatura `aberta` com vencimento e as linhas "Retainer mensal" (+ "Excedentes de {mês anterior}" se houver). Total recalculado. Recarrega tudo do Financeiro. | "{N} fatura(s) criada(s) · {M} já existia(m) em {competência}." (a parte "já existia(m)" só se M > 0) | 422 "competência inválida: '...'; esperado AAAA-MM" ou "...; mês fora de 01-12". 403 (membro, só via API). Genérico: "Não foi possível gerar a competência." |
| "Nova fatura" → "Abrir fatura" ("Abrindo…") | Cliente e competência preenchidos | Cria `igig.fatura` `aberta`, total R$ 0,00, com ou sem contrato. Fecha o formulário. "Cancelar" fecha sem salvar. | "Fatura aberta — adicione os itens" | 404 "Cliente não encontrado". 404 "Contrato não encontrado". 409 "Já existe fatura para este contrato em {competência}" (já há fatura não cancelada desse contrato no mês — use a existente ou cancele-a). 422 validação. Genérico: "Não foi possível abrir a fatura." |
| "Itens" | — | Abre/fecha o painel de itens da fatura (carrega as linhas só ao abrir) | — | — |
| "Adicionar item" ("Adicionando…") | Fatura `aberta`/`enviada`/`vencida`; descrição preenchida; valor válido | Insere linha em `igig.fatura_item`; servidor recalcula `valor_total` (Σ linhas; desconto negativo) e devolve a fatura. Limpa descrição, qtd e valor. | "Item adicionado — total R$ {novo total}" | Na tela: "Valor inválido. Use, por exemplo, 1500,00 ou 1.500,00.". 422 "Este desconto deixaria o total da fatura negativo." (reduza o desconto). 409 "Fatura paga não aceita novos itens." / "Fatura cancelada não aceita novos itens.". 404 "Fatura não encontrada". Genérico: "Não foi possível adicionar o item." |
| "Enviar fatura" → confirmação | **Administrador**; fatura não paga e não cancelada; cliente com e-mail; algum SMTP utilizável | Janela "Enviar fatura": "Enviar esta fatura por e-mail para o cliente, com o PDF em anexo?" Botão "Enviar fatura" ("Enviando…"). Gera o PDF da fatura na hora (agência, "Fatura — {competência}", cliente, competência, vencimento, status, itens com valores em R$ e total) e envia ao e-mail do cadastro do cliente, assunto "Fatura — {competência}", anexo "fatura-{competência}.pdf", pelo SMTP da agência (ou o da plataforma). Só depois do envio bem-sucedido grava `enviada_em = agora` (um novo envio atualiza a data) e, se a fatura estava `aberta`, `status='enviada'`; uma fatura **`vencida` continua `vencida`** (passa a mostrar "· enviada em dd/mm/aaaa"). | "Fatura enviada por e-mail." | 409 `smtp_nao_configurado` "Nenhum SMTP configurado: cadastre uma conta em Integrações → E-mail." · 422 `email_destinatario_ausente` "O cliente não tem e-mail cadastrado." (cadastre em Clientes → Dados) · 409 `fatura_fechada` "Fatura paga não pode ser enviada." / "Fatura cancelada não pode ser enviada." · 502 `envio_falhou` "Falha ao enviar o e-mail: {erro}" (a fatura **não** é marcada como enviada) · 404 "Fatura não encontrada." / "Cliente não encontrado." · 403 (não admin) · genérico "Não foi possível enviar a fatura." |
| Ícone "Marcar fatura {competência} como enviada" → confirmação | **Administrador**; fatura não paga e não cancelada | Janela "Marcar fatura como enviada": "Marcar esta fatura como enviada sem enviar nenhum e-mail? Use quando a fatura já foi entregue ao cliente por outro meio." Botão "Marcar como enviada" ("Marcando…"). Grava `enviada_em = agora` e, se a fatura estava `aberta`, `status='enviada'` — uma fatura `vencida` continua `vencida` (com "· enviada em dd/mm/aaaa") —, sem mandar nada. | "Fatura marcada como enviada." | 409 `fatura_fechada` "Fatura paga não pode ser marcada como enviada." / "Fatura cancelada não pode ser marcada como enviada." · 404 "Fatura não encontrada" · 403 · genérico "Não foi possível marcar como enviada." |
| "Marcar paga" → confirmação | **Administrador**; fatura não paga e não cancelada | Janela "Marcar fatura como paga": "Marcar esta fatura como paga? Registra a data de agora; não há como desfazer pela tela." Botão "Marcar paga" ("Marcando…"). Grava `status='paga'`, `pago_em = agora`. Pagar de novo uma fatura já paga não altera a data original. | "Fatura marcada como paga." | 409 "Fatura cancelada não pode ser paga.". 404 "Fatura não encontrada". 403 (não admin). Genérico: "Não foi possível marcar como paga." |
| Ícone vermelho "Cancelar fatura {competência}" → confirmação | **Administrador**; fatura não paga e não cancelada | Janela "Cancelar fatura": "Cancelar esta fatura? Uma fatura cancelada não pode ser reaberta nem marcada como paga." Botão "Cancelar fatura" ("Cancelando…"). Status `cancelada`; itens e histórico mantidos; libera a vaga contrato+competência para um novo "Gerar competência". Cancelar de novo não dá erro. | "Fatura cancelada." | 409 "Fatura paga não pode ser cancelada.". 404. 403. Genérico: "Não foi possível cancelar a fatura." |
| "Paga" (aba Financeiro do cliente) → "Marcar paga" | **Administrador** (o botão só aparece para eles); fatura não paga/não cancelada | Mesma confirmação "Marcar fatura como paga" e mesmo efeito de "Marcar paga". | "Fatura marcada como paga." | Como em "Marcar paga". |
| "Relatório" | — | Abre a janela de relatório (ver "Funcionalidade: Relatórios") | — | — |

### 6. Estados
- **Carregando:** resumo com 4 blocos cinza; DRE, excedentes, faturas e itens com blocos cinza; lista de clientes do formulário mostra "Carregando…".
- **Vazio:** DRE: "Nenhum cliente ainda." · Excedentes: "Nenhum contrato ativo com pacote definido nesta competência." · Faturas: "Nenhuma fatura emitida." · Itens: "Nenhum item lançado nesta fatura." · Aviso de atraso: não aparece. · Cartão do cliente: "Nenhuma fatura para este cliente. Faturas saem de "Gerar competência" no Financeiro."
- **Erro:** Resumo: texto do servidor ou "Não foi possível carregar o resumo." · DRE: "Não foi possível carregar o DRE." · Excedentes: "Não foi possível carregar os excedentes." · Faturas: "Não foi possível carregar as faturas." · Cartão do cliente: texto do servidor ou "Não foi possível carregar as faturas." · Aviso de atraso: texto do servidor ou "Não foi possível carregar as faturas em atraso." · Painel de itens: texto do servidor ou "Não foi possível carregar os itens desta fatura.".
- **Atualizando:** cartões do resumo ficam esmaecidos enquanto a nova competência carrega; toda ação recarrega todas as consultas do Financeiro.

### 7. Regras de negócio e por quê
1. **Origem do retainer (contrato):** ao gerar o contrato a partir de um orçamento aceito, o sistema copia `valor_mensal` (total mensal), `posts_por_mes` (soma das quantidades mensais da criação de conteúdo), `valor_excedente` (limite de escopo do orçamento) e `dia_vencimento`. **Só contratos `ativo` entram no MRR, no fechamento e nos excedentes.** (Detalhe no guia de Orçamentos/Contratos.)
2. **MRR** = soma do `valor_mensal` de todos os contratos ativos **agora**; não muda com a competência. *Por quê:* receita recorrente filtrada por mês passado responderia outra pergunta.
3. **A receber** = faturas da competência não pagas e não canceladas (inclui as vencidas). **Recebido** = faturas `paga` da competência. **Inadimplente** = faturas da competência vencidas e não pagas; é um subconjunto de "A receber", não uma soma à parte. Canceladas são ignoradas em tudo.
4. **Fechamento idempotente por contrato ativo × competência.** Rodar "Gerar competência" de novo não cobra duas vezes; o banco reforça com o índice único `idx_igig_fatura_competencia (org_id, contrato_id, competencia)` (ignora canceladas). Duas pessoas fechando ao mesmo tempo: a segunda vê "já existia(m)", nunca erro.
5. **Fatura cancelada não segura a vaga:** depois de cancelar, "Gerar competência" cria outra.
6. **Linhas criadas no fechamento:** "Retainer mensal" (tipo `mensalidade`, qtd 1, valor = `valor_mensal`; contrato sem valor → R$ 0,00) e "Excedentes de {mês anterior}" (tipo `excedente`, qtd = excedentes do mês anterior, valor unitário = `valor_excedente`), esta só se houver ≥ 1 excedente.
7. **Excedentes vão para o mês seguinte.** *Por quê:* regra do contrato — primeiro se cobra o retainer do mês; o que passou do pacote no mês trabalhado entra na fatura do mês subsequente.
8. **Fatura que já existia recebe o excedente que faltava**, sem duplicar (a checagem é pela descrição "Excedentes de {mês}"); faturas pagas ou canceladas não são tocadas.
9. **Vencimento** = `dia_vencimento` do contrato dentro do próprio mês da competência; se o dia não existe no mês, usa o último dia (ex.: dia 31 em 2026-02 → 28/02/2026). Contrato sem dia → fatura sem vencimento (nunca fica em atraso).
10. **Total da fatura é sempre derivado das linhas** (Σ quantidade × valor unitário, com desconto subtraindo), nunca digitado. *Por quê:* um cabeçalho que discorda das próprias linhas é o erro que o cliente percebe antes da agência.
11. **Desconto subtrai e não pode deixar o total negativo** (422 "Este desconto deixaria o total da fatura negativo."; o item não é lançado).
12. **Fatura paga ou cancelada não aceita itens** (409). *Por quê:* mudaria em silêncio um valor já pago ou anulado.
13. **Fatura manual com contrato** usa a mesma trava de duplicidade do fechamento (409). **Sem contrato ("Avulsa — sem contrato")** não tem trava: é possível abrir várias para o mesmo cliente e mês, e o fechamento não as enxerga (pode gerar outra fatura para o mesmo cliente). Use avulsa para cobranças extras; para a mensalidade, prefira "Gerar competência" ou escolha o contrato.
14. **Marcar paga** grava a data do clique (não a data real do pagamento); é idempotente; fatura cancelada não pode ser paga. **Cancelar** não apaga nada; fatura paga não pode ser cancelada (estorno é outro processo, não construído).
14b. **Enviar fatura** só marca `enviada` depois que o e-mail realmente saiu; se o SMTP falhar, nada muda. "Marcar como enviada" existe para quando a fatura foi entregue por fora (e-mail próprio, em mãos). Os dois exigem administrador (comunicação financeira com o cliente) e são recusados em fatura paga ou cancelada. *Por quê:* a etiqueta `enviada` precisa significar que o cliente de fato recebeu a cobrança.
14c. **Reenviar uma fatura vencida não a "desvence".** Os dois botões sempre atualizam a data de envio (`enviada_em`), mas nunca trocam `vencida` por `enviada`; a tela mostra "vencida · enviada em dd/mm/aaaa". *Por quê:* a rotina das 06:00 marcaria a fatura como `vencida` de novo no dia seguinte, e o status (e o "Inadimplente" do cliente) ficava oscilando; o atraso é um fato que o reenvio não muda.
14c. **Vencida e inadimplente são automáticos**: todo dia às 06:00 (Brasília) a rotina marca `vencida` toda fatura `aberta`/`enviada` com vencimento anterior a hoje, marca o cliente como `inadimplente` enquanto ele tiver alguma fatura vencida e o devolve a `ativo` quando não tiver mais nenhuma (paga ou cancelada).
15. **Excedentes — "entregue"** = pauta **publicada de verdade** (`publicado_em`) ou, na falta disso, **aprovada pelo cliente no portal** (data da primeira aprovação) dentro do mês (dia 1º até o último dia). A data **planejada** (`data_publicacao`) não conta mais. *Por quê:* uma peça que atrasou ou foi retirada depois de agendada não foi entregue e não pode ser cobrada. Como hoje nenhum canal publica de verdade, na prática "entregue" = aprovada no portal.
16. **Peça do plano nunca é excedente.** O pacote (`posts_por_mes`) é precificado com a convenção fixa de 4 semanas/mês (Σ dias da semana × quantidade por dia × 4). Num mês "de 5 semanas" o item recorrente gera uma ocorrência a mais — isso é o próprio plano, não pedido extra. Por isso as pautas geradas automaticamente a partir do orçamento aceito (`gerada_automaticamente` + `orcamento_item_id`) **nunca** são cobradas como excedente — mas contam para ocupar o pacote (regra 17) e aparecem em "entregues".
17. **Excedentes = máx(0, avulsas entregues − capacidade restante)**, com **capacidade restante = máx(0, pacote − peças do plano entregues na competência)**. As peças do plano nunca são cobradas como excedente, mas **ocupam** o pacote; só as pautas **avulsas** (criadas à mão no Calendário, fora do plano) podem virar excedente, e só pelo que passar do que o plano deixou livre. Exemplos (pacote 12): plano 12 + 2 avulsas → capacidade 0 → **2** excedentes; plano 10 + 3 avulsas → capacidade 2 → **1**; plano 8 + 3 avulsas → capacidade 4 → **0**. Se o plano sozinho já passa do pacote (mês "de 5 semanas"), a capacidade é 0 e **todas** as avulsas do mês são excedente (ex.: pacote 8, plano 10, 9 avulsas → 9). *Por quê:* comparar as avulsas com o pacote inteiro ignorava o que o plano já tinha consumido e cobrava a menos. Entregar menos não gera crédito. Valor = excedentes × `valor_excedente` (2 casas). Contrato sem pacote (`posts_por_mes` vazio ou 0) não aparece. A coluna "{entregues} / {contratados}" mostra plano + avulsas entregues.
17b. **Atribuição ao contrato:** uma peça do plano pertence ao contrato gerado do seu orçamento de origem (sem ambiguidade, mesmo com dois contratos). Uma peça avulsa só tem o cliente: é atribuída ao único contrato ativo com pacote desse cliente; se ele tiver dois ou mais, a avulsa não é atribuída a nenhum (registrado em log, nunca cobrado em dobro).
18. **Inadimplência (aviso de atraso)** = fatura não paga, não cancelada, com vencimento **anterior a hoje**; dias de atraso = hoje − vencimento. No dia do vencimento ainda não está atrasada. Ordenada da mais atrasada para a menos. A lista é calculada na hora (não espera a rotina das 06:00). Ela não envia cobrança; o bloqueio do portal de aprovação só acontece se a agência ligou `IGIG_PORTAL_BLOQUEIO_DIAS` (ver Capítulo 3, Portal). *Por quê:* bloquear o portal é decisão de negócio, não efeito colateral de um relatório.
19. **DRE — Receita** = soma do `valor_total` das faturas não canceladas do cliente **na competência selecionada** (pagas e não pagas — é faturamento, não caixa). **Custo real** = o mesmo "Custo real" do BI de Eficiência, sobre **todo o histórico** de horas. **Margem** = Receita − Custo (2 casas). **%** = Margem ÷ Receita × 100 (1 casa), exibida com vírgula (ex.: "52,8%"); sem receita, "0%" (não significa empate). O custo real soma os apontamentos em **segundos** (não em minutos arredondados).
20. **DRE — alerta:** se há horas sem custo/hora, a linha diz "{N} apontamento(s) sem custo/hora definido — a margem está SUPERESTIMADA." *Por quê:* custo subestimado deixa a margem mais alta do que a real. *O que fazer:* completar custo/hora e vínculos na página "Custos".

**Exemplo trabalhado — excedentes + fechamento.** Contrato ativo da "Padaria Sol": `valor_mensal` R$ 4.000,00; pacote 12 posts/mês; `valor_excedente` R$ 150,00; dia de vencimento 10.
- Em agosto/2026 (mês "de 5 semanas"), o item recorrente do plano gerou 13 pautas, todas aprovadas pelo cliente no portal em agosto → **peças do plano: 13, nunca cobradas como excedente**. Além disso, a agência criou à mão no Calendário 3 pautas avulsas, também aprovadas em agosto.
- Competência 2026-08 → "Itens excedentes — 2026-08": "Padaria Sol · 16 / 12 entregues · +3 · R$ 450,00 · → 2026-09" (entregues = 13 do plano + 3 avulsas; capacidade restante = máx(0, 12 − 13) = 0; excedentes = 3 avulsas − 0 = 3; 3 × R$ 150,00). As 13 do plano não geram cobrança, mesmo passando de 12 — mas, como já ocuparam todo o pacote, cada avulsa é cobrada.
- Uma pauta avulsa agendada para agosto mas **não aprovada** (nem publicada) em agosto não conta; se for aprovada em setembro, conta em setembro.
- Competência 2026-09 → administrador toca "Gerar competência" → toast "1 fatura(s) criada(s) em 2026-09." e a fatura 2026-09 tem:
  - "Retainer mensal" — 1 × R$ 4.000,00 = R$ 4.000,00
  - "Excedentes de 2026-08" — 3 × R$ 150,00 = R$ 450,00
  - **Total R$ 4.450,00**, "vence 10/09/2026".
- Tocar "Gerar competência" de novo: "0 fatura(s) criada(s) · 1 já existia(m) em 2026-09." — nada duplicado.
- Se em agosto o plano tivesse entregado só 9 peças (e as mesmas 3 avulsas): "12 / 12 entregues", capacidade restante = 12 − 9 = 3, excedentes = 3 − 3 = 0 → "dentro do pacote"; a fatura de setembro teria só o retainer (R$ 4.000,00).
- Desconto: na fatura de R$ 4.450,00, um item "Desconto" de 1 × R$ 200,00 deixa o total em R$ 4.450,00 − 200,00 = **R$ 4.250,00** (toast "Item adicionado — total R$ 4.250,00"; a linha aparece "− R$ 200,00" em vermelho). Um desconto de R$ 5.000,00 seria recusado: "Este desconto deixaria o total da fatura negativo.".

**Exemplo trabalhado — DRE (margem).** Padaria Sol, com o custo do exemplo do BI (R$ 2.100,00; 3 apontamentos sem custo da Carla). Faturas: 2026-08 R$ 4.000,00 (paga) e 2026-09 R$ 4.450,00 (aberta).
- Competência **2026-09**: Receita R$ 4.450,00 · Custo real R$ 2.100,00 · **Margem = 4.450,00 − 2.100,00 = R$ 2.350,00** · **% = 2.350 ÷ 4.450 × 100 = 52,8%** · alerta "3 apontamento(s) sem custo/hora definido — a margem está SUPERESTIMADA.".
- Se a Carla ganhasse função de R$ 60/h: custo = 2.100 + 5 × 60 = R$ 2.400,00 → margem R$ 2.050,00 → 2.050 ÷ 4.450 = **46,1%** (sem alerta).
- Competência **2026-08**: Receita R$ 4.000,00; o custo continua R$ 2.100,00 (todo o histórico) → margem R$ 1.900,00 → 47,5%. Por isso a nota "custo real é sempre o histórico completo": somar as margens mensais não dá a margem real do período.
- Cliente novo "Loja Lua", sem faturas na competência e com 8h da Ana (R$ 60/h): Receita R$ 0,00 · Custo R$ 480,00 · Margem **−R$ 480,00** (vermelho) · % **0%**.

### 8. Fluxo de dados
- **Resumo:** `useResumoFinanceiro` → **GET `/api/financeiro/resumo?competencia=AAAA-MM`** → `FinanceiroService.resumo`: `igig.contrato` ativos (MRR), `igig.fatura` da competência, `inadimplentes()` filtrado pela competência.
- **Fechamento:** `useGerarCompetencia` → **POST `/api/financeiro/faturas/gerar-competencia`** `{competencia}` (admin) → `gerar_faturas_da_competencia`: valida competência → `excedentes(mês anterior)` → faturas existentes da competência (com contrato, não canceladas) → para cada `igig.contrato` `status='ativo'`: garante linha de excedente na existente ou insere `igig.fatura` (`cliente_id`, `contrato_id`, `competencia`, `vencimento`, `status='aberta'`) + `igig.fatura_item` → `recalcular_total` grava `valor_total`. Resposta `{criadas, existentes}`.
- **Faturas:** `useFaturas` → **GET `/api/financeiro/faturas`** (filtros `cliente_id` ou `competencia`; se ambos, vale `cliente_id`) → ordenado por competência decrescente. `useCriarFatura` → **POST `/api/financeiro/faturas`** `{cliente_id, competencia, contrato_id?, vencimento?}`. `useFaturaItens` → **GET `/api/financeiro/faturas/{id}/itens`**. `useAdicionarItem` → **POST `/api/financeiro/faturas/{id}/itens`** `{descricao, tipo, quantidade, valor_unit}` → `igig.fatura_item` + `recalcular_total`. `useMarcarPaga` → **POST `/api/financeiro/faturas/{id}/pagar`** (admin) → `status='paga'`, `pago_em`. `useCancelarFatura` → **POST `/api/financeiro/faturas/{id}/cancelar`** (admin) → `status='cancelada'`. `useEnviarFatura` → **POST `/api/financeiro/faturas/{id}/enviar`** (admin) → `financeiro_service.enviar_fatura` → `email_config.resolver_smtp` (agência → plataforma → 409) → `documentos_pdf.renderizar_fatura_pdf` (PDF gerado na hora, não guardado) → envio SMTP com anexo → `FaturaRepository.marcar_enviada` (`status='enviada'`, `enviada_em`) → `{fatura, message_id}`. `useMarcarFaturaEnviada` → **POST `/api/financeiro/faturas/{id}/marcar-enviada`** (admin) → `marcar_enviada` (sem e-mail).
- **Excedentes:** `useExcedentes` → **GET `/api/financeiro/excedentes/{AAAA-MM}`** → `FinanceiroService.excedentes`: todas as `igig.pauta` → data de entrega (`publicado_em`, senão a primeira `igig.aprovacao` com `decisao='aprovado'` das tarefas da pauta) dentro do mês → pautas do plano atribuídas ao contrato via `orcamento_item` → `orcamento` → `igig.contrato`; avulsas ao único contrato ativo com pacote do cliente → `igig.cliente`. Somente leitura.
- **DRE:** `useDRE(competencia)` → **GET `/api/financeiro/dre?competencia=AAAA-MM`** (esta tela **não** passa `custo_por_competencia`, por isso o custo é o histórico completo; o Dashboard passa `true`) → `igig.cliente`, `igig.fatura` (exceto canceladas, da competência) + `BIService.eficiencia_por_cliente`.
- **Atraso:** `useInadimplentes` → **GET `/api/financeiro/inadimplentes`** (opcional `hoje=AAAA-MM-DD`; data malformada → 422 "data inválida: '...'; esperado AAAA-MM-DD").
- **Efeitos:** toda mutação invalida as consultas do Financeiro. O único e-mail disparado por esta página é o de "Enviar fatura" (para o cliente). Não há notificação nem cobrança automática. **Rotina diária 06:00** (`igig_financeiro_inadimplencia` → `atualizar_inadimplencia`): `igig.fatura` `aberta`/`enviada` vencidas → `vencida`; `igig.cliente.status` → `inadimplente` / de volta a `ativo`.

### 9. Dependências de configuração
- Contratos `ativo` (vindos de orçamento aceito + assinatura) com `valor_mensal`; para excedentes, `posts_por_mes` e `valor_excedente`; para vencimento automático, `dia_vencimento`. Sem contratos ativos, "Gerar competência" cria 0 faturas.
- Pautas avulsas aprovadas no portal (ou publicadas) no Calendário (base dos excedentes).
- SMTP (Integrações → E-mail, ou o SMTP da plataforma) e e-mail do cliente cadastrado, para "Enviar fatura".
- Agendador ligado no servidor (`NOCTUS_SCHEDULERS_ENABLED`) para as marcações automáticas de `vencida`/`inadimplente`.
- Tabela de custo/hora na página "Custos" e apontamentos na Esteira (base do custo real do DRE).
- `IGIG_PORTAL_BLOQUEIO_DIAS` (servidor, padrão 0 = desligado) — com N > 0, o portal de aprovação fica bloqueado para clientes com fatura vencida há mais de N dias ("Portal temporariamente indisponível").
- Gateway de pagamento (Asaas/Iugu) e NFS-e: **não configurados/não implementados** — daí o rodapé "Baixa manual: ...".

### 10. Limitações conhecidas
- **Sem gateway de pagamento, boleto ou NFS-e.** Colunas `gateway_id`/`nfse_id` ficam vazias; a baixa é manual.
- **Fechamento não roda sozinho** (nada fecha o mês automaticamente no dia 1º) e a fatura não é enviada automaticamente: "Enviar fatura" é um clique por fatura.
- **Régua de cobrança não implementada:** sem lembretes automáticos de cobrança por WhatsApp/e-mail.
- O e-mail da fatura vai só para o e-mail do cadastro do cliente, sem CC e sem texto editável; o PDF não fica guardado nem tem link para baixar pela tela.
- Excedentes olham só a quantidade: a peça do plano sempre ocupa o pacote primeiro, e o que sobra é disputado pelas avulsas; não há como marcar uma avulsa específica como "dentro do pacote" ou abonar uma peça.
- Excedentes usam os contratos ativos **hoje**, não os que estavam ativos no mês consultado; e, como "entregue" depende da aprovação no portal, uma aprovação tardia muda o número de um mês já consultado (é recalculado na hora).
- Cliente com 2+ contratos ativos com pacote: as peças avulsas dele não são atribuídas a nenhum contrato (sem aviso na tela); as do plano são.
- Não há editar/apagar fatura nem editar/apagar item; um item errado precisa ser compensado (ex.: com desconto) ou a fatura cancelada.
- Marcar paga não registra valor parcial, forma de pagamento nem data retroativa; não há "desfazer pagamento".
- DRE considera só custo de horas (sem ferramentas, mídia, impostos, overhead) e mistura períodos (receita do mês × custo de todo o histórico).

### 11. Perguntas frequentes
- **P: Não vejo o botão "Gerar competência" / "Marcar paga".** R: São ações só de administradores da agência. Membros veem "Somente administradores da agência podem fechar o mês.".
- **P: Rodei "Gerar competência" duas vezes; duplicou?** R: Não. Contratos já faturados no mês aparecem como "já existia(m)".
- **P: Por que o excedente de agosto está na fatura de setembro?** R: Regra do contrato: excedentes são cobrados na fatura do mês seguinte ao trabalho.
- **P: Lancei um desconto; o que acontece?** R: O valor é subtraído do total (a linha aparece com "−" em vermelho). Se deixar o total negativo, é recusado: "Este desconto deixaria o total da fatura negativo.".
- **P: Como digito R$ 1.500,00?** R: `1500,00`, `1.500,00`, `1.500` ou `1500.00` funcionam — todos viram mil e quinhentos.
- **P: Errei um item. Como apago?** R: Não é possível apagar itens. Lance um desconto compensando ou peça a um administrador para cancelar a fatura e abrir outra.
- **P: Mudei a competência e a lista de faturas não mudou.** R: Correto: a lista mostra todas as faturas. A competência afeta resumo, fechamento, DRE e excedentes.
- **P: Por que a margem diz SUPERESTIMADA?** R: Há horas de alguém sem custo/hora ou sem profissional vinculado ao usuário. Corrija em "Custos".
- **P: A fatura está atrasada mas continua "aberta".** R: A marcação como `vencida` acontece todo dia às 06:00 (horário de Brasília). Se venceu ontem, aguarde a rotina da manhã; o atraso já aparece no aviso vermelho.
- **P: O sistema cobra quem está atrasado ou bloqueia o portal?** R: Não cobra sozinho. O bloqueio do portal de aprovação só acontece se o servidor tiver `IGIG_PORTAL_BLOQUEIO_DIAS` ligado.
- **P: Como mando a fatura para o cliente?** R: Na lista "Faturas", toque em "Enviar fatura" e confirme — vai por e-mail, com o PDF anexo, para o e-mail do cadastro do cliente. Se você já enviou por outro meio, use o ícone "Marcar como enviada". Só administradores veem esses botões.
- **P: Apareceu "O cliente não tem e-mail cadastrado."** R: Cadastre o e-mail em Clientes → card do cliente → "Dados" e envie de novo.
- **P: Por que as peças do plano não viraram excedente num mês com 5 segundas?** R: O pacote é calculado com 4 semanas por mês; a ocorrência extra do calendário faz parte do plano e nunca é cobrada. Mas ela ocupa o pacote: nesse mês, qualquer peça avulsa entregue vira excedente.
- **P: Como é calculado o excedente?** R: Primeiro as peças do plano entregues ocupam o pacote; o que sobra é a capacidade restante. Só as avulsas que passarem dessa sobra são cobradas. Ex.: pacote 12, plano entregou 10 e houve 3 avulsas → sobram 2 → 1 excedente.
- **P: A margem do "DRE por conta" não bate com a "Margem no mês" do Dashboard.** R: É esperado. O DRE desta tela compara a receita da competência com o custo de **todo** o histórico de horas do cliente ("custo real é sempre o histórico completo"); o Dashboard usa só as horas apontadas no mês atual.
- **P: Reenviei uma fatura vencida e ela continua "vencida". Está errado?** R: Não. Reenviar (ou "Marcar como enviada") só registra a nova data de envio — aparece "· enviada em dd/mm/aaaa" ao lado — e a fatura continua vencida até ser paga ou cancelada.

---

## Página: Integrações

### 1. Propósito
Lugar onde a agência configura credenciais externas: e-mail (SMTP e Gmail), fontes de lead (WhatsApp/WAHA e Meta Lead Ads) e **canais de publicação social** (Instagram, Facebook, TikTok, LinkedIn). Título: "Integrações"; subtítulo: "E-mail, fontes de lead e canais de publicação. Senhas e tokens são gravados criptografados e nunca são exibidos de volta." Este guia detalha a casca da página e os canais sociais; os cartões de E-mail e de WhatsApp/Meta estão documentados nos guias próprios (Funcionalidade: E-mail; Fontes de lead WhatsApp/Meta).

### 2. Acesso
- **Rota:** `/integracoes`.
- **Menu lateral:** grupo "Principal", item "Integrações" — 10º item (logo após "Financeiro"). Visibilidade sujeita ao status de página (rota `integracoes`).
- **Quem vê:** qualquer usuário autenticado da agência vê o status de todos os canais.
- **Quem executa:** **conectar, substituir e desconectar canais sociais: só administradores da agência** (servidor exige `exigir_admin_da_org`). Membros veem "Somente administradores da agência podem alterar este canal." no lugar do formulário. Os cartões de WhatsApp/Meta Lead Ads também são só-admin (ver guias próprios). Regras de SMTP/Gmail: ver guia de E-mail.

### 3. Layout
Três grupos, nesta ordem:
1. **"E-mail"** — cartões "SMTP" e "Gmail" (ver guia de E-mail).
2. **"Fontes de lead"** — cartões WhatsApp (WAHA) e Meta Lead Ads (ver guia de Fontes de lead).
3. **"Canais de publicação"** — aviso vermelho de criptografia (se faltar a chave), depois um quadro com uma linha por canal (sempre os quatro, mesmo nunca configurados), e o rodapé "Enquanto um canal não estiver conectado, a publicação falha de forma explícita — nada é marcado como publicado sem confirmação da plataforma."

Nos grupos E-mail e Fontes de lead, os cartões ficam em duas colunas em telas grandes (≥1024px) e um embaixo do outro em telas menores.

**Cada linha de canal mostra:**
- Nome ("Instagram", "Facebook", "TikTok", "LinkedIn") e etiqueta de status:
  - "reconectar" (vermelha) — existe erro de credencial registrado; o texto do erro aparece embaixo em vermelho com ícone de alerta.
  - "não conectado" — sem token.
  - "conectado (env)" — sem token da agência, mas o servidor tem token de ambiente para o canal.
  - "conectado" — token da agência gravado e ativo.
- A conta externa (ex.: "@padariasol"), se informada.
- Texto de ajuda: Instagram "Meta Graph API — token de página com instagram_content_publish"; Facebook "Meta Graph API — token de página com pages_manage_posts"; TikTok "TikTok for Business — access token com video.publish"; LinkedIn "LinkedIn Open Platform — token com w_organization_social".
- Para administradores: campo de token (tipo senha; placeholder "colar token…" ou "substituir token…" se conectado), campo "@conta" e botão "Conectar"/"Substituir"; ícone de corrente partida "Desconectar {Canal}" (só quando conectado com token da agência — não para "conectado (env)").

**Retorno do Gmail:** ao voltar da autorização do Google (`?gmail=ok` ou `?gmail=erro&motivo=...`), a página mostra "Gmail conectado." ou "Não foi possível conectar o Gmail: {motivo}." (ou "Não foi possível conectar o Gmail."), recarrega o status do Gmail e limpa o endereço (detalhes no guia de E-mail).

### 4. Campos
| Campo (rótulo exato) | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| Token do canal (rótulo de acessibilidade "Token {Canal}"; placeholder "colar token…"/"substituir token…") | senha | Sim | 1–4000 caracteres (espaços nas pontas removidos) | vazio (sempre) | Nunca é exibido de volta; limpa ao salvar |
| "@conta" (rótulo de acessibilidade "Conta {Canal}") | texto | Não | até 200 caracteres | conta gravada, se houver | Só para exibição, não é segredo; atualiza sozinho se o valor gravado mudar |

### 5. Ações
| Ação (botão/gesto exato) | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| "Conectar" / "Substituir" | **Administrador**; token preenchido; criptografia configurada (botão desabilitado senão ou durante o envio) | Cifra o token (Fernet, `IGIG_COFRE_KEY`) e grava/atualiza `igig.integracao` do canal: `token_cifrado`, `conta_externa`, `conectado_em = agora`, `ultimo_erro = vazio`, `ativo = true`. Limpa o campo do token. Etiqueta vira "conectado" e o aviso "reconectar" some. | Sem toast (o campo limpa e a etiqueta muda) | Texto abaixo do formulário: 409 "Criptografia não configurada: defina IGIG_COFRE_KEY. Nenhum token é gravado em texto puro." (configuração do servidor — acionar suporte/TI). 422 "Canal inválido: {canal}". 422 validação de tamanho. 403 (não admin). Genérico: "Não foi possível salvar." |
| Ícone "Desconectar {Canal}" → confirmação | **Administrador**; canal conectado pela agência | Janela "Desconectar {Canal}": "Desconectar {Canal}? O token e a conta gravados são apagados; publicações futuras neste canal falharão até que ele seja reconectado." Botão "Desconectar" ("Desconectando…"). Apaga a linha de `igig.integracao`. A linha volta a "conectado (env)" se houver token do servidor, senão "não conectado". | Sem toast (janela fecha, status muda) | 404 "Canal não conectado". 422 "Canal inválido: {canal}". 403. Toast genérico: "Não foi possível desconectar o canal." |

### 6. Estados
- **Carregando:** bloco cinza grande no quadro de canais.
- **Vazio:** não se aplica — os quatro canais sempre aparecem.
- **Erro:** "Não foi possível carregar os canais de publicação."; sem chave de criptografia: aviso vermelho "Criptografia não configurada neste ambiente (IGIG_COFRE_KEY). Nenhum canal pode ser conectado até que o servidor seja configurado." e botões desabilitados. Erros de salvar aparecem abaixo do formulário da linha.
- **Atualizando:** após conectar/desconectar a lista é recarregada.

### 7. Regras de negócio e por quê
1. **Nenhum token é devolvido pela API — nunca.** O status não tem campo de token; o campo sempre começa vazio; não há "mostrar token" nem máscara. *Por quê:* segredo exibido é segredo vazado; uma máscara sugeriria que o valor pode ser revelado. Para trocar, cole um novo ("Substituir").
2. **Criptografia obrigatória.** Sem `IGIG_COFRE_KEY` nada é gravado (409). *Por quê:* nenhum token em texto puro.
3. **Um token por canal por agência.** *Por quê:* uma agência publica em contas de vários clientes; um token global da plataforma seria o modelo errado. O token de ambiente do servidor é só reserva para instalações de uma agência.
4. **Ordem de uso na publicação:** 1º token da agência; 2º token de ambiente do servidor.
5. **Conectar de novo substitui:** sobrescreve token, conta e data, reativa o canal e apaga o `ultimo_erro`.
6. **Só administradores alteram canais.** *Por quê:* trocar ou apagar a credencial de publicação tem o mesmo nível de confiança dos cartões de fontes de lead.
7. **"reconectar" só aparece para problema de credencial que reconectar resolve** (ex.: token ilegível após troca da chave do cofre). A falha "ainda não está disponível (homologação da API pendente)" **não** marca "reconectar". Quando uma tentativa de "Publicar" em Distribuição falha por token ilegível, esta página é atualizada automaticamente e já mostra "reconectar" (sem precisar recarregar).
8. **Uma chave (`IGIG_COFRE_KEY`) protege todos os segredos da agência:** tokens dos canais, senha SMTP, API key do WAHA, tokens da Meta Lead Ads, refresh token do Gmail e senhas do Cofre de Acessos (página Marca). Se a chave do servidor for trocada, os segredos gravados ficam ilegíveis e cada integração precisa ser reconectada.
9. **O token não é validado ao salvar** — um token inválido é aceito; o problema só aparece ao publicar.

### 8. Fluxo de dados
- **Listar:** `useIntegracoes` → **GET `/api/integracoes`** → para cada canal (`instagram`, `facebook`, `tiktok`, `linkedin`) lê `igig.integracao` por `(org_id, canal)`: sem registro → `conectado` = existe token de ambiente, `origem = 'env' | 'nenhuma'`; com registro → `conectado = token_cifrado presente e ativo`, `origem='org'`, `conta_externa`, `conectado_em`, `ultimo_erro`; todos com `cofre_configurado`.
- **Conectar:** `useConectarCanal` → **POST `/api/integracoes/{canal}`** `{token, conta_externa?}` (admin) → `IntegracaoRepository.conectar` (índice único `(org_id, canal)`).
- **Desconectar:** `useDesconectarCanal` → **DELETE `/api/integracoes/{canal}`** (admin) → apaga a linha.
- **Uso:** a Distribuição decifra o token no momento de publicar; token ilegível grava `ultimo_erro`.
- A tabela `igig.integracao` também guarda `smtp`, `gmail`, `whatsapp`, `meta_leads` (ver guias próprios).

### 9. Dependências de configuração
- `IGIG_COFRE_KEY` (servidor) — sem ela, aviso vermelho e botões desabilitados.
- Opcionais: `IGIG_META_TOKEN` (Instagram e Facebook), `IGIG_TIKTOK_TOKEN`, `IGIG_LINKEDIN_TOKEN` — geram "conectado (env)".
- App aprovado/homologado em cada plataforma (Meta, TikTok, LinkedIn) — **ainda não**; mesmo com token conectado, publicar falha com "A integração com {canal} ainda não está disponível (homologação da API pendente).".

### 10. Limitações conhecidas
- Sem login OAuth ("Conectar com Instagram"): o token é colado manualmente.
- Token não é validado ao salvar.
- Publicação real não existe em nenhum canal (`NOC-REMEDIATE[igig-publishing]`).
- Conectar não mostra toast de sucesso; a confirmação é visual (campo limpo, etiqueta "conectado").

### 11. Perguntas frequentes
- **P: Não consigo conectar; o botão está cinza.** R: Ou o token está vazio, ou o servidor não tem a chave de criptografia (aviso vermelho). No segundo caso só o suporte resolve.
- **P: Não aparece o formulário, só "Somente administradores da agência podem alterar este canal."** R: Conectar canais é ação de administrador da agência.
- **P: Quero ver o token salvo.** R: Não é possível; por segurança o sistema nunca devolve tokens. Cole um novo se precisar trocar.
- **P: O canal mostra "reconectar".** R: O token gravado não pôde ser usado (ex.: chave do cofre trocada). Cole o token de novo e toque "Substituir".
- **P: Conectei o Instagram, mas a publicação falha.** R: A integração real ainda está em homologação; a mensagem é "A integração com instagram ainda não está disponível (homologação da API pendente).". Não é problema do token.
- **P: O que é "conectado (env)"?** R: O servidor tem um token de reserva para esse canal; a agência não gravou um próprio. Não há botão de desconectar nesse caso.
- **P: Onde configuro SMTP, Gmail, WhatsApp ou Meta Lead Ads?** R: Na mesma página, nos grupos "E-mail" e "Fontes de lead" — ver os guias de E-mail e de Fontes de lead.

---

## Funcionalidade: Relatórios

### 1. Propósito
Gerar um relatório de um período, com prévia na tela e download em CSV ou PDF:
- **Financeiro:** faturamento, recebido, a receber, inadimplência (valor e quantidade) e, por cliente, faturamento, recebido, custo e margem.
- **Comercial:** funil por etapa (entradas, saídas, conversão), negócios ganhos e perdidos (quantidade e valor), motivos de perda por etapa, tempo médio parado antes da perda, orçamentos enviados/aceitos/recusados e ticket médio.

### 2. Acesso
- Financeiro → botão "Relatório" no cabeçalho. Não há item de menu próprio.
- Janela com título "Relatório" e descrição "Comercial (funil, ganhos/perdas, orçamentos) ou financeiro (faturamento, recebido, inadimplência, por cliente)."
- **Quem pode:** qualquer membro autenticado da agência (o servidor não exige administrador). Endpoint também chamável por outras partes do sistema (serviço puro).

### 3. Layout
- Topo: "Tipo", "De", "Até" (celular: um embaixo do outro; desktop: 3 colunas).
- Prévia logo abaixo (atualiza sozinha ao mudar tipo/datas; a anterior fica esmaecida enquanto a nova carrega).
- Rodapé: botões "CSV" e "PDF" ("Baixando…" durante o download). No celular (<640px) a janela é uma folha que sobe de baixo e os botões ocupam a largura.
- **Prévia Financeiro:** quadro vermelho de alertas (se houver); cartões "Faturamento", "Recebido", "A receber", "Inadimplência ({N})" (vermelho se N > 0); seção "Por cliente" com uma linha por cliente: nome, "fat. R$", "receb. R$", "custo R$", "margem R$ (x%)" (margem negativa em vermelho), e a nota "Custo por cliente é o custo medido total (não só do período)."
- **Prévia Comercial:** quadro vermelho de alertas (só quando algum dos alertas da regra 12 se aplica); cartões "Ganhos" ("{qtd} · R$"), "Perdidos", "Orçamentos env./aceit./recus." ("{e}/{a}/{r}"), "Ticket médio"; seção "Funil" (etapa, "{N} entradas · {N} saídas", %); seção "Motivos de perda · tempo médio parado {N} dias" (motivo, "em {etapa}", "{N}× · R$").

### 4. Campos
| Campo (rótulo exato) | Tipo | Obrigatório | Validação/limites | Padrão | Observação |
|---|---|---|---|---|---|
| "Tipo" | lista | Sim | "Financeiro" ou "Comercial" | "Financeiro" | |
| "De" | data | Sim | data válida | dia 1º do mês atual | |
| "Até" | data | Sim | não pode ser antes de "De" ("O fim vem antes do início.") | hoje | Com período invertido a prévia some e os botões ficam desabilitados |

### 5. Ações
| Ação (botão/gesto exato) | Pré-condições | O que acontece | Mensagem de sucesso | Erros possíveis |
|---|---|---|---|---|
| Mudar Tipo/De/Até | — | Recalcula a prévia (GET com `formato=json`) | — | Texto do servidor ou "Não foi possível gerar o relatório." (ex.: 422 "período inválido: início (...) é depois do fim (...)") |
| "CSV" | Período válido | Baixa `relatorio-{tipo}-{de}-{até}.csv` (UTF-8 com BOM, abre com acentos no Excel; números com ponto decimal; uma seção por bloco; alertas ao final como linhas "Alerta") | Arquivo salvo | Toast: texto do servidor ou "Não foi possível baixar o relatório." |
| "PDF" | Período válido | Baixa `relatorio-{tipo}-{de}-{até}.pdf` (A4, uma coluna, tabelas simples, valores em R$ no padrão brasileiro, ex.: "R$ 4.450,00"; alertas em itálico ao final) | Arquivo salvo | Idem |

### 6. Estados
- **Carregando:** dois blocos cinza.
- **Vazio:** Financeiro "Nenhum faturamento no período." (só quando a agência não tem clientes — todos os clientes aparecem, mesmo com zero) · Comercial "Nenhuma movimentação no período." (funil) e "Nenhuma perda no período." · Fallback "Relatório vazio.".
- **Erro:** "Não foi possível gerar o relatório." ou texto do servidor; período invertido: "O fim vem antes do início." no campo "Até".
- **Atualizando:** prévia anterior esmaecida.

### 7. Regras de negócio e por quê
1. **Financeiro — quais faturas entram:** as não canceladas cujo **mês de competência se sobrepõe** ao período (ex.: 15/09–20/09 inclui a fatura inteira de 2026-09).
2. Faturamento = soma dessas faturas; Recebido = as `paga`; A receber = as demais.
3. Inadimplência = faturas vencidas e não pagas **hoje** cuja competência cai no período.
4. **Custo por cliente = custo real de TODO o histórico** (mesma conta do BI/DRE); margem = faturamento − custo; % = margem ÷ faturamento × 100 (1 casa; 0 sem faturamento). *Por quê do aviso:* ainda não existe custo por período; o relatório avisa "O custo por cliente é medido sobre TODO o histórico de apontamentos, não apenas sobre o período deste relatório — a margem por período acima é aproximada." (aparece quando algum cliente tem custo > 0).
5. **Alerta de horas sem custo por cliente:** "{Cliente}: {N} apontamento(s) sem custo/hora definido — a margem está SUPERESTIMADA." — mesmo texto do DRE, agora também na prévia, no CSV e no PDF.
6. **Comercial — funil:** só etapas do pipeline "comercial", **na ordem das etapas do quadro**. Entradas = movimentos PARA a etapa no período; saídas = movimentos DA etapa no período; conversão = saídas ÷ entradas × 100 (0 sem entradas).
7. Ganhos: negócios `ganho` com data de ganho no período; valor = total mensal do orçamento aceito do negócio, ou, sem ele, o valor estimado do negócio. Perdidos: `perdido` com data de perda no período; valor = valor estimado.
8. Tempo médio parado = média de dias entre entrar na última etapa e ser marcado perdido (1 casa).
9. Motivos de perda agrupados por (motivo, etapa em que perdeu); sem motivo → "Sem motivo"; sem etapa → "Sem etapa"; ordenados pela quantidade.
10. Orçamentos enviados/aceitos/recusados pelas datas de envio/aceite/recusa no período; ticket médio = média do total mensal dos aceitos no período (0 se nenhum).
11. O relatório é **somente leitura** e usa o mesmo serviço (`gerar_relatorio`) para tela, CSV e PDF — os números nunca divergem entre formatos.
12. **Comercial — alertas** (só aparecem quando os dados sustentam; sem nenhum, a lista fica vazia — nada é inventado):
    - "{N} negócio(s) parado(s) além do SLA configurado da etapa em que estão." — usa a **mesma** regra de SLA por etapa configurada em Automações (regra "SLA estourado" ativa do Comercial); etapa sem regra de SLA não gera este alerta. Referência: meio-dia (UTC) do dia em que o relatório é gerado.
    - "{N} negócio(s) aberto(s) sem responsável definido." — negócios abertos do funil sem "Responsável" (ninguém faz o follow-up).
    - "{N} orçamento(s) expirando nos próximos 7 dias." — orçamentos ainda Rascunho/Enviado cuja validade cai entre hoje e hoje + 7 dias.
    - "Taxa de perda acima de 50% na(s) etapa(s): {etapas}." — só para etapas com pelo menos 3 entradas no período (uma perda isolada nunca vira alerta).
    Os alertas de SLA, sem responsável e orçamentos expirando olham a situação **atual** (não o período escolhido); o de taxa de perda usa o período.

**Exemplo trabalhado — relatório financeiro.** Período 01/08/2026–30/09/2026, com os dados da Padaria Sol acima: faturas 2026-08 (R$ 4.000,00, paga) e 2026-09 (R$ 4.450,00, aberta, vence 10/09/2026). Gerado em 28/09/2026:
- Faturamento R$ 8.450,00 · Recebido R$ 4.000,00 · A receber R$ 4.450,00 · Inadimplência (1) R$ 4.450,00 (vencida há 18 dias).
- Por cliente — Padaria Sol: fat. R$ 8.450,00 · receb. R$ 4.000,00 · custo R$ 2.100,00 · margem R$ 6.350,00 (6.350 ÷ 8.450 = 75,1%).
- Alertas: "Padaria Sol: 3 apontamento(s) sem custo/hora definido — a margem está SUPERESTIMADA." e o aviso de custo de todo o histórico.

**Exemplo — alertas do relatório comercial.** Gerado em 28/09/2026 para 01/09–28/09: a regra de SLA de "Negociação" é 72 h e há 2 negócios abertos nela desde 20/09 → "2 negócio(s) parado(s) além do SLA configurado da etapa em que estão."; 1 negócio aberto sem responsável → "1 negócio(s) aberto(s) sem responsável definido."; um orçamento Enviado com validade 02/10 → "1 orçamento(s) expirando nos próximos 7 dias."; "Qualificação" teve 4 entradas e 3 perdas no período (75%) → "Taxa de perda acima de 50% na(s) etapa(s): Qualificação.". Uma etapa com 2 entradas e 2 perdas não gera alerta (amostra pequena).

### 8. Fluxo de dados
- Prévia: `useRelatorioPreview` → **GET `/api/relatorios/{comercial|financeiro}?inicio=AAAA-MM-DD&fim=AAAA-MM-DD&formato=json`** (resposta no envelope `{data: ...}`).
- Download: `useBaixarRelatorio` → mesmo endpoint com `formato=csv|pdf`, baixado com o token de sessão e salvo no aparelho.
- Servidor: `gerar_relatorio(repos, org_id, tipo, inicio, fim)` (serviço puro, sem dependência de requisição) → `para_csv` / `para_pdf` (reportlab).
- Tabelas: comercial — `etapa` (pipeline comercial), `pipeline_movimentos`, `negocio`, `orcamento`, `automacao` (regras de SLA, para o alerta de parados); financeiro — `cliente`, `fatura` + BI (`tarefa`, `apontamento`, `profissional`, `funcao`, `pauta`).
- Sem efeitos colaterais; nenhum envio agendado.

### 9. Dependências de configuração
- Comercial: pipeline comercial com etapas e negócios movimentados; orçamentos com datas de envio/aceite/recusa.
- Financeiro: faturas lançadas; tabela de custo/hora em "Custos"; apontamentos na Esteira.
- Nenhuma variável de ambiente específica.

### 10. Limitações conhecidas
- Não há envio agendado de relatório por e-mail (o serviço é chamável, mas nada o agenda).
- Os alertas comerciais de SLA/sem responsável/orçamentos expirando refletem a situação de hoje, não a do período escolhido; o de SLA só existe para etapas com regra de SLA ativa em Automações.
- Custo por cliente não é do período (aviso explícito).
- O PDF é gerado com reportlab, não com o motor xhtml2pdf pedido pelo dono do produto para todos os PDFs.
- CSV usa ponto decimal nos números e datas ISO; PDF mostra o período em datas ISO ("Período: 2026-08-01 a 2026-09-30").
- Só acessível pela página Financeiro, mesmo o relatório comercial.

### 11. Perguntas frequentes
- **P: Onde fica o relatório comercial?** R: Financeiro → "Relatório" → "Tipo": "Comercial".
- **P: Os botões CSV/PDF estão cinza.** R: A data "Até" está antes de "De" ("O fim vem antes do início."), ou um download já está em andamento.
- **P: Escolhi 15 a 20 de setembro e apareceu a fatura inteira de setembro.** R: Correto: uma fatura entra quando o mês da competência se sobrepõe ao período.
- **P: Por que a margem por período é "aproximada"?** R: O custo é de todo o histórico de horas, não só do período.
- **P: O CSV abre com acentos estranhos.** R: O arquivo é UTF-8 com BOM, feito para abrir corretamente no Excel; se o programa pedir, escolha a codificação UTF-8.
- **P: O funil está fora de ordem?** R: Ele segue a ordem das etapas configurada no quadro comercial.
- **P: O PDF mostra valores como "R$ 4.450,00"?** R: Sim, padrão brasileiro.
- **P: Por que o relatório comercial não mostra alerta de negócios parados?** R: Esse alerta usa as regras "SLA estourado" configuradas em Automações; sem regra de SLA ativa na etapa, não há alerta. Os alertas só aparecem quando os dados sustentam.

---

# Capítulo 5 — Limitações globais e itens dependentes de fornecedor/decisão

> O que o IgIg **não faz hoje**, reunido num só lugar. Cada item foi conferido no código final. Use este capítulo para responder "o IgIg faz X?" com honestidade: se está aqui, a resposta é "ainda não" (ou "só em parte"), com o motivo e o que fazer enquanto isso. As limitações específicas de cada tela continuam na seção 10 da própria página.

## 5.1 Dependem de fornecedor externo (homologação, credenciais, contrato)

| Item | Situação no código | O que o usuário vê / o que fazer |
|---|---|---|
| **Publicação real nas redes** (Instagram, Facebook, TikTok, LinkedIn) | Os publicadores existem, mas **nenhum canal está homologado** (`CANAIS_HOMOLOGADOS` vazio; `NOC-REMEDIATE[igig-publishing]`). A rotina da fila roda a cada 5 minutos e ignora canais não homologados; o botão "Publicar"/"Publicar agora" termina em `falhou` com "A integração com {canal} ainda não está disponível (homologação da API pendente)." | Agende no IgIg para organizar a fila e publique diretamente na rede. Conectar o token em Integrações é possível, mas não publica. Quando um canal for homologado, a fila passa a publicá-lo sozinha, sem mudança de tela |
| **Coleta automática de métricas** das redes | Não existe; as métricas são digitadas à mão ("Entrada manual…") | Registre as coletas no painel "Métricas" de cada publicação |
| **Login OAuth das redes** ("Conectar com Instagram") | Não existe; o token é colado à mão e não é validado ao salvar | Um administrador cola o token em Integrações → "Canais de publicação" |
| **Assinatura digital de contratos** | **Simulação (dry-run)**: nenhum provedor (Clicksign, DocuSign, Autentique) integrado (`NOC-REMEDIATE[igig-assinatura]`); o link gerado não funciona; o webhook de assinatura existe e exige `IGIG_ASSINATURA_WEBHOOK_SECRET` | Aviso "Simulação (assinatura digital ainda não integrada) — este link não ativa o contrato de verdade.". Use a modalidade **"Física"** e "Marcar como assinado" |
| **Gateway de pagamento, boleto, Pix e NFS-e** (Asaas/Iugu) | Não implementados; `gateway_id`/`nfse_id` ficam vazios | Rodapé "Baixa manual: …". Cobre por fora e marque a fatura com "Marcar paga" |
| **Detecção de respostas por e-mail (Gmail)** | Depende da configuração GCP/Pub/Sub **da plataforma** (`GMAIL_PUSH_*`) e do app OAuth do Google | Sem ela: "Configuração GCP pendente na plataforma…" e as respostas não são detectadas; acione o suporte |
| **E-mail de convite da Equipe** | Enviado pelo provedor Resend da plataforma (`RESEND_API_KEY`) | Sem a chave (ou se o envio falhar), o convite é criado, o e-mail não sai e a tela avisa "Convite criado, mas o e-mail não foi enviado — copie o link"; use "Copiar link" e peça ao suporte para verificar |
| **Meta Lead Ads** | Depende do app Meta configurado fora do IgIg (Webhooks → Page → `leadgen`) | Configure o app na Meta antes de salvar a fonte em Integrações |
| **Assistente IgIg (chat de ajuda) e Assistente do negócio** | Dependem da chave Anthropic no servidor (em produção, `IGIG_ANTHROPIC_API_KEY`) e do orçamento de IA da organização | Sem chave: "O assistente de IA ainda não foi configurado para este produto." (chat) / "A IA não está configurada (chave da Anthropic ausente)." (card do negócio) |

## 5.2 Dependem de decisão do dono do produto

| Item | Situação | Efeito hoje |
|---|---|---|
| **Consentimento LGPD para o Assistente do negócio** | O catálogo de consentimentos de IA do IgIg **não está ativado** (`consent_features` comentado em `app/main.py`); ativar é decisão pendente do dono do produto | O Assistente do negócio envia dados pessoais do lead (nome, e-mail, telefone, dores etc.) à Anthropic sem um consentimento de IA específico do produto. Nada é gravado nem cacheado. O Assistente IgIg (chat de ajuda) não envia dados da agência |
| **Bloqueio do portal por inadimplência** | Implementado, mas **desligado por padrão** (`IGIG_PORTAL_BLOQUEIO_DIAS` = 0); um único N para o servidor | Ninguém é bloqueado até o responsável técnico definir N > 0 |
| **Motor de PDF** | Os PDFs usam reportlab, não o motor xhtml2pdf pedido para todos os PDFs | Visual simples (A4, tabelas); sem impacto funcional |
| **Visualizador somente leitura** | O papel "Visualizador" **não** tem trava no código: age como membro comum | Não conte com ele para restringir acesso |

## 5.3 Lacunas funcionais confirmadas (sem tela ou sem rotina)

- **Sincronização com Google Agenda:** não existe. O Calendário Editorial é interno ao IgIg; nada é enviado a nem lido de agendas externas.
- **Lembretes de card:** a aba "Lembretes" (card do cliente e do negócio) cria, edita, conclui e exclui lembretes, e a rotina de 5 em 5 minutos os entrega no sino usando o "Título" digitado (ou o nome do cliente/título do negócio, se ficou vazio); o "Responsável" escolhido é avisado quando tem login vinculado, além dos membros do card com login (sem nenhum dos dois, os administradores). Não há e-mail/WhatsApp nem lembrete recorrente.
- **Onboarding após a assinatura** (e-mail/WhatsApp de boas-vindas, formulário): não implementado (`NOC-REMEDIATE[igig-onboarding]`).
- **Régua de cobrança:** sem lembretes automáticos de cobrança; o envio de fatura é manual ("Enviar fatura"), uma por vez. Fechar o mês ("Gerar competência") também é manual.
- **Estorno, pagamento parcial, data retroativa de pagamento, editar/apagar fatura ou item:** não existem.
- **Relatórios agendados por e-mail:** não existem; o relatório é gerado sob demanda (Financeiro → "Relatório").
- **Histórico de movimentos na tela:** os dados existem (`pipeline_movimentos`, inclusive os cards movidos quando uma etapa é excluída), mas não há tela para vê-los fora da linha do tempo do card.
- **Mudar o papel de um membro da Equipe** ou o status de visibilidade das páginas (`status_pagina`): sem tela; feito pela equipe da plataforma.
- **Textos da plataforma base sem acento** (ex.: "Sem permissao", "Pagina nao encontrada", "Sessao expirando"): vêm do seed da plataforma. As mensagens de validação de formato (422) já vêm em português, com acento (ver Capítulo 0 § 12.1) — essa é a exceção.
- **Assistente IgIg:** responde só a partir deste manual; não consulta nem altera dados, não executa ações e não guarda a conversa no servidor.

## 5.4 O que mudou nesta versão (para quem conhecia a anterior)

Resolvido e já descrito nas páginas: rotinas diárias de inadimplência (06:00), fila de publicação e lembretes (a cada 5 min) agora rodam; portal de aprovação pode ser bloqueado por inadimplência (423); "Enviar fatura" e "Marcar como enviada"; excedentes contam só peças avulsas **entregues** (publicadas ou aprovadas), nunca peças do plano; alertas no relatório comercial; custo real em segundos no BI/DRE/relatório; números em padrão brasileiro ("52,8%", "0,40", "1,5 h", "1.500" = mil e quinhentos); exclusão de tarefa com qualquer apontamento ("Excluir mesmo assim"); apagar a pauta apaga os arquivos das peças; papel de etapa nunca some em silêncio (Esteira) e "Papéis das etapas" no Comercial; `/esteira?tarefa=` abre a tarefa; "Paga" no card do cliente só para admin e com confirmação; logo sem SVG; negócio para cliente existente ("Cliente existente" / "Novo negócio"); "Margem indisponível" sem custo/hora; texto correto de "Nova versão"; aviso de pautas conta só as criadas no aceite; pautas automáticas apagadas/movidas não voltam; o contrato vivo mantém "Abrir PDF do contrato"; Custos e Integrações → E-mail escondem controles só-admin; respostas de e-mail avisam também os Administradores; Assistente do negócio fixo em Claude Sonnet; reabrir reinicia o tempo na etapa; estados de carregamento/erro na Inadimplência do Dashboard; rótulo "Proprietário" com acento; o endereço pedido é lembrado depois do login; o menu no celular fecha ao navegar; Assistente IgIg disponível em todas as telas; convite não enviado agora avisa (com link para copiar) em vez de mostrar sucesso falso; a lista "Papel" do convite já mostra só o que quem convida pode conceder; mensagens de validação de formato (422) agora em português, por campo; aba **"Lembretes"** no card do cliente e do negócio (antes não havia como criar um lembrete); "Margem no mês" do Dashboard compara receita e custo do **mesmo mês** (o DRE do Financeiro continua com custo do histórico completo); excedentes descontam do pacote as peças do plano já entregues antes de cobrar as avulsas (a nota da tela mudou); reenviar ou "Marcar como enviada" numa fatura vencida não a volta para "enviada" — ela fica "vencida · enviada em dd/mm/aaaa"; excluir etapa movendo os cards grava o histórico de cada card; a notificação da decisão do cliente no portal abre a tarefa; `/esteira?tarefa=` abre a tarefa mesmo fora do filtro de cliente; mensagens específicas de duplicado (409) também em produção; a notificação de lembrete agora usa o "Título" digitado (não mais o nome do cliente/título do negócio) e avisa também o "Responsável" escolhido, quando tem login vinculado; um lembrete excluído em outra aba devolve 404 "Lembrete não encontrado" (não mais o nome técnico da tabela).
