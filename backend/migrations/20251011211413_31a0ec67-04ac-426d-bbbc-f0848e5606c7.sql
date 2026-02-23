-- Fix critical security issue: Remove overly permissive profiles policy
-- Drop the policy that allows ANY authenticated user to access all profiles
DROP POLICY IF EXISTS "Deny public access to profiles" ON public.profiles;

-- Ensure proper user-scoped policies exist
-- These will only create if they don't already exist
DO $$ 
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
    AND tablename = 'profiles' 
    AND policyname = 'Users can view their own profile'
  ) THEN
    CREATE POLICY "Users can view their own profile"
    ON public.profiles
    FOR SELECT
    TO authenticated
    USING (auth.uid() = id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
    AND tablename = 'profiles' 
    AND policyname = 'Users can update their own profile'
  ) THEN
    CREATE POLICY "Users can update their own profile"
    ON public.profiles
    FOR UPDATE
    TO authenticated
    USING (auth.uid() = id)
    WITH CHECK (auth.uid() = id);
  END IF;
END $$;

-- Fix password_request_codes table security
-- Add policy to prevent unauthorized access
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
    AND tablename = 'password_request_codes' 
    AND policyname = 'Only intended corretor can view their codes'
  ) THEN
    CREATE POLICY "Only intended corretor can view their codes"
    ON public.password_request_codes
    FOR SELECT
    TO authenticated
    USING (corretor_id = auth.uid());
  END IF;
END $$;

-- Fix user_roles table security
-- Add explicit deny for unauthenticated users
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
    AND tablename = 'user_roles' 
    AND policyname = 'Deny unauthenticated access to user_roles'
  ) THEN
    CREATE POLICY "Deny unauthenticated access to user_roles"
    ON public.user_roles
    FOR ALL
    TO anon
    USING (false);
  END IF;
END $$;