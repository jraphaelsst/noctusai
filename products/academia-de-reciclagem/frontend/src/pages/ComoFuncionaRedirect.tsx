/**
 * `/como-funciona` → `/o-projeto` (permanent, client-side).
 *
 * The page answered to `/como-funciona` until the nav made "O Projeto" its
 * entry point. The old path is kept alive rather than dropped: it is in the
 * wild (shared links, the landing's earlier "Ver como funciona" button), and
 * a 404 would be a silent dead end for anyone following one.
 *
 * The deep-link hash rides along, so `/como-funciona#carta` still opens the
 * matching topic on the new path.
 */
import { Navigate, useLocation } from 'react-router-dom';

export default function ComoFuncionaRedirect() {
  const { hash } = useLocation();
  return <Navigate to={`/o-projeto${hash}`} replace />;
}
