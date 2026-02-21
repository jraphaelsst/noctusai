import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { Resend } from "https://esm.sh/resend@4.0.0";
import * as bcrypt from "https://deno.land/x/bcrypt@v0.4.1/mod.ts";

const resend = new Resend(Deno.env.get("RESEND_API_KEY"));

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

// Security: Error sanitization to prevent information leakage
function sanitizeError(error: any): string {
  const msg = error?.message?.toLowerCase() || '';
  if (msg.includes('not found')) return 'Recurso não encontrado';
  if (msg.includes('permission') || msg.includes('policy')) return 'Permissão negada';
  if (msg.includes('duplicate')) return 'Registro duplicado';
  if (msg.includes('network') || msg.includes('fetch')) return 'Erro de conexão';
  if (msg.includes('password') && msg.includes('weak')) return 'Senha muito fraca';
  if (msg.includes('expirado')) return 'Código expirado';
  if (msg.includes('inválido')) return 'Código inválido';
  return 'Erro ao processar requisição';
}

interface RequestPasswordRequest {
  corretorId: string;
  corretorEmail: string;
  corretorNome: string;
  confirmationMethod: "email" | "sms";
  confirmationCode?: string;
  step: "request" | "confirm";
}

const handler = async (req: Request): Promise<Response> => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const supabaseClient = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_ANON_KEY") ?? "",
      {
        global: {
          headers: { Authorization: req.headers.get("Authorization")! },
        },
      }
    );

    // Verificar se é admin
    const {
      data: { user },
    } = await supabaseClient.auth.getUser();

    if (!user) {
      throw new Error("Não autenticado");
    }

    const { data: roleData } = await supabaseClient
      .from("user_roles")
      .select("role")
      .eq("user_id", user.id)
      .maybeSingle();

    if (roleData?.role !== "admin") {
      throw new Error("Acesso negado. Apenas administradores podem requisitar senhas.");
    }

    const {
      corretorId,
      corretorEmail,
      corretorNome,
      confirmationMethod,
      confirmationCode,
      step,
    }: RequestPasswordRequest = await req.json();

    if (step === "request") {
      // Gerar código de confirmação de 6 dígitos
      const code = Math.floor(100000 + Math.random() * 900000).toString();
      
      // Gerar senha temporária
      const tempPassword = Math.random().toString(36).slice(-10) + Math.random().toString(36).slice(-10).toUpperCase();
      
      // Hash da senha temporária para armazenamento seguro
      const hashedPassword = await bcrypt.hash(tempPassword);
      
      // Limpar códigos antigos deste admin/corretor
      await supabaseClient
        .from('password_request_codes')
        .delete()
        .eq('admin_user_id', user.id)
        .eq('corretor_id', corretorId);
      
      // Armazenar código no banco com expiração de 5 minutos
      const expiresAt = new Date(Date.now() + 5 * 60 * 1000);
      const { error: insertError } = await supabaseClient
        .from('password_request_codes')
        .insert({
          admin_user_id: user.id,
          corretor_id: corretorId,
          code: code,
          temp_password: hashedPassword,
          expires_at: expiresAt.toISOString(),
        });
      
      if (insertError) {
        throw insertError;
      }

      // Enviar código de confirmação
      const adminProfile = await supabaseClient
        .from("profiles")
        .select("email, telefone")
        .eq("id", user.id)
        .single();

      if (confirmationMethod === "email") {
        await resend.emails.send({
          from: "Sistema de Metas <onboarding@resend.dev>",
          to: [adminProfile.data?.email || user.email!],
          subject: "Código de Confirmação - Requisição de Senha",
          html: `
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
              <h2>Código de Confirmação</h2>
              <p>Você solicitou a senha do corretor <strong>${corretorNome}</strong>.</p>
              <p>Para confirmar esta ação, use o código abaixo:</p>
              <div style="background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 5px; margin: 20px 0;">
                ${code}
              </div>
              <p style="color: #666; font-size: 14px;">Este código expira em 5 minutos.</p>
              <p style="color: #666; font-size: 14px;">Se você não solicitou esta ação, ignore este email.</p>
            </div>
          `,
        });
      } else {
        // Para SMS, você precisaria integrar com um serviço como Twilio
        console.log(`SMS Code for ${adminProfile.data?.telefone}: ${code}`);
        // TODO: Implementar envio de SMS
      }

      return new Response(
        JSON.stringify({
          success: true,
          message: `Código de confirmação enviado por ${confirmationMethod}`,
        }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    } else if (step === "confirm") {
      // Buscar código de confirmação no banco
      const { data: storedCode, error: fetchError } = await supabaseClient
        .from('password_request_codes')
        .select('*')
        .eq('admin_user_id', user.id)
        .eq('corretor_id', corretorId)
        .single();

      if (fetchError || !storedCode) {
        throw new Error("Código não encontrado ou expirado");
      }

      // Verificar expiração
      const expiresAt = new Date(storedCode.expires_at);
      if (Date.now() > expiresAt.getTime()) {
        // Limpar código expirado
        await supabaseClient
          .from('password_request_codes')
          .delete()
          .eq('id', storedCode.id);
        throw new Error("Código expirado");
      }

      // Verificar se o código está correto
      if (storedCode.code !== confirmationCode) {
        throw new Error("Código inválido");
      }

      // Código correto - gerar nova senha e atualizar no auth
      // Nota: não podemos recuperar a senha hasheada, então geramos uma nova
      const newTempPassword = Math.random().toString(36).slice(-10) + Math.random().toString(36).slice(-10).toUpperCase();
      
      const supabaseAdmin = createClient(
        Deno.env.get("SUPABASE_URL") ?? "",
        Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
      );

      const { error: updateError } = await supabaseAdmin.auth.admin.updateUserById(
        corretorId,
        { password: newTempPassword }
      );

      if (updateError) {
        throw updateError;
      }

      // Enviar senha para o admin
      const adminProfile = await supabaseClient
        .from("profiles")
        .select("email")
        .eq("id", user.id)
        .single();

      await resend.emails.send({
        from: "Sistema de Metas <onboarding@resend.dev>",
        to: [adminProfile.data?.email || user.email!],
        subject: `Senha Temporária - ${corretorNome}`,
        html: `
          <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Senha Temporária Gerada</h2>
            <p>A senha temporária para <strong>${corretorNome}</strong> (${corretorEmail}) foi gerada com sucesso:</p>
            <div style="background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 24px; font-weight: bold; margin: 20px 0; word-break: break-all;">
              ${newTempPassword}
            </div>
            <p style="color: #d9534f; font-weight: bold;">⚠️ IMPORTANTE:</p>
            <ul style="color: #666;">
              <li>Esta senha é temporária e deve ser alterada pelo corretor no primeiro acesso</li>
              <li>Guarde esta senha em local seguro</li>
              <li>Não compartilhe esta informação por canais inseguros</li>
            </ul>
          </div>
        `,
      });

      // Limpar código usado do banco
      await supabaseClient
        .from('password_request_codes')
        .delete()
        .eq('id', storedCode.id);

      return new Response(
        JSON.stringify({
          success: true,
          message: "Senha gerada e enviada por email com sucesso",
        }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    throw new Error("Step inválido");
  } catch (error: any) {
    console.error("Erro em requisitar-senha:", error);
    return new Response(
      JSON.stringify({
        error: sanitizeError(error),
      }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }
};

serve(handler);
