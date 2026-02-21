import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.58.0';
import { z } from 'https://esm.sh/zod@3.22.4';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// Security: Error sanitization to prevent information leakage
function sanitizeError(error: any): string {
  const msg = error?.message?.toLowerCase() || '';
  if (msg.includes('not found')) return 'Recurso não encontrado';
  if (msg.includes('permission') || msg.includes('policy')) return 'Permissão negada';
  if (msg.includes('duplicate')) return 'Registro duplicado';
  return 'Erro ao processar requisição';
}

// Input validation schema
const moverClienteSchema = z.object({
  cliente_id: z.string().uuid({ message: 'ID de cliente inválido' }),
  para_etapa: z.enum(['qualificacao', 'visitas', 'proposta', 'negociacao', 'fechado'], {
    errorMap: () => ({ message: 'Etapa inválida' })
  }),
  motivo: z.string().max(500, { message: 'Motivo deve ter no máximo 500 caracteres' }).optional(),
  novo_indice: z.number().int().min(0, { message: 'Índice deve ser não-negativo' }).optional()
});

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

    // Verificar autenticação
    const {
      data: { user },
      error: authError,
    } = await supabaseClient.auth.getUser();

    if (authError || !user) {
      console.error('Erro de autenticação:', authError);
      return new Response(
        JSON.stringify({ error: 'Não autenticado' }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 401 }
      );
    }

    // Validate input
    const body = await req.json();
    const validationResult = moverClienteSchema.safeParse(body);
    
    if (!validationResult.success) {
      console.error('Erro de validação:', validationResult.error);
      return new Response(
        JSON.stringify({ 
          error: 'Dados inválidos',
          details: validationResult.error.errors.map(e => e.message)
        }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 400 }
      );
    }

    const { cliente_id, para_etapa, motivo, novo_indice } = validationResult.data;

    console.log('Movendo cliente:', { cliente_id, para_etapa, novo_indice });

    // Buscar cliente atual com nome
    const { data: cliente, error: clienteError } = await supabaseClient
      .from('clientes')
      .select('*, nome')
      .eq('id', cliente_id)
      .single();

    if (clienteError || !cliente) {
      console.error('Cliente não encontrado:', clienteError);
      return new Response(
        JSON.stringify({ error: sanitizeError(clienteError || new Error('not found')) }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
      );
    }

    const de_etapa = cliente.etapa_atual;

    // Se mudou de etapa, reordenar
    let novo_pos = cliente.kanban_pos;
    
    if (de_etapa !== para_etapa || novo_indice !== undefined) {
      // Buscar todos os clientes na etapa de destino
      const { data: clientesDestino, error: destinoError } = await supabaseClient
        .from('clientes')
        .select('id, kanban_pos')
        .eq('etapa_atual', para_etapa)
        .order('kanban_pos', { ascending: true });

      if (destinoError) {
        console.error('Erro ao buscar clientes da etapa destino:', destinoError);
        return new Response(
          JSON.stringify({ error: 'Erro ao reordenar' }),
          { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
        );
      }

      // Calcular nova posição
      const indice = novo_indice !== undefined ? novo_indice : 0;
      
      if (indice === 0) {
        // Inserir no início
        novo_pos = clientesDestino.length > 0 ? clientesDestino[0].kanban_pos - 10 : 0;
      } else if (indice >= clientesDestino.length) {
        // Inserir no final
        novo_pos = clientesDestino.length > 0 
          ? clientesDestino[clientesDestino.length - 1].kanban_pos + 10 
          : 0;
      } else {
        // Inserir entre dois cards
        const anterior = clientesDestino[indice - 1];
        const proximo = clientesDestino[indice];
        novo_pos = Math.floor((anterior.kanban_pos + proximo.kanban_pos) / 2);
      }
    }

    // Atualizar cliente
    const { data: clienteAtualizado, error: updateError } = await supabaseClient
      .from('clientes')
      .update({
        etapa_atual: para_etapa,
        kanban_pos: novo_pos,
      })
      .eq('id', cliente_id)
      .select()
      .single();

    if (updateError) {
      console.error('Erro ao atualizar cliente:', updateError);
      return new Response(
        JSON.stringify({ error: sanitizeError(updateError) }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
      );
    }

    // Registrar movimento
    const { error: movimentoError } = await supabaseClient
      .from('funil_movimentos')
      .insert({
        cliente_id,
        de_etapa,
        para_etapa,
        responsavel_id: user.id,
        motivo: motivo || null,
      });

    if (movimentoError) {
      console.error('Erro ao registrar movimento:', movimentoError);
    }

    // Registrar ação no log (não bloqueia se falhar)
    const { error: logError } = await supabaseClient.from("user_actions_log").insert({
      usuario_id: user.id,
      tipo_acao: 'mover',
      tipo_entidade: 'cliente',
      entidade_id: cliente_id,
      descricao: `Moveu cliente ${cliente.nome} de ${de_etapa} para ${para_etapa}`,
      detalhes: { de_etapa, para_etapa, motivo }
    });

    if (logError) {
      console.error('Erro ao registrar ação:', logError);
    }

    console.log('Cliente movido com sucesso:', clienteAtualizado);

    return new Response(
      JSON.stringify({ data: clienteAtualizado }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
    );
  } catch (error) {
    console.error('Erro geral:', error);
    return new Response(
      JSON.stringify({ 
        error: sanitizeError(error) 
      }),
      { 
        headers: { ...corsHeaders, 'Content-Type': 'application/json' }, 
        status: 500 
      }
    );
  }
});
