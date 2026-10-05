import { useNavigate } from 'react-router-dom';
import { ShieldCheck } from 'lucide-react';
import { MfaEnrollPanel } from '@noctusai/lib/components';
import { api, storeMfaTokens } from '../lib/api';

/**
 * Segurança — verificação em duas etapas (TOTP).
 *
 * Authenticated page (core's route table only mounts it behind auth). All the
 * behaviour — status, enrol up to 2 devices, remove a device, loading / empty /
 * error states — lives in the seed `MfaEnrollPanel` organ; this page only
 * supplies the intercepting api client (so removing a device at aal1 raises the
 * step-up dialog) and stores the aal2 tokens a verified enrolment returns.
 */
export function Security() {
  const navigate = useNavigate();
  return (
    <div className="mx-auto max-w-xl px-4 sm:px-6 lg:px-8 py-6 sm:py-8 lg:py-10">
      <button onClick={() => navigate('/settings')} className="mb-5 text-sm text-primary hover:underline">
        &larr; Voltar às Configurações da Conta
      </button>
      <div className="mb-2 flex items-center gap-2">
        <ShieldCheck className="h-6 w-6 text-primary" aria-hidden />
        <h1 className="text-2xl font-bold text-foreground">Segurança</h1>
      </div>
      <p className="mb-6 text-sm text-muted-foreground">
        A verificação em duas etapas protege sua conta com um código do aplicativo autenticador. Cadastre dois
        dispositivos: se perder um, o outro continua dando acesso.
      </p>
      <MfaEnrollPanel api={api} onVerified={storeMfaTokens} />
    </div>
  );
}
