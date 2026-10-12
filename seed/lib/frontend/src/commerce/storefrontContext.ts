/** Context carrying the loaded `Storefront` (provided by `<StorefrontShell/>`). */
import * as React from 'react';
import type { Storefront } from './types';

export const StorefrontContext = React.createContext<Storefront | null>(null);

/** The loaded storefront (inside `<StorefrontShell/>` only). */
export function useStorefrontData(): Storefront {
  const s = React.useContext(StorefrontContext);
  if (!s) throw new Error('useStorefrontData must be used inside <StorefrontShell/>');
  return s;
}

/** Like `useStorefrontData` but `null` outside a shell (components accept explicit props instead). */
export function useOptionalStorefront(): Storefront | null {
  return React.useContext(StorefrontContext);
}
