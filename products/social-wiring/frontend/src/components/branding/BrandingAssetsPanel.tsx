/**
 * Assets of a branding — logos, post models (references) and fonts uploaded to
 * private storage (shown via short-TTL signed URLs), plus link-only
 * references (prompt / palette / typography / model by URL).
 */
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Badge, Button, EmptyState, Field, FormError, Input, Select } from "@noctusai/lib/design-system";

import {
  useAddLinkReference,
  useDeleteReference,
  useUploadAsset,
  type AssetKind,
  type BrandingAsset,
  type LinkReferenceKind,
} from "@/hooks/useBranding";
import { fileToBase64 } from "@/lib/branding";
import { mensagemErroServidor } from "@/lib/erroServidor";

const KIND_LABEL: Record<string, string> = {
  logo: "Logo",
  model: "Post modelo",
  font: "Fonte",
  prompt: "Prompt exemplo",
  palette: "Paleta",
  typography: "Tipografia",
};

const UPLOAD_KINDS: AssetKind[] = ["logo", "model", "font"];
const LINK_KINDS: LinkReferenceKind[] = ["model", "prompt", "palette", "typography"];

function formatBytes(n: number | null): string {
  if (!n) return "";
  return n >= 1024 * 1024 ? `${(n / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
}

function AssetCard({ asset, onDelete, busy }: { asset: BrandingAsset; onDelete: () => void; busy: boolean }) {
  const isImage = asset.content_type?.startsWith("image/");
  return (
    <li className="space-y-2 rounded-md border p-2 text-xs" data-testid={`branding-asset-${asset.label}`}>
      {asset.signed_url && isImage ? (
        <img
          src={asset.signed_url}
          alt={asset.label}
          loading="lazy"
          className="h-28 w-full rounded bg-muted object-contain"
        />
      ) : null}
      {asset.signed_url_error && (
        <p role="alert" className="text-destructive">
          Não foi possível gerar o link do arquivo: {asset.signed_url_error}
        </p>
      )}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-medium">{asset.label}</div>
          <div className="flex flex-wrap items-center gap-1.5 text-muted-foreground">
            <Badge variant="outline">{KIND_LABEL[asset.kind] ?? asset.kind}</Badge>
            {formatBytes(asset.size_bytes)}
          </div>
          {asset.asset_url && (
            <a href={asset.asset_url} target="_blank" rel="noreferrer noopener" className="block truncate text-primary">
              {asset.asset_url}
            </a>
          )}
          {asset.notes && <p className="text-muted-foreground">{asset.notes}</p>}
        </div>
        <Button size="sm" variant="ghost" disabled={busy} onClick={onDelete} aria-label={`Remover ${asset.label}`}>
          Remover
        </Button>
      </div>
    </li>
  );
}

function UploadForm({ brandingId }: { brandingId: string }) {
  const upload = useUploadAsset(brandingId);
  const input = useRef<HTMLInputElement>(null);
  const [kind, setKind] = useState<AssetKind>("logo");
  const [error, setError] = useState<string | null>(null);

  const onPick = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    try {
      await upload.mutateAsync({ kind, label: file.name, content_base64: await fileToBase64(file) });
      toast.success(`${file.name} enviado`);
    } catch (err) {
      setError(mensagemErroServidor(err, "Falha ao enviar o arquivo"));
    } finally {
      if (input.current) input.current.value = "";
    }
  };

  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Tipo do arquivo">
          <Select value={kind} onChange={(e) => setKind(e.target.value as AssetKind)} data-testid="branding-upload-kind">
            {UPLOAD_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Arquivo (PNG, JPEG, WebP, GIF ou fonte WOFF/WOFF2/TTF/OTF — até 5 MB)">
          <input
            ref={input}
            type="file"
            data-testid="branding-upload-input"
            accept={kind === "font" ? ".woff,.woff2,.ttf,.otf" : "image/png,image/jpeg,image/webp,image/gif"}
            disabled={upload.isPending}
            onChange={(e) => void onPick(e.target.files?.[0])}
            className="block w-full text-xs"
          />
        </Field>
      </div>
      <FormError message={error} />
      {upload.isPending && <p className="text-xs text-muted-foreground">Enviando…</p>}
    </div>
  );
}

function LinkForm({ brandingId, onDone }: { brandingId: string; onDone: () => void }) {
  const add = useAddLinkReference(brandingId);
  const [kind, setKind] = useState<LinkReferenceKind>("prompt");
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setError(null);
    try {
      await add.mutateAsync({
        kind,
        label: label.trim(),
        asset_url: url.trim() || undefined,
        notes: notes.trim() || undefined,
      });
      onDone();
    } catch (err) {
      setError(mensagemErroServidor(err, "Falha ao adicionar a referência"));
    }
  };

  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <Field label="Tipo">
          <Select value={kind} onChange={(e) => setKind(e.target.value as LinkReferenceKind)}>
            {LINK_KINDS.map((k) => (
              <option key={k} value={k}>
                {KIND_LABEL[k]}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Rótulo" required>
          <Input value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Field label="URL (opcional)">
          <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://…" />
        </Field>
        <Field label="Notas (opcional)">
          <Input value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
      <FormError message={error} />
      <div className="flex gap-2">
        <Button variant="primary" size="sm" disabled={!label.trim() || add.isPending} onClick={() => void save()}>
          Adicionar referência
        </Button>
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancelar
        </Button>
      </div>
    </div>
  );
}

export function BrandingAssetsPanel({ brandingId, assets }: { brandingId: string; assets: BrandingAsset[] }) {
  const del = useDeleteReference(brandingId);
  const [linkOpen, setLinkOpen] = useState(false);

  const groups: { title: string; kinds: string[] }[] = [
    { title: "Logos", kinds: ["logo"] },
    { title: "Referências", kinds: ["model", "prompt", "palette", "typography"] },
    { title: "Fontes", kinds: ["font"] },
  ];

  return (
    <section data-testid="branding-assets" className="space-y-4">
      <UploadForm brandingId={brandingId} />
      <div className="flex justify-end">
        <Button size="sm" variant="outline" onClick={() => setLinkOpen((v) => !v)}>
          {linkOpen ? "Fechar" : "Adicionar referência por link"}
        </Button>
      </div>
      {linkOpen && <LinkForm brandingId={brandingId} onDone={() => setLinkOpen(false)} />}
      {assets.length === 0 ? (
        <EmptyState message="Nenhum ativo. Envie logos, posts modelo ou fontes." />
      ) : (
        groups.map((g) => {
          const items = assets.filter((a) => g.kinds.includes(a.kind));
          if (items.length === 0) return null;
          return (
            <div key={g.title} className="space-y-2">
              <h4 className="text-sm font-semibold">
                {g.title} ({items.length})
              </h4>
              <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                {items.map((a) => (
                  <AssetCard
                    key={a.id}
                    asset={a}
                    busy={del.isPending}
                    onDelete={() =>
                      del.mutate(a.id, {
                        onError: (err) => toast.error(mensagemErroServidor(err, "Falha ao remover o ativo")),
                      })
                    }
                  />
                ))}
              </ul>
            </div>
          );
        })
      )}
    </section>
  );
}
