# Documentação Técnica - Sistema de Gestão Imobiliária

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Stack Tecnológica](#stack-tecnológica)
3. [Arquitetura do Sistema](#arquitetura-do-sistema)
4. [Estrutura de Diretórios](#estrutura-de-diretórios)
5. [Banco de Dados](#banco-de-dados)
6. [Sistema de Autenticação](#sistema-de-autenticação)
7. [Sistema de Metas](#sistema-de-metas)
8. [Sistema de Clientes e Funil](#sistema-de-clientes-e-funil)
9. [Sistema de Imóveis](#sistema-de-imóveis)
10. [Sistema de Permutas e Negociações](#sistema-de-permutas-e-negociações)
11. [Edge Functions](#edge-functions)
12. [Hooks Customizados](#hooks-customizados)
13. [Componentes Principais](#componentes-principais)
14. [Gestão de Estado](#gestão-de-estado)
15. [Políticas RLS (Row Level Security)](#políticas-rls)
16. [Funções SQL do Banco](#funções-sql-do-banco)
17. [Padrões de Data e Timezone](#padrões-de-data-e-timezone)
18. [Log de Ações](#log-de-ações)
19. [Configurações e Variáveis de Ambiente](#configurações-e-variáveis-de-ambiente)

---

## Visão Geral

Sistema de gestão para corretores imobiliários que inclui:
- **Dashboard** com métricas e indicadores
- **Gestão de Metas** com automação e cálculo proporcional
- **Funil de Vendas** (Kanban) para acompanhamento de clientes
- **Cadastro de Imóveis** com informações completas
- **Sistema de Permutas** para matching de ofertas
- **Negociações** para acompanhamento de propostas
- **Administração** de usuários e roles

---

## Stack Tecnológica

### Frontend
| Tecnologia | Versão | Finalidade |
|------------|--------|------------|
| React | ^18.3.1 | Framework UI |
| TypeScript | - | Tipagem estática |
| Vite | - | Build tool |
| Tailwind CSS | - | Estilização |
| shadcn/ui | - | Componentes UI |
| TanStack Query | ^5.83.0 | Gerenciamento de estado servidor |
| React Router DOM | ^6.30.1 | Roteamento |
| Zustand | ^5.0.8 | Estado global |
| React Hook Form | ^7.61.1 | Formulários |
| Zod | ^3.25.76 | Validação |
| date-fns | ^4.1.0 | Manipulação de datas |
| Recharts | ^2.15.4 | Gráficos |
| Lucide React | ^0.462.0 | Ícones |
| @dnd-kit | ^6.3.1 | Drag and Drop |

### Backend (Lovable Cloud / Supabase)
| Componente | Finalidade |
|------------|------------|
| PostgreSQL | Banco de dados |
| Auth | Autenticação |
| Edge Functions | Lógica serverless (Deno) |
| RLS | Segurança a nível de linha |
| Realtime | Atualizações em tempo real |

---

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (React + Vite)                   │
├─────────────────────────────────────────────────────────────────┤
│  Pages          │  Components      │  Hooks           │  Store  │
│  - Dashboard    │  - UI (shadcn)   │  - useMetas      │  Zustand│
│  - Metas        │  - Layout        │  - useClientes   │         │
│  - Funil        │  - Modals        │  - useImoveis    │         │
│  - Clientes     │  - Auth          │  - usePermutas   │         │
│  - Imoveis      │  - Filtros       │  - useUserRole   │         │
│  - Permutas     │  - Metas         │  - etc...        │         │
│  - Negociacoes  │                  │                  │         │
│  - Usuarios     │                  │                  │         │
│  - Admin        │                  │                  │         │
└─────────────────┴──────────────────┴──────────────────┴─────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE CLIENT SDK                           │
│              (@supabase/supabase-js + TanStack Query)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        LOVABLE CLOUD                             │
├─────────────────────────────────────────────────────────────────┤
│  Auth           │  Database        │  Edge Functions            │
│  - Login        │  - profiles      │  - criar-meta-hoje         │
│  - Signup       │  - metas         │  - atualizar-status-metas  │
│  - Roles        │  - metas_config  │  - criar-metas-agendadas   │
│                 │  - clientes      │  - mover-cliente-etapa     │
│                 │  - imoveis       │  - registrar-atividade     │
│                 │  - negociacoes   │  - recuperar-senha         │
│                 │  - perfis_permu- │  - requisitar-senha        │
│                 │    tas           │  - desativar-metas-inativos│
│                 │  - user_roles    │                            │
│                 │  - user_actions_ │                            │
│                 │    log           │                            │
└─────────────────┴──────────────────┴────────────────────────────┘
```

---

## Estrutura de Diretórios

```
src/
├── components/
│   ├── auth/              # Componentes de autenticação
│   │   ├── AuthProvider.tsx
│   │   └── LoginForm.tsx
│   ├── clientes/          # Componentes do funil de clientes
│   │   ├── ClienteCard.tsx
│   │   ├── ColunaFunil.tsx
│   │   ├── FiltrosFunil.tsx
│   │   └── NovoClienteDialog.tsx
│   ├── filtros/           # Componentes de filtros
│   │   ├── FiltrosDashboard.tsx
│   │   └── FiltrosMetas.tsx
│   ├── imoveis/           # Componentes de imóveis
│   │   └── NovoImovelDialog.tsx
│   ├── layout/            # Componentes de layout
│   │   ├── Header.tsx
│   │   ├── Layout.tsx
│   │   └── Sidebar.tsx
│   ├── matching/          # Sistema de matching
│   │   └── MatchResultsPanel.tsx
│   ├── metas/             # Componentes de metas
│   │   └── MetasDraggableSection.tsx
│   ├── modals/            # Modais do sistema
│   │   ├── AdicionarRoleModal.tsx
│   │   ├── ConfiguracoesMetasModal.tsx
│   │   ├── ImpedimentosModal.tsx
│   │   ├── MetaDetalhesModal.tsx
│   │   ├── MetricasDetalhesModal.tsx
│   │   ├── NovaMetaModal.tsx
│   │   ├── NovoUsuarioModal.tsx
│   │   └── UsuarioDetalhesModal.tsx
│   ├── permutas/          # Componentes de permutas
│   │   └── NovoPerfilPermutaDialog.tsx
│   └── ui/                # Componentes shadcn/ui
│       └── ... (40+ componentes)
├── hooks/
│   ├── use-mobile.tsx     # Detecção de dispositivo móvel
│   ├── use-toast.ts       # Sistema de toasts
│   ├── useActionLog.ts    # Log de ações
│   ├── useAtividades.ts   # CRUD de atividades
│   ├── useAtualizarStatusMetas.ts
│   ├── useCepSearch.ts    # Busca de CEP
│   ├── useClientes.ts     # CRUD de clientes
│   ├── useConcluirMetaAgrupada.ts
│   ├── useCriarMetaHoje.ts
│   ├── useDebounce.ts     # Debounce helper
│   ├── useFunil.ts        # Dados do funil
│   ├── useImoveis.ts      # CRUD de imóveis
│   ├── useIsAdminOrCoordenador.ts
│   ├── useIsDev.ts
│   ├── useMatching.ts     # Sistema de matching
│   ├── useMetas.ts        # CRUD de metas
│   ├── useMetasConfig.ts  # Configuração de metas
│   ├── useMetasOrdem.ts   # Ordenação de metas
│   ├── usePermutas.ts     # CRUD de permutas
│   ├── useProfiles.ts     # Perfis de usuários
│   ├── useRecuperarSenha.ts
│   ├── useRequisitarSenha.ts
│   ├── useUserProfile.ts
│   ├── useUserRole.ts     # Role do usuário
│   └── useUserRoles.ts    # Todas as roles
├── lib/
│   ├── categorias.ts      # Definições de categorias de metas
│   ├── etapasConfig.ts    # Configuração das etapas do funil
│   ├── imovelValidations.ts
│   ├── utils.ts           # Utilitários gerais
│   └── validations.ts     # Schemas de validação
├── pages/
│   ├── Admin.tsx          # Administração
│   ├── ClienteDetalhes.tsx
│   ├── Clientes.tsx
│   ├── Dashboard.tsx      # Dashboard principal
│   ├── Funil.tsx          # Kanban de clientes
│   ├── Imoveis.tsx
│   ├── Index.tsx
│   ├── LogAcoes.tsx       # Histórico de ações
│   ├── Metas.tsx          # Gestão de metas
│   ├── Negociacoes.tsx
│   ├── NotFound.tsx
│   ├── Permutas.tsx
│   └── Usuarios.tsx       # Gestão de usuários
├── store/
│   ├── authStore.ts       # Estado de autenticação
│   ├── filtrosStore.ts    # Estado dos filtros
│   └── funilFiltrosStore.ts
├── types/
│   ├── clientes.ts        # Tipos de clientes
│   ├── imoveis.ts         # Tipos de imóveis
│   └── index.ts           # Tipos gerais
├── integrations/
│   └── supabase/
│       ├── client.ts      # Cliente Supabase (auto-gerado)
│       └── types.ts       # Tipos do DB (auto-gerado)
├── App.tsx                # Componente raiz
├── App.css
├── main.tsx               # Entry point
└── index.css              # Estilos globais + Design tokens

supabase/
├── config.toml            # Configuração do Supabase
├── functions/
│   ├── atualizar-status-metas/
│   ├── criar-meta-hoje/
│   ├── criar-metas-agendadas/
│   ├── desativar-metas-inativos/
│   ├── mover-cliente-etapa/
│   ├── recuperar-senha/
│   ├── registrar-atividade/
│   └── requisitar-senha/
└── migrations/            # Migrações do banco
```

---

## Banco de Dados

### Tabelas Principais

#### `profiles`
Perfis de usuários sincronizados com `auth.users`.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK, FK para auth.users |
| nome | text | Nome do usuário |
| email | text | Email do usuário |
| telefone | text | Telefone |
| avatar | text | URL do avatar |
| last_activity_at | timestamptz | Última atividade |
| created_at | timestamptz | Data de criação |
| updated_at | timestamptz | Última atualização |

#### `user_roles`
Roles de usuários do sistema.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK |
| user_id | uuid | FK para profiles |
| role | app_role | admin, corretor, coordenador, dev |
| created_at | timestamptz | Data de criação |

#### `metas`
Metas dos corretores.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | text | PK (formato MT0001) |
| usuario_id | uuid | FK para profiles |
| tipo | tipo_meta | diaria, semanal, mensal, anual |
| categoria | categoria_meta | Categoria da meta |
| categoria_custom | text | Categoria personalizada |
| meta_pretendida | integer | Valor alvo |
| meta_realizada | integer | Valor realizado |
| data_prazo | date | Data limite |
| status | status_meta | aberta, concluida, atrasada, no_prazo, vence_amanha |
| nivel_performance | nivel_performance_meta | baixo, regular, bom, excelente |
| dias_restantes | integer | Dias até o prazo |
| carry_in | integer | Carregado do período anterior |
| carry_out | integer | Carregado para próximo período |
| tem_impedimento | boolean | Possui impedimento |
| motivo_impedimento | text | Descrição do impedimento |
| criada_manualmente | boolean | Se foi criada manualmente |
| detalhes | text | Detalhes adicionais |
| nome | text | Nome customizado |
| finalizada_em | timestamptz | Data de conclusão |
| finalizada_no_prazo | boolean | Se foi concluída no prazo |
| conclusao_prazo | conclusao_prazo_meta | no_prazo, atrasada |

#### `metas_config`
Configurações de metas automáticas.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK |
| usuario_id | uuid | FK para profiles |
| tipo | tipo_meta | Tipo da meta (sempre mensal) |
| categoria | categoria_meta | Categoria |
| categoria_custom | text | Categoria personalizada |
| meta_pretendida | integer | Valor alvo mensal |
| ativo | boolean | Se está ativo |
| created_at | timestamptz | Data de criação |
| updated_at | timestamptz | Última atualização |

#### `clientes`
Clientes/Leads do funil.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK |
| usuario_id | uuid | FK para profiles (responsável) |
| nome | text | Nome do cliente |
| email | text | Email |
| telefone | text | Telefone |
| origem | text | Origem do lead |
| interesse | text | Interesse do cliente |
| observacoes | text | Observações |
| etapa_atual | etapa_funil | qualificacao, visitas, proposta, negociacao, fechado |
| probabilidade | integer | Probabilidade de fechamento (0-100) |
| valor_estimado | numeric | Valor estimado do negócio |
| arquivado | boolean | Se está arquivado |
| kanban_pos | integer | Posição no kanban |
| created_at | timestamptz | Data de criação |
| updated_at | timestamptz | Última atualização |

#### `atividades`
Atividades realizadas com clientes.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK |
| cliente_id | uuid | FK para clientes |
| usuario_id | uuid | FK para profiles |
| tipo | tipo_atividade | ligacao, email, reuniao, whatsapp, visita, proposta, negociacao, outro |
| descricao | text | Descrição da atividade |
| data_execucao | timestamptz | Data de execução |
| created_at | timestamptz | Data de criação |

#### `funil_movimentos`
Histórico de movimentações no funil.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK |
| cliente_id | uuid | FK para clientes |
| de_etapa | etapa_funil | Etapa de origem |
| para_etapa | etapa_funil | Etapa de destino |
| responsavel_id | uuid | FK para profiles |
| motivo | text | Motivo da movimentação |
| created_at | timestamptz | Data do movimento |

#### `imoveis`
Cadastro de imóveis.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | text | PK (formato IM0001) |
| owner_id | uuid | FK para profiles |
| status | text | Status do imóvel |
| finalidade | finalidade_imovel | venda, aluguel |
| preco_pedido | numeric | Preço pedido |
| aceita_permutas | boolean | Aceita permutas |
| tipo | tipo_imovel | casa, apartamento, terreno, comercial, rural, outro |
| cep | text | CEP |
| logradouro | text | Endereço |
| numero | text | Número |
| complemento | text | Complemento |
| bairro | text | Bairro |
| cidade | text | Cidade |
| estado | text | Estado |
| latitude | numeric | Latitude |
| longitude | numeric | Longitude |
| area_privativa | numeric | Área privativa (m²) |
| area_total | numeric | Área total (m²) |
| quartos | integer | Quartos |
| suites | integer | Suítes |
| banheiros | integer | Banheiros |
| vagas | integer | Vagas de garagem |
| andar | integer | Andar |
| condominio | numeric | Valor do condomínio |
| iptu | numeric | Valor do IPTU |
| condominio_nome | text | Nome do condomínio |
| ano_construcao | integer | Ano de construção |
| fotos | text[] | URLs das fotos |
| plantas | text[] | URLs das plantas |
| tour_virtual_url | text | URL do tour virtual |
| titulo_anuncio | text | Título do anúncio |
| descricao_seo | text | Descrição SEO |
| palavras_chave | text[] | Palavras-chave |
| pontos_de_interesse | text[] | Pontos de interesse |
| pronto_para_portais | boolean | Pronto para publicar |
| lqs_score_hint | text | Score de qualidade |
| observacoes_negociacao | text | Observações de negociação |
| created_at | timestamptz | Data de criação |
| updated_at | timestamptz | Última atualização |

#### `perfis_permutas`
Perfis de permutas (ofertas).

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | text | PK (formato PP0001) |
| cliente_ofertante_id | uuid | FK para profiles |
| status | text | Status do perfil |
| categoria | categoria_permuta | imovel, movel |
| tipo_imovel | tipo_imovel | Tipo (se imóvel) |
| faixa_preco_min | numeric | Preço mínimo |
| faixa_preco_max | numeric | Preço máximo |
| regiao_preferida | text[] | Regiões preferidas |
| metragem_min | numeric | Metragem mínima |
| metragem_max | numeric | Metragem máxima |
| quartos_min | integer | Quartos mínimos |
| vagas_min | integer | Vagas mínimas |
| tipo_movel | tipo_movel | carro, moto (se móvel) |
| marca | text | Marca (se móvel) |
| modelo | text | Modelo (se móvel) |
| ano_min | integer | Ano mínimo |
| ano_max | integer | Ano máximo |
| quilometragem_max | integer | Km máximo (se móvel) |
| aceita_completar_diferenca | boolean | Aceita completar diferença |
| limite_complemento | numeric | Limite de complemento |
| valor_estimado | numeric | Valor estimado da oferta |
| observacoes | text | Observações |
| created_at | timestamptz | Data de criação |
| updated_at | timestamptz | Última atualização |

#### `negociacoes`
Negociações entre imóveis e permutas.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | text | PK (formato NG0001) |
| owner_id | uuid | FK para profiles |
| imovel_id | text | FK para imoveis |
| perfil_permuta_id | text | FK para perfis_permutas |
| cliente_proprietario_id | uuid | Proprietário do imóvel |
| cliente_ofertante_id | uuid | Ofertante da permuta |
| valor_imovel | numeric | Valor do imóvel |
| valor_permuta | numeric | Valor da permuta |
| valor_complemento | numeric | Valor do complemento |
| status_etapa | status_negociacao | qualificacao, visitas, proposta, negociacao, fechado, cancelado |
| timeline | jsonb | Histórico de eventos |
| observacoes | text | Observações |
| created_at | timestamptz | Data de criação |
| updated_at | timestamptz | Última atualização |

#### `user_actions_log`
Log de ações dos usuários.

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| id | uuid | PK |
| usuario_id | uuid | FK para profiles |
| tipo_acao | tipo_acao | criar, editar, excluir, concluir, arquivar, desarquivar, mover, login, logout |
| tipo_entidade | tipo_entidade | meta, cliente, usuario, atividade, config_meta, auth, imovel, perfil_permuta, negociacao |
| entidade_id | text | ID da entidade afetada |
| descricao | text | Descrição da ação |
| detalhes | jsonb | Detalhes adicionais |
| created_at | timestamptz | Data da ação |

### Enums

```sql
-- Roles de usuário
CREATE TYPE app_role AS ENUM ('admin', 'corretor', 'coordenador', 'dev');

-- Tipos de meta
CREATE TYPE tipo_meta AS ENUM ('diaria', 'semanal', 'mensal', 'anual');

-- Categorias de meta
CREATE TYPE categoria_meta AS ENUM (
  'captacao', 'visitas', 'contatos', 'propostas', 'fechamento',
  'captacao_imoveis', 'captacao_compradores', 'atualizacao_imoveis', 'outro'
);

-- Status de meta
CREATE TYPE status_meta AS ENUM ('aberta', 'concluida', 'atrasada', 'no_prazo', 'vence_amanha');

-- Nível de performance
CREATE TYPE nivel_performance_meta AS ENUM ('baixo', 'regular', 'bom', 'excelente');

-- Conclusão do prazo
CREATE TYPE conclusao_prazo_meta AS ENUM ('no_prazo', 'atrasada');

-- Etapas do funil
CREATE TYPE etapa_funil AS ENUM ('qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado');

-- Tipos de atividade
CREATE TYPE tipo_atividade AS ENUM (
  'ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro'
);

-- Finalidade do imóvel
CREATE TYPE finalidade_imovel AS ENUM ('venda', 'aluguel');

-- Tipos de imóvel
CREATE TYPE tipo_imovel AS ENUM ('casa', 'apartamento', 'terreno', 'comercial', 'rural', 'outro');

-- Categorias de permuta
CREATE TYPE categoria_permuta AS ENUM ('imovel', 'movel');

-- Tipos de móvel
CREATE TYPE tipo_movel AS ENUM ('carro', 'moto');

-- Status de negociação
CREATE TYPE status_negociacao AS ENUM (
  'qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado', 'cancelado'
);

-- Tipos de ação (log)
CREATE TYPE tipo_acao AS ENUM (
  'criar', 'editar', 'excluir', 'concluir', 'arquivar', 'desarquivar', 'mover', 'login', 'logout'
);

-- Tipos de entidade (log)
CREATE TYPE tipo_entidade AS ENUM (
  'meta', 'cliente', 'usuario', 'atividade', 'config_meta', 'auth', 'imovel', 'perfil_permuta', 'negociacao'
);
```

---

## Sistema de Autenticação

### Fluxo de Autenticação

```
┌─────────────────────────────────────────────────────────────┐
│                     AuthProvider                             │
│  - Gerencia estado de autenticação                          │
│  - Escuta eventos onAuthStateChange                         │
│  - Sincroniza usuário com authStore (Zustand)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     LoginForm                                │
│  - Login com email/senha                                     │
│  - Signup com email/senha/nome/telefone                      │
│  - Auto-confirm habilitado                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  Trigger: handle_new_user                    │
│  - Cria profile automaticamente em auth.users               │
│  - Extrai nome e telefone dos metadados                     │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Trigger: assign_default_corretor_role           │
│  - Atribui role 'corretor' por padrão                       │
└─────────────────────────────────────────────────────────────┘
```

### Roles do Sistema

| Role | Permissões |
|------|------------|
| `admin` | Acesso total: gerenciar usuários, ver todas as metas/clientes/imóveis, editar roles |
| `coordenador` | Ver métricas agregadas, gerenciar equipe |
| `corretor` | Gerenciar próprias metas, clientes e imóveis |
| `dev` | Acesso a páginas em desenvolvimento |

### Hooks de Autorização

```typescript
// Verificar role do usuário
const { data: role } = useUserRole();

// Verificar se é admin
const { isAdmin, isLoading } = useIsAdmin();

// Verificar se é admin ou coordenador
const { isAdminOrCoordenador } = useIsAdminOrCoordenador();

// Verificar se é dev
const { isDev } = useIsDev();
```

---

## Sistema de Metas

### Hierarquia de Metas

```
                    ┌─────────────┐
                    │   ANUAL     │  ← Meta anual (projeção)
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────┴────┐ ┌─────┴────┐ ┌─────┴────┐
        │  MENSAL  │ │  MENSAL  │ │  MENSAL  │  ← 12 metas mensais
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
    ┌────────┼────────┐   ...         ...
    │        │        │
┌───┴──┐ ┌───┴──┐ ┌───┴──┐
│SEMANA│ │SEMANA│ │SEMANA│  ← ~4 metas semanais por mês
└──┬───┘ └──┬───┘ └──┬───┘
   │        │        │
  ...      ...      ...
   │
┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐ ┌──┴──┐
│SEG  │ │TER  │ │QUA  │ │QUI  │ │SEX  │  ← 5 metas diárias (dias úteis)
└─────┘ └─────┘ └─────┘ └─────┘ └─────┘
```

### Categorias de Metas

| Categoria | Label | Ordem |
|-----------|-------|-------|
| `atualizacao_imoveis` | Atualização de Imóveis | 0 |
| `captacao_imoveis` | Captação de Imóveis | 1 |
| `captacao_compradores` | Captação de Compradores | 2 |
| `visitas` | Visitas | 3 |
| `propostas` | Propostas | 4 |
| `fechamento` | Fechamento | 5 |
| `outro` | Outro | 8 |

### Cálculo Proporcional de Metas

Quando uma meta é criada, seu valor é calculado proporcionalmente aos dias úteis restantes no período.

```sql
-- Função: calcular_meta_proporcional(p_meta_mensal, p_tipo, p_data_ref)

CASE p_tipo
  WHEN 'diaria' THEN
    -- meta_mensal / dias_úteis_totais_do_mês
    RETURN CEIL(p_meta_mensal / dias_uteis_totais_mes(p_data_ref));
    
  WHEN 'semanal' THEN
    -- (meta_mensal / dias_úteis_totais_mês) * dias_úteis_restantes_semana
    meta_diaria := p_meta_mensal / dias_uteis_totais_mes(p_data_ref);
    RETURN CEIL(meta_diaria * dias_uteis_restantes_semana(p_data_ref));
    
  WHEN 'mensal' THEN
    -- meta_mensal * (dias_úteis_restantes / dias_úteis_totais)
    RETURN CEIL(p_meta_mensal * dias_uteis_restantes_mes / dias_uteis_totais_mes);
    
  WHEN 'anual' THEN
    -- meta_mensal * 12 * (dias_úteis_restantes_ano / dias_úteis_totais_ano)
    RETURN CEIL((p_meta_mensal * 12) * dias_uteis_restantes_ano / dias_uteis_totais_ano);
END CASE;
```

### Fluxo de Criação de Metas

#### Criação Manual (Modal "Nova Meta")
1. Usuário preenche formulário
2. Meta é criada com `criada_manualmente = true`
3. Sempre cria nova meta, mesmo que já exista outra similar

#### Criação Automática (Modal "Configurações")
1. Usuário configura meta mensal por categoria
2. Sistema salva configuração em `metas_config`
3. Para cada tipo (diária, semanal, mensal, anual):
   - Verifica se já existe meta para o período (`ensure_scaffold_meta`)
   - Se não existe, calcula valor proporcional (`calcular_meta_proporcional`)
   - Cria meta com `criada_manualmente = false`

#### Rollup de Metas (Trigger)
Quando uma meta diária é inserida/atualizada, o trigger `trigger_rollup_on_diaria`:
1. Calcula deltas de `meta_pretendida` e `meta_realizada`
2. Atualiza metas agregadas (semanal, mensal, anual) incrementalmente
3. Recalcula `carry_out` e `status`

### Status de Metas

| Status | Critério |
|--------|----------|
| `aberta` | Status inicial (não usado após primeira atualização) |
| `no_prazo` | `data_prazo >= hoje` e não concluída |
| `vence_amanha` | `data_prazo = amanhã` e não concluída |
| `atrasada` | `data_prazo < hoje` e não concluída |
| `concluida` | `meta_realizada >= meta_pretendida` |

### Nível de Performance

| Nível | Critério (% realizado) |
|-------|------------------------|
| `baixo` | < 50% |
| `regular` | 50% - 79% |
| `bom` | 80% - 99% |
| `excelente` | >= 100% |

---

## Sistema de Clientes e Funil

### Etapas do Funil

```
┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│ QUALIFICAÇÃO  │───▶│   VISITAS     │───▶│   PROPOSTA    │───▶│  NEGOCIAÇÃO   │───▶│   FECHADO     │
│               │    │               │    │               │    │               │    │               │
│ Leads novos   │    │ Agendamento   │    │ Proposta      │    │ Contrapro-    │    │ Venda         │
│ e qualifica-  │    │ de visitas    │    │ apresentada   │    │ posta e       │    │ concluída     │
│ ção inicial   │    │               │    │               │    │ ajustes       │    │               │
└───────────────┘    └───────────────┘    └───────────────┘    └───────────────┘    └───────────────┘
```

### Campos do Cliente

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `probabilidade` | 0-100% | Probabilidade de fechamento |
| `valor_estimado` | R$ | Valor estimado do negócio |
| `kanban_pos` | integer | Posição no kanban (menor = topo) |
| `arquivado` | boolean | Se está arquivado |

### Movimentação no Funil

1. Drag-and-drop no Kanban
2. Edge function `mover-cliente-etapa` registra movimento
3. Histórico salvo em `funil_movimentos`

---

## Sistema de Imóveis

### Status do Imóvel

| Status | Descrição |
|--------|-----------|
| `ativo` | Disponível para venda/aluguel |
| `vendido` | Vendido |
| `alugado` | Alugado |
| `inativo` | Temporariamente indisponível |

### Qualidade do Anúncio (LQS)

O campo `lqs_score_hint` indica a qualidade do anúncio:
- Fotos completas
- Descrição detalhada
- Palavras-chave
- Pontos de interesse
- Tour virtual

### Busca de CEP

Hook `useCepSearch` integra com ViaCEP para preenchimento automático de endereço.

---

## Sistema de Permutas e Negociações

### Fluxo de Matching

```
┌─────────────────┐         ┌─────────────────┐
│    IMÓVEL       │         │ PERFIL PERMUTA  │
│  (Oferta)       │         │   (Demanda)     │
│                 │         │                 │
│ - Preço         │◄───────▶│ - Faixa preço   │
│ - Tipo          │         │ - Tipo          │
│ - Localização   │         │ - Regiões       │
│ - Especificações│         │ - Specs min/max │
└────────┬────────┘         └────────┬────────┘
         │                           │
         └───────────┬───────────────┘
                     │
                     ▼
            ┌────────────────┐
            │    MATCHING    │
            │                │
            │ Score calculado│
            │ por critérios: │
            │ - Região       │
            │ - Preço        │
            │ - Especific.   │
            │ - Qualidade    │
            └────────┬───────┘
                     │
                     ▼
            ┌────────────────┐
            │  NEGOCIAÇÃO    │
            │                │
            │ Acompanhamento │
            │ via timeline   │
            └────────────────┘
```

### Etapas da Negociação

Mesmas etapas do funil de clientes:
- `qualificacao`
- `visitas`
- `proposta`
- `negociacao`
- `fechado`
- `cancelado`

---

## Edge Functions

### `criar-meta-hoje`
Cria metas diárias para o dia atual baseado nas configurações ativas.

**Gatilho**: Manual ou automático (cron)  
**Autenticação**: Requer token JWT  
**Dias**: Apenas segunda a sexta

### `criar-metas-agendadas`
Cria metas automáticas no início de períodos (dia, semana, mês, ano).

**Gatilho**: Cron job diário  
**Autenticação**: Service role  
**Lógica**:
- Diárias: seg-sex para categorias específicas
- Semanais: aos domingos
- Mensais: dia 1
- Anuais: 1º de janeiro

### `atualizar-status-metas`
Atualiza status de todas as metas baseado na data atual.

**Gatilho**: Cron job ou manual  
**Atualizações**:
- `dias_restantes` = `data_prazo - hoje`
- Status para `vence_amanha`, `atrasada`, `no_prazo`

### `desativar-metas-inativos`
Desativa configurações de metas para usuários inativos (20+ dias).

**Gatilho**: Cron job  
**Critério**: `last_activity_at < NOW() - 20 days`

### `mover-cliente-etapa`
Move cliente entre etapas do funil e registra histórico.

### `registrar-atividade`
Registra atividade realizada com cliente.

### `requisitar-senha` / `recuperar-senha`
Sistema de recuperação de senha via código temporário.

---

## Hooks Customizados

### Gerenciamento de Dados

| Hook | Finalidade |
|------|------------|
| `useMetas` | CRUD de metas |
| `useMetasConfig` | Configurações de metas automáticas |
| `useClientes` | CRUD de clientes |
| `useImoveis` | CRUD de imóveis |
| `usePermutas` | CRUD de perfis de permuta |
| `useAtividades` | CRUD de atividades |
| `useFunil` | Dados agregados do funil |

### Autorização

| Hook | Retorno |
|------|---------|
| `useUserRole` | Role atual do usuário |
| `useIsAdmin` | `{ isAdmin, isLoading }` |
| `useIsAdminOrCoordenador` | `{ isAdminOrCoordenador }` |
| `useIsDev` | `{ isDev }` |

### Utilitários

| Hook | Finalidade |
|------|------------|
| `useDebounce` | Debounce de valores |
| `useCepSearch` | Busca de endereço por CEP |
| `useActionLog` | Registro de ações |
| `useCriarMetaHoje` | Criação de metas diárias |
| `useConcluirMetaAgrupada` | Conclusão de metas agregadas |
| `useAtualizarStatusMetas` | Atualização de status |

---

## Componentes Principais

### Layout

- **`Layout`**: Container principal com Sidebar e Header
- **`Sidebar`**: Menu lateral de navegação
- **`Header`**: Cabeçalho com user info e ações

### Modais

- **`NovaMetaModal`**: Criação manual de metas
- **`ConfiguracoesMetasModal`**: Configuração de metas automáticas
- **`MetaDetalhesModal`**: Detalhes e edição de meta
- **`ImpedimentosModal`**: Registro de impedimentos
- **`NovoUsuarioModal`**: Criação de usuários
- **`UsuarioDetalhesModal`**: Detalhes de usuário
- **`AdicionarRoleModal`**: Adicionar role a usuário

### Clientes/Funil

- **`ColunaFunil`**: Coluna do Kanban
- **`ClienteCard`**: Card de cliente no Kanban
- **`FiltrosFunil`**: Filtros do funil
- **`NovoClienteDialog`**: Criação de cliente

### Metas

- **`MetasDraggableSection`**: Seção de metas com drag-and-drop
- **`MetricCard`**: Card de métrica
- **`MetaCard`**: Card de meta individual

---

## Gestão de Estado

### Zustand Stores

```typescript
// authStore.ts - Estado de autenticação
interface AuthState {
  user: User | null;
  setUser: (user: User | null) => void;
}

// filtrosStore.ts - Filtros do dashboard/metas
interface FiltrosState {
  dataInicio: Date | null;
  dataFim: Date | null;
  corretorId: string | null;
  // ... setters
}

// funilFiltrosStore.ts - Filtros do funil
interface FunilFiltrosState {
  busca: string;
  responsavelId: string;
  origem: string;
  incluirArquivados: boolean;
  // ... setters
}
```

### TanStack Query

Configuração otimizada:

```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutos
      gcTime: 1000 * 60 * 10, // 10 minutos
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});
```

---

## Políticas RLS

### Padrão de Políticas

1. **Usuários veem seus próprios dados**
   ```sql
   USING (auth.uid() = usuario_id)
   ```

2. **Admins veem todos os dados**
   ```sql
   USING (has_role(auth.uid(), 'admin'))
   ```

3. **Inserção apenas de dados próprios**
   ```sql
   WITH CHECK (auth.uid() = usuario_id)
   ```

### Função Auxiliar

```sql
CREATE FUNCTION has_role(_user_id uuid, _role app_role)
RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM user_roles
    WHERE user_id = _user_id AND role = _role
  )
$$ LANGUAGE sql STABLE SECURITY DEFINER;
```

---

## Funções SQL do Banco

### Funções de Data/Timezone

| Função | Descrição |
|--------|-----------|
| `current_date_sao_paulo()` | Data atual em SP |
| `now_sao_paulo()` | Timestamp atual em SP |
| `normalize_timestamp_sp(ts)` | Normaliza timestamp para SP |

### Funções de Dias Úteis

| Função | Descrição |
|--------|-----------|
| `dias_uteis_mes(date)` | Total de dias úteis no mês |
| `dias_uteis_totais_mes(date)` | Alias para dias_uteis_mes |
| `dias_uteis_restantes_mes(date)` | Dias úteis restantes no mês |
| `dias_uteis_totais_semana(date)` | Total de dias úteis na semana |
| `dias_uteis_restantes_semana(date)` | Dias úteis restantes na semana |
| `dias_uteis_totais_ano(date)` | Total de dias úteis no ano |
| `dias_uteis_restantes_ano(date)` | Dias úteis restantes no ano |

### Funções de Metas

| Função | Descrição |
|--------|-----------|
| `calcular_meta_proporcional(meta_mensal, tipo, data_ref)` | Calcula meta proporcional |
| `ensure_scaffold_meta(usuario_id, tipo, categoria, data_ref)` | Busca meta existente |
| `rollup_metas(usuario_id, categoria, data_ref)` | Rollup de metas agregadas |
| `period_end_date(tipo, data_ref)` | Data final do período |
| `get_period_key(tipo, data_ref)` | Chave do período (YYYY-MM-DD, YYYY-WW, etc) |
| `calcular_nivel_performance(realizada, pretendida)` | Nível de performance |
| `calcular_dias_restantes(data_prazo)` | Dias até o prazo |
| `atualizar_status_metas()` | Atualiza status de todas as metas |
| `concluir_meta_agrupada(meta_id)` | Conclui meta agregada |
| `desativar_metas_usuarios_inativos()` | Desativa configs de usuários inativos |

### Funções de ID

| Função | Descrição |
|--------|-----------|
| `generate_meta_id()` | Gera ID no formato MT0001 |
| `generate_imovel_id()` | Gera ID no formato IM0001 |
| `generate_perfil_permuta_id()` | Gera ID no formato PP0001 |
| `generate_negociacao_id()` | Gera ID no formato NG0001 |

---

## Padrões de Data e Timezone

**Timezone padrão**: `America/Sao_Paulo`

### Regras

1. **Banco de dados**: Todas as datas armazenadas em SP
2. **Edge Functions**: Usam `America/Sao_Paulo`
3. **Frontend**: Exibe em `DD/MM/YYYY`

### Utilitários (src/lib/utils.ts)

```typescript
// Formatar data para exibição
formatDate(dateString: string, includeTime?: boolean): string

// Data atual à meia-noite (para filtros)
getTodayAtMidnight(): Date

// Remove horário de uma data
stripTime(date: Date): Date
```

### Boas Práticas

✅ Usar `formatDate()` para exibir datas  
✅ Usar `getTodayAtMidnight()` em filtros  
✅ Usar dados calculados do banco (`dias_restantes`, `status`)  
✅ Usar funções SQL (`current_date_sao_paulo()`)  

❌ Não usar `new Date()` para comparações  
❌ Não fazer cálculos locais de data  
❌ Não converter manualmente timezones  

---

## Log de Ações

### Tipos de Ação

| Tipo | Descrição |
|------|-----------|
| `criar` | Criação de registro |
| `editar` | Edição de registro |
| `excluir` | Exclusão de registro |
| `concluir` | Conclusão (metas) |
| `arquivar` | Arquivamento (clientes) |
| `desarquivar` | Desarquivamento |
| `mover` | Movimentação (funil) |
| `login` | Login no sistema |
| `logout` | Logout do sistema |

### Registro Automático

Todos os hooks de mutação registram ações automaticamente:

```typescript
supabase.from("user_actions_log").insert({
  usuario_id: user.id,
  tipo_acao: 'criar',
  tipo_entidade: 'meta',
  entidade_id: meta.id,
  descricao: `Criou meta ${meta.tipo}`,
  detalhes: { ... }
}).then(); // Non-blocking
```

---

## Configurações e Variáveis de Ambiente

### Variáveis Disponíveis

| Variável | Descrição |
|----------|-----------|
| `VITE_SUPABASE_URL` | URL do Supabase |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Chave pública |
| `VITE_SUPABASE_PROJECT_ID` | ID do projeto |

### Secrets (Edge Functions)

| Secret | Descrição |
|--------|-----------|
| `SUPABASE_URL` | URL do Supabase |
| `SUPABASE_ANON_KEY` | Chave anônima |
| `SUPABASE_SERVICE_ROLE_KEY` | Chave de serviço |
| `SUPABASE_DB_URL` | URL do banco |
| `RESEND_API_KEY` | API do Resend (emails) |
| `ADMIN_EMAIL` | Email do admin |

### Config do Supabase (supabase/config.toml)

```toml
[auth]
site_url = "..."
enable_signup = true
enable_email_autoconfirm = true

[db]
timezone = "America/Sao_Paulo"
```

---

## Considerações de Segurança

1. **RLS ativo em todas as tabelas**
2. **Função `has_role` com SECURITY DEFINER**
3. **Sanitização de erros em Edge Functions**
4. **Tokens JWT validados em todas as requisições**
5. **Service role apenas em Edge Functions**
6. **Nunca expor chaves privadas no frontend**

---

## Performance

### Otimizações Implementadas

1. **Lazy loading** de páginas
2. **TanStack Query** com staleTime/gcTime otimizados
3. **Debounce** em buscas
4. **Atualização otimista** em mutações
5. **Rollup incremental** de metas (trigger)
6. **Índices** em colunas frequentemente consultadas

---

## Manutenção

### Cron Jobs Recomendados

| Job | Frequência | Edge Function |
|-----|------------|---------------|
| Atualizar status | Diário às 00:05 | `atualizar-status-metas` |
| Criar metas | Diário às 00:10 | `criar-metas-agendadas` |
| Desativar inativos | Semanal | `desativar-metas-inativos` |

---

## Versionamento

- **Última atualização**: 2025-12-30
- **Versão do documento**: 1.0.0

---

## Referências

- [DATE_TIMEZONE_GUIDE.md](./DATE_TIMEZONE_GUIDE.md) - Guia de datas e timezone
- [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) - Sistema de design
- [MODAL_PATTERNS.md](./MODAL_PATTERNS.md) - Padrões de modais
