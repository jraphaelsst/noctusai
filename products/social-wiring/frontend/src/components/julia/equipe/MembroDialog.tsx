/** Add / edit one member of the org's WhatsApp staff list (a design-system modal; the server refusal stays inline). */
import { useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  EXPLICACAO_PAPEL, ROTULO_PAPEL, type MembroEntrada, type MembroEquipe, type PapelEquipe, type UsuarioOrg,
} from "@/hooks/useJuliaEquipeWhatsapp";

interface Props {
  aberto: boolean;
  /** null = a new member. */
  membro: MembroEquipe | null;
  papeis: PapelEquipe[];
  usuarios: UsuarioOrg[];
  pendente: boolean;
  erro: string | null;
  onSalvar: (corpo: MembroEntrada) => void;
  onFechar: () => void;
}

const SELECT_CLASS =
  "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring";

export function MembroDialog({ aberto, membro, papeis, usuarios, pendente, erro, onSalvar, onFechar }: Props) {
  const [nome, setNome] = useState(membro?.nome ?? "");
  const [papel, setPapel] = useState<PapelEquipe>(membro?.papel ?? "corretor");
  const [telefone, setTelefone] = useState(membro?.telefone ? `+${membro.telefone}` : "");
  const [userId, setUserId] = useState(membro?.user_id ?? "");
  const valido = nome.trim().length > 0 && (telefone.trim().length > 0 || userId !== "");

  return (
    <Dialog open={aberto} onOpenChange={(o) => { if (!o && !pendente) onFechar(); }}>
      <DialogContent data-testid="membro-dialog">
        <DialogHeader>
          <DialogTitle>{membro ? "Editar membro da equipe" : "Adicionar à equipe"}</DialogTitle>
          <DialogDescription>
            Somente números cadastrados aqui são equipe. Qualquer outro número que escreva na linha pública é tratado como lead.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <label htmlFor="membro-nome" className="text-sm font-medium">Nome</label>
            <Input id="membro-nome" value={nome} maxLength={120} onChange={(e) => setNome(e.target.value)} data-testid="membro-nome" />
          </div>
          <div className="space-y-1">
            <label htmlFor="membro-papel" className="text-sm font-medium">Papel</label>
            <select id="membro-papel" className={SELECT_CLASS} value={papel} onChange={(e) => setPapel(e.target.value as PapelEquipe)} data-testid="membro-papel">
              {papeis.map((p) => <option key={p} value={p}>{ROTULO_PAPEL[p]}</option>)}
            </select>
            <p className="text-xs text-muted-foreground" data-testid="membro-papel-explicacao">{EXPLICACAO_PAPEL[papel]}</p>
          </div>
          <div className="space-y-1">
            <label htmlFor="membro-telefone" className="text-sm font-medium">WhatsApp (com DDI e DDD)</label>
            <Input id="membro-telefone" value={telefone} placeholder="+55 11 99999-9999" onChange={(e) => setTelefone(e.target.value)} data-testid="membro-telefone" />
          </div>
          <div className="space-y-1">
            <label htmlFor="membro-usuario" className="text-sm font-medium">Usuário do sistema (opcional)</label>
            <select id="membro-usuario" className={SELECT_CLASS} value={userId} onChange={(e) => setUserId(e.target.value)} data-testid="membro-usuario">
              <option value="">Sem usuário vinculado</option>
              {usuarios.map((u) => <option key={u.id} value={u.id}>{u.nome ?? u.id}</option>)}
            </select>
          </div>
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="membro-erro">{erro}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onFechar} disabled={pendente}>Cancelar</Button>
          <Button
            disabled={!valido || pendente} data-testid="membro-salvar"
            onClick={() => onSalvar({ nome: nome.trim(), papel, telefone: telefone.trim() || null, user_id: userId || null })}
          >
            {pendente && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Salvar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
