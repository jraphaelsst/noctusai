-- Create enum for meta types
CREATE TYPE public.tipo_meta AS ENUM ('diaria', 'semanal', 'mensal', 'anual');

-- Create enum for meta status
CREATE TYPE public.status_meta AS ENUM ('em_andamento', 'concluida', 'atrasada', 'no_prazo');

-- Function to generate next corretor ID
CREATE OR REPLACE FUNCTION public.generate_corretor_id()
RETURNS TEXT AS $$
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
$$ LANGUAGE plpgsql;

-- Function to generate next meta ID
CREATE OR REPLACE FUNCTION public.generate_meta_id()
RETURNS TEXT AS $$
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
$$ LANGUAGE plpgsql;

-- Create corretores table
CREATE TABLE public.corretores (
    id TEXT PRIMARY KEY DEFAULT public.generate_corretor_id(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefone TEXT NOT NULL,
    avatar TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
);

-- Create metas table
CREATE TABLE public.metas (
    id TEXT PRIMARY KEY DEFAULT public.generate_meta_id(),
    corretor_id TEXT REFERENCES public.corretores(id) ON DELETE CASCADE NOT NULL,
    tipo public.tipo_meta NOT NULL,
    meta_pretendida INTEGER NOT NULL,
    meta_realizada INTEGER DEFAULT 0,
    data_prazo DATE NOT NULL,
    status public.status_meta DEFAULT 'em_andamento' NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    finalizada_em TIMESTAMP WITH TIME ZONE,
    finalizada_no_prazo BOOLEAN
);

-- Enable RLS
ALTER TABLE public.corretores ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.metas ENABLE ROW LEVEL SECURITY;

-- RLS Policies for corretores
CREATE POLICY "Users can view their own corretor data" 
ON public.corretores 
FOR SELECT 
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own corretor data" 
ON public.corretores 
FOR INSERT 
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own corretor data" 
ON public.corretores 
FOR UPDATE 
USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own corretor data" 
ON public.corretores 
FOR DELETE 
USING (auth.uid() = user_id);

-- RLS Policies for metas
CREATE POLICY "Users can view their own metas" 
ON public.metas 
FOR SELECT 
USING (EXISTS (
    SELECT 1 FROM public.corretores 
    WHERE corretores.id = metas.corretor_id 
    AND corretores.user_id = auth.uid()
));

CREATE POLICY "Users can insert metas for their corretores" 
ON public.metas 
FOR INSERT 
WITH CHECK (EXISTS (
    SELECT 1 FROM public.corretores 
    WHERE corretores.id = metas.corretor_id 
    AND corretores.user_id = auth.uid()
));

CREATE POLICY "Users can update their own metas" 
ON public.metas 
FOR UPDATE 
USING (EXISTS (
    SELECT 1 FROM public.corretores 
    WHERE corretores.id = metas.corretor_id 
    AND corretores.user_id = auth.uid()
));

CREATE POLICY "Users can delete their own metas" 
ON public.metas 
FOR DELETE 
USING (EXISTS (
    SELECT 1 FROM public.corretores 
    WHERE corretores.id = metas.corretor_id 
    AND corretores.user_id = auth.uid()
));

-- Function to update timestamps
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_corretores_updated_at
    BEFORE UPDATE ON public.corretores
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();

CREATE TRIGGER update_metas_updated_at
    BEFORE UPDATE ON public.metas
    FOR EACH ROW
    EXECUTE FUNCTION public.update_updated_at_column();