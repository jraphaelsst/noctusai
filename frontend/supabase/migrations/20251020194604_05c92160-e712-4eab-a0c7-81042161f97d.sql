-- Adicionar 'vence_amanha' ao enum status_meta
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_enum WHERE enumlabel = 'vence_amanha' AND enumtypid = 'status_meta'::regtype) THEN
        ALTER TYPE status_meta ADD VALUE 'vence_amanha';
    END IF;
END $$;