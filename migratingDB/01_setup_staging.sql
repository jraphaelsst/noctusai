-- =====================================================================
-- ETAPA 1: Configuração, lookup tables e staging tables
-- Cria a infraestrutura temporária para a migração
-- =====================================================================

-- Validate that at least one user exists
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM auth.users LIMIT 1) THEN
    RAISE EXCEPTION 'No users found in auth.users. Create at least one user before running this migration.';
  END IF;
END $$;

-- Config table with owner UUID
CREATE TEMP TABLE migration_config (
  key TEXT PRIMARY KEY,
  value TEXT
);

INSERT INTO migration_config VALUES ('owner_id', '0ea5f710-fd59-4e66-94b3-d1cc8ca2cbcd');
INSERT INTO migration_config VALUES ('profile_id', '0ea5f710-fd59-4e66-94b3-d1cc8ca2cbcd');

-- ─────────────────────────────────────────────────────────────────────
-- LOOKUP TABLES
-- ─────────────────────────────────────────────────────────────────────

CREATE TEMP TABLE tipo_imovel_map (
  old_id INTEGER PRIMARY KEY,
  novo_tipo TEXT NOT NULL,
  descricao TEXT
);

INSERT INTO tipo_imovel_map VALUES
  (1,  'apartamento',  'Apartamento (AP* refs)'),
  (2,  'casa',         'Casa em Condomínio / Casa secundária'),
  (3,  'terreno',      'Terreno (TE* refs)'),
  (6,  'comercial',    'Galpão / Comercial (GA* refs)'),
  (7,  'casa',         'Casa (77% dos imóveis, tipo mais comum)'),
  (8,  'rural',        'Chácara / Rural'),
  (9,  'comercial',    'Sala Comercial'),
  (10, 'apartamento',  'Cobertura / Apartamento especial'),
  (11, 'comercial',    'Prédio Comercial (PR* refs)'),
  (13, 'rural',        'Sítio / Fazenda'),
  (14, 'terreno',      'Área / Loteamento (AR* refs)');

CREATE TEMP TABLE zona_map (
  old_id INTEGER PRIMARY KEY,
  nova_zona TEXT NOT NULL
);

INSERT INTO zona_map VALUES
  (1, 'norte'),
  (4, 'oeste'),
  (6, 'sul'),
  (7, 'leste'),
  (8, 'norte');

CREATE TEMP TABLE tipo_automovel_map (
  old_id INTEGER PRIMARY KEY,
  novo_tipo TEXT NOT NULL
);

INSERT INTO tipo_automovel_map VALUES
  (1, 'carro');

-- ─────────────────────────────────────────────────────────────────────
-- ID MAPPING TABLES
-- ─────────────────────────────────────────────────────────────────────

CREATE TEMP TABLE imovel_id_map (
  old_id INTEGER PRIMARY KEY,
  new_uuid UUID NOT NULL DEFAULT gen_random_uuid()
);

CREATE TEMP TABLE permuta_id_map (
  old_id INTEGER PRIMARY KEY,
  new_uuid UUID NOT NULL DEFAULT gen_random_uuid()
);

CREATE TEMP TABLE proprietario_id_map (
  old_id INTEGER PRIMARY KEY,
  new_uuid UUID NOT NULL DEFAULT gen_random_uuid()
);

CREATE TEMP TABLE condominio_id_map (
  old_id INTEGER PRIMARY KEY,
  new_uuid UUID NOT NULL DEFAULT gen_random_uuid()
);

-- ─────────────────────────────────────────────────────────────────────
-- STAGING TABLES
-- ─────────────────────────────────────────────────────────────────────

CREATE TEMP TABLE stg_imovel (
  id INTEGER PRIMARY KEY,
  ref TEXT,
  valor_venda INTEGER,
  condominio_id INTEGER,
  criado_por_id INTEGER,
  proprietario_id INTEGER,
  tipo_id INTEGER,
  zona_id INTEGER,
  corretor_id INTEGER
);

CREATE TEMP TABLE stg_permuta_imovel (
  id INTEGER PRIMARY KEY,
  tipo_id INTEGER,
  condominio TEXT,
  zona_id INTEGER,
  cep TEXT,
  estado TEXT,
  cidade TEXT,
  bairro TEXT,
  endereco TEXT,
  valor INTEGER,
  criado_por_id INTEGER,
  proprietario_id INTEGER,
  codigo TEXT,
  numero TEXT,
  corretor_id INTEGER,
  ref TEXT
);

CREATE TEMP TABLE stg_interesse_imovel (
  id INTEGER PRIMARY KEY,
  observacoes TEXT,
  criado_em TIMESTAMPTZ,
  atualizado_em TIMESTAMPTZ,
  criado_por_id INTEGER,
  imovel_id INTEGER,
  estado TEXT,
  tipo_imovel_id INTEGER,
  valor_maximo NUMERIC,
  valor_minimo NUMERIC,
  zona_id INTEGER,
  bairro TEXT,
  cep TEXT,
  cidade TEXT,
  endereco TEXT
);

CREATE TEMP TABLE stg_interesse_automovel (
  id INTEGER PRIMARY KEY,
  criado_em TIMESTAMPTZ,
  atualizado_em TIMESTAMPTZ,
  criado_por_id INTEGER,
  imovel_id INTEGER,
  tipo_automovel_id INTEGER,
  valor_maximo NUMERIC,
  valor_minimo NUMERIC
);

CREATE TEMP TABLE stg_permuta_interesse (
  id INTEGER PRIMARY KEY,
  cep TEXT,
  estado TEXT,
  cidade TEXT,
  bairro TEXT,
  endereco TEXT,
  valor_minimo NUMERIC,
  valor_maximo NUMERIC,
  observacoes TEXT,
  criado_em TIMESTAMPTZ,
  atualizado_em TIMESTAMPTZ,
  criado_por_id INTEGER,
  permuta_imovel_id INTEGER,
  tipo_imovel_id INTEGER,
  zona_id INTEGER
);
