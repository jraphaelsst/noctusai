-- 008: Matrícula text extraction table
-- Stores PDF upload metadata and OCR-extracted text from property registration documents.

CREATE TABLE IF NOT EXISTS erp.matricula_extracoes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    user_id UUID NOT NULL,
    nome_arquivo TEXT NOT NULL,
    tamanho_bytes INTEGER,
    num_paginas INTEGER,
    texto_extraido TEXT,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    erro_mensagem TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS
ALTER TABLE erp.matricula_extracoes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "org_isolation" ON erp.matricula_extracoes
    USING (org_id = ((current_setting('request.jwt.claims', true)::json->>'user_metadata')::json->>'org_id')::uuid);

-- Indexes
CREATE INDEX idx_matricula_extracoes_org_id ON erp.matricula_extracoes(org_id);
CREATE INDEX idx_matricula_extracoes_user_id ON erp.matricula_extracoes(user_id);
CREATE INDEX idx_matricula_extracoes_created_at ON erp.matricula_extracoes(created_at DESC);

-- Trigger for updated_at
CREATE TRIGGER set_updated_at_matricula_extracoes
    BEFORE UPDATE ON erp.matricula_extracoes
    FOR EACH ROW EXECUTE FUNCTION erp.set_timestamps_sp();

-- Sidebar visibility
INSERT INTO erp.status_pagina (nome_pagina, status)
VALUES ('matriculas', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
