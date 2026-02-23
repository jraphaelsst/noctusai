-- Backfill profiles for existing users without a profile
INSERT INTO public.profiles (id, nome, email, telefone)
SELECT u.id,
       COALESCE(u.raw_user_meta_data->>'nome', u.email),
       u.email,
       COALESCE(u.raw_user_meta_data->>'telefone', '')
FROM auth.users u
LEFT JOIN public.profiles p ON p.id = u.id
WHERE p.id IS NULL;

-- Ensure signup trigger exists to auto-create profiles for new users
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'on_auth_user_created') THEN
    CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();
  END IF;
END $$;