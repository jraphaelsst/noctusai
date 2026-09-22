/**
 * A nav/footer link that targets a landing section by id (`#projeto`,
 * `#pilares`, `#inicio`, ...).
 *
 * On the landing itself (`pathname === "/"`) it's a plain in-page anchor —
 * the browser jumps straight to the section, no router involvement. On any
 * other public page (`/o-projeto`, `/a-carta`) the same section lives on
 * the landing, so it renders a react-router `Link` to `/#<hash>`; the
 * landing's own `useHashScroll` (see `pages/Landing.tsx`) then smooth-
 * scrolls to it once mounted, since a client-side route change does not
 * trigger the browser's native hash-scroll the way a full navigation would.
 */
import type { AnchorHTMLAttributes, ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';

export interface SectionLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  hash: string;
  children: ReactNode;
}

export function SectionLink({ hash, children, ...rest }: SectionLinkProps) {
  const location = useLocation();
  const onLanding = location.pathname === '/';

  if (onLanding) {
    return (
      <a href={`#${hash}`} {...rest}>
        {children}
      </a>
    );
  }

  return (
    <Link to={`/#${hash}`} {...rest}>
      {children}
    </Link>
  );
}
