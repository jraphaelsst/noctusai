
-- Habilitar extensões necessárias
CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- Configurar cron job para criar metas diárias automaticamente
-- Executa todos os dias às 00:01 (horário do servidor)
SELECT cron.schedule(
  'criar-metas-diarias-automaticas',
  '1 0 * * *',
  $$
  SELECT
    net.http_post(
        url:='https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/criar-metas-agendadas',
        headers:='{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
        body:='{}'::jsonb
    ) as request_id;
  $$
);
