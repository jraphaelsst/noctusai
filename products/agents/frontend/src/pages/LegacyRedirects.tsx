/**
 * Old routes -> the unified agent page (agents-unified CONTRACT §7). Every agent now lives on `/agentes/:key`;
 * the former per-agent shells (`/bia`, `/agentes/bia/persona`, `/studio/:key`) and the catalogue listing redirect
 * there, keeping the query (`?tab=…&secao=…` deep links) and hash. Old bookmarks and in-app links keep working.
 *
 * The generic ones (`/studio/:key`, `/agentes/:key/persona`) carry no agent key. The named ones are old
 * bookmarks of the academia agent and of the pre-rename keys (2026-10-19: Academia "Julia" became "Bia";
 * the SDR studio agent `lead-imob` became "julia").
 * NOC-REMEDIATE[drop-julia-route-redirects]: drop the named redirects one release after the Renata cutover.
 */
import { Navigate, useLocation, useParams } from "react-router-dom";

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

/** `/studio` (the former Agent Studio console) -> `/agentes`, where its actions now live. */
export function RedirectStudio() {
  return <RedirectTo to="/agentes" />;
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

/** `/bia` and the pre-rename `/julia` -> the academia agent's chat section. */
export function RedirectAcademiaChat() {
  return <RedirectTo to="/agentes/bia" tab="conversar" />;
}

/** pre-rename `/agentes/julia/persona` -> the academia agent's persona section */
export function RedirectJuliaPersonaToBia() {
  return <RedirectTo to="/agentes/bia" tab="persona" />;
}

/** pre-rename `/studio/lead-imob` -> `/agentes/julia` */
export function RedirectLeadImobStudioToJulia() {
  return <RedirectTo to="/agentes/julia" />;
}
