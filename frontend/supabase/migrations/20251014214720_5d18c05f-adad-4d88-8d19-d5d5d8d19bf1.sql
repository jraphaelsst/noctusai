-- Adicionar novos tipos ao enum tipo_entidade
ALTER TYPE tipo_entidade ADD VALUE IF NOT EXISTS 'imovel';
ALTER TYPE tipo_entidade ADD VALUE IF NOT EXISTS 'perfil_permuta';
ALTER TYPE tipo_entidade ADD VALUE IF NOT EXISTS 'negociacao';