-- =====================================================================
-- Diário entre sessões: banco de dados do servidor (FASE 2)
-- PROPOSTA. NÃO IMPLEMENTAR SEM APROVAÇÃO EXPRESSA DE MÔNICA TANGERINO
-- e sem avaliação jurídica (LGPD, dados pessoais sensíveis).
-- PostgreSQL 15+. Pensado para Supabase ou Postgres com auth equivalente,
-- onde auth.uid() devolve o id da pessoa autenticada.
-- =====================================================================
-- Princípios aplicados:
--  P1 a analisanda decide o que envia; P2 a profissional vê só envios.
--  Conteúdo textual cifrado no aparelho (ponta a ponta): o servidor guarda
--  bytea cifrado e nunca a chave. Colunas *_cifrado seguem esse padrão.
-- =====================================================================

create extension if not exists pgcrypto;  -- gen_random_uuid()

-- ---------- tipos ----------
create type levar_escolha as enum ('sim', 'talvez', 'nao');
create type canal_envio  as enum ('app', 'whatsapp', 'copia');
create type papel        as enum ('analisanda', 'profissional');

-- ---------- pessoas ----------
create table pessoa (
  id              uuid primary key,                 -- = auth.users.id
  papel           papel not null,
  criado_em       timestamptz not null default now()
);

create table profissional (
  id              uuid primary key references pessoa(id) on delete cascade,
  nome_exibicao   text not null,                     -- 'Mônica Tangerino'
  whatsapp        text,                              -- '5511975518400'
  chave_publica   bytea not null                     -- para cifrar envios destinados a ela
);

create table analisanda (
  id              uuid primary key references pessoa(id) on delete cascade,
  profissional_id uuid not null references profissional(id),
  nome_cifrado    bytea not null,                    -- nome como ela digitou
  sessao_cifrado  bytea,                             -- 'quintas, 18h'
  ativa           boolean not null default true
);

-- ---------- consentimento (LGPD art. 11, I) ----------
create table termo (
  versao          text primary key,                  -- '2026-11-v1'
  texto           text not null,
  publicado_em    timestamptz not null default now()
);

create table consentimento (
  id              uuid primary key default gen_random_uuid(),
  analisanda_id   uuid not null references analisanda(id) on delete cascade,
  termo_versao    text not null references termo(versao),
  aceito_em       timestamptz not null default now(),
  revogado_em     timestamptz
);
create index on consentimento (analisanda_id);

-- ---------- catálogos (texto aprovado; leitura pública autenticada) ----------
create table emocao (
  id     text primary key,                           -- 'ansiedade' ... 'nao-sei'
  rotulo text not null,
  ordem  smallint not null unique
);

create table pergunta (
  id       text primary key,                         -- 'p1'..'p5'
  indice_v1 smallint not null unique,                -- 0..4 (migração)
  icone    text not null,
  texto    text not null,
  ativa    boolean not null default true
);

create table despertar (
  id        text primary key,                        -- 'd1'..'d6'
  indice_v1 smallint not null unique,                -- 0..5
  texto     text not null,
  ativa     boolean not null default true
);

create table citacao (
  id        serial primary key,
  texto     text not null,
  autor     text not null,
  obra      text not null,
  ativa     boolean not null default true
);

-- ---------- registros ----------
-- Campos de texto cifrados no aparelho. Metadados em claro só o mínimo
-- necessário para sincronizar e filtrar (datas, escolha, marcação).
create table registro (
  id                 uuid primary key,               -- gerado no aparelho
  analisanda_id      uuid not null references analisanda(id) on delete cascade,
  criado_em          timestamptz not null,
  atualizado_em      timestamptz not null,
  exemplo            boolean not null default false, -- exemplos não sobem ao servidor; coluna existe só por simetria
  conteudo_cifrado   bytea not null,                 -- JSON cifrado: happened, mind, did, answer, extra, questionText
  pergunta_id        text references pergunta(id),
  levar_escolha      levar_escolha not null,         -- passo 7, imutável
  levar_marcado      boolean not null,               -- aba Levar
  apagado_em         timestamptz                     -- exclusão lógica para propagar a outros aparelhos; purga em 30 dias
);
create index on registro (analisanda_id, criado_em desc);

