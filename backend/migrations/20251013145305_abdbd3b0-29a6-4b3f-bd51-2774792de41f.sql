-- Add explicit deny policy for anonymous users on profiles table
CREATE POLICY "Deny unauthenticated access to profiles"
ON public.profiles
FOR ALL
TO anon
USING (false);