import { useEffect, useState } from "react";
import { useAuthStore } from '@noctusai/seed/infra';
import { api } from '@noctusai/seed/infra';
import { toast } from "sonner";
import { Users, UserPlus, Trash2, Loader2, Mail, X } from "lucide-react";
import { resolveSSOContext, StatusPaginaPanel } from "@noctusai/lib";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Member {
  id: string;
  nome: string;
  email: string;
  role: string;
  org_role: string;
  avatar_url?: string;
  created_at: string;
}

interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
  expires_at: string;
}

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrador",
  member: "Membro",
  owner: "Proprietario",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function Equipe() {
  const { user } = useAuthStore();
  const ssoCtx = resolveSSOContext(user?.user_metadata);
  const isAdmin = ssoCtx.isProductAdmin || ssoCtx.org.role === "owner" || ssoCtx.org.role === "admin";

  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [loading, setLoading] = useState(true);

  // Invite modal
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member");
  const [inviting, setInviting] = useState(false);

  // Confirm remove
  const [confirmRemove, setConfirmRemove] = useState<Member | null>(null);
  const [removing, setRemoving] = useState(false);

  async function fetchData() {
    try {
      const [membersRes, invitesRes] = await Promise.all([
        api.get<{ data: Member[] }>("/api/team"),
        api.get<{ data: Invitation[] }>("/api/team/invitations").catch(() => ({ data: [] })),
      ]);
      setMembers(membersRes.data || []);
      setInvitations(invitesRes.data || []);
    } catch {
      toast.error("Erro ao carregar dados da equipe");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user) fetchData();
  }, [user]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setInviting(true);
    try {
      await api.post("/api/team/invite", { email: inviteEmail, role: inviteRole });
      toast.success("Convite enviado com sucesso");
      setShowInviteModal(false);
      setInviteEmail("");
      setInviteRole("member");
      fetchData();
    } catch (err: any) {
      toast.error("Erro ao enviar convite", {
        description: err?.message || err?.detail || "Tente novamente",
      });
    } finally {
      setInviting(false);
    }
  }

  async function handleRemoveMember() {
    if (!confirmRemove) return;
    setRemoving(true);
    try {
      await api.delete(`/api/team/${confirmRemove.id}`);
      toast.success("Membro removido");
      setConfirmRemove(null);
      fetchData();
    } catch (err: any) {
      toast.error("Erro ao remover membro", {
        description: err?.message || "Tente novamente",
      });
    } finally {
      setRemoving(false);
    }
  }

  async function handleCancelInvite(inviteId: string) {
    try {
      await api.delete(`/api/team/invitations/${inviteId}`);
      toast.success("Convite cancelado");
      fetchData();
    } catch (err: any) {
      toast.error("Erro ao cancelar convite", {
        description: err?.message || "Tente novamente",
      });
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Carregando equipe...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <Users className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-2xl font-bold text-foreground">Equipe</h1>
            <p className="text-sm text-muted-foreground">
              {members.length} membro{members.length !== 1 ? "s" : ""} na organizacao
            </p>
          </div>
        </div>
        {isAdmin && (
          <button
            className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
            onClick={() => setShowInviteModal(true)}
          >
            <UserPlus className="h-4 w-4" />
            Convidar
          </button>
        )}
      </div>

      {/* Members Table */}
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Nome</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">E-mail</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
              <th className="px-4 py-3 font-medium text-muted-foreground hidden md:table-cell">Entrou em</th>
              {isAdmin && (
                <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {members.map((member) => (
              <tr key={member.id} className="bg-card">
                <td className="px-4 py-3 font-medium text-foreground">
                  <div className="flex flex-col">
                    <span>{member.nome || "—"}</span>
                    <span className="text-xs text-muted-foreground sm:hidden">{member.email}</span>
                  </div>
                  {member.id === user?.id && (
                    <span className="ml-2 inline-flex rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                      Voce
                    </span>
                  )}
                </td>
                <td className="px-4 py-3 text-foreground hidden sm:table-cell">{member.email}</td>
                <td className="px-4 py-3">
                  <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                    {ROLE_LABELS[member.role] || ROLE_LABELS[member.org_role] || member.role}
                  </span>
                </td>
                <td className="px-4 py-3 text-foreground hidden md:table-cell">
                  {member.created_at
                    ? new Date(member.created_at).toLocaleDateString("pt-BR")
                    : "—"}
                </td>
                {isAdmin && (
                  <td className="px-4 py-3">
                    {member.id !== user?.id &&
                      member.org_role !== "owner" &&
                      member.role !== "owner" && (
                        <button
                          className="inline-flex items-center gap-1 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
                          onClick={() => setConfirmRemove(member)}
                        >
                          <Trash2 className="h-3 w-3" />
                          Remover
                        </button>
                      )}
                  </td>
                )}
              </tr>
            ))}
            {members.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                  Nenhum membro encontrado
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Pending Invitations */}
      {isAdmin && (
        <section>
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold text-foreground">
            <Mail className="h-5 w-5 text-muted-foreground" />
            Convites pendentes
            {invitations.length > 0 && (
              <span className="inline-flex rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400">
                {invitations.length}
              </span>
            )}
          </h2>

          {invitations.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum convite pendente</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="px-4 py-3 font-medium text-muted-foreground">E-mail</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Papel</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground hidden sm:table-cell">Expira em</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Acoes</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {invitations.map((inv) => (
                    <tr key={inv.id} className="bg-card">
                      <td className="px-4 py-3 font-medium text-foreground">{inv.email}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-foreground">
                          {ROLE_LABELS[inv.role] || inv.role}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-foreground hidden sm:table-cell">
                        {inv.expires_at
                          ? new Date(inv.expires_at).toLocaleDateString("pt-BR")
                          : "—"}
                      </td>
                      <td className="px-4 py-3">
                        <button
                          className="inline-flex items-center gap-1 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-1 text-xs font-medium text-destructive hover:bg-destructive/20 transition-colors"
                          onClick={() => handleCancelInvite(inv.id)}
                        >
                          Cancelar
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* Page-visibility control — the status_pagina write-side organ (seed lib). */}
      {isAdmin && (
        <div className="mt-6">
          <StatusPaginaPanel api={api} enabled />
        </div>
      )}

      {/* Invite Modal */}
      {showInviteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShowInviteModal(false)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold text-foreground">Convidar membro</h2>
              <button
                className="rounded-md p-1.5 text-muted-foreground hover:bg-muted transition-colors"
                onClick={() => setShowInviteModal(false)}
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <form onSubmit={handleInvite} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">E-mail</label>
                <input
                  type="email"
                  placeholder="colaborador@empresa.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">Papel</label>
                <select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as "admin" | "member")}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <option value="member">Membro</option>
                  <option value="admin">Administrador</option>
                </select>
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                  onClick={() => setShowInviteModal(false)}
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-6 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                  disabled={inviting || !inviteEmail}
                >
                  {inviting ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Enviando...
                    </>
                  ) : (
                    "Enviar convite"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Confirm Remove Modal */}
      {confirmRemove && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setConfirmRemove(null)}
        >
          <div
            className="w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-lg border border-border bg-card p-6 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-2 text-lg font-semibold text-foreground">Remover membro</h2>
            <p className="mb-6 text-sm text-muted-foreground">
              Tem certeza que deseja remover{" "}
              <strong className="text-foreground">{confirmRemove.nome || confirmRemove.email}</strong>{" "}
              da organizacao? Esta acao nao pode ser desfeita.
            </p>
            <div className="flex justify-end gap-3">
              <button
                className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-muted transition-colors"
                onClick={() => setConfirmRemove(null)}
              >
                Cancelar
              </button>
              <button
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-6 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleRemoveMember}
                disabled={removing}
              >
                {removing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Removendo...
                  </>
                ) : (
                  "Confirmar remocao"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
