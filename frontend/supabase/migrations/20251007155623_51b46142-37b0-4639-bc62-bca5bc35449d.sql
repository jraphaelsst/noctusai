-- Remover o default existente
ALTER TABLE metas ALTER COLUMN status DROP DEFAULT;

-- Criar novo enum com o valor correto
CREATE TYPE status_meta_new AS ENUM ('aberta', 'concluida', 'atrasada', 'no_prazo');

-- Converter coluna para texto temporariamente
ALTER TABLE metas ALTER COLUMN status TYPE TEXT;

-- Atualizar valores
UPDATE metas SET status = 'aberta' WHERE status = 'em_andamento';

-- Converter para o novo enum
ALTER TABLE metas 
  ALTER COLUMN status TYPE status_meta_new 
  USING status::status_meta_new;

-- Remover o enum antigo
DROP TYPE status_meta;

-- Renomear o novo enum
ALTER TYPE status_meta_new RENAME TO status_meta;

-- Definir o novo default
ALTER TABLE metas ALTER COLUMN status SET DEFAULT 'aberta'::status_meta;