/**
 * `/obrigado?pedido=<token>` — public thank-you page (same identity as the landing).
 * Polls GET /api/public/pedidos/{token} every 3 s for up to 2 minutes while the
 * order is `pendente`; `pago` shows the download button; `reembolsado` and
 * not-found have their own states. After 2 min still pending → reassurance copy.
 */
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "@noctusai/lib";
import { POLL_MAX_MS, usePedido } from "@/hooks/useStore";
import { assetUrl } from "@/lib/api";
import "./landing.css";

export default function Obrigado() {
  const [params] = useSearchParams();
  const token = params.get("pedido");
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setTimedOut(true), POLL_MAX_MS);
    return () => clearTimeout(t);
  }, []);

  const { data, error, showSkeleton } = usePedido(token, timedOut);
  const notFound = !token || (error instanceof ApiError && error.status === 404);
  const failed = !!error && !notFound && !data;

  let body: React.ReactNode;
  if (notFound) {
    body = (
      <>
        <p className="eyebrow">Pedido não encontrado</p>
        <h2 style={{ marginTop: 14 }}>Não achamos este <span className="k">pedido</span>.</h2>
        <p className="lead">Confira o link que você recebeu. Se acabou de pagar, o link de download também chega no seu e-mail.</p>
      </>
    );
  } else if (showSkeleton) {
    body = (
      <>
        <p className="eyebrow">Um instante</p>
        <h2 style={{ marginTop: 14 }}>Buscando seu <span className="k">pedido</span>…</h2>
        <p className="lead"><span className="sk block" aria-hidden="true" /></p>
      </>
    );
  } else if (failed) {
    body = (
      <>
        <p className="eyebrow">Erro</p>
        <h2 style={{ marginTop: 14 }}>Não foi possível <span className="k">consultar</span> o pedido.</h2>
        <p className="lead">Atualize a página em instantes. Se o pagamento foi concluído, o link chega por e-mail.</p>
      </>
    );
  } else if (data?.status === "pago") {
    const href = assetUrl(data.download_url);
    body = (
      <>
        <p className="eyebrow">Pagamento confirmado</p>
        <h2 style={{ marginTop: 14 }}>Seu contrato está <span className="k">pronto</span>.</h2>
        <p className="lead">Enviamos para {data.email_mascarado}. Você também pode baixar agora:</p>
        {href && <a className="btn" href={href}>Baixar meu kit</a>}
      </>
    );
  } else if (data?.status === "reembolsado") {
    body = (
      <>
        <p className="eyebrow">Pedido reembolsado</p>
        <h2 style={{ marginTop: 14 }}>Este pedido foi <span className="k">reembolsado</span>.</h2>
        <p className="lead">O acesso ao download foi encerrado e o valor retorna pela mesma forma de pagamento.</p>
      </>
    );
  } else if (data?.status === "falhou") {
    body = (
      <>
        <p className="eyebrow">Pagamento não concluído</p>
        <h2 style={{ marginTop: 14 }}>O pagamento <span className="k">não foi concluído</span>.</h2>
        <p className="lead">Nenhum valor foi cobrado. Você pode tentar novamente pela página inicial.</p>
      </>
    );
  } else if (timedOut) {
    body = (
      <>
        <p className="eyebrow">Aguardando confirmação do pagamento</p>
        <h2 style={{ marginTop: 14 }}>Já estamos <span className="k">de olho</span>.</h2>
        <p className="lead">Assim que o pagamento for confirmado você recebe o link por e-mail.</p>
      </>
    );
  } else {
    body = (
      <>
        <p className="eyebrow">Aguardando confirmação do pagamento</p>
        <h2 style={{ marginTop: 14 }}>Falta <span className="k">pouco</span>.</h2>
        <p className="lead" role="status">Estamos aguardando a confirmação do pagamento. Esta página atualiza sozinha.</p>
      </>
    );
  }

  return (
    <div className="store-landing thanks">
      <main className="card">{body}</main>
    </div>
  );
}
