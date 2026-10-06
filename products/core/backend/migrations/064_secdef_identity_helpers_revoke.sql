-- 061 hard-kept public.current_user_id() and public.is_customer() as
-- "RLS helpers", but no policy, column default or function body uses them
-- and nothing calls them via RPC (verified live 2026-10-06). Kept callable
-- they trip the secdef probe (verify_db_guards) for no benefit, so they
-- follow every other non-helper SECURITY DEFINER function.
REVOKE EXECUTE ON FUNCTION public.current_user_id() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.is_customer() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.current_user_id() TO service_role;
GRANT EXECUTE ON FUNCTION public.is_customer() TO service_role;
