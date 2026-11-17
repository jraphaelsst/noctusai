/**
 * "Adicionar perfil" (contract §4.2): the library is platform-wide, so adding a profile is a PLATFORM-ADMIN
 * write — members cannot suggest profiles (owner Q10) and see only a notice. Handle input with a 500 ms-debounced
 * live check (#10), optional "Conta usada para monitorar" (#15), submit (#11). The admin flag is the same
 * `GET /treinamentos/admin` probe the other admin-only Biblioteca panels use; the server enforces the gate.
 */
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  useContasDescoberta,
  useSolicitarPerfil,
  useVerificarPerfil,
  type VerificacaoPerfil,
} from "@/hooks/geracao/useBiblioteca";
import { useTreinamentosAdmin } from "@/hooks/geracao/useTreinamentos";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { mensagemEstruturas } from "./estruturas/erros";
import { normalizarHandle } from "./handle";
import { ehPerfilOptout, MSG_PERFIL_OPTOUT, textoTransparencia } from "./optout";

export const MSG_VERIFICACAO: Record<VerificacaoPerfil["status"], string> = {
  disponivel: "✓ Username válido",
  ja_monitorado: "⚠️ Este perfil já está na biblioteca (monitorado)",
  na_minha_biblioteca: "⚠️ Este perfil já está na sua biblioteca.",
  sem_conta_descoberta:
    "✗ Nenhuma fonte de dados configurada para monitorar perfis. Fale com o administrador.",
};

export function SolicitarPerfil({ marcaId, contato }: { marcaId?: string; contato?: string }) {
  const adminQ = useTreinamentosAdmin();
  if (adminQ.isPending) return <p role="status" className="text-sm text-muted-foreground">Carregando…</p>;
  if (adminQ.data !== true) {
    return (
      <p role="status" className="max-w-md text-sm text-muted-foreground" data-testid="perfil-somente-admin">
        A biblioteca é da plataforma: somente administradores adicionam perfis. Para pedir um perfil novo, fale com o
        administrador.
      </p>
    );
  }
  return <SolicitarPerfilAdmin marcaId={marcaId} contato={contato} />;
}

function SolicitarPerfilAdmin({ marcaId, contato }: { marcaId?: string; contato?: string }) {
  const [texto, setTexto] = useState("");
  const [contaId, setContaId] = useState("");
  const [optout, setOptout] = useState(false);
  const norm = normalizarHandle(texto);
  const handleDebounced = useDebouncedValue(norm.ok ? norm.handle : "", 500);

  const verificar = useVerificarPerfil(handleDebounced, marcaId);
  const contasQ = useContasDescoberta();
  const solicitar = useSolicitarPerfil();
  const contas = contasQ.data ?? [];

  const aguardando = norm.ok && handleDebounced !== norm.handle;
  const status = norm.ok && !aguardando ? verificar.data?.status : undefined;
  const podeEnviar = norm.ok && status === "disponivel" && !solicitar.isPending;

  async function enviar() {
    if (!norm.ok || !podeEnviar) return;
    try {
      const p = await solicitar.mutateAsync({
        handle: norm.handle,
        ...(contaId ? { conta_descoberta_id: contaId } : {}),
      });
      toast.success(
        p.status === "aguardando"
          ? "Perfil adicionado à biblioteca. Ele será monitorado assim que a ingestão estiver ativa."
          : "Perfil adicionado à biblioteca.",
      );
      setTexto("");
    } catch (e) {
      if (ehPerfilOptout(e)) {
        setOptout(true);
        return;
      }
      toast.error(mensagemEstruturas(e, "Não foi possível adicionar o perfil."));
    }
  }

  // The check result only speaks for the CURRENT, settled handle; a stale error from the
  // previous value (or a cleared field) must never keep the opt-out message on screen.
  const erroDaVerificacao = norm.ok && !aguardando ? verificar.error : null;
  let mensagem: string | null = null;
  if (ehPerfilOptout(erroDaVerificacao) || optout) mensagem = MSG_PERFIL_OPTOUT;
  else if (texto.trim() && norm.ok === false) mensagem = norm.erro;
  else if (status) mensagem = MSG_VERIFICACAO[status];
  else if (norm.ok && (aguardando || verificar.isFetching)) mensagem = "Verificando...";
  else if (norm.ok && !aguardando && verificar.isError) mensagem = "Não foi possível verificar o perfil agora.";

  return (
    <form
      className="flex max-w-md flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="sp-handle">Perfil do Instagram (deve começar com @)</Label>
        <Input
          id="sp-handle"
          placeholder="@perfil"
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
            setOptout(false);
          }}
          autoComplete="off"
        />
        {mensagem && (
          <p
            role="status"
            className={
              mensagem === MSG_PERFIL_OPTOUT
                ? "text-sm font-medium text-destructive"
                : "text-xs text-muted-foreground"
            }
          >
            {mensagem}
          </p>
        )}
      </div>
      {contas.length > 1 && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="sp-conta">Conta usada para monitorar</Label>
          <select
            id="sp-conta"
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
            value={contaId}
            onChange={(e) => setContaId(e.target.value)}
          >
            <option value="">Padrão</option>
            {contas.map((c) => (
              <option key={c.id} value={c.id}>
                {c.ig_username ? `@${c.ig_username}` : c.nome}
              </option>
            ))}
          </select>
        </div>
      )}
      <p className="text-xs text-muted-foreground" data-testid="nota-transparencia">
        {textoTransparencia(contato)}
      </p>
      <Button type="submit" className="w-fit" disabled={!podeEnviar}>
        {solicitar.isPending ? "Adicionando..." : "Adicionar perfil"}
      </Button>
    </form>
  );
}
