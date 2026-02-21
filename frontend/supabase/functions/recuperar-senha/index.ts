import { serve } from "https://deno.land/std@0.168.0/http/server.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";
import { Resend } from "https://esm.sh/resend@4.0.0";

const resend = new Resend(Deno.env.get("RESEND_API_KEY"));

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
};

interface RecuperarSenhaRequest {
  email: string;
}

// Security: Error sanitization to prevent information leakage
function sanitizeError(error: any): string {
  const msg = error?.message?.toLowerCase() || '';
  if (msg.includes('not found')) return 'Recurso não encontrado';
  if (msg.includes('permission') || msg.includes('policy')) return 'Permissão negada';
  if (msg.includes('duplicate')) return 'Registro duplicado';
  if (msg.includes('network') || msg.includes('fetch')) return 'Erro de conexão';
  return 'Erro ao processar requisição';
}

const handler = async (req: Request): Promise<Response> => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    const { email }: RecuperarSenhaRequest = await req.json();

    if (!email || !email.trim()) {
      throw new Error("Email é obrigatório");
    }

    const supabaseAdmin = createClient(
      Deno.env.get("SUPABASE_URL") ?? "",
      Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? ""
    );

    // Verificar se o usuário existe
    const { data: users, error: fetchError } = await supabaseAdmin.auth.admin.listUsers();
    
    if (fetchError) {
      throw fetchError;
    }

    const user = users.users.find(u => u.email === email.trim());

    if (!user) {
      // Não revelar se o usuário existe ou não por segurança
      return new Response(
        JSON.stringify({
          success: true,
          message: "Se o email estiver cadastrado, você receberá instruções em breve.",
        }),
        {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    // Gerar senha temporária
    const tempPassword = Math.random().toString(36).slice(-10) + Math.random().toString(36).slice(-10).toUpperCase();

    // Atualizar senha do usuário
    const { error: updateError } = await supabaseAdmin.auth.admin.updateUserById(
      user.id,
      { password: tempPassword }
    );

    if (updateError) {
      throw updateError;
    }

    // Get admin email from environment
    const adminEmail = Deno.env.get("ADMIN_EMAIL");
    if (!adminEmail) {
      throw new Error("ADMIN_EMAIL não configurado");
    }

    // Enviar email para o administrador com a nova senha
    await resend.emails.send({
      from: "Sistema de Metas <onboarding@resend.dev>",
      to: [adminEmail],
      subject: `Recuperação de Senha - ${user.email}`,
      html: `
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
          <h2>Solicitação de Recuperação de Senha</h2>
          <p>O usuário <strong>${user.email}</strong> solicitou a recuperação de senha.</p>
          <p>Uma nova senha temporária foi gerada:</p>
          <div style="background-color: #f4f4f4; padding: 20px; text-align: center; font-size: 24px; font-weight: bold; margin: 20px 0; word-break: break-all;">
            ${tempPassword}
          </div>
          <p style="color: #d9534f; font-weight: bold;">⚠️ IMPORTANTE:</p>
          <ul style="color: #666;">
            <li>Esta senha é temporária</li>
            <li>O usuário deve ser orientado a alterá-la no primeiro acesso</li>
            <li>Entre em contato com o usuário para fornecer a nova senha</li>
          </ul>
        </div>
      `,
    });

    // Enviar email para o usuário informando que deve entrar em contato com o suporte
    if (user.email) {
      await resend.emails.send({
        from: "Sistema de Metas <onboarding@resend.dev>",
        to: [user.email],
        subject: "Recuperação de Senha",
        html: `
          <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Recuperação de Senha</h2>
            <p>Olá,</p>
            <p>Recebemos sua solicitação de recuperação de senha.</p>
            <p>Uma nova senha temporária foi gerada e enviada para o administrador do sistema.</p>
            <p style="color: #2563eb; font-weight: bold;">Por favor, entre em contato com o suporte pelo email:</p>
            <div style="background-color: #f4f4f4; padding: 15px; text-align: center; margin: 20px 0;">
              <a href="mailto:${adminEmail}" style="color: #2563eb; font-size: 18px; text-decoration: none;">
                ${adminEmail}
              </a>
            </div>
            <p style="color: #666;">
              O administrador irá fornecer sua nova senha temporária. Após o login, recomendamos que você altere a senha para uma de sua preferência.
            </p>
          </div>
        `,
      });
    }

    return new Response(
      JSON.stringify({
        success: true,
        message: "Se o email estiver cadastrado, você receberá instruções em breve.",
      }),
      {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (error: any) {
    console.error("Erro em recuperar-senha:", error);
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
