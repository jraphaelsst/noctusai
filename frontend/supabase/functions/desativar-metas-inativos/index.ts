import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Security: Error sanitization to prevent information leakage
function sanitizeError(error: any): string {
  const msg = error?.message?.toLowerCase() || '';
  if (msg.includes('permission') || msg.includes('policy')) return 'Permissão negada';
  return 'Erro ao processar requisição';
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    console.log('Executando verificação de usuários inativos...');

    // Executar função que desativa metas de usuários inativos (20+ dias)
    const { data, error } = await supabase.rpc('desativar_metas_usuarios_inativos');

    if (error) {
      console.error('Erro ao desativar metas de usuários inativos:', error);
      throw error;
    }

    console.log('Resultado da verificação:', data);

    return new Response(
      JSON.stringify({
        success: true,
        ...data,
      }),
      {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200,
      }
    );
  } catch (error) {
    console.error('Erro na função desativar-metas-inativos:', error);
    return new Response(
      JSON.stringify({ 
        success: false, 
        error: sanitizeError(error)
      }),
      {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 500,
      }
    );
  }
});
