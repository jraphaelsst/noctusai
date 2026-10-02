/**
 * `/admin` — "Página de vendas": edits the whole settings document that feeds the
 * public landing (GET/PUT /api/admin/settings with optimistic versioning), the
 * author photo and the kit file. Non-admin (403) → explicit "Sem acesso", never the form.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { ApiError } from "@noctusai/lib";
import {
  Badge, Button, Card, Field, FormError, Input, Skeleton, Switch, Textarea,
} from "@noctusai/lib/design-system";
import { AccessDenied, isForbidden } from "@/components/AccessDenied";
import { useAdminSettings, useKitFile, useSaveSettings, useUploadFoto, useUploadKit } from "@/hooks/useStore";
import {
  BIO_MAX, MAX_ITEMS, assetUrl, centsFromDigits, centsToMask, formatBRL, type StoreSettings,
} from "@/lib/api";

const PHOTO_MAX = 5 * 1024 * 1024;
const KIT_MAX = 50 * 1024 * 1024;

export function validateSettings(s: StoreSettings): string[] {
  const e: string[] = [];
  if (!s.product_name.trim()) e.push("Informe o nome do produto.");
  if (s.price_cents < 100 || s.price_cents > 1_000_000) e.push("O preço deve ficar entre R$ 1,00 e R$ 10.000,00.");
  if (s.items.length < 1 || s.items.length > MAX_ITEMS) e.push(`Use de 1 a ${MAX_ITEMS} itens na lista.`);
  if (s.items.some((i) => !i.label.trim())) e.push("Todo item precisa de um nome.");
  if (s.guarantee_days < 0 || s.guarantee_days > 30 || !Number.isInteger(s.guarantee_days)) e.push("A garantia vai de 0 a 30 dias.");
  if (!s.author.name.trim()) e.push("Informe o nome do autor.");
  if (s.author.bio.length > BIO_MAX) e.push(`A bio passa de ${BIO_MAX} caracteres.`);
  return e;
}

function MoneyInput({ cents, onChange, label }: { cents: number; onChange: (c: number) => void; label: string }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-sm text-muted-foreground">R$</span>
      <Input
        aria-label={label}
        inputMode="numeric"
        value={centsToMask(cents)}
        onChange={(e) => onChange(centsFromDigits(e.target.value))}
        className="text-right tabular-nums"
      />
    </div>
  );
}

export default function Admin() {
  const settings = useAdminSettings();
  const save = useSaveSettings();
  const foto = useUploadFoto();
  const kit = useKitFile();
  const uploadKit = useUploadKit();

  const [draft, setDraft] = useState<StoreSettings | null>(null);
  const [conflict, setConflict] = useState(false);
  const [photoRev, setPhotoRev] = useState(0);
  const photoInput = useRef<HTMLInputElement>(null);
  const kitInput = useRef<HTMLInputElement>(null);

  const version = settings.data?.version;
  useEffect(() => {
    if (settings.data) setDraft(structuredClone(settings.data.data));
    // re-seed ONLY when a new ledger version arrives, never on background refetch of the same one
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const dirty = useMemo(
    () => !!draft && !!settings.data && JSON.stringify(draft) !== JSON.stringify(settings.data.data),
    [draft, settings.data],
  );
  const errors = useMemo(() => (draft ? validateSettings(draft) : []), [draft]);
  const total = useMemo(() => draft?.items.reduce((n, i) => n + i.anchor_cents, 0) ?? 0, [draft]);

  if (isForbidden(settings.error)) return <AccessDenied />;
  if (settings.showSkeleton || !draft) {
    if (settings.isError) {
      return <FormError message="Não foi possível carregar as configurações. Atualize a página." />;
    }
    return <div className="space-y-3" aria-busy="true"><Skeleton className="h-8 w-64" /><Skeleton className="h-64 w-full" /></div>;
  }

  const patch = (p: Partial<StoreSettings>) => setDraft({ ...draft, ...p });
  const patchItem = (i: number, p: Partial<StoreSettings["items"][number]>) =>
    patch({ items: draft.items.map((it, k) => (k === i ? { ...it, ...p } : it)) });
  const move = (i: number, d: -1 | 1) => {
    const items = [...draft.items];
    const j = i + d;
    if (j < 0 || j >= items.length) return;
    [items[i], items[j]] = [items[j], items[i]];
    patch({ items });
  };

  function onSave() {
    if (!draft || version === undefined) return;
    setConflict(false);
    save.mutate(
      { data: draft, version },
      {
        onSuccess: () => toast.success("Página de vendas salva."),
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) setConflict(true);
          else toast.error(err instanceof ApiError && err.status === 422 ? "Confira os campos: o servidor recusou os dados." : "Não foi possível salvar.");
        },
      },
    );
  }

  function pickPhoto(file?: File) {
    if (!file) return;
    if (file.size > PHOTO_MAX) return void toast.error("A foto passa de 5 MB.");
    foto.mutate(file, {
      onSuccess: () => { setPhotoRev((n) => n + 1); toast.success("Foto atualizada."); },
      onError: () => toast.error("Não foi possível enviar a foto."),
    });
  }
  function pickKit(file?: File) {
    if (!file) return;
    if (file.size > KIT_MAX) return void toast.error("O arquivo passa de 50 MB.");
    uploadKit.mutate(file, {
      onSuccess: () => toast.success("Kit substituído."),
      onError: () => toast.error("Não foi possível enviar o kit."),
    });
  }

  const photoSrc = draft.author.has_photo || foto.isSuccess ? `${assetUrl("/api/public/autor/foto")}?v=${photoRev}` : null;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Página de vendas</h1>
        <p className="text-sm text-muted-foreground">Tudo que aparece na página pública. Versão {version}.</p>
      </div>

      {conflict && (
        <div role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive flex items-center justify-between gap-3">
          <span>Alguém salvou antes de você. Recarregue para ver a versão atual (suas edições não salvas serão descartadas).</span>
          <Button variant="outline" size="sm" onClick={() => { setConflict(false); void settings.refetch().then((r) => r.data && setDraft(structuredClone(r.data.data))); }}>Recarregar</Button>
        </div>
      )}

      <Card className="space-y-4">
        <h2 className="font-semibold">Produto</h2>
        <Field label="Nome do produto" required>
          <Input value={draft.product_name} onChange={(e) => patch({ product_name: e.target.value })} />
        </Field>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Preço" required>
            <MoneyInput label="Preço" cents={draft.price_cents} onChange={(c) => patch({ price_cents: c })} />
          </Field>
          <Field label="Garantia (dias)">
            <Input type="number" min={0} max={30} value={draft.guarantee_days}
              onChange={(e) => patch({ guarantee_days: Math.trunc(Number(e.target.value) || 0) })} />
          </Field>
        </div>
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <div>
            <p className="text-sm font-medium">Vendas abertas</p>
            <p className="text-xs text-muted-foreground">Desligado, o botão de compra mostra "Vendas pausadas".</p>
          </div>
          <Switch aria-label="Vendas abertas" checked={draft.checkout_enabled} onCheckedChange={(v) => patch({ checkout_enabled: v })} />
        </div>
      </Card>

      <Card className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Itens do kit (preço de referência)</h2>
          <Badge variant="muted">Total: {formatBRL(total)}</Badge>
        </div>
        {draft.items.map((it, i) => (
          <div key={i} className="grid grid-cols-[1fr_9rem_auto] items-center gap-2">
            <Input aria-label={`Item ${i + 1}`} value={it.label} onChange={(e) => patchItem(i, { label: e.target.value })} />
            <MoneyInput label={`Valor do item ${i + 1}`} cents={it.anchor_cents} onChange={(c) => patchItem(i, { anchor_cents: c })} />
            <div className="flex gap-1">
              <Button variant="ghost" size="icon" aria-label="Subir" disabled={i === 0} onClick={() => move(i, -1)}><ArrowUp className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" aria-label="Descer" disabled={i === draft.items.length - 1} onClick={() => move(i, 1)}><ArrowDown className="h-4 w-4" /></Button>
              <Button variant="ghost" size="icon" aria-label="Remover" disabled={draft.items.length <= 1}
                onClick={() => patch({ items: draft.items.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
        <Button variant="outline" size="sm" disabled={draft.items.length >= MAX_ITEMS}
          onClick={() => patch({ items: [...draft.items, { label: "", anchor_cents: 0 }] })}>
          <Plus className="mr-1 h-4 w-4" /> Adicionar item
        </Button>
      </Card>

      <Card className="space-y-4">
        <h2 className="font-semibold">Autor</h2>
        <div className="grid grid-cols-2 gap-4">
          <Field label="Nome" required><Input value={draft.author.name} onChange={(e) => patch({ author: { ...draft.author, name: e.target.value } })} /></Field>
          <Field label="Profissão"><Input value={draft.author.role} onChange={(e) => patch({ author: { ...draft.author, role: e.target.value } })} /></Field>
        </div>
        <Field label="Bio">
          <Textarea rows={5} value={draft.author.bio} onChange={(e) => patch({ author: { ...draft.author, bio: e.target.value } })} />
          <span className={`block text-right text-xs ${draft.author.bio.length > BIO_MAX ? "text-destructive" : "text-muted-foreground"}`}>
            {draft.author.bio.length}/{BIO_MAX}
          </span>
        </Field>
        <div className="flex items-center gap-4">
          {photoSrc ? <img src={photoSrc} alt="Foto do autor" className="h-24 w-20 rounded object-cover border border-border" />
            : <div className="h-24 w-20 rounded border border-dashed border-border text-xs text-muted-foreground grid place-items-center text-center p-1">Sem foto</div>}
          <div>
            <input ref={photoInput} type="file" accept="image/*" hidden onChange={(e) => pickPhoto(e.target.files?.[0])} />
            <Button variant="outline" size="sm" disabled={foto.isPending} onClick={() => photoInput.current?.click()}>
              {foto.isPending ? "Enviando…" : "Enviar foto (até 5 MB)"}
            </Button>
            <p className="mt-1 text-xs text-muted-foreground">A foto vale na hora, sem precisar salvar.</p>
          </div>
        </div>
      </Card>

      <Card className="space-y-3">
        <h2 className="font-semibold">Arquivo do kit</h2>
        {kit.showSkeleton ? <Skeleton className="h-5 w-48" /> : isForbidden(kit.error) ? null : kit.data?.exists ? (
          <p className="text-sm">Kit publicado: {kit.data.size ? `${(kit.data.size / 1048576).toFixed(1)} MB` : "tamanho desconhecido"}
            {kit.data.updated_at ? ` · atualizado em ${new Date(kit.data.updated_at).toLocaleString("pt-BR")}` : ""}</p>
        ) : (
          <p role="alert" className="text-sm text-destructive">Nenhum kit enviado. Compradores não conseguem baixar.</p>
        )}
        <input ref={kitInput} type="file" accept=".zip,application/zip" hidden onChange={(e) => pickKit(e.target.files?.[0])} />
        <Button variant="outline" size="sm" disabled={uploadKit.isPending} onClick={() => kitInput.current?.click()}>
          {uploadKit.isPending ? "Enviando…" : kit.data?.exists ? "Substituir kit (.zip, até 50 MB)" : "Enviar kit (.zip, até 50 MB)"}
        </Button>
      </Card>

      {errors.length > 0 && <FormError message={errors.join(" ")} />}
      <div className="flex items-center gap-3">
        <Button onClick={onSave} disabled={!dirty || errors.length > 0 || save.isPending}>
          {save.isPending ? "Salvando…" : "Salvar"}
        </Button>
        {dirty && !save.isPending && <span className="text-xs text-muted-foreground">Alterações não salvas</span>}
      </div>
    </div>
  );
}
