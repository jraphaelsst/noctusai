/**
 * One drawer for every Conhecimento section: Cancelar/Salvar, dirty-exit
 * confirm (Lais copy), optimistic-lock (409 versao_conflito) reload prompt.
 * Fields come from the registry (`secoes.ts`); chips use the design-system
 * `MultiSelectPopover`; the leave-confirm is the seed `useConfirm`.
 */
import { useEffect, useRef, useState } from "react";
import { Loader2, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { MultiSelectPopover } from "@noctusai/lib/design-system";
import { useConfirm } from "@noctusai/lib/components";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  codigoErroConhecimento, mensagemErroConhecimento, useSalvarSecao, type SecaoSalva,
} from "@/hooks/useLaisConhecimento";
import { PerfilMockup } from "./PerfilMockup";
import { get, set, type Campo, type SecaoSpec } from "./secoes";

export const MSG_SAIR = "Sair da edição? As modificações feitas não serão salvas.";

interface Telefone { setor: string; telefone: string; principal: boolean }
const E164 = /^\+\d{10,15}$/;

function TelefonesEditor({ value, onChange }: { value: Telefone[]; onChange: (v: Telefone[]) => void }) {
  const upd = (i: number, p: Partial<Telefone>) => onChange(value.map((t, j) => (j === i ? { ...t, ...p } : t)));
  const principal = (i: number) => onChange(value.map((t, j) => ({ ...t, principal: j === i })));
  return (
    <div className="space-y-3" data-testid="telefones-editor">
      {value.length === 0 && <p className="text-sm text-muted-foreground">Nenhum contato cadastrado.</p>}
      {value.map((t, i) => (
        <div key={i} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2">
          <div><Label>Setor</Label><Input value={t.setor} maxLength={60} aria-label={`Setor ${i + 1}`} onChange={(e) => upd(i, { setor: e.target.value })} /></div>
          <div>
            <Label>Telefone (+5511999999999)</Label>
            <Input value={t.telefone} aria-label={`Telefone ${i + 1}`} onChange={(e) => upd(i, { telefone: e.target.value })}
              aria-invalid={t.telefone !== "" && !E164.test(t.telefone)} />
          </div>
          <div className="flex items-center gap-2 pb-1">
            <label className="flex items-center gap-1 text-xs">
              <input type="radio" name="tel-principal" checked={t.principal} aria-label={`Principal ${i + 1}`} onChange={() => principal(i)} /> Principal
            </label>
            <Button type="button" variant="ghost" size="sm" aria-label={`Remover contato ${i + 1}`}
              onClick={() => { const r = value.filter((_, j) => j !== i); if (t.principal && r.length) r[0] = { ...r[0], principal: true }; onChange(r); }}>
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" disabled={value.length >= 10}
        onClick={() => onChange([...value, { setor: "", telefone: "", principal: value.length === 0 }])}>
        <Plus className="mr-1 h-4 w-4" /> Adicionar novo contato
      </Button>
    </div>
  );
}

function CampoInput({ c, dados, onChange }: { c: Campo; dados: Record<string, unknown>; onChange: (path: string, v: unknown) => void }) {
  const v = get(dados, c.path);
  const id = `campo-${c.path}`;
  switch (c.kind) {
    case "switch":
      return (
        <div className="flex items-center justify-between gap-3">
          <Label htmlFor={id}>{c.label}</Label>
          <Switch id={id} checked={!!v} onCheckedChange={(x: boolean) => onChange(c.path, x)} />
        </div>
      );
    case "radio":
      return (
        <fieldset className="space-y-1.5"><legend className="text-sm font-medium">{c.label}</legend>
          {c.opcoes?.map((o) => (
            <label key={String(o.value)} className="flex items-center gap-2 text-sm">
              <input type="radio" name={id} checked={(v ?? null) === o.value} onChange={() => onChange(c.path, o.value)} /> {o.label}
            </label>
          ))}
        </fieldset>
      );
    case "chips": {
      const sel = Array.isArray(v) ? (v as (string | number)[]) : [];
      return (
        <div className="space-y-1.5"><Label>{c.label}</Label>
          <MultiSelectPopover label={c.label} triggerLabel="Selecionar" showChips testId={id}
            options={(c.opcoes ?? []).map((o) => ({ value: String(o.value), label: o.label }))}
            selected={sel.map(String)}
            onToggle={(val) => {
              const typed = c.numeric ? Number(val) : val;
              onChange(c.path, sel.includes(typed) ? sel.filter((x) => x !== typed) : [...sel, typed]);
            }} />
        </div>
      );
    }
    case "textarea":
      return (<div className="space-y-1.5"><Label htmlFor={id}>{c.label}</Label>
        <Textarea id={id} rows={4} maxLength={c.max} value={(v as string) ?? ""} onChange={(e) => onChange(c.path, e.target.value)} /></div>);
    case "number":
      return (<div className="space-y-1.5"><Label htmlFor={id}>{c.label}</Label>
        <Input id={id} type="number" min={0} value={v === null || v === undefined ? "" : String(v)}
          onChange={(e) => onChange(c.path, e.target.value === "" ? null : Number(e.target.value))} /></div>);
    case "readonly":
      return (<div className="space-y-1.5"><Label htmlFor={id}>{c.label}</Label>
        <Input id={id} readOnly value={(v as string) ?? ""} />{c.ajuda && <p className="text-xs text-muted-foreground">{c.ajuda}</p>}</div>);
    default:
      return (<div className="space-y-1.5"><Label htmlFor={id}>{c.label}</Label>
        <Input id={id} type={c.kind === "date" ? "date" : "text"} maxLength={c.max} value={(v as string) ?? ""}
          onChange={(e) => onChange(c.path, e.target.value)} />
        {c.ajuda && <p className="text-xs text-muted-foreground">{c.ajuda}</p>}</div>);
  }
}

function validar(spec: SecaoSpec, dados: unknown): string | null {
  if (spec.custom === "telefones") {
    const l = dados as Telefone[];
    if (l.some((t) => !t.setor.trim() || !E164.test(t.telefone))) return "Informe o setor e um telefone válido (ex.: +5511999999999) em cada contato.";
    if (l.length > 0 && l.filter((t) => t.principal).length !== 1) return "Escolha exatamente um contato principal.";
  }
  return null;
}

export interface SecaoDrawerProps {
  spec: SecaoSpec;
  saved: SecaoSalva | undefined;
  /** Refetches the page query and returns the fresh section (409 recovery). */
  onReload: () => Promise<SecaoSalva | undefined>;
  onClose: () => void;
}

export function SecaoDrawer({ spec, saved, onReload, onClose }: SecaoDrawerProps) {
  const confirm = useConfirm();
  const salvar = useSalvarSecao();
  const [base, setBase] = useState(() => ({ dados: saved?.dados ?? spec.defaults, versao: saved?.versao ?? 0 }));
  const [draft, setDraft] = useState<unknown>(base.dados);
  const [conflito, setConflito] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(base.dados);
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  const tentarFechar = async () => {
    if (dirtyRef.current && !(await confirm({ title: MSG_SAIR, confirmLabel: "Sair", cancelLabel: "Continuar editando", tone: "danger" }))) return;
    onClose();
  };
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") void tentarFechar(); };
    document.addEventListener("keydown", h);
    return () => document.removeEventListener("keydown", h);
  });

  const onSalvar = async () => {
    const inv = validar(spec, draft);
    if (inv) { setErro(inv); return; }
    setErro(null);
    try {
      await salvar.mutateAsync({ secao: spec.key, dados: draft, versao: base.versao });
      toast.success("Salvo. A Julia já usa estas informações.");
      onClose();
    } catch (err) {
      if (codigoErroConhecimento(err) === "versao_conflito") setConflito(true);
      else setErro(mensagemErroConhecimento(err, "Não foi possível salvar."));
    }
  };

  const recarregar = async () => {
    const fresco = await onReload();
    const b = { dados: fresco?.dados ?? spec.defaults, versao: fresco?.versao ?? 0 };
    setBase(b); setDraft(b.dados); setConflito(false); setErro(null);
  };

  const dadosObj = (draft && typeof draft === "object" && !Array.isArray(draft) ? draft : {}) as Record<string, unknown>;
  const onChange = (path: string, v: unknown) => setDraft((d: unknown) => set(d, path, v));

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50" onClick={() => void tentarFechar()}>
      <aside role="dialog" aria-modal="true" aria-label={`Editar ${spec.titulo}`} data-testid="secao-drawer"
        className="flex h-full w-full max-w-lg flex-col overflow-y-auto bg-background shadow-xl" onClick={(e) => e.stopPropagation()}>
        <header className="flex items-start justify-between border-b p-4">
          <div><h2 className="text-lg font-semibold">{spec.titulo}</h2><p className="text-sm text-muted-foreground">{spec.descricao}</p></div>
          <Button variant="ghost" size="sm" aria-label="Fechar" onClick={() => void tentarFechar()}><X className="h-4 w-4" /></Button>
        </header>
        <div className="flex-1 space-y-4 p-4">
          {conflito && (
            <div role="alert" className="space-y-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm" data-testid="conflito">
              <p>{mensagemErroConhecimento({ body: { error: { code: "versao_conflito" } } }, "")}</p>
              <Button size="sm" variant="outline" onClick={() => void recarregar()}>Recarregar</Button>
            </div>
          )}
          {spec.key === "perfil_whatsapp" && <PerfilMockup dados={dadosObj} />}
          {spec.custom === "telefones" ? (
            <TelefonesEditor value={Array.isArray(draft) ? (draft as Telefone[]) : []} onChange={(v) => setDraft(v)} />
          ) : (
            spec.campos.filter((c) => !c.quando || c.quando(dadosObj)).map((c) => (
              <CampoInput key={c.path} c={c} dados={dadosObj} onChange={onChange} />
            ))
          )}
          {erro && <p role="alert" className="text-sm text-destructive" data-testid="erro-salvar">{erro}</p>}
        </div>
        <footer className="flex justify-end gap-2 border-t p-4">
          <Button variant="outline" onClick={() => void tentarFechar()}>Cancelar</Button>
          <Button onClick={() => void onSalvar()} disabled={!dirty || salvar.isPending || conflito}>
            {salvar.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} Salvar
          </Button>
        </footer>
      </aside>
    </div>
  );
}
