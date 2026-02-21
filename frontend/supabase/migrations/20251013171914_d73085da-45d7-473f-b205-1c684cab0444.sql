-- Add missing DELETE policy for admins on metas
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies 
    WHERE schemaname = 'public' 
      AND tablename = 'metas' 
      AND policyname = 'Admins can delete all metas'
  ) THEN
    CREATE POLICY "Admins can delete all metas"
    ON public.metas
    FOR DELETE
    USING (public.has_role(auth.uid(), 'admin'));
  END IF;
END $$;