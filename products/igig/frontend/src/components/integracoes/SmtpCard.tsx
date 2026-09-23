/**
 * Integrações → SMTP (wave-2 contract, Slice B): the account orçamentos and
 * automations send e-mail through.
 *
 * `origem` is shown as a badge, never hidden: `org` (the agency's own
 * account), `plataforma` (the platform env fallback — works, but the e-mails
 * leave from the platform's address), `nenhuma` (sending fails loudly).
 * The password is write-only: the API never returns it, the field starts
 * empty, and leaving it empty on save keeps the stored one.
 */
import { useEffect, useState } from "react";
import { Button, Field, FormError, Input, Select } from "@noctusai/lib/design-system";
import type { BadgeVariant } from "@noctusai/lib/design-system";
import { Mail, Send, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import {
  useSmtp,
  useSmtpMutations,
  type OrigemSmtp,
  type SegurancaSmtp,
  type SmtpStatus,
} from "@/hooks/useEmailIntegracao";
import { describeError } from "@/lib/errors";
import { IntegracaoCard } from "./IntegracaoCard";

const ORIGEM_BADGE: Record<OrigemSmtp, { texto: string; variante: BadgeVariant }> = {
  org: { texto: "configurado", variante: "default" },
  plataforma: { texto: "usando SMTP da plataforma", variante: "outline" },
  nenhuma: { texto: "não configurado", variante: "muted" },
};

interface Form {
  host: string;
  port: string;
  username: string;
  password: string;
  security: SegurancaSmtp;
  from_email: string;
  from_name: string;
}

const VAZIO: Form = { host: "", port: "587", username: "", password: "", security: "starttls", from_email: "", from_name: "" };

/** Only the org's OWN account seeds the form — the platform fallback's
 * values are not the agency's to edit. */
function formDe(s: SmtpStatus | null): Form {
  if (!s || s.origem !== "org") return VAZIO;
  return {
    host: s.host ?? "",
    port: String(s.port ?? 587),
    username: s.username ?? "",
    password: "",
    security: s.security ?? "starttls",
    from_email: s.from_email ?? "",
    from_name: s.from_name ?? "",
  };
}

export function SmtpCard() {
  const { smtp, showSkeleton, isError, error } = useSmtp();
  const { salvar, remover, testar } = useSmtpMutations();
  const [f, setF] = useState<Form>(VAZIO);
  const [sujo, setSujo] = useState(false);
  const [para, setPara] = useState("");
  const [removendo, setRemovendo] = useState(false);

  useEffect(() => {
    if (!sujo) setF(formDe(smtp));
  }, [smtp, sujo]);

  const set = (k: keyof Form) => (e: { target: { value: string } }) => {
    setF((p) => ({ ...p, [k]: e.target.value }));
    setSujo(true);
  };

  const proprio = smtp?.origem === "org";
  const valido = f.host.trim() && Number(f.port) > 0 && f.username.trim() && f.from_email.trim() && (proprio || f.password);

  return (
    <IntegracaoCard
      titulo="E-mail (SMTP)"
      icone={<Mail className="h-4 w-4" />}
      badge={smtp ? ORIGEM_BADGE[smtp.origem] : null}
      descricao={
        smtp?.origem === "plataforma" ? (
          <>
            Sem SMTP próprio, os e-mails saem pela conta da plataforma ({smtp.from_email ?? "remetente padrão"}).
            Configure a conta da agência para enviar com o seu endereço.
          </>
        ) : (
          "Conta usada para enviar orçamentos e e-mails das automações."
        )
      }
      showSkeleton={showSkeleton}
      erro={isError ? describeError(error, "Não foi possível carregar o SMTP.") : null}
      testId="smtp-card"
    >
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!valido) return;
          salvar.mutate(
            {
              host: f.host.trim(),
              port: Number(f.port),
              username: f.username.trim(),
              password: f.password || undefined,
              security: f.security,
              from_email: f.from_email.trim(),
              from_name: f.from_name.trim() || null,
            },
            {
              onSuccess: () => {
                setSujo(false);
                toast.success("SMTP salvo.");
              },
            },
          );
        }}
      >
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="sm:col-span-2">
            <Field label="Servidor (host)" required>
              <Input className="max-sm:h-10" value={f.host} onChange={set("host")} placeholder="smtp.gmail.com" />
            </Field>
          </div>
          <Field label="Porta" required>
            <Input className="max-sm:h-10" type="number" inputMode="numeric" min={1} max={65535} value={f.port} onChange={set("port")} />
          </Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Usuário" required>
            <Input className="max-sm:h-10" autoComplete="off" value={f.username} onChange={set("username")} />
          </Field>
          <Field label="Senha" required={!proprio}>
            <Input
              className="max-sm:h-10"
              type="password"
              autoComplete="new-password"
              aria-label="Senha SMTP"
              placeholder={proprio ? "manter senha atual…" : "senha ou senha de app"}
              value={f.password}
              onChange={set("password")}
            />
          </Field>
          <Field label="Segurança">
            <Select className="h-10 sm:h-8" value={f.security} onChange={set("security")} aria-label="Segurança">
              <option value="starttls">STARTTLS (587)</option>
              <option value="ssl">SSL/TLS (465)</option>
            </Select>
          </Field>
          <Field label="Remetente (e-mail)" required>
            <Input className="max-sm:h-10" type="email" inputMode="email" value={f.from_email} onChange={set("from_email")} />
          </Field>
          <div className="sm:col-span-2">
            <Field label="Remetente (nome)">
              <Input className="max-sm:h-10" value={f.from_name} onChange={set("from_name")} placeholder="Agência Exemplo" />
            </Field>
          </div>
        </div>
        <FormError message={salvar.isError ? describeError(salvar.error, "Não foi possível salvar o SMTP.") : null} />
        <div className="flex flex-wrap justify-between gap-2">
          {proprio ? (
            <Button type="button" variant="ghost" className="text-destructive max-sm:h-10" onClick={() => setRemovendo(true)}>
              <Trash2 className="mr-1 h-4 w-4" /> Remover
            </Button>
          ) : (
            <span />
          )}
          <Button type="submit" className="max-sm:h-10" disabled={!valido || !sujo || salvar.isPending}>
            {salvar.isPending ? "Salvando…" : "Salvar SMTP"}
          </Button>
        </div>
      </form>

      {smtp?.configurado ? (
        <form
          className="flex flex-wrap items-end gap-2 border-t border-border pt-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!para.trim()) return;
            testar.mutate(para.trim(), {
              onSuccess: () => toast.success(`E-mail de teste enviado para ${para.trim()}.`),
            });
          }}
        >
          <div className="min-w-0 flex-1">
            <Field label="Testar envio para">
              <Input
                className="max-sm:h-10"
                type="email"
                inputMode="email"
                aria-label="E-mail de teste"
                value={para}
                onChange={(e) => setPara(e.target.value)}
                placeholder="voce@agencia.com"
              />
            </Field>
          </div>
          <Button type="submit" variant="outline" className="max-sm:h-10" disabled={!para.trim() || testar.isPending}>
            <Send className="mr-1 h-4 w-4" /> {testar.isPending ? "Enviando…" : "Testar envio"}
          </Button>
          {testar.isError ? (
            <p role="alert" className="w-full text-sm text-destructive">
              {describeError(testar.error, "O envio de teste falhou.")}
            </p>
          ) : null}
        </form>
      ) : null}

      <ConfirmDialog
        open={removendo}
        title="Remover SMTP"
        description={
          <p>
            Remover a conta SMTP da agência? Sem ela, os e-mails passam a sair pelo SMTP da plataforma (se houver) ou
            deixam de ser enviados.
          </p>
        }
        confirmLabel={remover.isPending ? "Removendo…" : "Remover"}
        busy={remover.isPending}
        onCancel={() => setRemovendo(false)}
        onConfirm={() =>
          remover.mutate(undefined, {
            onSuccess: () => {
              setRemovendo(false);
              setSujo(false);
              toast.success("SMTP removido.");
            },
            onError: (e) => toast.error(describeError(e, "Não foi possível remover o SMTP.")),
          })
        }
      />
    </IntegracaoCard>
  );
}
