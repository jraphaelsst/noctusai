-- Configurar cron jobs para criação automática de metas
-- Horário de Brasília = UTC-3, então 00h em Brasília = 03h UTC

-- Criar metas diárias todos os dias às 03h UTC (00h Brasília)
SELECT cron.schedule(
  'criar-metas-diarias',
  '0 3 * * *',
  $$
  SELECT net.http_post(
    url := 'https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/criar-metas-automaticas',
    headers := '{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
    body := '{"tipoMeta": "diaria"}'::jsonb
  );
  $$
);

-- Criar metas semanais todo domingo às 03h UTC (00h Brasília)
SELECT cron.schedule(
  'criar-metas-semanais',
  '0 3 * * 0',
  $$
  SELECT net.http_post(
    url := 'https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/criar-metas-automaticas',
    headers := '{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
    body := '{"tipoMeta": "semanal"}'::jsonb
  );
  $$
);

-- Criar metas mensais no dia 1 de cada mês às 03h UTC (00h Brasília)
SELECT cron.schedule(
  'criar-metas-mensais',
  '0 3 1 * *',
  $$
  SELECT net.http_post(
    url := 'https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/criar-metas-automaticas',
    headers := '{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
    body := '{"tipoMeta": "mensal"}'::jsonb
  );
  $$
);

-- Criar metas anuais no dia 1º de janeiro às 03h UTC (00h Brasília)
SELECT cron.schedule(
  'criar-metas-anuais',
  '0 3 1 1 *',
  $$
  SELECT net.http_post(
    url := 'https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/criar-metas-automaticas',
    headers := '{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
    body := '{"tipoMeta": "anual"}'::jsonb
  );
  $$
);