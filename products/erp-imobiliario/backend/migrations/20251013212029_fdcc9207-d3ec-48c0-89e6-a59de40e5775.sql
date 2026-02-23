-- Remove a política restritiva de inserção e cria uma nova que permite todos os tipos
DROP POLICY IF EXISTS "Users can insert their own metas" ON metas;

-- Nova política que permite criar qualquer tipo de meta
CREATE POLICY "Users can insert their own metas"
ON metas FOR INSERT
TO authenticated
WITH CHECK (
  usuario_id = auth.uid() 
  AND usuario_id IS NOT NULL
);