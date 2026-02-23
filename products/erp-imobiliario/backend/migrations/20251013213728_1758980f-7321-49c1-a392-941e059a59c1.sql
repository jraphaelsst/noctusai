-- Adicionar roles admin e dev para joaoraphaelsst@gmail.com
INSERT INTO public.user_roles (user_id, role)
SELECT id, 'admin'::app_role
FROM public.profiles
WHERE email = 'joaoraphaelsst@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;

INSERT INTO public.user_roles (user_id, role)
SELECT id, 'dev'::app_role
FROM public.profiles
WHERE email = 'joaoraphaelsst@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;