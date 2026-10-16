/**
 * "Canal" origins of the live "Filtro de leads" (§59.0 a8). The live list has
 * 60 entries; this is the named subset (portals, ads, owned channels, AI
 * assistants) — extend here when the backend exposes the org's origins.
 * NOC-REMEDIATE[lais-canais-origens]: replace with a server-provided list — 2026-10-15
 */
export const CANAIS: readonly string[] = [
  "Grupo Zap", "ZAP Imóveis", "Viva Real", "OLX", "ImovelWeb", "Chaves na Mão", "NetImoveis", "Kenlo", "RD Station",
  "Guia de Imóveis", "Facebook", "Instagram", "Google", "WhatsApp", "Site Próprio", "Placa", "Remarketing",
  "Conversas", "ChatGPT", "Claude", "MCP",
];
