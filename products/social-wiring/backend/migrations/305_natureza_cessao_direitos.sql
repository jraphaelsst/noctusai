-- Migration: natureza_cessao_direitos
-- Schema: social_wiring

SET search_path = social_wiring, public;

-- A compromissário's CESSION of his promise rights ("os compromissários
-- compradores … CEDERAM E TRANSFERIRAM todos os seus direitos e obrigações
-- decorrentes do compromisso …, à FULANO") was typed 'outro'. It is its own
-- nature: it moves the contract position, NOT the domain, so it is never a
-- "última transferência" of ownership. Forward-safe: widens the CHECK
-- vocabulary, drops nothing already valid.
ALTER TABLE social_wiring.matricula_ato_detalhes
    DROP CONSTRAINT IF EXISTS matricula_ato_detalhes_natureza_check;
ALTER TABLE social_wiring.matricula_ato_detalhes
    ADD CONSTRAINT matricula_ato_detalhes_natureza_check
    CHECK (natureza IS NULL OR natureza IN (
        'compra_e_venda', 'doacao', 'permuta', 'partilha', 'dacao',
        'arrematacao', 'adjudicacao', 'integralizacao', 'cessao_direitos',
        'hipoteca', 'alienacao_fiduciaria', 'cancelamento', 'penhora',
        'usufruto', 'indisponibilidade', 'construcao', 'outro'
    ));
