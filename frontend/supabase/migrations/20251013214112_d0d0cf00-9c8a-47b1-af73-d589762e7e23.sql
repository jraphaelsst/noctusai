-- Remover role corretor de joaoraphaelsst@gmail.com
DELETE FROM public.user_roles
WHERE user_id IN (
  SELECT id 
  FROM public.profiles 
  WHERE email = 'joaoraphaelsst@gmail.com'
)
AND role = 'corretor'::app_role;