-- Migration 007: Certidões Negativas
-- Automated certificate issuance and AI analysis for due diligence

-- Consultation requests (one per person/company)
CREATE TABLE IF NOT EXISTS erp.certidao_consultas (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid,
    created_by uuid NOT NULL,
    tipo_documento text NOT NULL CHECK (tipo_documento IN ('cpf', 'cnpj')),
    documento text NOT NULL,
    nome text NOT NULL,
    data_nascimento text,
    genero text CHECK (genero IS NULL OR genero IN ('M', 'F')),
    rg text,
    nome_mae text,
    nome_pai text,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'concluida', 'erro')),
    total_certidoes int NOT NULL DEFAULT 0,
    concluidas int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Individual certificate results within a consultation
CREATE TABLE IF NOT EXISTS erp.certidao_resultados (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    consulta_id uuid NOT NULL REFERENCES erp.certidao_consultas(id) ON DELETE CASCADE,
    org_id uuid,
    tipo text NOT NULL,
    nome_display text NOT NULL,
    ordem int NOT NULL DEFAULT 0,
    status text NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'processando', 'sucesso', 'erro')),
    analise_ia text,
    arquivo_url text,
    arquivo_nome text,
    api_response jsonb,
    erro_mensagem text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_org ON erp.certidao_consultas(org_id);
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_status ON erp.certidao_consultas(status);
CREATE INDEX IF NOT EXISTS idx_certidao_consultas_documento ON erp.certidao_consultas(documento);
CREATE INDEX IF NOT EXISTS idx_certidao_resultados_consulta ON erp.certidao_resultados(consulta_id);
CREATE INDEX IF NOT EXISTS idx_certidao_resultados_org ON erp.certidao_resultados(org_id);

-- RLS policies
ALTER TABLE erp.certidao_consultas ENABLE ROW LEVEL SECURITY;
ALTER TABLE erp.certidao_resultados ENABLE ROW LEVEL SECURITY;

-- Consultas: users can see their own consultations
CREATE POLICY certidao_consultas_select ON erp.certidao_consultas
    FOR SELECT TO authenticated USING (created_by = auth.uid());
CREATE POLICY certidao_consultas_insert ON erp.certidao_consultas
    FOR INSERT TO authenticated WITH CHECK (created_by = auth.uid());
CREATE POLICY certidao_consultas_update ON erp.certidao_consultas
    FOR UPDATE TO authenticated USING (created_by = auth.uid());
CREATE POLICY certidao_consultas_delete ON erp.certidao_consultas
    FOR DELETE TO authenticated USING (created_by = auth.uid());

-- Resultados: users can see results for their consultations
CREATE POLICY certidao_resultados_select ON erp.certidao_resultados
    FOR SELECT TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = auth.uid())
    );
CREATE POLICY certidao_resultados_insert ON erp.certidao_resultados
    FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY certidao_resultados_update ON erp.certidao_resultados
    FOR UPDATE TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = auth.uid())
    );
CREATE POLICY certidao_resultados_delete ON erp.certidao_resultados
    FOR DELETE TO authenticated USING (
        EXISTS (SELECT 1 FROM erp.certidao_consultas WHERE id = consulta_id AND created_by = auth.uid())
    );

-- Service role bypass (for background processing)
CREATE POLICY certidao_consultas_service ON erp.certidao_consultas
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY certidao_resultados_service ON erp.certidao_resultados
    FOR ALL USING (auth.role() = 'service_role');

-- Auto-update timestamps
CREATE TRIGGER set_certidao_consultas_updated
    BEFORE UPDATE ON erp.certidao_consultas
    FOR EACH ROW
    EXECUTE FUNCTION erp.set_timestamps_sp();

CREATE TRIGGER set_certidao_resultados_updated
    BEFORE UPDATE ON erp.certidao_resultados
    FOR EACH ROW
    EXECUTE FUNCTION erp.set_timestamps_sp();

-- Seed sidebar page entry
INSERT INTO erp.status_pagina (nome_pagina, status)
VALUES ('certidoes', 'producao')
ON CONFLICT (nome_pagina) DO NOTHING;
