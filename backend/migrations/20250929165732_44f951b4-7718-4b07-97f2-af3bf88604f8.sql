-- Fix security issues by setting search_path for functions

-- Update generate_corretor_id function with security definer
CREATE OR REPLACE FUNCTION public.generate_corretor_id()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    last_id TEXT;
    last_number INTEGER;
    next_number INTEGER;
    next_id TEXT;
BEGIN
    -- Get the last corretor ID
    SELECT id INTO last_id 
    FROM public.corretores 
    WHERE id ~ '^CT[0-9]+$'
    ORDER BY 
        CASE 
            WHEN LENGTH(SUBSTRING(id FROM 3)) = 4 THEN CAST(SUBSTRING(id FROM 3) AS INTEGER)
            ELSE CAST(SUBSTRING(id FROM 3) AS INTEGER) + 100000
        END DESC
    LIMIT 1;
    
    -- If no corretor exists, start with CT0001
    IF last_id IS NULL THEN
        RETURN 'CT0001';
    END IF;
    
    -- Extract number from last ID
    last_number := CAST(SUBSTRING(last_id FROM 3) AS INTEGER);
    next_number := last_number + 1;
    
    -- Format next ID
    IF next_number <= 9999 THEN
        next_id := 'CT' || LPAD(next_number::TEXT, 4, '0');
    ELSE
        next_id := 'CT' || next_number::TEXT;
    END IF;
    
    RETURN next_id;
END;
$$;

-- Update generate_meta_id function with security definer
CREATE OR REPLACE FUNCTION public.generate_meta_id()
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    last_id TEXT;
    last_number INTEGER;
    next_number INTEGER;
    next_id TEXT;
BEGIN
    -- Get the last meta ID
    SELECT id INTO last_id 
    FROM public.metas 
    WHERE id ~ '^MT[0-9]+$'
    ORDER BY 
        CASE 
            WHEN LENGTH(SUBSTRING(id FROM 3)) = 4 THEN CAST(SUBSTRING(id FROM 3) AS INTEGER)
            ELSE CAST(SUBSTRING(id FROM 3) AS INTEGER) + 100000
        END DESC
    LIMIT 1;
    
    -- If no meta exists, start with MT0001
    IF last_id IS NULL THEN
        RETURN 'MT0001';
    END IF;
    
    -- Extract number from last ID
    last_number := CAST(SUBSTRING(last_id FROM 3) AS INTEGER);
    next_number := last_number + 1;
    
    -- Format next ID
    IF next_number <= 9999 THEN
        next_id := 'MT' || LPAD(next_number::TEXT, 4, '0');
    ELSE
        next_id := 'MT' || next_number::TEXT;
    END IF;
    
    RETURN next_id;
END;
$$;

-- Update update_updated_at_column function with security definer
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;