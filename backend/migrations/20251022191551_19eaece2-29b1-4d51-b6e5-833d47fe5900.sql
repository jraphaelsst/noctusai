-- Habilitar extensões necessárias para cron jobs
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- Agendar atualização de status de metas para 23h59 todos os dias (horário de São Paulo - UTC-3)
-- 23h59 em São Paulo = 02h59 UTC do dia seguinte
SELECT cron.schedule(
  'atualizar-status-metas-diario',
  '59 2 * * *', -- 02h59 UTC = 23h59 Brasília
  $$
  SELECT
    net.http_post(
        url:='https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/atualizar-status-metas',
        headers:='{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
        body:='{}'::jsonb
    ) as request_id;
  $$
);