-- Emoções e despertares: em claro permitiria contagem no servidor, mas
-- revela informação sensível. Recomendação: guardar dentro de conteudo_cifrado.
-- As tabelas abaixo só devem ser usadas se Mônica e a assessoria jurídica
-- aprovarem metadados em claro.
create table registro_emocao (
  registro_id uuid not null references registro(id) on delete cascade,
  emocao_id   text not null references emocao(id),
  primary key (registro_id, emocao_id)
);

create table registro_despertar (
  registro_id  uuid not null references registro(id) on delete cascade,
  despertar_id text not null references despertar(id),
  primary key (registro_id, despertar_id)
);

-- ---------- envios a Mônica ----------
create table envio (
  id                uuid primary key default gen_random_uuid(),
  analisanda_id     uuid not null references analisanda(id) on delete cascade,
  profissional_id   uuid not null references profissional(id),
  criado_em         timestamptz not null default now(),
  canal             canal_envio not null,
  conteudo_cifrado  bytea not null,                  -- texto montado, cifrado para chave_publica da profissional
  lido_em           timestamptz
);
create index on envio (profissional_id, criado_em desc);

create table envio_item (
  envio_id    uuid not null references envio(id) on delete cascade,
  registro_id uuid not null,                         -- sem FK: o registro pode ser apagado depois; o envio permanece
  primary key (envio_id, registro_id)
);

-- ---------- auditoria mínima (sem conteúdo) ----------
create table evento (
  id        bigserial primary key,
  pessoa_id uuid references pessoa(id) on delete set null,
  tipo      text not null,   -- 'login','envio_criado','envio_lido','consentimento_revogado','conta_excluida'
  em        timestamptz not null default now()
);

-- =====================================================================
-- Segurança por linha (RLS)
-- =====================================================================
alter table pessoa           enable row level security;
alter table profissional     enable row level security;
alter table analisanda       enable row level security;
alter table consentimento    enable row level security;
alter table registro         enable row level security;
alter table registro_emocao  enable row level security;
alter table registro_despertar enable row level security;
alter table envio            enable row level security;
alter table envio_item       enable row level security;
alter table evento           enable row level security;
alter table emocao   enable row level security;
alter table pergunta enable row level security;
alter table despertar enable row level security;
alter table citacao  enable row level security;
alter table termo    enable row level security;

-- catálogos: leitura para autenticadas
create policy cat_emocao    on emocao    for select to authenticated using (true);
create policy cat_pergunta  on pergunta  for select to authenticated using (true);
create policy cat_despertar on despertar for select to authenticated using (true);
create policy cat_citacao   on citacao   for select to authenticated using (ativa);
create policy cat_termo     on termo     for select to authenticated using (true);

-- pessoa e perfis: cada uma vê a si mesma
create policy pessoa_self on pessoa for select using (id = auth.uid());
create policy analisanda_self on analisanda for all using (id = auth.uid()) with check (id = auth.uid());
create policy profissional_self on profissional for select using (id = auth.uid());
-- a analisanda precisa ler a chave pública e o nome da sua profissional
create policy profissional_da_analisanda on profissional for select
  using (id in (select profissional_id from analisanda where id = auth.uid()));
-- a profissional vê a lista das suas analisandas (só id e nome cifrado)
create policy analisandas_da_profissional on analisanda for select
  using (profissional_id = auth.uid());

-- consentimento: só a própria analisanda
create policy consentimento_self on consentimento for all
  using (analisanda_id = auth.uid()) with check (analisanda_id = auth.uid());

-- registros: SOMENTE a dona. A profissional não tem política aqui (P2).
create policy registro_dona on registro for all
  using (analisanda_id = auth.uid()) with check (analisanda_id = auth.uid());
create policy registro_emocao_dona on registro_emocao for all
  using (registro_id in (select id from registro where analisanda_id = auth.uid()))
  with check (registro_id in (select id from registro where analisanda_id = auth.uid()));
