/**
 * `<QuoteSendDialog/>` — send a quote to the customer: by e-mail (the PDF attached) or just mint the link to hand
 * over yourself (WhatsApp, chat). The link is a bearer credential: it is shown to the staff member who asked for
 * it and copied on request — never persisted client-side.
 */
import * as React from 'react';
import { Button, Dialog, DialogBody, DialogFooter, DialogHeader, Field, FormError, Input, Textarea } from './controls';
import { quotesErrorMessage } from './hooks';
import { defaultQuotesT } from './i18n';
import type { QuotesOrganProps } from './shared';
import type { QuoteSendResult } from './types';

export interface QuoteSendDialogProps extends QuotesOrganProps {
  open: boolean;
  onClose: () => void;
  quoteId: string;
  /** The customer's e-mail, used to prefill the recipient. */
  defaultTo?: string | null;
  onSent?: (result: QuoteSendResult) => void;
}

export function QuoteSendDialog({ hooks, t = defaultQuotesT, open, onClose, quoteId, defaultTo, onSent }: QuoteSendDialogProps) {
  const { send } = hooks.useQuoteMutations();
  const [channel, setChannel] = React.useState<'email' | 'link'>('email');
  const [to, setTo] = React.useState(defaultTo ?? '');
  const [message, setMessage] = React.useState('');
  const [err, setErr] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<QuoteSendResult | null>(null);
  const [copied, setCopied] = React.useState<'ok' | 'fail' | null>(null);

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    setErr(null);
    try {
      const body: Parameters<typeof send.mutateAsync>[0] = { id: quoteId, channel };
      if (channel === 'email' && to.trim()) body.to = to.trim();
      if (message.trim()) body.message = message.trim();
      const out = await send.mutateAsync(body);
      setResult(out);
      onSent?.(out);
    } catch (e) {
      setErr(quotesErrorMessage(e, t));
    }
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied('ok');
    } catch {
      setCopied('fail'); // never silent: the user is told to copy by hand
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={t('send.title')}>
      <form onSubmit={submit}>
        <DialogHeader>
          <h3 className="text-sm font-semibold">{t('send.title')}</h3>
        </DialogHeader>
        <DialogBody className="space-y-3">
          {result ? (
            <div className="space-y-2" role="status">
              <p className="text-sm">{result.channel === 'email' ? t('send.sent_email', { to: result.sent_to ?? '' }) : t('send.sent_link')}</p>
              <Field label={t('send.link_label')}>
                <Input readOnly value={result.url} onFocus={(e) => e.currentTarget.select()} />
              </Field>
              <Button type="button" size="sm" variant="outline" onClick={() => copy(result.url)}>{t('send.copy')}</Button>
              {copied === 'ok' ? <p role="status" className="text-xs">{t('send.copied')}</p> : null}
              {copied === 'fail' ? <p role="alert" className="text-xs text-destructive">{t('send.copy_failed')}</p> : null}
            </div>
          ) : (
            <>
              <fieldset className="space-y-1">
                <legend className="text-xs text-muted-foreground">{t('send.channel')}</legend>
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="quote-send-channel" checked={channel === 'email'} onChange={() => setChannel('email')} />
                  {t('send.email')}
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="quote-send-channel" checked={channel === 'link'} onChange={() => setChannel('link')} />
                  {t('send.link')}
                </label>
              </fieldset>
              {channel === 'email' ? (
                <Field label={t('send.to')}>
                  <Input type="email" value={to} onChange={(e) => setTo(e.target.value)} />
                </Field>
              ) : null}
              <Field label={t('send.message')}>
                <Textarea rows={3} maxLength={1000} value={message} onChange={(e) => setMessage(e.target.value)} />
              </Field>
              <FormError message={err} />
            </>
          )}
        </DialogBody>
        <DialogFooter className="justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose}>{result ? t('common.close') : t('common.cancel')}</Button>
          {result ? null : (
            <Button type="submit" variant="primary" disabled={send.isPending}>{send.isPending ? t('send.sending') : t('send.submit')}</Button>
          )}
        </DialogFooter>
      </form>
    </Dialog>
  );
}
