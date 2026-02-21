import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.58.0';
import { z } from 'https://esm.sh/zod@3.22.4';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// --- Input validation ---
const requestSchema = z.object({
  imovel_id: z.string().optional(),
  perfil_permuta_id: z.string().optional(),
}).refine(
  (data) => data.imovel_id || data.perfil_permuta_id,
  { message: 'Either imovel_id or perfil_permuta_id is required' }
);

// --- Scoring functions (ported from useMatching.ts) ---

interface Imovel {
  id: string;
  owner_id: string;
  tipo: string;
  preco_pedido: number;
  aceita_permutas: boolean;
  cidade?: string | null;
  estado?: string | null;
  bairro?: string | null;
  area_privativa?: number | null;
  area_total?: number | null;
  quartos?: number | null;
  vagas?: number | null;
  fotos?: string[] | null;
  titulo_anuncio?: string | null;
  descricao_seo?: string | null;
  palavras_chave?: string[] | null;
  pontos_de_interesse?: string[] | null;
  tour_virtual_url?: string | null;
}

interface PerfilPermuta {
  id: string;
  cliente_ofertante_id: string;
  categoria: string;
  tipo_imovel?: string | null;
  faixa_preco_min?: number | null;
  faixa_preco_max?: number | null;
  regiao_preferida?: string[] | null;
  metragem_min?: number | null;
  metragem_max?: number | null;
  quartos_min?: number | null;
  vagas_min?: number | null;
  aceita_completar_diferenca: boolean;
  limite_complemento?: number | null;
  valor_estimado?: number | null;
}

interface MatchResult {
  imovel_id: string;
  perfil_permuta_id: string;
  score: number;
  justificativa: string;
  detalhes: {
    compatibilidade_regiao: number;
    compatibilidade_preco: number;
    compatibilidade_specs: number;
    qualidade_anuncio: number;
    gap_valor: number;
  };
}

function calcularScoreRegiao(imovel: Imovel, perfil: PerfilPermuta): number {
  if (perfil.regiao_preferida && perfil.regiao_preferida.length > 0) {
    const regiaoMatch = perfil.regiao_preferida.some((regiao: string) => {
      const regLower = regiao.toLowerCase();
      return (
        imovel.cidade?.toLowerCase().includes(regLower) ||
        imovel.estado?.toLowerCase().includes(regLower) ||
        imovel.bairro?.toLowerCase().includes(regLower)
      );
    });
    return regiaoMatch ? 30 : 10;
  }
  return 20; // No region preference
}

function calcularScorePreco(imovel: Imovel, perfil: PerfilPermuta): number {
  if (!perfil.faixa_preco_min && !perfil.faixa_preco_max) return 20;

  const preco = imovel.preco_pedido;
  const min = perfil.faixa_preco_min || 0;
  const max = perfil.faixa_preco_max || Infinity;

  if (preco >= min && preco <= max) {
    const centro = (min + (max === Infinity ? min * 2 : max)) / 2;
    const amplitude = ((max === Infinity ? min * 2 : max) - min) / 2;
    if (amplitude === 0) return 25;
    const distanciaCentro = Math.abs(preco - centro);
    const scoreNormalizado = 1 - (distanciaCentro / amplitude);
    return Math.round(25 * scoreNormalizado);
  }

  // Outside range but with 10% tolerance
  const tolerancia = 0.1;
  if (preco < min && preco >= min * (1 - tolerancia)) return 15;
  if (preco > max && max !== Infinity && preco <= max * (1 + tolerancia)) return 15;

  return 0;
}

function calcularScoreEspecificacoes(imovel: Imovel, perfil: PerfilPermuta): number {
  let score = 0;

  // Property type
  if (perfil.tipo_imovel && perfil.tipo_imovel === imovel.tipo) {
    score += 5;
  }

  // Area
  if (perfil.metragem_min || perfil.metragem_max) {
    const area = imovel.area_total || imovel.area_privativa || 0;
    const min = perfil.metragem_min || 0;
    const max = perfil.metragem_max || Infinity;
    if (area >= min && area <= max) {
      score += 5;
    }
  }

  // Bedrooms
  if (perfil.quartos_min && imovel.quartos && imovel.quartos >= perfil.quartos_min) {
    score += 5;
  }

  // Parking spots
  if (perfil.vagas_min && imovel.vagas && imovel.vagas >= perfil.vagas_min) {
    score += 5;
  }

  return score;
}

