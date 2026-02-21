-- Drop the overly permissive profile visibility policy
DROP POLICY IF EXISTS "Usuários podem ver todos os perfis" ON public.profiles;

-- Create restricted policy: Users can view their own profile
CREATE POLICY "Users can view their own profile"
ON public.profiles
FOR SELECT
USING (auth.uid() = id);

-- Create admin policy: Admins can view all profiles
CREATE POLICY "Admins can view all profiles"
ON public.profiles
FOR SELECT
USING (public.has_role(auth.uid(), 'admin'::app_role));