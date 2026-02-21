-- Habilitar extensão pg_cron se ainda não estiver habilitada
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Criar cron job para executar diariamente às 3h da manhã (horário de Brasília)
-- Executa a edge function que verifica e desativa metas de usuários inativos
SELECT cron.schedule(
  'desativar-metas-usuarios-inativos',
  '0 6 * * *', -- 6h UTC = 3h Brasília
  $$
  SELECT
    net.http_post(
      url:='https://cbwkcnskstiathdzwtmn.supabase.co/functions/v1/desativar-metas-inativos',
      headers:='{"Content-Type": "application/json", "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImNid2tjbnNrc3RpYXRoZHp3dG1uIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTkxNjQ0MTQsImV4cCI6MjA3NDc0MDQxNH0.5V6Dgu3DzFzozKpi1Oh9zOxBvPWZraDcrBsL_kit1-M"}'::jsonb,
      body:=concat('{"time": "', now(), '"}')::jsonb
    ) as request_id;
  $$
);