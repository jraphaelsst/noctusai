/**
 * Old routes -> the unified agent page (agents-unified CONTRACT §7). Every agent now lives on `/agentes/:key`;
 * the former per-agent shells (`/bia`, `/agentes/bia/persona`, `/studio/:key`) and the catalogue listing redirect
 * there, keeping the query (`?tab=…&secao=…` deep links) and hash. Old bookmarks and in-app links keep working.
 *
 * The generic ones (`/studio/:key`, `/agentes/:key/persona`) carry no agent key. The academia ones (`/bia`,
 * `/julia`, `/agentes/bia/persona|conversar`) ask the server which agent the org's academia chat is (the Renata
 * cutover moved it off the `bia` key, which is free for a new agent: `/agentes/bia` itself is NOT redirected).
 * `/studio/lead-imob` is the pre-rename SDR key (became "julia").
 * NOC-REMEDIATE[drop-julia-route-redirects]: drop the named redirects one release after the Renata cutover.
 */
import { Navigate, useLocation, useParams } from "react-router-dom";
import { useDestinoChat } from "@/hooks/useAgentesPainel";

function destino(to: string, search: string, hash: string, tab?: string): string {
  const params = new URLSearchParams(search);
  if (tab) params.set("tab", tab);
  const q = params.toString();
  return `${to}${q ? `?${q}` : ""}${hash}`;
}

function RedirectTo({ to, tab }: { to: string; tab?: string }) {
  const { search, hash } = useLocation();
  return <Navigate to={destino(to, search, hash, tab)} replace />;
}

/** `/studio/:key` -> `/agentes/:key` (the Studio tab ids ARE the page section ids). */
export function RedirectStudioAgent() {
  const { key = "" } = useParams<{ key: string }>();
  return <RedirectTo to={`/agentes/${encodeURIComponent(key)}`} />;
}

/** `/agentes/:key/persona` -> `/agentes/:key?tab=persona` */
export function RedirectAgentePersona() {
  const { key = "" } = useParams<{ key: string }>();
  return <RedirectTo to={`/agentes/${encodeURIComponent(key)}`} tab="persona" />;
}

/** `/agentes/catalogo` -> `/agentes` (the listing IS the catalogue now). */
export function RedirectCatalogo() {
  return <RedirectTo to="/agentes" />;
}

/**
 * The academia agent is DATA since the Renata cutover: the server names it (`GET /api/agents/painel/destino-chat`).
 * Nothing is rendered until it answers (never a guess); an org without an in-app chat agent lands on the listing.
 */
function RedirectAcademia({ tab }: { tab: string }) {
  const { search, hash } = useLocation();
  const { data, showSkeleton, isError } = useDestinoChat();
  if (showSkeleton) {
    return (
      <div className="p-6 text-sm text-muted-foreground" role="status">
        Abrindo o agente…
      </div>
    );
  }
  if (isError || !data) return <Navigate to={destino("/agentes", search, hash)} replace />;
  return <Navigate to={destino(`/agentes/${encodeURIComponent(data.key)}`, search, hash, tab)} replace />;
}

/** `/bia`, the pre-rename `/julia` and `/agentes/bia/conversar` -> the academia agent's chat section. */
export function RedirectAcademiaChat() {
  return <RedirectAcademia tab="conversar" />;
}

/** `/agentes/bia/persona` and the pre-rename `/agentes/julia/persona` -> the academia agent's persona section */
export function RedirectAcademiaPersona() {
  return <RedirectAcademia tab="persona" />;
}

/** pre-rename `/studio/lead-imob` -> `/agentes/julia` */
export function RedirectLeadImobStudioToJulia() {
  return <RedirectTo to="/agentes/julia" />;
}
