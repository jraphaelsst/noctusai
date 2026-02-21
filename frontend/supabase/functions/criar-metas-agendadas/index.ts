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
  return 'Erro ao processar requisição';
}

interface MetaConfig {
  id: string;
  usuario_id: string;
  tipo: 'diaria' | 'semanal' | 'mensal' | 'anual';
  categoria: 'captacao' | 'visitas' | 'contatos' | 'propostas' | 'fechamento';
  meta_pretendida: number;
  ativo: boolean;
}

Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseServiceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseServiceKey);

    // Obter data atual em São Paulo (America/Sao_Paulo)
    const now = new Date();
    const saoPauloFormatter = new Intl.DateTimeFormat('en-CA', { 
      timeZone: 'America/Sao_Paulo',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit'
    });
    const hoje = saoPauloFormatter.format(now); // YYYY-MM-DD
    
    const saoPauloDate = new Date(now.toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' }));
    const diaDaSemana = saoPauloDate.getDay(); // 0 = domingo, 1 = segunda, etc
    const diaDoMes = saoPauloDate.getDate();
    const mesDoAno = saoPauloDate.getMonth() + 1;

    console.log('Executando agendamento de metas:', {
      hoje,
      diaDaSemana,
      diaDoMes,
      mesDoAno
    });

    let metasEncontradas = 0;
    let rollupsExecutados = 0;

    // Categorias permitidas para processamento automático de metas diárias
    const categoriasPermitidas = ['captacao_imoveis', 'captacao_compradores', 'atualizacao_imoveis', 'visitas'];

    // Buscar todos os usuários com configurações ativas (tipo mensal)
    const { data: configs, error: configError } = await supabase
      .from('metas_config')
      .select('*')
      .eq('tipo', 'mensal') // Configs mensais são a base
      .eq('ativo', true);

    if (configError) {
      console.error('Erro ao buscar configs:', configError);
      throw configError;
    }

    console.log(`Encontradas ${configs?.length || 0} configurações ativas`);

    for (const config of configs || []) {
      // Seg-Sex: buscar meta diária existente (apenas categorias permitidas)
      // IMPORTANTE: ensure_scaffold_meta agora APENAS busca, não cria nova
      if (diaDaSemana >= 1 && diaDaSemana <= 5 && categoriasPermitidas.includes(config.categoria)) {
        const { data: metaId, error: scaffoldError } = await supabase.rpc('ensure_scaffold_meta', {
          p_usuario_id: config.usuario_id,
          p_tipo: 'diaria',
          p_categoria: config.categoria,
          p_data_ref: hoje
        });

        if (!scaffoldError && metaId) {
          metasEncontradas++;
          console.log(`Meta diária encontrada: ${config.categoria} para usuário ${config.usuario_id}`);
        }
      }

      // Domingo: buscar/processar meta semanal
      if (diaDaSemana === 0) {
        const { data: metaId, error: scaffoldError } = await supabase.rpc('ensure_scaffold_meta', {
          p_usuario_id: config.usuario_id,
          p_tipo: 'semanal',
          p_categoria: config.categoria,
          p_data_ref: hoje
        });

        if (!scaffoldError && metaId) {
          metasEncontradas++;
          console.log(`Meta semanal encontrada: ${config.categoria}`);
        }
      }

      // Dia 1: buscar/processar meta mensal
      if (diaDoMes === 1) {
        const { data: metaId, error: scaffoldError } = await supabase.rpc('ensure_scaffold_meta', {
          p_usuario_id: config.usuario_id,
          p_tipo: 'mensal',
          p_categoria: config.categoria,
          p_data_ref: hoje
        });

        if (!scaffoldError && metaId) {
          metasEncontradas++;
          console.log(`Meta mensal encontrada: ${config.categoria}`);
        }
      }

      // 1 de janeiro: buscar/processar meta anual
      if (diaDoMes === 1 && mesDoAno === 1) {
        const { data: metaId, error: scaffoldError } = await supabase.rpc('ensure_scaffold_meta', {
          p_usuario_id: config.usuario_id,
          p_tipo: 'anual',
          p_categoria: config.categoria,
          p_data_ref: hoje
        });

        if (!scaffoldError && metaId) {
          metasEncontradas++;
          console.log(`Meta anual encontrada: ${config.categoria}`);
        }
      }
    }

    console.log(`Total de metas encontradas: ${metasEncontradas}, rollups executados: ${rollupsExecutados}`);

    return new Response(
      JSON.stringify({
        success: true,
        metasEncontradas,
        rollupsExecutados,
        timestamp: now.toISOString()
      }),
      {
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
        status: 200,
      }
    );
  } catch (error) {
    console.error('Erro na função criar-metas-agendadas:', error);
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
