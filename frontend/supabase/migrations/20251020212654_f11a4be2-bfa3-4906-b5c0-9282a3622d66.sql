-- Add policy to allow admins to insert metas for any user
CREATE POLICY "Admins can insert metas for any user"
ON public.metas
FOR INSERT
TO authenticated
WITH CHECK (has_role(auth.uid(), 'admin'));