function calcularQualidadeAnuncio(imovel: Imovel): number {
  let score = 0;

  // Photos
  if (imovel.fotos && imovel.fotos.length >= 8) {
    score += 3;
  } else if (imovel.fotos && imovel.fotos.length >= 4) {
    score += 2;
  } else if (imovel.fotos && imovel.fotos.length > 0) {
    score += 1;
  }

  // Title and description
  if (imovel.titulo_anuncio && imovel.titulo_anuncio.length > 20) score += 2;
  if (imovel.descricao_seo && imovel.descricao_seo.length > 50) score += 2;

  // Keywords
  if (imovel.palavras_chave && imovel.palavras_chave.length >= 3) score += 1;

  // Points of interest
  if (imovel.pontos_de_interesse && imovel.pontos_de_interesse.length > 0) score += 1;

  // Virtual tour
  if (imovel.tour_virtual_url) score += 1;

  return score;
}

function calcularMatch(imovel: Imovel, perfil: PerfilPermuta): MatchResult {
  if (perfil.categoria !== 'imovel') {
    return {
      score: 0,
      imovel_id: imovel.id,
      perfil_permuta_id: perfil.id,
      justificativa: 'Matching de móveis ainda não implementado',
      detalhes: {
        compatibilidade_regiao: 0,
        compatibilidade_preco: 0,
        compatibilidade_specs: 0,
        qualidade_anuncio: 0,
        gap_valor: 0,
      },
    };
  }

  const scoreRegiao = calcularScoreRegiao(imovel, perfil);
  const scorePreco = calcularScorePreco(imovel, perfil);
  const scoreSpecs = calcularScoreEspecificacoes(imovel, perfil);
  const scoreQualidade = calcularQualidadeAnuncio(imovel);

  const scoreTotal = scoreRegiao + scorePreco + scoreSpecs + scoreQualidade;

  const gapValor = imovel.preco_pedido - (perfil.valor_estimado || 0);
  const podeComplementar =
    perfil.aceita_completar_diferenca && gapValor <= (perfil.limite_complemento || 0);

  let justificativa = '';
  if (scoreTotal >= 80) {
    justificativa = 'Compatibilidade alta. ';
  } else if (scoreTotal >= 60) {
    justificativa = 'Compatibilidade boa. ';
  } else if (scoreTotal >= 40) {
    justificativa = 'Compatibilidade média. ';
  } else {
    justificativa = 'Compatibilidade baixa. ';
  }

  if (scoreRegiao >= 25) justificativa += 'Região compatível. ';
  if (scorePreco >= 20) justificativa += 'Preço dentro do esperado. ';
  if (gapValor > 0 && podeComplementar) {
    justificativa += `Diferença de R$ ${gapValor.toFixed(2)} coberta pelo complemento.`;
  }

  return {
    score: Math.min(scoreTotal, 100),
    imovel_id: imovel.id,
    perfil_permuta_id: perfil.id,
    justificativa: justificativa.trim(),
    detalhes: {
      compatibilidade_regiao: scoreRegiao,
      compatibilidade_preco: scorePreco,
      compatibilidade_specs: scoreSpecs,
      qualidade_anuncio: scoreQualidade,
      gap_valor: gapValor,
    },
  };
}

