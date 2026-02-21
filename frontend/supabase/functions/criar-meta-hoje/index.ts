import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Security: Error sanitization to prevent information leakage
function sanitizeError(error: any): string {
  const msg = error?.message?.toLowerCase() || '';
  if (msg.includes('not found')) return 'Recurso não encontrado';
  if (msg.includes('permission') || msg.includes('policy')) return 'Permissão negada';
  if (msg.includes('autenticado')) return 'Sessão expirada';
  return 'Erro ao processar requisição';
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    // Obter usuário autenticado
    const authHeader = req.headers.get('Authorization');
    if (!authHeader) {
      return new Response(JSON.stringify({ success: false, error: 'Usuário não autenticado' }), {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 401,
      });
    }
    const token = authHeader.replace('Bearer ', '');
    const { data: { user }, error: userError } = await supabase.auth.getUser(token);

    if (userError || !user) {
      throw new Error('Usuário não autenticado');
    }

    // Data de hoje em São Paulo (America/Sao_Paulo)
    const now = new Date();
    const saoPauloFormatter = new Intl.DateTimeFormat('en-CA', { 
      timeZone: 'America/Sao_Paulo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
    const hoje = saoPauloFormatter.format(now); // YYYY-MM-DD
    
    const saoPauloDate = new Date(now.toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' }));
    const diaDaSemana = saoPauloDate.getDay();

    // Apenas segunda a sexta
    if (diaDaSemana === 0 || diaDaSemana === 6) {
      return new Response(
        JSON.stringify({ 
          success: false, 
          message: 'Metas diárias são criadas apenas de segunda a sexta-feira' 
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
      );
    }

    // Categorias permitidas para criação automática
    const categoriasPermitidas = ['captacao_imoveis', 'captacao_compradores', 'atualizacao_imoveis', 'visitas'];

    // Buscar configs ativas do usuário (tipo mensal)
    const { data: configs, error: configError } = await supabase
      .from('metas_config')
      .select('*')
      .eq('usuario_id', user.id)
      .eq('tipo', 'mensal')
      .eq('ativo', true)
      .in('categoria', categoriasPermitidas);

    if (configError) throw configError;

    // Calcular dias úteis do mês corrente (SP)
    const { data: diasUteisMesData, error: diasUteisError } = await supabase.rpc('dias_uteis_mes', {
      p_data_ref: hoje,
    });
    if (diasUteisError) throw diasUteisError;
    const diasUteisMes = Number(diasUteisMesData) || 22;

    let metasCriadas = 0;
    let metasJaExistiam = 0;

    for (const config of configs || []) {
      // Calcular meta diária usando a função de cálculo proporcional
      const { data: diariaPretendida, error: calcError } = await supabase.rpc('calcular_meta_proporcional', {
        p_meta_mensal: config.meta_pretendida || 0,
        p_tipo: 'diaria',
        p_data_ref: hoje
      });

      if (calcError) {
        console.error('Erro ao calcular meta proporcional:', calcError);
        throw calcError;
      }

      // Verificar se a meta diária de hoje já existe
      const { data: existente, error: existErr } = await supabase
        .from('metas')
        .select('id')
        .eq('usuario_id', user.id)
        .eq('tipo', 'diaria')
        .eq('categoria', config.categoria)
        .eq('data_prazo', hoje)
        .maybeSingle();

      if (existErr && existErr.code !== 'PGRST116') {
        throw existErr;
      }

      if (existente?.id) {
        metasJaExistiam++;
      } else {
        // Criar meta diária baseada na meta mensal dividida por dias úteis
        const { error: insertErr } = await supabase
          .from('metas')
          .insert({
            usuario_id: user.id,
            tipo: 'diaria',
            categoria: config.categoria,
            meta_pretendida: diariaPretendida,
            data_prazo: hoje,
            status: 'no_prazo',
            criada_manualmente: false,
          });
        if (insertErr) throw insertErr;
        metasCriadas++;

        // Garantir (apenas buscar/criar via trigger) metas agregadas existentes
        for (const tipo of ['semanal', 'mensal', 'anual'] as const) {
          await supabase.rpc('ensure_scaffold_meta', {
            p_usuario_id: user.id,
            p_tipo: tipo,
            p_categoria: config.categoria,
            p_data_ref: hoje,
          });
        }
      }
    }

    return new Response(
      JSON.stringify({ 
        success: true,
        metasCriadas,
        metasJaExistiam,
        message: `${metasCriadas} meta(s) criada(s), ${metasJaExistiam} já existiam`,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
    );
  } catch (error) {
    console.error('Erro ao criar metas de hoje:', error);
    return new Response(
      JSON.stringify({ 
        success: false, 
        error: sanitizeError(error)
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
    );
  }
});
