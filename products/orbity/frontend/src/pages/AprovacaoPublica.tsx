/**
 * AprovacaoPublica — public, unauthenticated content approval page.
 *
 * Route: /aprovar/:token  (publicRoutes seam — no auth required)
 *
 * GET  /api/content/approve/{token} → shows the post to approve
 * POST /api/content/approve/{token} → submits decision { decision, feedback? }
 *
 * Handles four states:
 *   loading      — spinner skeleton
 *   expired/done — 404 or 410 (link expired or already decided)
 *   error        — unexpected error
 *   success      — show post + Aprovar / Solicitar revisão actions
 *
 * The api client is used without an auth header — these endpoints require
 * no JWT, mirroring usePublicReport's pattern in useRelatorios.ts.
 */
import { useState } from "react";
import { useParams } from "react-router-dom";
import {
  usePublicApproval,
  useDecideApproval,
  type ApprovalDecision,
} from "@/hooks/useConteudo";
import {
  CheckCircle2,
  XCircle,
  Clock,
  AlertCircle,
  Image,
  Megaphone,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Shared shell
// ---------------------------------------------------------------------------

function PageShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50 py-10 px-4">
      <div className="mx-auto max-w-2xl space-y-6">{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

function LoadingState() {
  return (
    <PageShell>
      <div className="rounded-xl bg-white border border-gray-200 p-6 shadow-sm animate-pulse space-y-4">
        <div className="h-4 bg-gray-200 rounded w-1/3" />
        <div className="h-6 bg-gray-200 rounded w-2/3" />
        <div className="h-32 bg-gray-200 rounded" />
      </div>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Terminal states (expired / already decided / error)
// ---------------------------------------------------------------------------

type TerminalReason = "expired" | "decided" | "error";

function TerminalState({
  reason,
  message,
}: {
  reason: TerminalReason;
  message?: string;
}) {
  const configs: Record<
    TerminalReason,
    { icon: React.ElementType; color: string; title: string; body: string }
  > = {
    expired: {
      icon: Clock,
      color: "text-amber-400",
      title: "Link expirado",
      body: "Este link de aprovação expirou. Solicite um novo link à agência.",
    },
    decided: {
      icon: CheckCircle2,
      color: "text-green-500",
      title: "Decisão já registrada",
      body: "Esta aprovação já foi respondida. Obrigado!",
    },
    error: {
      icon: AlertCircle,
      color: "text-red-400",
      title: "Erro ao carregar",
      body: message ?? "Ocorreu um erro inesperado. Tente novamente mais tarde.",
    },
  };

  const { icon: Icon, color, title, body } = configs[reason];

  return (
    <PageShell>
      <div className="rounded-xl bg-white border border-gray-200 p-10 text-center shadow-sm">
        <Icon className={`h-12 w-12 mx-auto mb-4 ${color}`} />
        <h2 className="text-lg font-semibold text-gray-800 mb-2">{title}</h2>
        <p className="text-sm text-gray-500">{body}</p>
      </div>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Success state (confirmed decision)
// ---------------------------------------------------------------------------

function DoneState({ decision }: { decision: ApprovalDecision }) {
  return (
    <PageShell>
      <div className="rounded-xl bg-white border border-gray-200 p-10 text-center shadow-sm">
        {decision === "approved" ? (
          <CheckCircle2 className="h-12 w-12 text-green-500 mx-auto mb-4" />
        ) : (
          <XCircle className="h-12 w-12 text-amber-400 mx-auto mb-4" />
        )}
        <h2 className="text-lg font-semibold text-gray-800 mb-2">
          {decision === "approved" ? "Conteúdo aprovado!" : "Revisão solicitada!"}
        </h2>
        <p className="text-sm text-gray-500">
          {decision === "approved"
            ? "Ótimo! O conteúdo foi aprovado e a equipe foi notificada."
            : "A equipe foi notificada com o seu feedback e irá revisar o conteúdo."}
        </p>
      </div>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------
// Platform badge
// ---------------------------------------------------------------------------

const PLATFORM_LABELS: Record<string, string> = {
  instagram: "Instagram",
  facebook: "Facebook",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  twitter: "Twitter / X",
};

function PlatformBadge({ platform }: { platform: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">
      <Megaphone className="h-3 w-3" />
      {PLATFORM_LABELS[platform] ?? platform}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Main approval form
// ---------------------------------------------------------------------------

export default function AprovacaoPublica() {
  const { token } = useParams<{ token: string }>();
  const { data, isPending, isError, error } = usePublicApproval(token ?? null);
  const decide = useDecideApproval(token ?? null);

  const [feedback, setFeedback] = useState("");
  const [showFeedback, setShowFeedback] = useState(false);
  const [submitted, setSubmitted] = useState<ApprovalDecision | null>(null);

  // --- Loading ---
  if (isPending && !data) return <LoadingState />;

  // --- Error / expired / already decided ---
  if (isError) {
    const msg = (error as Error)?.message ?? "";
    const isExpired =
      msg.includes("410") ||
      msg.toLowerCase().includes("expir") ||
      msg.toLowerCase().includes("already");
    const isDecided = msg.toLowerCase().includes("decided");
    return (
      <TerminalState
        reason={isExpired ? "expired" : isDecided ? "decided" : "error"}
        message={msg}
      />
    );
  }

  if (!data) return null;

  // Already decided (from API status)
  if (data.status !== "pending") {
    return <TerminalState reason="decided" />;
  }

  // Submitted this session
  if (submitted) return <DoneState decision={submitted} />;

  // --- Expired ---
  const expiresAt = new Date(data.expires_at);
  if (expiresAt < new Date()) return <TerminalState reason="expired" />;

  async function handleDecision(decision: ApprovalDecision) {
    if (decision === "revision" && !feedback.trim()) {
      setShowFeedback(true);
      return;
    }
    await decide.mutateAsync({ decision, feedback: feedback.trim() || undefined });
    setSubmitted(decision);
  }

  const { post } = data;

  return (
    <PageShell>
      {/* Header */}
      <div className="rounded-xl bg-white border border-gray-200 p-6 shadow-sm">
        <div className="flex items-center gap-3 mb-3">
          <div className="rounded-lg bg-indigo-50 p-2">
            <Megaphone className="h-5 w-5 text-indigo-600" />
          </div>
          <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
            Aprovação de Conteúdo
          </span>
        </div>
        <PlatformBadge platform={post.platform} />
        {post.scheduled_for && (
          <p className="text-xs text-gray-400 mt-2">
            Agendado para:{" "}
            {new Date(post.scheduled_for).toLocaleDateString("pt-BR", {
              day: "2-digit",
              month: "long",
              year: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        )}
      </div>

      {/* Media preview */}
      {post.media_url && (
        <div className="rounded-xl bg-white border border-gray-200 overflow-hidden shadow-sm">
          <img
            src={post.media_url}
            alt="Mídia do post"
            className="w-full object-cover max-h-80"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
      )}
      {!post.media_url && (
        <div className="rounded-xl bg-gray-100 border border-gray-200 p-8 text-center text-gray-400">
          <Image className="h-8 w-8 mx-auto mb-2" />
          <p className="text-sm">Sem mídia anexada</p>
        </div>
      )}

      {/* Caption */}
      {post.caption && (
        <div className="rounded-xl bg-white border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Legenda</p>
          <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">
            {post.caption}
          </p>
        </div>
      )}

      {/* Hashtags */}
      {post.hashtags && (
        <div className="rounded-xl bg-white border border-gray-200 p-5 shadow-sm">
          <p className="text-xs font-semibold text-gray-400 uppercase mb-2">Hashtags</p>
          <p className="text-sm text-indigo-600 break-words">{post.hashtags}</p>
        </div>
      )}

      {/* Feedback textarea (revealed on "Solicitar revisão") */}
      {showFeedback && (
        <div className="rounded-xl bg-amber-50 border border-amber-200 p-5 shadow-sm space-y-2">
          <label className="text-sm font-medium text-amber-800">
            Descreva o que precisa ser ajustado:
          </label>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={4}
            placeholder="Ex: ajustar a legenda, trocar a imagem, mudar o horário..."
            className="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-400 resize-none"
          />
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-col sm:flex-row gap-3">
        <button
          onClick={() => handleDecision("approved")}
          disabled={decide.isPending}
          className="flex-1 flex items-center justify-center gap-2 rounded-xl bg-green-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-green-700 disabled:opacity-60 transition-colors"
        >
          <CheckCircle2 className="h-4 w-4" />
          Aprovar
        </button>
        <button
          onClick={() => {
            if (!showFeedback) {
              setShowFeedback(true);
            } else {
              handleDecision("revision");
            }
          }}
          disabled={decide.isPending || (showFeedback && !feedback.trim())}
          className="flex-1 flex items-center justify-center gap-2 rounded-xl border border-amber-400 bg-amber-50 px-6 py-3 text-sm font-semibold text-amber-800 shadow-sm hover:bg-amber-100 disabled:opacity-60 transition-colors"
        >
          <XCircle className="h-4 w-4" />
          {showFeedback ? "Enviar revisão" : "Solicitar revisão"}
        </button>
      </div>

      {decide.isError && (
        <p className="text-center text-sm text-red-500">
          Erro ao enviar decisão. Tente novamente.
        </p>
      )}

      <p className="text-center text-xs text-gray-300 pt-2">
        Powered by Orbity · NoctusAI
      </p>
    </PageShell>
  );
}
