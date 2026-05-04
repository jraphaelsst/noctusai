-- ============================================================================
-- Media Scheduling — baseline seed data.
--
-- Per Phase 2 spec: seed canonical service-type rows + a small representative
-- set of condominiums. The real production data migration (real WhatsApp ↔
-- OpenAI conversations + real condominiums + real properties from the source
-- DB) is OUT OF SCOPE for Phase 2 — filed as a follow-up project.
--
-- Idempotent via ON CONFLICT — safe to re-apply on top of an existing schema.
--
-- Source reference: /Users/rapha/Documents/repository/NoctusAI/
--                   whatsapp-google-scheduling/scripts/seeds/mock_data.sql
-- ============================================================================

SET search_path = media_scheduling, public;


-- ============================================================================
-- 1. service_types — the canonical 4 services the source bot dispatches on
-- ============================================================================
-- Names match source mock_data.sql verbatim — the LLM dispatcher's tool
-- schema enumerates these literal strings, and the seed scheduling engine's
-- duration tables key by these names. Changing them here breaks downstream.

INSERT INTO media_scheduling.service_types (name, description, active) VALUES
    ('photos',       'Fotografia imobiliária.',         true),
    ('videos',       'Vídeo imobiliário.',              true),
    ('reels',        'Reels para redes sociais.',       true),
    ('virtual_tour', 'Tour virtual do imóvel.',         true)
ON CONFLICT (name) DO NOTHING;


-- ============================================================================
-- 2. condominiums — minimal representative set for end-to-end smoke tests
-- ============================================================================
-- Mirrors the source mock_data.sql shape (4 condos including one with NULL
-- coordinates to exercise the missing-coordinate validation path in the
-- seed TravelLookup adapter). Real production condominiums (~dozens) land
-- in the future real-data-migration project.

INSERT INTO media_scheduling.condominiums (name, address, latitude, longitude, notes, active) VALUES
    ('Reserva One',
     'Estrada do Capuava, Cotia, São Paulo, Brazil',
     -23.6037, -46.8805,
     'Baseline condominium near office region (smoke-test reference).',
     true),
    ('The Square Residences',
     'The Square Open Mall, Cotia, São Paulo, Brazil',
     -23.5897, -46.8337,
     'Office reference condominium for route-optimization smoke tests.',
     true),
    ('Vintage Granja',
     'Avenida São Camilo, Granja Viana, Cotia, São Paulo, Brazil',
     -23.5909, -46.8421,
     'Nearby condominium for same-area scheduling smoke tests.',
     true),
    ('Condomínio Sem Coordenadas',
     'Endereço pendente, Cotia, São Paulo, Brazil',
     NULL, NULL,
     'Used to exercise missing-coordinate validation in TravelLookup.',
     true)
ON CONFLICT (name) DO NOTHING;
