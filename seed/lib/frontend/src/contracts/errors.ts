import { apiErrorCode, errorMessage } from './hooks';
import { t } from './i18n';

/** pt-BR message of a failed call: the mapped code when the organ knows it, else the server's own text. */
export function contractsErrorText(err: unknown): string {
  const code = apiErrorCode(err);
  const key = code ? `error.${code}` : '';
  const mapped = key ? t(key) : '';
  return mapped && mapped !== key ? mapped : `${t('error.generic')}: ${errorMessage(err)}`;
}
