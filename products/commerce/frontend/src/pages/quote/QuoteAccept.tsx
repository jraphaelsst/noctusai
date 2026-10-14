/**
 * `/orcamento/:token` — the customer's public page to read, accept or decline a quote. NO login and NOT inside the authed
 * shell (a `publicRoutes` entry): the signed token in the URL is the credential, every bad token is the same "link
 * inválido" screen. The decision is an append-only consent record (name, time, IP, the exact sentence shown, sha256 of the terms).
 */
import { useParams } from "react-router-dom";
import { QuoteAcceptPage } from "@noctusai/lib";

import { publicQuotes } from "@/lib/backoffice";

export default function QuoteAccept() {
  const { token } = useParams<{ token: string }>();
  return <QuoteAcceptPage hooks={publicQuotes} token={token ?? ""} />;
}
