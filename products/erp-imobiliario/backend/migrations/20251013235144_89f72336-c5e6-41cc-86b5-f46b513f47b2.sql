-- Criar função que atribui role de corretor por padrão para novos usuários
CREATE OR REPLACE FUNCTION public.assign_default_corretor_role()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Atribuir role de corretor por padrão
  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'corretor')
  ON CONFLICT (user_id, role) DO NOTHING;
  
  RETURN NEW;
END;
$$;

-- Modificar o trigger existente para incluir a atribuição de role
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW 
  EXECUTE FUNCTION public.handle_new_user();

-- Criar novo trigger para atribuir role de corretor
CREATE TRIGGER on_auth_user_created_assign_role
  AFTER INSERT ON auth.users
  FOR EACH ROW 
  EXECUTE FUNCTION public.assign_default_corretor_role();