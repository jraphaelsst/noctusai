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
const registrarAtividadeSchema = z.object({
  cliente_id: z.string().uuid({ message: 'ID de cliente inválido' }),
  tipo: z.enum(['ligacao', 'email', 'reuniao', 'whatsapp', 'visita', 'proposta', 'negociacao', 'outro'], {
    errorMap: () => ({ message: 'Tipo de atividade inválido' })
  }),
  descricao: z.string()
    .min(1, { message: 'Descrição não pode estar vazia' })
    .max(2000, { message: 'Descrição deve ter no máximo 2000 caracteres' }),
  data_execucao: z.string().datetime({ message: 'Data de execução inválida' }).optional()
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
    const validationResult = registrarAtividadeSchema.safeParse(body);
    
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

    const { cliente_id, tipo, descricao, data_execucao } = validationResult.data;

    console.log('Registrando atividade:', { cliente_id, tipo, descricao });

    // Verificar se o cliente existe e o usuário tem acesso
    const { data: cliente, error: clienteError } = await supabaseClient
      .from('clientes')
      .select('id')
      .eq('id', cliente_id)
      .single();

    if (clienteError || !cliente) {
      console.error('Cliente não encontrado:', clienteError);
      return new Response(
        JSON.stringify({ error: sanitizeError(clienteError || new Error('not found')) }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 404 }
      );
    }

    // Criar atividade
    const { data: atividade, error: atividadeError } = await supabaseClient
      .from('atividades')
      .insert({
        cliente_id,
        usuario_id: user.id,
        tipo,
        descricao,
        data_execucao: data_execucao || new Date().toISOString(),
      })
      .select()
      .single();

    if (atividadeError) {
      console.error('Erro ao criar atividade:', atividadeError);
      return new Response(
        JSON.stringify({ error: sanitizeError(atividadeError) }),
        { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
      );
    }

    // Buscar lista atualizada de atividades
    const { data: atividades, error: listaError } = await supabaseClient
      .from('atividades')
      .select(`
        *,
        usuario:profiles!atividades_usuario_id_fkey(nome, email)
      `)
      .eq('cliente_id', cliente_id)
      .order('data_execucao', { ascending: false });

    if (listaError) {
      console.error('Erro ao buscar atividades:', listaError);
    }

    console.log('Atividade registrada com sucesso:', atividade);

    return new Response(
      JSON.stringify({ 
        data: atividade,
        atividades: atividades || []
      }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 200 }
    );
  } catch (error) {
    console.error('Erro no servidor:', error);
    return new Response(
      JSON.stringify({ error: sanitizeError(error) }),
      { headers: { ...corsHeaders, 'Content-Type': 'application/json' }, status: 500 }
    );
  }
});
