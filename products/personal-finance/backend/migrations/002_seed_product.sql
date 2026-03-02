-- Seed the Personal Finance product into the core products table
-- Run this against the public schema (core platform)
INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES (
    'Financas Pessoais',
    'personal-finance',
    'Gestao inteligente de financas pessoais, investimentos e patrimonio',
    '💰',
    'http://localhost:8090',
    '#10b981',
    true
) ON CONFLICT (slug) DO NOTHING;
