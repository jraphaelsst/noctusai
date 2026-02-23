-- Criar tabela de profiles vinculada aos usuários
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  nome TEXT NOT NULL,
  email TEXT NOT NULL,
  telefone TEXT NOT NULL,
  avatar TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- RLS Policies para profiles
CREATE POLICY "Usuários podem ver todos os perfis"
ON public.profiles
FOR SELECT
TO authenticated
USING (true);

CREATE POLICY "Usuários podem atualizar seu próprio perfil"
ON public.profiles
FOR UPDATE
TO authenticated
USING (auth.uid() = id);

CREATE POLICY "Usuários podem inserir seu próprio perfil"
ON public.profiles
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = id);

-- Trigger para atualizar updated_at
CREATE TRIGGER update_profiles_updated_at
BEFORE UPDATE ON public.profiles
FOR EACH ROW
EXECUTE FUNCTION public.update_updated_at_column();

-- Função para criar perfil automaticamente ao registrar usuário
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, nome, email, telefone)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'nome', NEW.email),
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'telefone', '')
  );
  RETURN NEW;
END;
$$;

-- Trigger para criar perfil ao registrar usuário
CREATE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW
EXECUTE FUNCTION public.handle_new_user();

-- PRIMEIRO: Remover todas as policies da tabela metas
DROP POLICY IF EXISTS "Users can view their own metas" ON public.metas;
DROP POLICY IF EXISTS "Users can insert metas for their corretores" ON public.metas;
DROP POLICY IF EXISTS "Users can update their own metas" ON public.metas;
DROP POLICY IF EXISTS "Users can delete their own metas" ON public.metas;

-- Adicionar coluna temporária na tabela metas
ALTER TABLE public.metas ADD COLUMN profile_id UUID;

-- Remover constraint e coluna antiga
ALTER TABLE public.metas DROP CONSTRAINT IF EXISTS metas_corretor_id_fkey;
ALTER TABLE public.metas DROP COLUMN corretor_id CASCADE;

-- Renomear nova coluna e adicionar constraint
ALTER TABLE public.metas RENAME COLUMN profile_id TO corretor_id;
ALTER TABLE public.metas ADD CONSTRAINT metas_corretor_id_fkey 
  FOREIGN KEY (corretor_id) REFERENCES public.profiles(id) ON DELETE CASCADE;

-- Criar novas RLS policies para metas usando profiles
CREATE POLICY "Users can view their own metas"
ON public.metas
FOR SELECT
TO authenticated
USING (auth.uid() = corretor_id);

CREATE POLICY "Users can insert their own metas"
ON public.metas
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() = corretor_id);

CREATE POLICY "Users can update their own metas"
ON public.metas
FOR UPDATE
TO authenticated
USING (auth.uid() = corretor_id);

CREATE POLICY "Users can delete their own metas"
ON public.metas
FOR DELETE
TO authenticated
USING (auth.uid() = corretor_id);

-- Admins podem ver todas as metas
CREATE POLICY "Admins can view all metas"
ON public.metas
FOR SELECT
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

-- Admins podem atualizar todas as metas
CREATE POLICY "Admins can update all metas"
ON public.metas
FOR UPDATE
TO authenticated
USING (public.has_role(auth.uid(), 'admin'));

-- Remover tabela antiga de corretores
DROP TABLE IF EXISTS public.corretores CASCADE;