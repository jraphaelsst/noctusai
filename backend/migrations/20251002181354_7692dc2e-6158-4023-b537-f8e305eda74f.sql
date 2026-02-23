-- Add explicit denial policy for unauthenticated access to profiles
CREATE POLICY "Deny public access to profiles"
ON public.profiles
FOR ALL
TO public
USING (auth.uid() IS NOT NULL);

-- Allow admins to update any profile
CREATE POLICY "Admins can update all profiles"
ON public.profiles
FOR UPDATE
TO authenticated
USING (public.has_role(auth.uid(), 'admin'::app_role));