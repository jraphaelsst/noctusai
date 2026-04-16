/**
 * ERP Equipe — Admin-only team management page.
 *
 * Sections:
 * - Membros: list current team members with role badges
 * - Convites Pendentes: list pending invitations with cancel action
 * - "Convidar" button opens a modal to invite new members by email + role
 *
 * All data flows through the FastAPI backend (/api/team/*).
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  Users,
  UserPlus,
  Mail,
  Trash2,
  Clock,
  Shield,
  Loader2,
  XCircle,
} from "lucide-react";
import { useIsAdmin } from "@/hooks/useUserRole";
import {
  useTeamMembers,
  useTeamInvitations,
  useSendInvite,
  useCancelInvite,
  useRemoveMember,
} from "@/hooks/useEquipe";
import { toast } from "sonner";
import { format } from "date-fns";
import { ptBR } from "date-fns/locale";

// ── Role config ──────────────────────────────────────────────

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrador",
  coordenador: "Coordenador",
  dev: "Desenvolvedor",
  corretor: "Corretor",
};

const ROLE_COLORS: Record<string, string> = {
  admin: "bg-slate-700 hover:bg-slate-700/80 text-white border-slate-700",
  dev: "bg-purple-600 hover:bg-purple-600/80 text-white border-purple-600",
  coordenador: "border-primary text-primary",
  corretor: "bg-secondary text-secondary-foreground",
};

const AVAILABLE_ROLES = [
  { value: "admin", label: "Administrador" },
  { value: "coordenador", label: "Coordenador" },
  { value: "dev", label: "Desenvolvedor" },
  { value: "corretor", label: "Corretor" },
];

// ── Component ────────────────────────────────────────────────

export default function Equipe() {
  const navigate = useNavigate();
  const { isAdmin, isLoading: isLoadingRole } = useIsAdmin();

  // Modal state
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("corretor");

  // Guard: admin-only
  useEffect(() => {
    if (!isLoadingRole && !isAdmin) {
      toast.error("Acesso negado", {
        description: "Voce nao tem permissao para acessar esta pagina.",
      });
      navigate("/");
    }
  }, [isAdmin, isLoadingRole, navigate]);

  // ── Queries ──────────────────────────────────────────────

  const {
    data: members = [],
    isLoading: loadingMembers,
  } = useTeamMembers(isAdmin);

  const {
    data: invitations = [],
    isLoading: loadingInvitations,
  } = useTeamInvitations(isAdmin);

  // ── Mutations ────────────────────────────────────────────

  const sendInvite = useSendInvite(() => {
    setInviteOpen(false);
    setInviteEmail("");
    setInviteRole("corretor");
  });

  const cancelInvite = useCancelInvite();

  const removeMember = useRemoveMember();

  // ── Handlers ─────────────────────────────────────────────

  const handleInviteSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!inviteEmail.trim()) {
        toast.error("Email e obrigatorio");
        return;
      }
      sendInvite.mutate({ email: inviteEmail.trim(), role: inviteRole });
    },
    [inviteEmail, inviteRole, sendInvite],
  );

  // ── Guards ───────────────────────────────────────────────

  if (!isAdmin && !isLoadingRole) return null;

  const isLoading = loadingMembers || loadingInvitations || isLoadingRole;

  const pendingInvitations = invitations.filter((inv) => inv.status === "pending");

  // ── Helpers ──────────────────────────────────────────────

  function getInitials(name: string): string {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .substring(0, 2)
      .toUpperCase();
  }

  function isExpired(expiresAt: string): boolean {
    return new Date(expiresAt) < new Date();
  }

  // ── Render ───────────────────────────────────────────────

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Page header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">Equipe</h1>
          <p className="text-sm text-muted-foreground">
            Gerencie membros e convites da sua equipe
          </p>
        </div>

        {/* Invite button + modal */}
        <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
          <DialogTrigger asChild>
            <Button className="gap-2">
              <UserPlus className="h-4 w-4" />
              Convidar
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Convidar membro</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleInviteSubmit} className="space-y-4 pt-2">
              <div className="space-y-2">
                <Label htmlFor="invite-email">Email</Label>
                <Input
                  id="invite-email"
                  type="email"
                  placeholder="email@exemplo.com"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="invite-role">Cargo</Label>
                <Select value={inviteRole} onValueChange={setInviteRole}>
                  <SelectTrigger id="invite-role">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {AVAILABLE_ROLES.map((r) => (
                      <SelectItem key={r.value} value={r.value}>
                        {r.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setInviteOpen(false)}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={sendInvite.isPending} className="gap-2">
                  {sendInvite.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Enviando...
                    </>
                  ) : (
                    <>
                      <Mail className="h-4 w-4" />
                      Enviar convite
                    </>
                  )}
                </Button>
              </div>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* ── Membros ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            <CardTitle>Membros ({members.length})</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
              <Skeleton className="h-16" />
            </div>
          ) : members.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Nenhum membro encontrado.
            </p>
          ) : (
            <div className="divide-y divide-border">
              {members.map((member) => (
                <div
                  key={member.id}
                  className="flex items-center gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <Avatar className="h-10 w-10">
                    <AvatarFallback className="bg-primary/10 text-primary text-sm font-semibold">
                      {getInitials(member.nome)}
                    </AvatarFallback>
                  </Avatar>

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {member.nome}
                    </p>
                    <p className="text-xs text-muted-foreground truncate">
                      {member.email}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 flex-shrink-0">
                    {member.roles.map((role) => (
                      <Badge
                        key={role}
                        variant="outline"
                        className={`text-xs ${ROLE_COLORS[role] || ROLE_COLORS.corretor}`}
                      >
                        {ROLE_LABELS[role] || role}
                      </Badge>
                    ))}
                  </div>

                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-muted-foreground hover:text-destructive flex-shrink-0"
                    onClick={() => removeMember.mutate(member.id)}
                    disabled={removeMember.isPending}
                    title="Remover membro"
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Convites Pendentes ── */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Clock className="h-5 w-5 text-primary" />
            <CardTitle>Convites Pendentes ({pendingInvitations.length})</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-14" />
              <Skeleton className="h-14" />
            </div>
          ) : pendingInvitations.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              Nenhum convite pendente.
            </p>
          ) : (
            <div className="divide-y divide-border">
              {pendingInvitations.map((inv) => (
                <div
                  key={inv.id}
                  className="flex items-center gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex items-center justify-center h-10 w-10 rounded-full bg-muted">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                  </div>

                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {inv.email}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Enviado em{" "}
                      {format(new Date(inv.created_at), "dd MMM yyyy", {
                        locale: ptBR,
                      })}
                      {isExpired(inv.expires_at) && (
                        <span className="text-destructive ml-2">Expirado</span>
                      )}
                      {!isExpired(inv.expires_at) && (
                        <span className="ml-2">
                          Expira em{" "}
                          {format(new Date(inv.expires_at), "dd MMM yyyy", {
                            locale: ptBR,
                          })}
                        </span>
                      )}
                    </p>
                  </div>

                  <Badge
                    variant="outline"
                    className={`text-xs flex-shrink-0 ${ROLE_COLORS[inv.role] || ROLE_COLORS.corretor}`}
                  >
                    {ROLE_LABELS[inv.role] || inv.role}
                  </Badge>

                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-muted-foreground hover:text-destructive flex-shrink-0"
                    onClick={() => cancelInvite.mutate(inv.id)}
                    disabled={cancelInvite.isPending}
                    title="Cancelar convite"
                  >
                    <XCircle className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