// --- Main handler ---
Deno.serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseClient = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_ANON_KEY') ?? '',
      {
        global: {
          headers: { Authorization: req.headers.get('Authorization')! },
        },
      }
    );

    // Verify authentication
    const {
      data: { user },
      error: authError,
    } = await supabaseClient.auth.getUser();

    if (authError || !user) {
      return new Response(
        JSON.stringify({ error: 'Não autenticado' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 401 }
      );
    }

    // Validate input
    const body = await req.json();
    const validation = requestSchema.safeParse(body);

    if (!validation.success) {
      return new Response(
        JSON.stringify({
          error: 'Dados inválidos',
          details: validation.error.errors.map((e) => e.message),
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
      );
    }

    const { imovel_id, perfil_permuta_id } = validation.data;
    let matchResults: MatchResult[] = [];

    if (imovel_id) {
      // Match one imóvel against all perfis de permuta
      console.log('Generating matches for imovel:', imovel_id);

      const { data: imovel, error: imovelError } = await supabaseClient
        .from('imoveis')
        .select('*')
        .eq('id', imovel_id)
        .single();

      if (imovelError || !imovel) {
        return new Response(
          JSON.stringify({ error: 'Imóvel não encontrado' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
        );
      }

      const { data: perfis, error: perfisError } = await supabaseClient
        .from('perfis_permutas')
        .select('*')
        .eq('categoria', 'imovel');

      if (perfisError) {
        console.error('Error fetching perfis:', perfisError);
        return new Response(
          JSON.stringify({ error: 'Erro ao buscar perfis de permuta' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
        );
      }

      if (perfis && perfis.length > 0) {
        matchResults = perfis
          .map((perfil) => calcularMatch(imovel as Imovel, perfil as PerfilPermuta))
          .filter((m) => m.score > 0);
      }

      // Delete existing matches for this imóvel before inserting new ones
      await supabaseClient
        .from('matches')
        .delete()
        .eq('imovel_id', imovel_id);
    }

    if (perfil_permuta_id) {
      // Match one perfil against all imóveis that accept permutas
      console.log('Generating matches for perfil:', perfil_permuta_id);

      const { data: perfil, error: perfilError } = await supabaseClient
        .from('perfis_permutas')
        .select('*')
        .eq('id', perfil_permuta_id)
        .single();

      if (perfilError || !perfil) {
        return new Response(
          JSON.stringify({ error: 'Perfil de permuta não encontrado' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
        );
      }

      const { data: imoveis, error: imoveisError } = await supabaseClient
        .from('imoveis')
        .select('*')
        .eq('aceita_permutas', true);

      if (imoveisError) {
        console.error('Error fetching imoveis:', imoveisError);
        return new Response(
          JSON.stringify({ error: 'Erro ao buscar imóveis' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
        );
      }

      if (imoveis && imoveis.length > 0) {
        matchResults = imoveis
          .map((imovel) => calcularMatch(imovel as Imovel, perfil as PerfilPermuta))
          .filter((m) => m.score > 0);
      }

      // Delete existing matches for this perfil before inserting new ones
      await supabaseClient
        .from('matches')
        .delete()
        .eq('perfil_permuta_id', perfil_permuta_id);
    }

    // Insert new matches into the database
    if (matchResults.length > 0) {
      const matchRows = matchResults.map((m) => ({
        imovel_id: m.imovel_id,
        perfil_permuta_id: m.perfil_permuta_id,
        score: m.score,
        status: 'pendente',
        justificativa: m.justificativa,
        detalhes: m.detalhes,
      }));

      const { error: insertError } = await supabaseClient
        .from('matches')
        .upsert(matchRows, {
          onConflict: 'imovel_id,perfil_permuta_id',
          ignoreDuplicates: false,
        });

      if (insertError) {
        console.error('Error inserting matches:', insertError);
        return new Response(
          JSON.stringify({ error: 'Erro ao salvar matches' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
        );
      }
    }

    // Log the action
    supabaseClient
      .from('user_actions_log')
      .insert({
        usuario_id: user.id,
        tipo_acao: 'criar',
        tipo_entidade: 'match',
        descricao: `Gerou ${matchResults.length} matches${imovel_id ? ` para imóvel ${imovel_id}` : ''}${perfil_permuta_id ? ` para perfil ${perfil_permuta_id}` : ''}`,
        detalhes: {
          imovel_id,
          perfil_permuta_id,
          total_matches: matchResults.length,
          scores: matchResults.map((m) => m.score),
        },
      })
      .then();

    console.log(`Generated ${matchResults.length} matches successfully`);

    return new Response(
      JSON.stringify({
        data: matchResults,
        total: matchResults.length,
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
    );
  } catch (error) {
    console.error('Error:', error);
    return new Response(
      JSON.stringify({ error: 'Erro ao processar requisição' }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
    );
  }
});
