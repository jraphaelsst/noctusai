-- Create table to store temporary password request confirmation codes
CREATE TABLE IF NOT EXISTS public.password_request_codes (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  admin_user_id UUID NOT NULL,
  corretor_id UUID NOT NULL,
  code TEXT NOT NULL,
  temp_password TEXT NOT NULL,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable Row Level Security
ALTER TABLE public.password_request_codes ENABLE ROW LEVEL SECURITY;

-- Create policy: Only admins can access their own codes
CREATE POLICY "Admins can manage their own password request codes"
ON public.password_request_codes
FOR ALL
USING (auth.uid() = admin_user_id);

-- Create index for faster lookups
CREATE INDEX idx_password_request_codes_admin_corretor 
ON public.password_request_codes(admin_user_id, corretor_id);

-- Create function to automatically delete expired codes
CREATE OR REPLACE FUNCTION public.delete_expired_password_codes()
RETURNS void AS $$
BEGIN
  DELETE FROM public.password_request_codes
  WHERE expires_at < now();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Optional: Create a trigger or scheduled job to clean up expired codes periodically