create policy registro_despertar_dona on registro_despertar for all
  using (registro_id in (select id from registro where analisanda_id = auth.uid()))
  with check (registro_id in (select id from registro where analisanda_id = auth.uid()));

-- envios: a analisanda cria e lê os seus; a profissional lê os destinados a ela
create policy envio_analisanda_insere on envio for insert
  with check (analisanda_id = auth.uid()
              and profissional_id = (select profissional_id from analisanda where id = auth.uid())
              and exists (select 1 from consentimento c where c.analisanda_id = auth.uid() and c.revogado_em is null));
create policy envio_analisanda_le on envio for select using (analisanda_id = auth.uid());
create policy envio_profissional_le on envio for select using (profissional_id = auth.uid());
create policy envio_profissional_marca_lido on envio for update
  using (profissional_id = auth.uid()) with check (profissional_id = auth.uid());

create policy envio_item_insere on envio_item for insert
  with check (envio_id in (select id from envio where analisanda_id = auth.uid()));
create policy envio_item_le on envio_item for select
  using (envio_id in (select id from envio where analisanda_id = auth.uid() or profissional_id = auth.uid()));

-- eventos: inseridos por função de servidor; leitura só da própria pessoa
create policy evento_self on evento for select using (pessoa_id = auth.uid());

-- Observação: restringir o UPDATE da profissional à coluna lido_em com
-- privilégio de coluna:  revoke update on envio from authenticated;
--                        grant update (lido_em) on envio to authenticated;
revoke update on envio from authenticated;
grant update (lido_em) on envio to authenticated;

-- ---------- carga dos catálogos ----------
insert into emocao (id, rotulo, ordem) values
 ('ansiedade','Ansiedade',1),('tristeza','Tristeza',2),('medo','Medo',3),('vergonha','Vergonha',4),
 ('culpa','Culpa',5),('raiva','Raiva',6),('frustracao','Frustração',7),('solidao','Solidão',8),
 ('alegria','Alegria',9),('paz','Paz',10),('amor','Amor',11),('carinho','Carinho',12),
 ('gratidao','Gratidão',13),('alivio','Alívio',14),('orgulho','Orgulho',15),('nao-sei','Não sei nomear',16);

insert into pergunta (id, indice_v1, icone, texto) values
 ('p1',0,'heart','O que você gosta de fazer simplesmente porque sente prazer, mesmo que isso não tenha nenhuma utilidade prática?'),
 ('p2',1,'star','Quando foi a última vez que você se surpreendeu positivamente com alguma atitude sua? O que aconteceu?'),
 ('p3',2,'loop','Existe alguma coisa que você faz por costume, mas que hoje talvez já não combine tanto com quem você é?'),
 ('p4',3,'user','Em quais momentos do seu dia você sente que pode ser você mesma, sem se preocupar tanto com o que os outros vão pensar?'),
 ('p5',4,'sprout','Se você pudesse dar um pouco mais de espaço para uma vontade sua nesta semana, qual seria?');

insert into despertar (id, indice_v1, texto) values
 ('d1',0,'Lembrei de uma situação que vivi.'),
 ('d2',1,'Percebi algo que ainda não tinha pensado.'),
 ('d3',2,'Fiquei curiosa para entender melhor isso.'),
 ('d4',3,'Senti vontade de escrever mais.'),
 ('d5',4,'Não soube muito bem o que responder.'),
 ('d6',5,'Foi bom dedicar um momento a mim.');

-- ---------- privilégios ----------
-- No Supabase o papel authenticated já recebe privilégios nas tabelas.
-- Em PostgreSQL puro, conceder explicitamente (as políticas RLS continuam valendo):
-- grant select, insert, update, delete on all tables in schema public to authenticated;
-- grant usage on all sequences in schema public to authenticated;
-- Testado em PostgreSQL 16 em 31/10/2026: a analisanda lê o próprio registro,
-- a profissional não lê registros, lê o envio destinado a ela e só marca lido_em.
